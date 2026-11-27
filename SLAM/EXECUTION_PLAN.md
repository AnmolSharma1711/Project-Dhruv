# 🤖 Robot Execution Plan — SLAM Project
> **Platform:** Jetson Orin Nano · **ROS 2 Humble** · Updated: 2026-11-21

---

## 📌 Project Status

| Phase | Status | Owner |
|-------|--------|-------|
| IMU Driver (`/imu/data`) | ✅ Done | Akshat |
| LiDAR Odometry (`/odom_rf2o`) | ✅ Done | Kushal |
| EKF Fusion (`/odometry/filtered`) | ✅ Done | Dhruv |
| Mapping (SLAM Toolbox → map saved) | ✅ Done | Dhruv |
| AMCL + Map Server (`localization_node`) | ✅ Done | Dhruv |
| **Nav2 Navigation (global planner + controller)** | ✅ Package Built | **Anmol** |

---

## 🔗 Symlink Setup — IMPORTANT

All ROS packages live under `~/Desktop/SLAM/` but are **symlinked** into `~/ros2_ws/src/` so colcon can build them. This means:

- **Edit files in `~/Desktop/SLAM/`** — the source of truth
- Changes are reflected immediately without re-running `ln -s` again
- After any change to `setup.py` or `package.xml`, re-run `colcon build`
- After any Python code change (since `--symlink-install` is used), no rebuild needed

```bash
# How the symlinks are set up (run ONCE per package, already done):
ln -s ~/Desktop/SLAM/ekf_node            ~/ros2_ws/src/ekf_node
ln -s ~/Desktop/SLAM/slam_node           ~/ros2_ws/src/slam_node
ln -s ~/Desktop/SLAM/localization_node   ~/ros2_ws/src/localization_node
# anmol's package (to be created):
ln -s ~/Desktop/SLAM/anmol              ~/ros2_ws/src/anmol
```

> **Build command (run from `~/ros2_ws`):**
> ```bash
> colcon build --symlink-install
> source install/setup.bash
> ```

---

## 🗺️ TF Tree (Current — Navigation Mode)

```
map ──(AMCL publishes)──▶ odom ──(EKF publishes @ 30Hz)──▶ base_link
                                                               ├──▶ imu_link      (static, z=+0.115m)
                                                               └──▶ laser         (static, z=+0.625m, yaw=90°)
                                                                        ↑
                                             published by start_odom.launch.py
```

---

## 🗂️ Saved Maps & Checkpoints

| File | Location | Description |
|------|----------|-------------|
| `project_lab.pgm` | `saved_map/` | **PRIMARY MAP** — used for navigation |
| `project_lab.yaml` | `saved_map/` | Map metadata |
| `checkpoints.json` | `saved_map/` | 8 checkpoints: home, p1–p6, center |

**Active checkpoints (map frame):**

| Name | X (m) | Y (m) | Yaw (°) |
|------|-------|-------|---------|
| home | 0.0093 | 0.1475 | -5.7° |
| p1 | 4.112 | 0.1612 | -176.6° |
| p2 | 6.1522 | 2.053 | -160.8° |
| p3 | 3.9505 | 2.5371 | -124.3° |
| p4 | 1.0091 | 3.194 | -44.3° |
| p5 | 0.5052 | 1.6702 | -12.4° |
| center | 2.382 | 1.3741 | -86.7° |
| p6 | 3.1135 | -0.3341 | -88.4° |

---

## ⚡ FULL STARTUP SEQUENCE (Navigation Mode)

### 🚀 Option A — One-Shot Startup (Recommended)

```bash
# Install tmux once if not already present
sudo apt install tmux -y

# Run the startup script — opens all nodes in a tmux session
bash ~/Desktop/SLAM/anmol/scripts/startup.sh
```

**What it does (automated):**
| Delay | Window | Node |
|-------|--------|------|
| now   | 0 IMU  | `imu_publisher_node.py` (Akshat) |
| now   | 1 Odom | `start_odom.launch.py` — LiDAR + rf2o + static TFs (Kushal) |
| 5 s   | 2 IMU-TF | `static_transform_publisher base_link→imu_link` (required by EKF) |
| 7 s   | 3 EKF  | `ekf_localization.launch.py` (Dhruv) |
| 12 s  | 4 AMCL | `localize` node — **YOU TYPE CHECKPOINT HERE** |
| 20 s  | 5 Nav2 | `nav2_bringup.launch.py` (Anmol) |

