# Project Dhruv · Jetson deployment and operation

The guide runs in an ARM64 Docker container. A small service on the Jetson host owns trip state and invokes your installed ROS 2 Humble command. You start SLAM and initialize AMCL as usual. The two services communicate over a local Unix socket. Sarvam handles speech, Azure handles dialogue, and an optional private Kaggle notebook describes selected camera frames.

## 1. Prepare the Jetson

Use the Ubuntu 22.04 user who owns the PulseAudio session and the ROS workspace. For installation and daily operation, follow [the combined guide](../setup_and_commmands.md). Run the following diagnostics from the Brain directory.

```sh
cd ~/Project-Dhruv/Brain
docker compose version
pactl info
pactl list short sources
pactl list short sinks
id -u
id -g
stat -c %g /dev/video0
ls -l "$XDG_RUNTIME_DIR/pulse/native" "$HOME/.config/pulse/cookie"
```

Install missing PulseAudio client tools with `sudo apt install pulseaudio-utils`. This configuration requires a PulseAudio host server supporting `module-echo-cancel` with the WebRTC backend. Use the physical ReSpeaker input and the actual robot speaker. A source ending in `.monitor` records playback. The previous robot used the sink `alsa_output.usb-SEEED_ReSpeaker_4_Mic_Array__UAC1.0_-00.iec958-stereo`. Check the actual device names before setting them. Stop the previous conversation application before starting this one.

```bash
umask 077
cp -n .env.example .env
chmod 600 .env
nano .env
```

| Setting | Value |
|---|---|
| `MIC_SOURCE`, `SPEAKER_SINK` | The physical source and sink names. The service creates its own paired echo-cancel routes on boot. |
| `ROBOT_UID`, `ROBOT_GID`, `VIDEO_GID` | The numeric user, group, and video device group from the commands above. |
| `PULSE_RUNTIME_DIR`, `PULSE_COOKIE_FILE` | Absolute user audio directory and existing PulseAudio authentication cookie. |
| `DHRUV_RUNTIME_DIR` | Absolute path to the bridge socket directory, default `/home/<user>/.local/run/project-dhruv`. The container shares only this directory with the bridge. |
| `CAMERA_HOST_DEVICE` | V4L2 capture device. Default `/dev/video0`. A stable path under `/dev/v4l/by-id` can also be used. |
| `SARVAM_API_KEY` | Key with speech-to-text and speech synthesis access. |
| `AZURE_CHAT_URL`, `AZURE_OPENAI_API_KEY` | Full Azure OpenAI deployment chat completions URL with API version and its matching key. Use a deployment supporting `max_tokens`, for example GPT-4o mini. |
| `VOICE_LANGUAGE`, `SARVAM_SPEAKER` | Defaults `hi-IN` and `ritu`. Use `en-IN` for an English session. |
| `VISION_URL`, `VISION_TOKEN` | Dedicated HTTPS origin and shared random secret from step 3. Leave both empty for local recognition and exhibit conversation without cloud scene descriptions. |

## 2. Supply the exhibition content and enroll people

Edit `data/locations.json`. All eight actual checkpoints are present. Fill each `facts` field with the approved explanation and add unique aliases in the languages visitors will use. For instance, if the window exhibit really is at p2, add `"the window exhibit"` to p2's aliases and describe the project there. Current location, recent conversation, and the small catalog reach Azure together so it can handle “this one” and comparisons between exhibits. Recreate or restart the container after catalog edits.

Install the local face models if enrolling people:

```bash
python3 -m host.face_models
```

For each participant who has agreed to recognition, put a clear, single-face reference photograph in `data/faces/` and add a record to `data/people.json`, for example:

```json
{
  "guide": {
    "name": "Exhibit Guide",
    "image": "guide.jpg",
    "context": "Introduces the robotics exhibit."
  }
}
```

Alternatively, after reviewing a participant's existing profile, import by filename stem with `python3 -m host.import_faces ~/DhruvBrain NAME`. The importer reads the selected portrait and its matching description. Keep only information suitable for speaking aloud and sharing with Azure. Recognition runs locally when a conversation turn needs identity. An ambiguous match, multiple visible faces, or an unregistered person gets a neutral response. Validate each enrollment with both the registered person and someone else under room lighting. Restart the container after edits.

## 3. Prepare the private Kaggle scene service

The deployment uses a separate private notebook named `anmolsharma1117/project-dhruv-vision`. A separate notebook preserves the existing local-automation-test project. On a workstation with the Kaggle CLI authenticated as that account, run:

```bash
python3 -m cloud.notebook build
```

Import `cloud/bundle/vision.ipynb` into a private notebook with the indicated slug, enable Internet and GPU, and attach these Kaggle Secrets. Generate a fresh shared token using `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` in a private terminal.

