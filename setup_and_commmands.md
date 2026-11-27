# Set up and run Dhruv

**Use the Jetson for the robot commands.** Your Windows PC holds the repository. The Jetson has the microphone, speaker, camera, sensors and motors.

**What happens during a visit?** A visitor says “Take me to p1.” Brain asks for confirmation. SLAM drives to p1 while Brain pauses listening and camera processing. When navigation reports success, Brain wakes up and introduces p1 using the facts you supplied.

## A. One-time setup on the Jetson

### 1. Get the project

Push the folder from Windows using the instructions at the end of this guide. On the Jetson, log in as the normal robot user. Replace `YOUR_REPOSITORY_URL` with the URL of your new repository.

```bash
git clone YOUR_REPOSITORY_URL ~/Project-Dhruv
cd ~/Project-Dhruv
ls
```

You should see **Brain**, **SLAM**, and **dhruv**. Keep this location because the supplied host service uses it.

### 2. Check the software and hardware

On your existing robot, keep the working ROS 2 Humble installation, Docker, and the host PulseAudio session. Turn off the old brain and SLAM launchers before switching over, with the chassis stationary. This avoids two programs using the same motor port or responding through the same speaker.

```bash
source /opt/ros/humble/setup.bash
docker compose version
pactl info
ls /dev/video0 /dev/ttyUSB0 /dev/ttyACM0 /dev/i2c-7
```

These names are the camera, LiDAR, Arduino and IMU bus used by the supplied configuration. Check the physical connection and port if one is missing. Use the same audio user that normally operates Dhruv.

