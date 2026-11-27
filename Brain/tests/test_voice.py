import asyncio
import base64
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from voice.audio import process
from voice.conversation import Conversation
from voice.providers import Providers, speech_clips, wav
from voice.pulse import configure
from voice.turns import Segmenter


class SegmentationTests(unittest.TestCase):
    def test_short_noise_and_preroll(self):
        gate = Segmenter(onset=3, silence=2)
        events = [gate.feed(bytes([i]), value) for i, value in
                  enumerate([True, False, True, True, True, False, False])]
        self.assertEqual([event for event, _ in events if event], ["onset", "turn"])
        self.assertEqual(events[-1][1], bytes(range(7)))

    def test_overlong_speech_does_not_become_multiple_requests(self):
        gate = Segmenter(onset=2, silence=2, max_frames=20)
        events = [gate.feed(b"x", value)[0] for value in [True]*50 + [False]*2 + [True]*4 + [False]*2]
        self.assertEqual(list(filter(None, events)), ["onset", "too_long", "onset", "turn"])


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.providers = AsyncMock()
        self.providers.transcribe.return_value = "hello"
        self.providers.answer.return_value = "welcome"
        self.providers.synthesize.return_value = b"audio"
        self.play = AsyncMock()
        self.brain = Conversation(self.providers, self.play)
        self.addAsyncCleanup(self.brain.close)

    async def finish_turn(self):
        await self.brain.submit(b"pcm")
        await self.brain.candidate
        await self.brain.reply

    async def test_complete_and_expire_history(self):
        await self.finish_turn()
        self.assertEqual(len(self.brain.history), 2)
        self.brain.last_activity -= 181
        await self.finish_turn()
        self.assertEqual(len(self.brain.history), 2)

    async def check_interruption(self, stage):
        entered = asyncio.Event()

        async def pending(*args):
            entered.set()
            await asyncio.Event().wait()

        stage.side_effect = pending
        await self.brain.submit(b"pcm")
        await asyncio.wait_for(entered.wait(), 1)
        await self.brain.onset()
        self.assertFalse(any(msg["role"] == "assistant" for msg in self.brain.history))
        stage.side_effect = None
        await self.finish_turn()
        self.assertEqual(self.brain.history[-1]["content"], "welcome")

    async def test_cancel_transcription(self):
        await self.check_interruption(self.providers.transcribe)

    async def test_cancel_generation(self):
        await self.check_interruption(self.providers.answer)
        self.play.assert_awaited_once()

    async def test_cancel_synthesis(self):
        await self.check_interruption(self.providers.synthesize)
        self.play.assert_awaited_once()

    async def test_cancel_playback(self):
        await self.check_interruption(self.play)

    async def test_crowd_mode_ignores_unaddressed_speech(self):
        brain = Conversation(self.providers, self.play, ["Dhruv"])
        self.addAsyncCleanup(brain.close)
        await brain.submit(b"pcm")
        await brain.candidate
        self.providers.answer.assert_not_called()
        self.providers.transcribe.return_value = "Hello Dhruv!"
        await brain.submit(b"pcm")
        await brain.candidate
        await brain.reply
        self.play.assert_awaited_once()

    async def test_provider_failure_recovers(self):
        self.providers.synthesize.side_effect = TimeoutError()
        with self.assertLogs("brain", level="WARNING"):
            await self.finish_turn()
        self.play.assert_not_called()
        self.providers.synthesize.side_effect = None
        await self.finish_turn()
        self.play.assert_awaited_once()


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def test_long_turn_splits_without_losing_samples(self):
        pcm = b"\x14\0" * (16000 * 60)
        clips = list(speech_clips(pcm))
        self.assertEqual(len(clips), 3)
        self.assertEqual(b"".join(clips), pcm)
        self.assertTrue(all(len(clip) <= 27 * 32000 for clip in clips))

    async def test_http_contract_and_pcm(self):
        pcm = b"\0\0" * 320
        requests = []

        def handle(request):
            requests.append(request.url.path)
            if request.url.path == "/speech-to-text":
                self.assertIn(wav(pcm), request.content)
                self.assertEqual(request.headers["api-subscription-key"], "test-s")
                return httpx.Response(200, json={"transcript": "hello"})
            if request.url.path == "/text-to-speech":
                self.assertEqual(json.loads(request.content)["speech_sample_rate"], 16000)
                return httpx.Response(200, json={"audios": [base64.b64encode(wav(pcm)).decode()]})
            self.assertEqual(request.headers["api-key"], "test-a")
            return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

        env = {"AZURE_CHAT_URL": "https://test.openai.azure.com/openai/deployments/test/chat/completions",
               "AZURE_OPENAI_API_KEY": "test-a", "SARVAM_API_KEY": "test-s"}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with patch.dict(os.environ, env):
                api = Providers(client)
            self.assertEqual(await api.transcribe(pcm), "hello")
            self.assertEqual(await api.answer([{"role": "user", "content": "hello"}]), "hi")
            self.assertEqual(await api.synthesize("hi"), pcm)
            self.assertEqual(len(requests), 3)


class AudioRoutingTests(unittest.TestCase):
    @patch.dict(os.environ, {"MIC_SOURCE": "usb.input", "SPEAKER_SINK": "usb.output"})
    def test_reuse_only_paired_configured_devices(self):
        sources = {"usb.input": {}, "dhruv_aec_mic": {"owner_module": 5}}
        sinks = {"usb.output": {}, "dhruv_aec_speaker": {"owner_module": 5}}
        args = ("source_master=usb.input sink_master=usb.output source_name=dhruv_aec_mic "
                "sink_name=dhruv_aec_speaker aec_method=webrtc rate=16000 channels=1")
        modules = [{"index": 5, "name": "module-echo-cancel", "argument": args}]
        with patch("voice.pulse.devices", side_effect=lambda kind: sources if kind == "sources" else sinks), \
             patch("voice.pulse.pactl", return_value=json.dumps(modules)):
            configure()
            sinks["dhruv_aec_speaker"]["owner_module"] = 6
            with self.assertRaises(ValueError):
                configure()


class PlaybackProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_reaps_a_running_child(self):
        ready = asyncio.get_running_loop().create_future()

        async def run():
            async with process(sys.executable, "-c", "import time; time.sleep(60)") as child:
                ready.set_result(child)
                await asyncio.Event().wait()

        task = asyncio.create_task(run())
        child = await asyncio.wait_for(ready, 5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        self.assertIsNotNone(child.returncode)