| Kaggle Secret | Purpose |
|---|---|
| `VISION_TOKEN` | Same token as the robot's private environment. |
| `NGROK_AUTHTOKEN` | Your ngrok agent credential. |
| `NGROK_DOMAIN` | Your assigned, dedicated hostname without a scheme or path. Set the robot's `VISION_URL` to `https://` plus this hostname. |

Run the notebook, or submit an updated version from the project root:

```bash
python3 -m cloud.notebook status
python3 -m cloud.notebook push
python3 -m cloud.notebook status
```

Push starts a GPU run. Wait for **Vision gateway ready on configured hostname** in Kaggle's logs. A running kernel can still be installing Ollama or downloading Moondream. The notebook exposes a bounded caption request and a service identity check, with Ollama bound to loopback. The robot verifies a fresh signed challenge before capturing a frame for upload. Stop the run in Kaggle after use. Notebook sessions and quotas can expire; text conversation and local recognition can continue.

For exhibition startup on a Linux host with the authenticated Kaggle CLI on its PATH, run `python3 -m cloud.notebook ensure` once after the private notebook exists and has its secrets attached. It checks status and submits a fresh version after a terminal state. A queued or running notebook is reused. Credential and unrecognized status errors are reported before submission. Only the host that owns GPU startup should run this command.

## 4. Start the combined robot

Follow **Daily startup** in [the combined guide](../setup_and_commmands.md). Both services use the packaged SLAM map and checkpoint file.

## 5. Guide a visit

Ask “What is this exhibit?” or “What am I holding?” Say **“Go to p1”**, **“Take me to the window exhibit”** (if configured), or **“पी वन पर चलो”**. Dhruv repeats the destination. Answer **yes** or **हाँ** after the prompt finishes. A completed confirmation prompt is valid for 45 seconds. A question about a location only requests an explanation.

While driving, the guide closes microphone capture, playback, and its camera worker. No conversation or visual inference is started in transit. The host runs the equivalent of:

```bash
source /opt/ros/humble/setup.bash
source ~/.local/share/project-dhruv/ros_ws/install/setup.bash
ros2 run nav navigate_to p1
```

Use the bridge for operator-initiated trips while the guide is running so position and sleep remain synchronized:

```bash
python3 -m host.bridge go p2
python3 -m host.bridge status
python3 -m host.bridge stop
```

Keep the physical stop accessible. The voice microphone sleeps during travel. The operator stop sends SIGINT to the navigator process group, which invokes the existing ROS cancellation path. A failed, timed-out, canceled, or interrupted trip leaves the current position unknown and suspends the guide. Verify that motion stopped, re-localize in AMCL as needed, and run `python3 -m host.bridge localize POINT` only when the robot is at that checkpoint. The last confirmed arrival is retained separately. A successful trip wakes conversation and introduces the destination. If a separate terminal moves the robot directly through ROS, synchronize the guide manually before resuming use.

## 6. Commission with SLAM running

1. Check `capture ready`, ask ten short questions and interrupt several replies midway. Measure first-word loss, time to audible silence, and whether any canceled reply resumes. Begin with `VAD_MODE=2`, six 20 ms onset frames and 600 ms end silence. The capture loop retains 300 ms of pre-roll. Tune one setting at a time in the actual room.
2. Repeat with fans and nearby conversations. Optional `ADDRESS_CUES=Dhruv,ध्रुव` requires a cue in each utterance and delays interruption until STT confirms it. In this mode include the cue when confirming movement too. Local speech detection alone cannot determine which visitor is addressing the robot.
3. Check one known and one unknown visitor, a camera question with the notebook online, and an exhibit question after stopping the notebook. On camera or gateway failure, Dhruv should acknowledge unavailable visual context.
4. Start a supervised short trip from center. Check `status` during motion and on arrival. Repeat a supervised cancellation and recovery. Compare CPU, memory and thermal load with `tegrastats` before, during and after motion. Keep localization active.
5. Check a guide restart at a known destination and a host reboot. The former preserves location; the latter requires operator localization. Capture loss causes the container to restart. Cloud turn failures are logged by stage without recording raw speech or transcripts.

Run the regression tests inside the built container from the project root:

```bash
docker compose run --rm --no-deps -v "$PWD/tests:/app/tests:ro" -v "$PWD/host:/app/host:ro" -v "$PWD/cloud:/app/cloud:ro" conversation python -m unittest discover -s tests -v
```

Check `journalctl --user -u project-dhruv-nav -b` for ROS startup, process output and checkpoint errors. For an echo-cancel mismatch after changing devices, stop the guide, inspect `pactl list short modules`, unload only the module containing both Dhruv device names, and restart the guide. For a 401 or 403 verify the key and the account or deployment named by that processing stage. Avoid sharing rendered Compose environments or raw credentials.

To shut down while stationary, run `bash dhruv stop` from the repository root. Stop a running GPU notebook separately.
