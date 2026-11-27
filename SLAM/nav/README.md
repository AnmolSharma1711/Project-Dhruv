# nav - Nav2 navigation + Arduino bridge (forward + pivot only)

## Run order (separate terminals, or `bash scripts/startup.sh` for tmux)
1. IMU   2. rf2o + LiDAR   3. EKF
4. `ros2 run localization_node localize --ros-args -p map:=... -p checkpoints_file:=...`
   (type the start checkpoint, wait for "Localized - ready to control")
5. `ros2 launch nav nav2_bringup.launch.py`      (starts Nav2 AND its own serial bridge)
6. `ros2 run nav navigate_to`  (or `... navigate_to p1 p4 home`)
Do NOT run slam_node's drive.launch.py together with step 5 (same serial port).

## Launch arguments
| arg | default | meaning |
|---|---|---|
| odom_topic | /odometry/filtered | used by bt_navigator, controller, smoother (check `ros2 topic list`) |
| robot_radius | 0.13 | centre to outer edge, metres. **TODO: measure it** |
| serial_port | /dev/ttyACM0 | Arduino |
| dry_run | false | true = bridge only logs, no serial |

## Measured calibration (at power 180 = app full speed)
| | value | used as |
|---|---|---|
| forward | 0.148 m/s | pwm_per_mps = 1216 |
| turn | 360 deg / 2.75 s = 2.285 rad/s | pwm_per_radps = 78.8 |
| smallest power that moves | 25 | min_pwm |
Settings: config/bridge.yaml (bridge) and config/nav2_params.yaml (Nav2).

## Tests (no ROS needed)
    cd nav && PYTHONPATH=. python3 test/test_drive_math.py && PYTHONPATH=. python3 test/test_params.py

## Hardware test checklist (in this order)
1. `dry_run:=true`, send a goal: logged `<MIX,...>` lines look sensible and the middle number is always 0.
2. Robot lifted: publish a small forward and a small left-turn Twist to /cmd_vel_smoothed.
   Forward must spin the wheels forward, left must pivot left. Otherwise flip drive_sign / turn_sign.
3. Floor, clear space, hand on the power switch: navigate to the nearest checkpoint.
4. Put a box in the path: it should stop or go around. Ctrl-C in navigate_to must stop the robot.
5. Only then try the far checkpoints.
