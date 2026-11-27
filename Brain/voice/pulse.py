"""Configure a paired host PulseAudio echo canceller without changing desktop defaults."""
import json
import os
import subprocess


def pactl(*args):
    return subprocess.check_output(["pactl", *args], text=True, timeout=8)


def devices(kind):
    return {row["name"]: row for row in json.loads(pactl("--format=json", "list", kind))}


def configure():
    source = os.environ.get("MIC_SOURCE", "").strip()
    sink = os.environ.get("SPEAKER_SINK", "").strip()
    sources, sinks = devices("sources"), devices("sinks")
    if source not in sources or source.endswith(".monitor") or sink not in sinks:
        raise ValueError("Set MIC_SOURCE and SPEAKER_SINK to attached physical PulseAudio devices")
    args = [f"source_master={source}", f"sink_master={sink}", "source_name=dhruv_aec_mic",
            "sink_name=dhruv_aec_speaker", "aec_method=webrtc", "rate=16000", "channels=1"]
    existing = {row["index"]: row for row in json.loads(pactl("--format=json", "list", "modules"))}
    mic = sources.get("dhruv_aec_mic")
    speaker = sinks.get("dhruv_aec_speaker")
    if mic or speaker:
        module = existing.get(int(mic["owner_module"])) if mic else None
        if (not mic or not speaker or not module or mic["owner_module"] != speaker["owner_module"]
                or module["name"] != "module-echo-cancel"
                or set(args) != set(module["argument"].split())):
            raise ValueError("Existing Dhruv echo-cancel devices do not match configured hardware")
    else:
        pactl("load-module", "module-echo-cancel", *args)
    if "dhruv_aec_mic" not in devices("sources") or "dhruv_aec_speaker" not in devices("sinks"):
        raise RuntimeError("PulseAudio did not expose the paired echo-cancel devices")
