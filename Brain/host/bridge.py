"""Run as the ROS user after sourcing the same workspace as SLAM's Goto window."""
import argparse
import asyncio
import contextlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import uuid

from voice.navigation import POINTS

ROOT = Path(os.getenv("DHRUV_STATE_DIR", Path.home() / ".local/state/project-dhruv"))
RUNTIME = Path(os.getenv("DHRUV_RUNTIME_DIR", Path.home() / ".local/run/project-dhruv"))


class Navigation:
    def __init__(self, database, boot, command=("ros2", "run", "nav", "navigate_to")):
        self.db = sqlite3.connect(database)
        self.db.execute("CREATE TABLE IF NOT EXISTS robot (id INTEGER PRIMARY KEY, state TEXT NOT NULL)")
        row = self.db.execute("SELECT state FROM robot WHERE id=1").fetchone()
        self.state = json.loads(row[0]) if row else dict(mode="unlocalized", current=None, last=None,
                                                       target=None, boot=boot, revision="", outcome="new")
        if self.state["mode"] == "moving":
            self.update(mode="uncertain", current=None, boot=boot, outcome="bridge interrupted")
        elif self.state["boot"] != boot:
            self.update(mode="unlocalized", current=None, boot=boot, outcome="host rebooted")
        elif not row:
            self.update()
        self.command = command
        self.job = self.child = None
        self.stopping = False
        self.interrupt_sent = False
        self.closing = False
        self.stop_event = asyncio.Event()

    def update(self, **fields):
        state = dict(self.state, **fields, revision=uuid.uuid4().hex)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO robot VALUES(1, ?)", (json.dumps(state),))
        self.state = state

    def dispatch(self, msg, admin=False):
        action = msg["action"]
        target = msg.get("point")
        if action == "status":
            return self.state
        if self.closing:
            raise ValueError("Bridge is shutting down")
        if action == "stop" and admin:
            self.stopping = True
            self.stop_event.set()
            if self.child:
                self.interrupt()
            return self.state
        if target not in POINTS:
            raise ValueError("Unknown checkpoint")
        if action == "localize" and admin:
            if self.state["mode"] == "moving" or (self.job and not self.job.done()):
                raise ValueError("Trip is active")
            self.update(mode="ready", current=target, target=None, outcome="operator localized")
        elif action == "go":
            if self.state["mode"] != "ready" or msg.get("revision") != self.state["revision"]:
                raise ValueError("Position or navigation state changed")
            if self.state["current"] == target:
                raise ValueError("Already at checkpoint")
            self.update(mode="moving", current=None, target=target, outcome="requested")
            self.stopping = False
            self.interrupt_sent = False
            self.stop_event.clear()
            self.job = asyncio.create_task(self.travel(target))
        else:
            raise ValueError("Unsupported operation")
        return self.state

    def interrupt(self):
        if self.child and self.child.returncode is None and not self.interrupt_sent:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.child.pid, signal.SIGINT)
                self.interrupt_sent = True

    async def travel(self, target):
        try:
            self.child = await asyncio.create_subprocess_exec(*self.command, target, start_new_session=True)
            if self.stopping:
                self.interrupt()
            exited = asyncio.create_task(self.child.wait())
            stopped = asyncio.create_task(self.stop_event.wait())
            try:
                done, _ = await asyncio.wait((exited, stopped), timeout=155,
                                            return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    raise asyncio.TimeoutError()
                code = exited.result() if exited in done else "operator stop"
            finally:
                for task in (exited, stopped):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(exited, stopped, return_exceptions=True)
            if code == 0 and not self.stopping:
                self.update(mode="ready", current=target, last=target, target=None, outcome="arrived")
                return
            outcome = f"navigator exit {code}"
        except (OSError, asyncio.TimeoutError) as error:
            outcome = type(error).__name__
        finally:
            if self.child and self.child.returncode is None:
                self.interrupt()
                try:
                    await asyncio.wait_for(self.child.wait(), 8)
                except asyncio.TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(self.child.pid, signal.SIGKILL)
                    await self.child.wait()
            self.child = None
        self.update(mode="uncertain", current=None, outcome=outcome)

    async def close(self):
        self.closing = True
        self.stopping = True
        self.stop_event.set()
        self.interrupt()
        if self.job and not self.job.done():
            await self.job
        self.db.close()


async def handle(robot, reader, writer, admin):
    try:
        msg = json.loads(await asyncio.wait_for(reader.readline(), 3))
        result = robot.dispatch(msg, admin)
    except (KeyError, TypeError, ValueError, asyncio.TimeoutError) as error:
        result = {"error": str(error)[:160]}
    try:
        writer.write(json.dumps(result).encode() + b"\n")
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def serve():
    import fcntl
    os.umask(0o077)
    ROOT.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    lock = (ROOT / "session.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    robot = Navigation(ROOT / "robot.sqlite", Path("/proc/sys/kernel/random/boot_id").read_text().strip())
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    async with contextlib.AsyncExitStack() as stack:
        for path, admin in [(RUNTIME / "nav.sock", False), (ROOT / "operator.sock", True)]:
            path.unlink(missing_ok=True)
            server = await asyncio.start_unix_server(
                lambda r, w, a=admin: handle(robot, r, w, a), path, limit=2048)
            await stack.enter_async_context(server)
        await stop.wait()
    await robot.close()
    lock.close()


async def operator(args):
    reader, writer = await asyncio.open_unix_connection(ROOT / "operator.sock")
    try:
        msg = {"action": args.action, "point": args.point}
        if args.action == "go":
            status_reader, status_writer = await asyncio.open_unix_connection(ROOT / "operator.sock")
            try:
                status_writer.write(b'{"action":"status"}\n')
                await status_writer.drain()
                status = json.loads(await asyncio.wait_for(status_reader.readline(), 3))
                msg["revision"] = status["revision"]
            finally:
                status_writer.close()
                await status_writer.wait_closed()
        writer.write(json.dumps(msg).encode() + b"\n")
        await writer.drain()
        result = json.loads(await asyncio.wait_for(reader.readline(), 3))
        print(json.dumps(result, indent=2))
        return int("error" in result)
    finally:
        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["serve", "status", "localize", "go", "stop"])
    parser.add_argument("point", nargs="?", choices=sorted(POINTS))
    args = parser.parse_args()
    if args.action == "serve":
        asyncio.run(serve())
    else:
        raise SystemExit(asyncio.run(operator(args)))
