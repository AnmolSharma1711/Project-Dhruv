#!/usr/bin/env bash
# Run on the Jetson: ./server.sh [start CHECKPOINT [--dry-run]|status|watch|logs SERVICE|errors|attach SERVICE|stop]
set -eo pipefail
root=$(cd "$(dirname "$0")" && pwd)
base=${XDG_STATE_HOME:-$HOME/.local/state}/slam-server
session=slam-server
services=(imu odom ekf amcl nav)
mkdir -p "$base"
die() { echo "$*" >&2; exit 1; }
setup() {
  source /opt/ros/humble/setup.bash
  source "${SLAM_WS:-$HOME/ros2_ws}/install/setup.bash"
}
hint() {
  case "$1" in
    imu) echo 'Check I2C, imu_worker and the sudo prompt in the IMU pane.';;
    odom) echo 'Check /dev/ttyUSB0, /scan and /odom_rf2o_corrected.';;
    ekf) echo 'Check /imu/data, corrected odometry and the imu_link transform.';;
    amcl) echo 'Check map path, starting checkpoint, direction and map-to-base transform.';;
    nav) echo 'Check controller logs, local obstacle map, filtered odometry and Arduino serial.';;
  esac
}
worker() {
  local svc=$1 run=$2 checkpoint=$3 dry=$4
  export ROS_LOG_DIR="$run/ros" PYTHONUNBUFFERED=1 RCUTILS_COLORIZED_OUTPUT=0
  cd "$root"
  setup
  case "$svc" in
    imu) cd akshat/imu_argon; sudo -v && bash start_imu.sh;;
    odom) ros2 launch "$root/kushal/rf2o_odometry/start_odom.launch.py";;
    ekf) ros2 launch ekf_node ekf_localization.launch.py;;
    amcl) { printf '%s\n' "$checkpoint"; cat; } | ros2 run localization_node localize --ros-args \
         -p "map:=$root/saved_map/project_lab.yaml" -p "checkpoints_file:=$root/saved_map/checkpoints.json";;
    nav)
      echo 'Waiting for localization before starting navigation.'
      until grep -q 'Localized — ready to control' "$run/amcl.log" 2>/dev/null; do
        [[ ! -e "$run/amcl.exit" ]] || die 'AMCL exited before localization'
        sleep 1
      done
      ros2 launch anmol nav2_bringup.launch.py "dry_run:=$dry";;
  esac
}
# Heartbeats come from received messages, so a live launcher cannot mask a dead child.
health() {
  setup
  python3 - "$1" <<'PYHEALTH'
import sys, time
from pathlib import Path
import rclpy
from nav_msgs.msg import OccupancyGrid, Odometry
from sensor_msgs.msg import Imu, LaserScan
from rclpy.qos import qos_profile_sensor_data
from tf2_ros import Buffer, TransformListener
from rclpy.time import Time
run = Path(sys.argv[1])
rclpy.init()
node = rclpy.create_node("slam_server_health")
buffer = Buffer()
listener = TransformListener(buffer, node)
last = {}
def seen(key):
    now = time.monotonic()
    if now - last.get(key, 0) >= 1:
        (run / ("heartbeat-" + key)).touch()
        last[key] = now
for key, topic, kind in [
    ("imu", "/imu/data", Imu), ("scan", "/scan", LaserScan),
    ("odom", "/odom_rf2o_corrected", Odometry), ("ekf", "/odometry/filtered", Odometry),
    ("nav", "/local_costmap/costmap", OccupancyGrid)
]:
    node.create_subscription(kind, topic, lambda msg, key=key: seen(key), qos_profile_sensor_data)
def check_pose():
    if buffer.can_transform("map", "base_link", Time()):
        stamp = buffer.lookup_transform("map", "base_link", Time()).header.stamp
        if abs(node.get_clock().now().nanoseconds / 1e9 - stamp.sec - stamp.nanosec / 1e9) < 5:
            seen("amcl")
node.create_timer(1, check_pose)
rclpy.spin(node)
PYHEALTH
}
status() {
  local run=$1 svc state detail line incident key age
  for svc in "${services[@]}"; do
    state=LIVE; detail='receiving data'
    if [[ -f "$run/stopped" ]]; then printf '%-5s STOPPED\n' "$svc"; continue; fi
    if [[ -e "$run/$svc.exit" ]]; then
      state=CRASHED; detail="unexpected exit $(cat "$run/$svc.exit")"
    elif ! tmux has-session -t "=$session:$svc" 2>/dev/null; then
      state=WARNING; detail='pane offline'
    elif [[ "$svc" = nav ]] && ! grep -q 'Localized — ready to control' "$run/amcl.log"; then
      state=WARNING; detail='waiting for AMCL'
    elif [[ "$svc" = imu ]] && ! grep -qi 'warm-up complete\|publishing live' "$run/imu.log"; then
      state=WARNING; detail='waiting for IMU warm-up or sudo password'
    elif [[ -s "$run/$svc.latest" ]]; then
      read -r incident line < "$run/$svc.latest" || true
      if [[ "$incident" =~ ^[0-9]+$ ]] && (( $(date +%s) - incident < 60 )); then state=WARNING; detail="$line"; fi
    fi
    if [[ "$state" = LIVE ]]; then
      for key in "$svc" $( [[ "$svc" != odom ]] || echo scan ); do
        age=$(stat -c %Y "$run/heartbeat-$key" 2>/dev/null || echo 0)
        if (( $(date +%s) - age > 8 )); then state=WARNING; detail="no recent $key data — $(hint "$svc")"; break; fi
      done
    fi
    printf '%-5s %-8s %s\n' "$svc" "$state" "${detail:0:220}"
  done
}
case "${1:-start}" in
  _health) health "$2";;
  _worker)
    shift; svc=$1; run=$2
    set +e
    (set -e; worker "$@") 2>&1 | stdbuf -i0 awk -W interactive -v svc="$svc" -v dir="$run" '
      {stamp=strftime("%Y-%m-%dT%H:%M:%S%z"); print stamp, $0; fflush();
       if (tolower($0) ~ /\[warn|\[error|\[fatal|traceback|process has died|permission denied|not sure yet|did not start|cannot open|no such file|command not found/) {
         print stamp, svc, $0 >> (dir "/issues.log"); close(dir "/issues.log");
         print systime(), $0 > (dir "/" svc ".latest"); close(dir "/" svc ".latest")
       }}' | tee -a "$run/$svc.log"
    rc=${PIPESTATUS[0]}; echo "$rc" > "$run/$svc.exit"
    echo "$(date -Is) $svc EXIT $rc — $(hint "$svc")" >> "$run/issues.log"; exit "$rc";;
  start)
    shift || true
    exec 9>"$base/start.lock"; flock -n 9 || die 'Another startup is in progress.'
    if tmux has-session -t "=$session" 2>/dev/null; then flock -u 9; exec "$root/server.sh" watch; fi
    setup
    if tmux has-session -t '=slam' 2>/dev/null; then die 'Existing manual tmux session slam is running. Inspect with tmux attach -t slam. Stop its services before starting this supervisor.'; fi
    nodes=$(timeout 10 ros2 node list --no-daemon --spin-time 3) || die 'Cannot inspect existing ROS services.'
    if grep -Eq '/(calibrated_imu_node|rf2o_worker|rplidar_node|ekf_localization_node|amcl|map_server|controller_server|cmd_vel_bridge)$' <<< "$nodes"; then die 'Robot services already running. Stop their owning terminals before starting another stack.'; fi
    checkpoint=${1:-}; dry=false
    [[ -n "$checkpoint" ]] || read -rp 'Starting checkpoint (robot facing its saved direction): ' checkpoint
    [[ ${2:-} != --dry-run ]] || dry=true
    [[ $# -le 2 && ( -z ${2:-} || $2 = --dry-run ) ]] || die 'Usage: server.sh start CHECKPOINT [--dry-run]'
    python3 -c 'import json,sys; sys.exit(sys.argv[2] not in json.load(open(sys.argv[1])))' "$root/saved_map/checkpoints.json" "$checkpoint" || die 'Unknown checkpoint'
    run=$(mktemp -d "$base/$(date +%Y%m%d-%H%M%S)-XXXX")
    mkdir "$run/ros"; touch "$run/issues.log"; for svc in "${services[@]}"; do touch "$run/$svc.log"; done
    ln -sfnT "$run" "$base/latest"
    # Keep the session on partial startup so even the first crash is inspectable.
    printf -v health_cmd '%q ' "$root/server.sh" _health "$run"
    tmux new-session -d -s "$session" -n dashboard "$health_cmd > '$run/health.log' 2>&1; exec sleep infinity"
    for svc in "${services[@]}"; do
      printf -v cmd '%q ' "$root/server.sh" _worker "$svc" "$run" "$checkpoint" "$dry"
      tmux new-window -d -t "$session:" -n "$svc" "$cmd"
    done
    flock -u 9
    echo "Logs: $run. If IMU asks for sudo, use ./server.sh attach imu."
    exec "$root/server.sh" watch;;
  stop)
    run=$(readlink -f "$base/latest")
    for svc in nav amcl ekf odom imu; do tmux send-keys -t "=$session:$svc" C-c 2>/dev/null || true; done
    for i in {1..12}; do [[ $(tmux list-windows -t "=$session" 2>/dev/null | wc -l) -le 1 ]] && break; sleep 1; done
    [[ $(tmux list-windows -t "=$session" 2>/dev/null | wc -l) -le 1 ]] || die 'Some services are still stopping. Inspect the service panes.'
    tmux kill-session -t "=$session" 2>/dev/null || true
    touch "$run/stopped"
    echo "Stopped. Logs: $run";;
  status|watch|errors|logs|attach)
    action=$1; run="$base/latest"; [[ -d "$run" ]] || die "No server.sh run yet under $base"
    case "$action" in
      status) status "$run";;
      watch) while true; do [[ ! -t 1 ]] || printf '\033[H\033[2J'; date -Is; status "$run"; sleep 3; done;;
      errors) tail -80 "$run/issues.log"; for svc in "${services[@]}"; do printf '%s: %s\n' "$svc" "$(hint "$svc")"; done;;
      logs|attach) svc=${2:-}; case "$svc" in imu|odom|ekf|amcl|nav) ;; *) die 'Choose imu, odom, ekf, amcl or nav';; esac
        if [[ "$action" = logs ]]; then tail -n 80 -F "$run/$svc.log"; else exec tmux attach-session -t "=$session:$svc"; fi;;
    esac;;
  *) die 'Usage: server.sh [start CHECKPOINT [--dry-run]|status|watch|errors|logs SERVICE|attach SERVICE|stop]';;
esac
