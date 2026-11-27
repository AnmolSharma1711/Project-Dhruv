# Project Dhruv

**Start here → [Set up and run the robot](setup_and_commmands.md)**

Dhruv has two parts. **SLAM** tells the robot where it is and drives it between checkpoints. **Brain** listens to a visitor, explains the exhibits, and asks SLAM to drive. The Jetson runs both.

| Folder | What you will use it for |
|---|---|
| [Brain](Brain/) | Microphone, speaker, camera, face recognition, cloud connections and navigation requests |
| [SLAM](SLAM/) | Sensors, localization, maps, motor control and navigation |
| [Exhibit descriptions](Brain/data/locations.json) | The facts Dhruv uses to explain each checkpoint |
| [Room map and checkpoints](SLAM/saved_map/) | Where the eight destinations are in the physical room |

Once installed, the daily procedure takes two terminals. Start SLAM, enter the robot's physical starting checkpoint, then start Brain. The [setup guide](setup_and_commmands.md) shows exactly where to type each command and what to wait for.
