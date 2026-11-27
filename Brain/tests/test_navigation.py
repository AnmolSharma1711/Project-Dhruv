import asyncio
import json
from pathlib import Path
import os
import sys
import tempfile
import unittest

from host.bridge import Navigation, handle


class NavigationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "state.sqlite"
        self.robot = Navigation(self.path, "boot", (sys.executable, "-c", "import sys;sys.exit(0)"))
        self.addAsyncCleanup(self.robot.close)

    def localize(self, point="center"):
        return self.robot.dispatch({"action": "localize", "point": point}, admin=True)

    def go(self, point, revision=None):
        return self.robot.dispatch({"action": "go", "point": point,
                                    "revision": revision or self.robot.state["revision"]})

    async def test_real_child_and_replay(self):
        with self.assertRaises(ValueError):
            self.go("p1")
        start = self.localize()
        moving = self.go("p1")
        self.assertIsNone(moving["current"])
        with self.assertRaises(ValueError):
            self.go("p2")
        await self.robot.job
        self.assertEqual((self.robot.state["current"], self.robot.state["last"]), ("p1", "p1"))
        with self.assertRaises(ValueError):
            self.go("p2", start["revision"])
        restored = Navigation(self.path, "boot")
        self.addAsyncCleanup(restored.close)
        self.assertEqual(restored.state["current"], "p1")

    async def test_failed_trip_blocks_motion_until_operator_relocalizes(self):
        self.localize()
        self.go("p1")
        await self.robot.job
        self.robot.command = (sys.executable, "-c", "raise SystemExit(1)")
        self.go("p2")
        await self.robot.job
        self.assertEqual(self.robot.state["mode"], "uncertain")
        self.assertIsNone(self.robot.state["current"])
        self.assertEqual(self.robot.state["last"], "p1")
        with self.assertRaises(ValueError):
            self.go("home")
        self.localize("center")
        self.assertEqual(self.robot.state["last"], "p1")

    async def test_unclean_restart_and_host_reboot(self):
        self.robot.update(mode="moving", target="p3", last="p1", current=None)
        restored = Navigation(self.path, "boot")
        self.addAsyncCleanup(restored.close)
        self.assertEqual(restored.state["mode"], "uncertain")
        restored.dispatch({"action": "localize", "point": "home"}, admin=True)
        reboot = Navigation(self.path, "next-boot")
        self.addAsyncCleanup(reboot.close)
        self.assertEqual((reboot.state["mode"], reboot.state["current"], reboot.state["last"]),
                         ("unlocalized", None, "p1"))

    async def test_disallow_admin_calls_from_container(self):
        with self.assertRaises(ValueError):
            self.robot.dispatch({"action": "localize", "point": "center"})
        with self.assertRaises(ValueError):
            self.robot.dispatch({"action": "stop"})
        with self.assertRaises(ValueError):
            self.go("p9")

    @unittest.skipUnless(os.name == "posix", "Unix domain socket and ROS process group")
    async def test_socket_and_operator_stop(self):
        sock = self.path.parent / "nav.sock"
        server = await asyncio.start_unix_server(lambda r,w: handle(self.robot, r,w, False), str(sock))
        async with server:
            reader, writer = await asyncio.open_unix_connection(str(sock))
            writer.write(b'{"action":"status"}\n')
            await writer.drain()
            self.assertEqual(json.loads(await reader.readline())["mode"], "unlocalized")
            writer.close()
            await writer.wait_closed()
            self.localize()
            self.robot.command = ("/bin/sh", "-c", "exec sleep 60")
            self.go("home")
            self.robot.dispatch({"action": "stop"}, admin=True)
            await asyncio.wait_for(self.robot.job, 12)
            self.assertEqual(self.robot.state["mode"], "uncertain")
