import asyncio
import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from cloud.notebook import build
from voice.camera import Camera
from voice.guide import Guide
from voice.conversation import Conversation
from voice.__main__ import supervise


class GuideTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ai = AsyncMock()
        self.ai.language = "en-IN"
        self.ai.perception_needed.return_value = "none"
        self.ai.answer.return_value = "reply"
        self.camera = AsyncMock()
        self.nav = AsyncMock(return_value={"mode":"ready", "revision":"one", "current":"center", "last":None})
        self.guide = Guide(self.ai, self.camera, Path(__file__).resolve().parents[1] / "data", self.nav)

    async def ask(self, text):
        return await self.guide.reply([{"role":"user","content":text}])

    async def test_motion_requires_heard_prompt_and_fresh_confirmation(self):
        await self.ask("Go to P one.")
        await self.ask("Yes.")
        self.assertFalse(any(c.args == ("go",) for c in self.nav.await_args_list))
        self.assertIn("p2", await self.ask("Take me to point 2"))
        self.guide.delivered()
        self.assertIsNone(await self.ask("Yes"))
        self.nav.assert_awaited_with("go", point="p2", revision="one")

    async def test_negation_questions_and_changed_position_cannot_dispatch(self):
        for text in ["Don't go to p2", "What is at p1?", "go to p1 and p2"]:
            await self.ask(text)
        await self.ask("पी वन पर चलो")
        self.guide.delivered()
        self.nav.return_value["revision"] = "two"
        self.assertIn("expired", await self.ask("हाँ"))
        self.assertFalse(any(c.args == ("go",) for c in self.nav.await_args_list))

    async def test_context_and_offline_vision(self):
        await self.ask("How does this exhibit work?")
        self.camera.observe.assert_not_called()
        ctx = self.ai.answer.await_args.args[1]
        self.assertEqual(ctx["current_checkpoint"], "center")
        self.assertEqual(len(ctx["exhibits"]), 8)
        self.ai.perception_needed.return_value = "scene"
        self.camera.observe.side_effect = TimeoutError
        await self.ask("What am I holding?")
        self.assertEqual(self.ai.answer.await_args.args[1]["observation"], {"unavailable":True})

    async def test_face_context(self):
        self.ai.perception_needed.return_value = "face"
        self.camera.observe.return_value = {"visitor":"example", "context":"curator"}
        await self.ask("Who is here?")
        self.assertEqual(self.ai.answer.await_args.args[1]["observation"]["context"], "curator")

    async def test_spoken_confirmation_path(self):
        conversation = Conversation(self.ai, AsyncMock(), guide=self.guide)
        self.addAsyncCleanup(conversation.close)
        for transcript in ["Go to p4", "yes"]:
            self.ai.transcribe.return_value = transcript
            await conversation.onset()
            await conversation.submit(b"sample")
            await conversation.candidate
            await conversation.reply
        self.nav.assert_awaited_with("go", point="p4", revision="one")
        conversation.play.assert_awaited_once()

    async def test_resolve_exhibit_description_then_confirm(self):
        self.ai.destination.return_value = "p3"
        self.assertIn("p3", await self.ask("Take me to the robotics exhibit"))
        self.assertFalse(any(c.args == ("go",) for c in self.nav.await_args_list))

    async def test_sleep_in_transit_and_resume_on_arrival(self):
        conversation = Conversation(self.ai, AsyncMock(), guide=self.guide)
        listening = asyncio.Event()
        paused = asyncio.Event()
        arrived = asyncio.Event()
        state = dict(mode="ready", revision="a", outcome="localized", current="center")

        async def capture(_):
            listening.set()
            try:
                await asyncio.Event().wait()
            finally:
                paused.set()

        async def acknowledge(_, guide, point):
            self.assertEqual(point, "p2")
            arrived.set()

        with tempfile.TemporaryDirectory() as folder, \
             patch("voice.__main__.HEARTBEAT", Path(folder)/"health"), \
             patch("voice.__main__.listen", capture), \
             patch("voice.__main__.arrival", acknowledge), \
             patch("voice.__main__.request", new=AsyncMock(side_effect=lambda _: dict(state))):
            task = asyncio.create_task(supervise(conversation, self.guide))
            try:
                await asyncio.wait_for(listening.wait(), 3)
                state.update(mode="moving", revision="b", current=None)
                await asyncio.wait_for(paused.wait(), 3)
                await asyncio.sleep(0.05)
                self.camera.close.assert_awaited_once()
                state.update(mode="ready", outcome="arrived", revision="c", current="p2")
                await asyncio.wait_for(arrived.wait(), 3)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_wrong_endpoint_receives_no_frame_or_secret(self):
        requests = []
        def handle(req):
            requests.append(req)
            return httpx.Response(200, text="wrong")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with patch.dict("os.environ", {"VISION_URL":"https://example.test", "VISION_TOKEN":"a"*40}):
                camera = Camera(client)
            camera.sample = AsyncMock()
            with self.assertRaises(ValueError):
                await camera.observe("scene")
            camera.sample.assert_not_called()
            self.assertEqual(len(requests), 1)
            self.assertNotIn("Authorization", requests[0].headers)

    async def test_authenticated_frame_upload(self):
        token = "a"*40
        def handle(req):
            if req.url.path == "/identity":
                nonce = req.url.params["challenge"]
                return httpx.Response(200, text=hmac.new(token.encode(), nonce.encode(), hashlib.sha256).hexdigest())
            self.assertEqual(req.headers["Authorization"], "Bearer "+token)
            return httpx.Response(200, json={"description":"A red object"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with patch.dict("os.environ", {"VISION_URL":"https://example.test", "VISION_TOKEN":token}):
                camera = Camera(client)
            camera.sample = AsyncMock(return_value={"image":"image-bytes"})
            self.assertEqual(await camera.observe("scene"), {"current_scene":"A red object"})

    def test_notebook_bundle_contains_only_deployable_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            build(path)
            self.assertEqual({p.name for p in path.iterdir()}, {"vision.ipynb","kernel-metadata.json"})
            source = "".join(json.loads((path/"vision.ipynb").read_text())["cells"][0]["source"])
            compile(source, "vision.ipynb", "exec")
