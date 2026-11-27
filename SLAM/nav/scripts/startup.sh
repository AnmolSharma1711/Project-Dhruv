#!/bin/bash
# =============================================================================
# SLAM Robot - full startup in one tmux session.   Usage: bash scripts/startup.sh
#
# Override paths with environment variables, for example:
#   SLAM_DIR=$HOME/Desktop/SLAM MAP=$HOME/maps/lab.yaml bash scripts/startup.sh
#
# Windows: 0 IMU | 1 Odom | 2 IMU-TF | 3 EKF | 4 AMCL (type start checkpoint here)
#          5 Nav2 (waits until localized) | 6 Goto (run navigate_to here)
# tmux keys: Ctrl+B <n> switch window, Ctrl+B d detach, Ctrl+B [ scroll (q exits)
# =============================================================================
SESSION="${SESSION:-slam}"
SLAM_DIR="${SLAM_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
MAP="${MAP:-$SLAM_DIR/saved_map/project_lab.yaml}"
CHECKPOINTS="${CHECKPOINTS:-$SLAM_DIR/saved_map/checkpoints.json}"
ROS_SETUP="/opt/ros/humble/setup.bash"
WS_SETUP="${WS_SETUP:-$HOME/.local/share/project-dhruv/ros_ws/install/setup.bash}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v tmux >/dev/null || { echo "tmux not found: sudo apt install tmux"; exit 1; }
[ -f "$MAP" ] || { echo "Map not found: $MAP"; exit 1; }
[ -f "$CHECKPOINTS" ] || { echo "Checkpoints not found: $CHECKPOINTS"; exit 1; }
echo "Map:         $MAP"
echo "Checkpoints: $CHECKPOINTS"

_send() { local target="$1"; shift; tmux send-keys -t "$target" "source $ROS_SETUP && source $WS_SETUP && $*" Enter; }

tmux new-session -d -s "$SESSION" -n "IMU" -x 220 -y 50
tmux send-keys -t "$SESSION:IMU" \
  "cd $SLAM_DIR/akshat/imu_argon && source $ROS_SETUP && python3 imu_publisher_node.py" Enter
sleep 1

tmux new-window -t "$SESSION" -n "Odom"
_send "$SESSION:Odom" "ros2 launch $SLAM_DIR/kushal/rf2o_odometry/start_odom.launch.py"
sleep 1

# EKF drops all IMU data without base_link -> imu_link
tmux new-window -t "$SESSION" -n "IMU-TF"
tmux send-keys -t "$SESSION:IMU-TF" \
  "source $ROS_SETUP && sleep 5 && ros2 run tf2_ros static_transform_publisher --x 0 --y 0 --z 0.115 --roll 0 --pitch 0 --yaw 0 --frame-id base_link --child-frame-id imu_link" Enter

tmux new-window -t "$SESSION" -n "EKF"
_send "$SESSION:EKF" "sleep 7 && ros2 launch ekf_node ekf_localization.launch.py"

tmux new-window -t "$SESSION" -n "AMCL"
_send "$SESSION:AMCL" "sleep 12 && ros2 run localization_node localize --ros-args -p map:=$MAP -p checkpoints_file:=$CHECKPOINTS"

# Nav2 starts only AFTER localization (no blind sleep)
tmux new-window -t "$SESSION" -n "Nav2"
tmux send-keys -t "$SESSION:Nav2" "bash $SCRIPT_DIR/wait_for_amcl.sh && source $ROS_SETUP && source $WS_SETUP && ros2 launch nav nav2_bringup.launch.py" Enter

tmux new-window -t "$SESSION" -n "Goto"
tmux send-keys -t "$SESSION:Goto" "source $ROS_SETUP && source $WS_SETUP && export SLAM_CHECKPOINTS=$CHECKPOINTS && echo 'When Nav2 is active run:  ros2 run nav navigate_to'" Enter

tmux select-window -t "$SESSION:AMCL"
echo "Session '$SESSION' started. AMCL window is focused: type the robot's start checkpoint there."
tmux attach-session -t "$SESSION"
