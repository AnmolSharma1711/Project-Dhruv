#!/bin/bash
# =============================================================================
# SLAM Robot — Full Startup Script
# File   : ~/Desktop/SLAM/anmol/scripts/startup.sh
# Usage  : bash ~/Desktop/SLAM/anmol/scripts/startup.sh
#
# Starts all required ROS 2 nodes in a tmux session with named windows.
# After startup, the AMCL window is focused so you can type the localization
# checkpoint name interactively.
#
# Window layout:
#   0: IMU      — imu_publisher_node.py  (Akshat)
#   1: Odom     — start_odom.launch.py   (Kushal: LiDAR + rf2o + static TFs)
#   2: IMU-TF   — static_transform_publisher for base_link → imu_link
#   3: EKF      — ekf_localization.launch.py (Dhruv)
#   4: AMCL     — localize node  ← YOU TYPE CHECKPOINT HERE
#   5: Nav2     — nav2_bringup.launch.py (Anmol)
#
# Key bindings (tmux):
#   Ctrl+B 0-5   switch window
#   Ctrl+B d     detach (session keeps running)
#   Ctrl+B [     scroll mode (q to exit)
#   Ctrl+B &     kill current window
#
# Requirements:
#   sudo apt install tmux
# =============================================================================

set -e

SESSION="slam"
SLAM_DIR="$HOME/Desktop/SLAM"
ROS_SETUP="/opt/ros/humble/setup.bash"
WS_SETUP="$HOME/ros2_ws/install/setup.bash"

# ---------------------------------------------------------------------------
# Helper: source both setup files and run a command in a tmux pane
# ---------------------------------------------------------------------------
_send() {
  local target="$1"
  shift
  tmux send-keys -t "$target" "source $ROS_SETUP && source $WS_SETUP && $*" Enter
}

# ---------------------------------------------------------------------------
# Clean up any stale FastDDS shared-memory locks (prevents RTPS errors)
# ---------------------------------------------------------------------------
echo "🧹  Cleaning stale FastDDS SHM locks …"
sudo rm -rf /dev/shm/fastrtps_* 2>/dev/null || true

# ---------------------------------------------------------------------------
# Kill any existing slam session so we start fresh
# ---------------------------------------------------------------------------
tmux kill-session -t "$SESSION" 2>/dev/null || true
sleep 0.5

# ---------------------------------------------------------------------------
# Window 0 — IMU Driver (Akshat)
# ---------------------------------------------------------------------------
echo "▶  Creating tmux session '$SESSION' …"
tmux new-session -d -s "$SESSION" -n "IMU" -x 220 -y 50

tmux send-keys -t "$SESSION:IMU" \
  "cd $SLAM_DIR/akshat/imu_argon && source $ROS_SETUP && python3 imu_publisher_node.py" \
  Enter

echo "   Window 0 (IMU)   — started"
sleep 1

# ---------------------------------------------------------------------------
# Window 1 — LiDAR + rf2o + Static TFs (Kushal)
# ---------------------------------------------------------------------------
tmux new-window -t "$SESSION" -n "Odom"
_send "$SESSION:Odom" \
  "ros2 launch $SLAM_DIR/kushal/rf2o_odometry/start_odom.launch.py"

echo "   Window 1 (Odom)  — started"
sleep 1

# ---------------------------------------------------------------------------
# Window 2 — Static TF: base_link → imu_link
#   EKF drops ALL IMU data without this transform.
#   Delay 5 s so the launch system is up before we publish.
# ---------------------------------------------------------------------------
tmux new-window -t "$SESSION" -n "IMU-TF"
tmux send-keys -t "$SESSION:IMU-TF" \
  "source $ROS_SETUP && sleep 5 && \
   ros2 run tf2_ros static_transform_publisher \
   --x 0 --y 0 --z 0.115 \
   --roll 0 --pitch 0 --yaw 0 \
   --frame-id base_link --child-frame-id imu_link" \
  Enter

echo "   Window 2 (IMU-TF)— will publish after 5 s"
sleep 0.5

# ---------------------------------------------------------------------------
# Window 3 — EKF Sensor Fusion (Dhruv)
#   Delay 7 s so IMU + rf2o are publishing before EKF subscribes.
# ---------------------------------------------------------------------------
tmux new-window -t "$SESSION" -n "EKF"
_send "$SESSION:EKF" \
  "sleep 7 && ros2 launch ekf_node ekf_localization.launch.py"

echo "   Window 3 (EKF)   — will start after 7 s"
sleep 0.5

# ---------------------------------------------------------------------------
# Window 4 — AMCL Localization  ← INTERACTIVE — YOU TYPE CHECKPOINT HERE
#   Delay 12 s so EKF and /scan are live before AMCL starts.
# ---------------------------------------------------------------------------
tmux new-window -t "$SESSION" -n "AMCL"
_send "$SESSION:AMCL" \
  "sleep 12 && ros2 run localization_node localize \
   --ros-args \
   -p map:=$SLAM_DIR/saved_map/project_lab.yaml \
   -p checkpoints_file:=$SLAM_DIR/saved_map/checkpoints.json"

echo "   Window 4 (AMCL)  — will start after 12 s  ← TYPE CHECKPOINT HERE"
sleep 0.5

# ---------------------------------------------------------------------------
# Window 5 — Nav2 Navigation (Anmol)
#   Delay 20 s — AMCL must be localized before Nav2 plans routes.
# ---------------------------------------------------------------------------
tmux new-window -t "$SESSION" -n "Nav2"
_send "$SESSION:Nav2" \
  "sleep 20 && ros2 launch anmol nav2_bringup.launch.py"

echo "   Window 5 (Nav2)  — will start after 20 s"

# ---------------------------------------------------------------------------
# Focus the AMCL window so user sees the checkpoint prompt
# ---------------------------------------------------------------------------
tmux select-window -t "$SESSION:AMCL"

echo ""
echo "============================================================"
echo "  SLAM Robot Startup — session '$SESSION'"
echo "============================================================"
echo "  Window  Node          Starts in"
echo "  ------  ----          ---------"
echo "  0 IMU   imu_publisher  now"
echo "  1 Odom  rf2o + LiDAR   now"
echo "  2 IMU-TF imu_link TF   5 s"
echo "  3 EKF   ekf fusion     7 s"
echo "  4 AMCL  localization   12 s  ← FOCUSED (type checkpoint)"
echo "  5 Nav2  navigation     20 s"
echo ""
echo "  Ctrl+B 0-5  switch window   |   Ctrl+B d  detach"
echo "  After Nav2 is active run:   ros2 run anmol navigate_to <name>"
echo "============================================================"
echo ""

# Attach to the session (blocks until user detaches with Ctrl+B d)
tmux attach-session -t "$SESSION"