On a **fresh Ubuntu 22.04 Jetson**, first install [ROS 2 Humble](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html) and [Docker Engine with Compose](https://docs.docker.com/engine/install/ubuntu/). Once the ROS apt repository is available, install the robot tools:

```bash
sudo apt update
sudo apt install git g++ tmux pulseaudio pulseaudio-utils python3-colcon-common-extensions python3-rosdep python3-numpy python3-yaml python3-serial ros-humble-navigation2 ros-humble-nav2-bringup ros-humble-slam-toolbox ros-humble-rplidar-ros
# Only on a fresh installation where rosdep has never been initialized:
sudo rosdep init
rosdep update
```

Your user needs Docker access and read/write access to the Arduino and LiDAR serial devices (usually the `dialout` group). Re-login after a group change. The existing IMU launcher uses sudo for its I²C worker; it may prompt in the **IMU** tmux window at startup. The installation reuses RF2O from your existing ROS workspace when available, or builds the [upstream ROS 2 driver](https://github.com/MAPIRlab/rf2o_laser_odometry/tree/ros2).

### 3. Tell Brain which microphone, speaker and cloud accounts to use

```bash
cd ~/Project-Dhruv
bash dhruv configure
nano Brain/.env
```

The first command lists your audio devices and creates a private settings file. It fills in your user ID, audio socket and camera group, and selects the ReSpeaker when there is one clear match. Running it again preserves your settings.

| Field in `Brain/.env` | What to enter |
|---|---|
| `MIC_SOURCE` | The physical microphone name printed under sources. Skip entries ending in `.monitor`. |
| `SPEAKER_SINK` | The speaker name printed under sinks. |
| `SARVAM_API_KEY` | Your Sarvam speech API key. |
| `AZURE_CHAT_URL` | Your full Azure deployment chat URL, including its API version. A template is already in the file. |
| `AZURE_OPENAI_API_KEY` | The key for that Azure endpoint. |
| `VOICE_LANGUAGE` | Keep `hi-IN` for Hindi or enter `en-IN` for English. |

In nano, press **Ctrl+O**, **Enter**, then **Ctrl+X**. For your first voice test you can leave `VISION_URL` and `VISION_TOKEN` empty. Kaggle is used for questions about what the camera sees.

### 4. Build the software once

```bash
cd ~/Project-Dhruv
bash dhruv install
```

Wait for **Installed**. This builds the bundled ROS packages in a separate workspace, compiles the IMU helper for the Jetson, builds the Brain Docker image, and installs the host navigation service. Your existing ROS workspace can still supply its working hardware drivers. Repeat this step after updating ROS sources or the Brain image.

### 5. Add your exhibition content

- **Project explanations:** edit [Brain/data/locations.json](Brain/data/locations.json). Fill in `facts` for each exhibit. An alias such as “the window exhibit” lets a visitor refer to the place by name.
- **Physical destinations:** [SLAM/saved_map/checkpoints.json](SLAM/saved_map/checkpoints.json) contains the coordinates for `p1` through `p6`, `home` and `center`. Keep these coordinates for the room where this map was recorded.
- **Recognize a person:** from `~/Project-Dhruv/Brain`, run `python3 -m host.face_models`, then add that person's approved photo and profile following [face enrollment](Brain/setup_and_commmands.md#2-supply-the-exhibition-content-and-enroll-people).
- **Describe a live camera frame:** follow [Kaggle setup](Brain/setup_and_commmands.md#3-prepare-the-private-kaggle-scene-service) for account `anmolsharma1117`. Set the two vision fields in `Brain/.env`. Wait for **Vision gateway ready** in Kaggle before trying “What am I holding?”

## B. Daily startup — two Jetson terminals

| Where | What to do | How to know it worked |
|---|---|---|
| **Terminal 1** | Physically place Dhruv at **center** in its mapped orientation. Run the SLAM command below. | A tmux screen opens in the **AMCL** window. |
| **Inside AMCL** | Type **center** and press **Enter**. | Wait for **Localized — ready to control**. Nav2 starts next and can take a few seconds. |
| **Terminal 2** | Run the Brain command below. | Docker shows the conversation service running. Logs show **capture ready**. |

**Terminal 1**

```bash
cd ~/Project-Dhruv
bash dhruv slam
```

Type `center` **inside the AMCL prompt**. Leave Terminal 1 running. If prompted for the IMU password, press **Ctrl+B**, release both keys, then **0** to visit IMU. Return to AMCL with **Ctrl+B**, then **4**.

**Terminal 2**

```bash
cd ~/Project-Dhruv
bash dhruv brain center
bash dhruv logs
```

The first `center` tells **SLAM** where the robot physically is. The second tells **Brain** which exhibit it is at. Use the same actual checkpoint in both places. If Nav2 is still starting, wait and retry `bash dhruv brain center`. Press **Ctrl+C** to leave the logs; conversation continues.

**Try it.** Ask “Where are we?” Then say “Go to p1” and answer “yes” after the confirmation finishes. Start with a nearby checkpoint and keep the physical stop accessible. Wait for arrival, then ask “What does this exhibit do?”

## C. During a visit

Run these commands in a Jetson terminal from `~/Project-Dhruv`.

| Goal | Command |
|---|---|
| Show the current location and container status | `bash dhruv status` |
| Send an operator-requested trip to p2 | `bash dhruv go p2` |
| Request cancellation of a trip | `bash dhruv cancel` |
| Read the microphone, cloud and playback logs | `bash dhruv logs` |
| Restart Brain after a confirmed arrival, reusing its saved location | `bash dhruv brain` |
| End the session once the chassis is stationary | `bash dhruv stop` |

Use the operator wrapper for manual trips during a guided visit. It calls your familiar `ros2 run nav navigate_to POINT` and keeps Brain's position synchronized. Voice sleeps during movement, so use the operator cancellation command or the robot's physical stop. After a failed or canceled trip, confirm the chassis has stopped, re-localize it at a known checkpoint in AMCL, then run `bash dhruv brain POINT`. Stop a running Kaggle session separately at the end of the day.

## D. If something goes wrong

| What you see | First thing to check |
|---|---|
| “Nav2 is not active” | In Terminal 1, confirm you typed the checkpoint in AMCL. Check the IMU window for a sudo prompt. Wait for Nav2 startup. |
| Brain shows `uncertain` | A trip did not finish cleanly. Use the recovery steps above; the recorded last arrival is history. |
| No spoken reply | Check `bash dhruv logs`. For device errors, verify `MIC_SOURCE` and `SPEAKER_SINK`. For HTTP 401/403, check the key for that stage. |
| Brain cannot describe a camera frame | Verify `/dev/video0`, the camera group, the Kaggle ready message, and matching vision credentials. |
| Navigation service will not start | Run `journalctl --user -u project-dhruv-nav -b -n 40`. Check that installation finished and the saved checkpoint file exists. |

After changing `Brain/.env`, run `bash dhruv brain` while stationary. For more detail see the [Brain reference](Brain/setup_and_commmands.md) and [SLAM navigation notes](SLAM/nav/README.md).

## E. Publish this folder from Windows

Create an empty remote repository in your Git hosting account. Open **PowerShell** on your PC:

```powershell
cd D:\Project-Dhruv
git status
git add .
git diff --cached --stat
git commit -m "Add integrated Dhruv brain and SLAM system"
git remote add origin YOUR_REPOSITORY_URL
git push -u origin main
```

Replace `YOUR_REPOSITORY_URL` with your actual remote URL. Review the staged files before committing. Keep API keys in the ignored `Brain/.env`; keep personal photos and private visitor profiles on the Jetson.