After `✓ Localized — ready to control` appears in Window 4:
```bash
# Navigate to any checkpoint by name (run in a new tmux pane or new terminal)
ros2 run anmol navigate_to home
ros2 run anmol navigate_to p1
ros2 run anmol navigate_to center
# No argument → interactive prompt listing all checkpoints
ros2 run anmol navigate_to
```

**tmux keys:** `Ctrl+B 0-5` switch windows · `Ctrl+B d` detach · `Ctrl+B [` scroll

---

### Option B — Manual Terminals (original method, unchanged below)

> Run each command in a **separate terminal** on the Jetson Orin Nano.
> Source ROS 2 at the top of every terminal: `source /opt/ros/humble/setup.bash && source ~/ros2_ws/install/setup.bash`

---
## Resolve Error
```bash
sudo rm -rf /dev/shm/fastrtps*
```

### TERMINAL 1 — IMU Driver (Akshat)

```bash
source /opt/ros/humble/setup.bash
cd ~/Desktop/SLAM/akshat/imu_argon
sudo -v                          # cache sudo password first
python3 imu_publisher_node.py
```

**Wait for:** `Warm-up complete! Publishing live /imu/data...`

> **Note:** This also requires the `imu_worker` binary compiled:
> ```bash
> g++ -O3 -Wall imu_worker.cpp -o imu_worker    # only if binary missing
> ```

---

### Static IMU TF (runs automatically via startup.sh — only needed for manual Option B)

```bash
source /opt/ros/humble/setup.bash
ros2 run tf2_ros static_transform_publisher \
  --x 0 --y 0 --z 0.115 \
  --roll 0 --pitch 0 --yaw 0 \
  --frame-id base_link --child-frame-id imu_link
```

> [!IMPORTANT]
> EKF drops **all IMU data** without this transform. Run this before Terminal 3 (EKF).
> The startup.sh script does this automatically in Window 2 (IMU-TF).

### TERMINAL 2 — LiDAR + rf2o + Static TFs (Kushal)

```bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch ~/Desktop/SLAM/kushal/rf2o_odometry/start_odom.launch.py
```

This single launch starts:
- **RPLIDAR A1** on `/dev/ttyUSB0` → publishes `/scan` (frame: `laser`)
- **Static TF** `base_footprint → base_link` (z = +0.035 m)
- **Static TF** `base_link → laser` (z = +0.625 m, yaw = 90°)
- **rf2o_laser_odometry** (after 3s delay) → publishes `/odom_rf2o`
- **rf2o_worker.py** (after 3.5s delay) → publishes `/odom_rf2o_corrected`

**Wait for:** `RF2O Holonomic Worker started → publishing /odom_rf2o_corrected`

> **Note:** Launch file is at `~/Desktop/SLAM/kushal/rf2o_odometry/start_odom.launch.py`
> Run it from the `kushal/rf2o_odometry/` directory OR use the full path.

---

### TERMINAL 3 — EKF Sensor Fusion (Dhruv)

```bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch ekf_node ekf_localization.launch.py
```

**Wait for:** `EKF ready. Frames: odom -> base_link | inputs: imu(/imu/data), rf2o(/odom_rf2o), vo(/visual_odom)`

**Verify (optional, new terminal):**
```bash
python3 ~/Desktop/SLAM/ekf_watch.py    # live x, y, yaw readout
```

---

### TERMINAL 4 — Map Server + AMCL Localization

```bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 run localization_node localize \
  --ros-args \
  -p map:=$HOME/Desktop/SLAM/saved_map/project_lab.yaml \
  -p checkpoints_file:=$HOME/Desktop/SLAM/saved_map/checkpoints.json
```

**What happens:**
1. Launches `map_server` (loads `project_lab.yaml` → publishes `/map`)
2. Launches `amcl` (particle filter, uses `/scan` + TF `odom→base_link`)
3. Launches `lifecycle_manager` (activates both)
4. Waits for AMCL to come alive
5. **Asks you:** `Where is the robot roughly? (checkpoint name, q = quit):`
6. Type the checkpoint closest to where the robot currently is (e.g. `home`)
7. AMCL refines the pose. Wait for: `✓ Localized — ready to control`

**Keep this terminal open for the entire session.**

---

### ✅ VERIFY LOCALIZATION

In a new terminal:
```bash
source /opt/ros/humble/setup.bash
ros2 run tf2_ros tf2_echo map base_link
```

**Expected output:** A stream of transforms showing the robot's pose in the map frame.
If you see `Transform not found` or errors → AMCL has not localized yet.

