#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
source /opt/ros/humble/setup.bash
source "$HOME/.local/share/project-dhruv/ros_ws/install/setup.bash"
export SLAM_CHECKPOINTS="$PWD/../SLAM/saved_map/checkpoints.json"
test -r "$SLAM_CHECKPOINTS" || { echo "Missing checkpoint file: $SLAM_CHECKPOINTS" >&2; exit 1; }
exec python3 -m host.bridge serve
