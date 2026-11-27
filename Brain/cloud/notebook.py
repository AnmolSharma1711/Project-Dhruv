import argparse
import json
import re
from pathlib import Path
import subprocess
import tempfile

KERNEL = "anmolsharma1117/project-dhruv-vision"


def build(directory):
    directory.mkdir(exist_ok=True, parents=True)
    source = Path(__file__).with_name("kernel.py").read_text(encoding="utf8")
    notebook = {"nbformat": 4, "nbformat_minor": 4, "metadata": {"kernelspec": {
        "display_name": "Python 3", "language": "python", "name": "python3"}},
        "cells": [{"cell_type": "code", "execution_count": None, "outputs": [], "metadata": {},
                   "source": source.splitlines(keepends=True)}]}
    (directory / "vision.ipynb").write_text(json.dumps(notebook), encoding="utf8")
    meta = {"id": KERNEL, "title": "Project Dhruv Vision", "code_file": "vision.ipynb",
            "language": "python", "kernel_type": "notebook", "is_private": True,
            "enable_gpu": True, "enable_internet": True, "dataset_sources": [],
            "competition_sources": [], "kernel_sources": []}
    (directory / "kernel-metadata.json").write_text(json.dumps(meta), encoding="utf8")


def push():
    with tempfile.TemporaryDirectory() as folder:
        build(Path(folder))
        subprocess.run(["kaggle", "kernels", "push", "-p", folder], check=True)


def ensure():
    """Single Jetson startup owner. Fail closed on unknown status or authentication failure."""
    import fcntl
    root = Path.home() / ".local/state/project-dhruv"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (root / "kaggle.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        status = subprocess.check_output(["kaggle", "kernels", "status", KERNEL],
                                         text=True, timeout=30).lower()
        if re.search(r"\b(running|queued|pending|starting)\b", status):
            print("Kaggle notebook is already queued or running")
        elif re.search(r"\b(complete|completed|cancelacknowledged|canceled|cancelled|error|failed)\b", status):
            push()
        else:
            raise RuntimeError("Unknown notebook status; check it in Kaggle")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build", "push", "status", "ensure"])
    args = parser.parse_args()
    if args.action == "status":
        subprocess.run(["kaggle", "kernels", "status", KERNEL], check=True)
    elif args.action == "push":
        push()
    elif args.action == "ensure":
        ensure()
    else:
        build(Path(__file__).with_name("bundle"))
