"""Generate a private environment from attached Jetson devices on first run."""
import os
from pathlib import Path
import subprocess

def names(kind):
    output = subprocess.check_output(["pactl", "list", "short", kind], text=True)
    return [line.split()[1] for line in output.splitlines() if len(line.split()) >= 2]

def main():
    people = Path("data/people.json")
    if not people.exists():
        people.write_text(Path("data/people.example.json").read_text())
    home = Path.home()
    camera = Path("/dev/video0")
    values = dict(ROBOT_UID=str(os.getuid()), ROBOT_GID=str(os.getgid()),
                  PULSE_RUNTIME_DIR=str(Path(os.getenv("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))/"pulse"),
                  PULSE_COOKIE_FILE=str(home/".config/pulse/cookie"),
                  DHRUV_RUNTIME_DIR=str(home/".local/run/project-dhruv"))
    if camera.exists():
        values["VIDEO_GID"] = str(camera.stat().st_gid)
    for kind, key in [("sources","MIC_SOURCE"), ("sinks","SPEAKER_SINK")]:
        options = [n for n in names(kind) if not n.endswith(".monitor") and not n.startswith("dhruv_aec_")]
        matched = [n for n in options if "respeaker" in n.lower()]
        if len(matched) == 1:
            values[key] = matched[0]
        print(key, "choices:", *options, sep="\n  ")
    target = Path(".env")
    if not target.exists():
        os.umask(0o077)
        lines = []
        for line in Path(".env.example").read_text().splitlines():
            key = line.partition("=")[0]
            lines.append(f"{key}={values[key]}" if key in values else line)
        with target.open("x") as output:
            output.write("\n".join(lines)+"\n")
    print("Review Brain/.env and enter your cloud credentials. Existing values are preserved.")

if __name__ == "__main__":
    main()
