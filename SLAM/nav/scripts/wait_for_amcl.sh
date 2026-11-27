#!/bin/bash
# Blocks until AMCL has published a pose (i.e. you typed the localization checkpoint
# and the robot is localized). Used so Nav2 never starts before localization.
source /opt/ros/humble/setup.bash
[ -f "$HOME/.local/share/project-dhruv/ros_ws/install/setup.bash" ] && source "$HOME/.local/share/project-dhruv/ros_ws/install/setup.bash"
until timeout 4 ros2 topic echo --once --qos-durability transient_local \
        --qos-reliability reliable /amcl_pose >/dev/null 2>&1; do
  echo "waiting for localization (type the start checkpoint in the AMCL window) ..."
  sleep 2
done
echo "localized - starting Nav2"
