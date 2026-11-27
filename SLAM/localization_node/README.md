# localization_node  (map server + AMCL)

Put this folder inside ~/SLAM, then:

    ln -s ~/SLAM/localization_node ~/ros2_ws/src/localization_node
    cd ~/ros2_ws && colcon build --packages-select localization_node
    source install/setup.bash

Needs:  sudo apt install ros-humble-nav2-map-server ros-humble-nav2-amcl ros-humble-nav2-lifecycle-manager

Before running: close the slam_toolbox mapping terminal. Keep IMU, rf2o and EKF running.

Run:

    ros2 run localization_node localize
    (different map)  ros2 run localization_node localize --ros-args -p map:=/full/path/my_map.yaml

Type the checkpoint name where the robot is standing. When it prints
"Localized — ready to control", you can start the bridge and goto_checkpoint.
Server log: /tmp/localization_server.log