---

### TERMINAL 5 — Nav2 Navigation (Anmol)

> **Status: ✅ Package built & verified** — `anmol/` package complete, plugin names confirmed working.

#### Step A — First-time setup (run ONCE on Jetson)

```bash
# 1. Install Nav2 if not already present
sudo apt install ros-humble-navigation2 ros-humble-nav2-bringup -y

# 2. Install pyserial for Arduino serial bridge
pip3 install pyserial

# 3. Create symlink so colcon can find the package
#    NOTE: workspace is ~/ros2_ws  (NOT ~/Desktop/SLAM/ros2_ws)
mkdir -p ~/ros2_ws/src
rm -rf ~/ros2_ws/src/anmol          # remove stale entry if it exists
ln -s ~/Desktop/SLAM/anmol ~/ros2_ws/src/anmol

# 4. Build the package
cd ~/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select anmol --symlink-install
```

#### Step B — Every session (after Terminals 1–4 are running and AMCL is localized)

```bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch anmol nav2_bringup.launch.py
```

### Checkpoint Navigation — `navigate_to` (Recommended)
```bash
# In a new terminal after Nav2 is active:
source /opt/ros/humble/setup.bash && source ~/ros2_ws/install/setup.bash

# Navigate to a named checkpoint (uses correct yaw from checkpoints.json)
ros2 run anmol navigate_to p1
ros2 run anmol navigate_to home
ros2 run anmol navigate_to center

# Interactive mode (no argument → shows list and prompts)
ros2 run anmol navigate_to
```

> [!IMPORTANT]
> Always use `navigate_to` instead of raw `ros2 action send_goal`.
> The raw command hardcodes `orientation: {w: 1.0}` = yaw 0° for every goal,
> forcing the robot to rotate to face east at every checkpoint regardless of the
> intended heading. `navigate_to` reads the correct yaw from `checkpoints.json`.

### Raw Action Command (manual override / debugging only)
```bash
# Example: checkpoint p1  (x=4.112, y=0.161, yaw=-3.08 rad → qz=-1.0, qw=0.0 approx)
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: 'map', stamp: {sec: 0, nanosec: 0}}, pose: {position: {x: 4.112, y: 0.161, z: 0.0}, orientation: {x: 0.0, y: 0.0, z: -1.0, w: 0.0}}}}"
```

> **For testing without Arduino** (dry run — no serial port needed):
> ```bash
> ros2 launch anmol nav2_bringup.launch.py dry_run:=true
> ```

**Wait for:** All 6 Nav2 nodes to print `Lifecycle transition: active`
*(planner_server, controller_server, smoother_server, behavior_server, bt_navigator, velocity_smoother)*

> **Note:** `cmd_vel_bridge` will also print:
> `Serial opened: /dev/ttyACM0  →  MODE:AUTO sent`
> This confirms Arduino is connected and in autonomous mode.

> **Config-only changes** (yaml edits) take effect immediately with `--symlink-install` — no rebuild needed, just relaunch.

#### Step C — Test Navigation

**Option 1 — RViz2 (recommended, visual)**
```bash
# In a new terminal:
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
rviz2
```
In RViz2:
1. Add display → `By Topic` → `/map` (OccupancyGrid)
2. Add display → `By Topic` → `/scan` (LaserScan)
3. Add display → `Nav2 Goal` plugin (or use "2D Nav Goal" button in toolbar)
4. Click on the map to set a goal — robot will plan and drive

**Option 2 — `navigate_to` CLI (Recommended)**
```bash
# Navigate to any checkpoint by name — reads correct yaw from checkpoints.json
ros2 run anmol navigate_to p1
ros2 run anmol navigate_to home
ros2 run anmol navigate_to center
# No argument → interactive prompt listing all 8 checkpoints
ros2 run anmol navigate_to
```

**Option 3 — Verify cmd_vel is flowing to Arduino**
```bash
# Watch Nav2 motor commands in real time
ros2 topic echo /cmd_vel

# Check plan is being generated
ros2 topic hz /plan
ros2 topic hz /cmd_vel
```

#### Quick health check after launch
```bash
# All Nav2 topics should appear:
ros2 topic list | grep -E "cmd_vel|plan|costmap|goal"

# TF chain must be complete (requires Terminals 1-4 running):
ros2 run tf2_ros tf2_echo map base_link
```

---

## 🔎 Useful Diagnostic Commands

Run these in any terminal to check system health:

```bash
# Check all active topics
ros2 topic list

# Check topic frequencies
ros2 topic hz /imu/data            # expect ~180 Hz
ros2 topic hz /scan                # expect ~10 Hz
ros2 topic hz /odom_rf2o           # expect ~10 Hz
ros2 topic hz /odometry/filtered   # expect ~30 Hz
ros2 topic hz /amcl_pose           # expect ~1 Hz (updates on movement)
ros2 topic hz /map                 # expect 1 Hz (Transient Local, latched)

# Check TF tree
ros2 run tf2_tools view_frames     # saves frames.pdf
ros2 run tf2_ros tf2_echo map base_link        # localization check
ros2 run tf2_ros tf2_echo odom base_link       # EKF output check
ros2 run tf2_ros tf2_echo base_link laser      # static TF check

# Check EKF diagnostics
ros2 topic echo /diagnostics --once

# Check AMCL pose
ros2 topic echo /amcl_pose --once

# IMU live dashboard
cd ~/Desktop/SLAM/akshat/imu_argon
python3 verify_imu.py
```

---

## 📦 Packages in `~/ros2_ws/src/` and Their Source

| ROS Package | Source (via symlink) | Build Command |
|-------------|---------------------|---------------|
| `ekf_node` | `~/Desktop/SLAM/ekf_node` | `colcon build --packages-select ekf_node` |
| `slam_node` | `~/Desktop/SLAM/slam_node` | `colcon build --packages-select slam_node` |
| `localization_node` | `~/Desktop/SLAM/localization_node` | `colcon build --packages-select localization_node` |
| `anmol` ✅ | `~/Desktop/SLAM/anmol` | `colcon build --packages-select anmol --symlink-install` |
| `rf2o_laser_odometry` | system install or separate ws | pre-built |
| `rplidar_ros` | system install | pre-built |

---

## 🔧 Nav2 — What Anmol Needs to Build

The next phase is building the `anmol/` package with Nav2. Here is what it needs:

### Inputs it consumes:
| Topic/TF | Type | From |
|----------|------|------|
| `/odometry/filtered` | `nav_msgs/Odometry` | EKF (Terminal 3) |
| `/scan` | `sensor_msgs/LaserScan` | RPLIDAR (Terminal 2) |
| `/map` | `nav_msgs/OccupancyGrid` | AMCL/map_server (Terminal 4) |
| TF `map → odom` | TF | AMCL (Terminal 4) |
| TF `odom → base_link` | TF | EKF (Terminal 3) |
| TF `base_link → laser` | TF | start_odom launch (Terminal 2) |

### Outputs it produces:
| Topic | Type | To |
|-------|------|----|
| `/cmd_vel` | `geometry_msgs/Twist` | Motor driver / robot wheels |
| `/plan` | `nav_msgs/Path` | RViz visualization |
| `/local_plan` | `nav_msgs/Path` | RViz visualization |

### Key Nav2 parameters for this robot:
| Parameter | Value | Why |
|-----------|-------|-----|
| `robot_radius` | `0.13` m | 11 cm + 2 cm margin |
| `inflation_radius` | `0.22` m | robot_radius + 9 cm |
| `max_vel_x` | `0.35` m/s | Motor limit |
| `max_vel_theta` | `0.8` rad/s | Motor limit |
| `odom_topic` | `/odometry/filtered` | Custom EKF output |
| `scan_topic` | `/scan` | RPLIDAR output |
| `base_frame_id` | `base_link` | |
| `odom_frame_id` | `odom` | |
| `global_frame` (global costmap) | `map` | |
| `global_frame` (local costmap) | `odom` | |

---

## ❗ Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| `No TF between map and base_link` | AMCL not running or not localized yet. Check Terminal 4 |
| `RPLiDAR not found` | Check USB: `ls /dev/ttyUSB*`. May need: `sudo chmod 666 /dev/ttyUSB0` |
| `imu_worker: Permission denied` | Run `sudo -v` first, then restart imu_publisher_node.py |
| `EKF: stale IMU` | IMU not running. Start Terminal 1 first |
| `AMCL: bad localization` | Type checkpoint name again in Terminal 4, or gently push robot to trigger scan matching |
| `colcon build fails` | Check `source /opt/ros/humble/setup.bash` is done first |
| `ros2 command not found` | Need to source: `source /opt/ros/humble/setup.bash` |

---

*Last updated: 2026-11-26 — startup.sh (tmux), navigate_to node (correct yaw), nav2_params tuned for smooth motion*
