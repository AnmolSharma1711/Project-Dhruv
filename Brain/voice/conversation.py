import asyncio
import logging
import re
import time
from collections import deque

import httpx


log = logging.getLogger("brain")


class Conversation:
    def __init__(self, providers, play, cues=(), idle_seconds=180, guide=None):
        self.guide = guide
        self.providers = providers
        self.play = play
        self.cues = tuple(re.compile(r"(?<!\w)" + re.escape(cue) + r"(?!\w)", re.I)
                          for cue in cues)
        self.history = deque(maxlen=12)
        self.last_activity = 0
        self.idle_seconds = idle_seconds
        self.candidate = self.reply = None

    @staticmethod
    async def stop(task):
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def onset(self):
        await self.stop(self.candidate)
        if not self.cues:
            await self.stop(self.reply)
        log.info("speech onset")

    async def submit(self, pcm):
        await self.stop(self.candidate)
        self.candidate = asyncio.create_task(self.recognize(pcm))

    async def recognize(self, pcm):
        try:
            # Each upload is below the Sarvam REST duration limit.
            clip_budget = 1 + len(pcm) // (26 * 32000)
            async with asyncio.timeout(20 * clip_budget):
                text = await self.providers.transcribe(pcm)
            if not text or (self.cues and not any(pattern.search(text) for pattern in self.cues)):
                return
            await self.stop(self.reply)
            now = time.monotonic()
            if now - self.last_activity >= self.idle_seconds:
                self.history.clear()
            self.last_activity = now
            self.history.append({"role": "user", "content": text})
            self.reply = asyncio.create_task(self.respond())
        except Exception as error:
            self.report("transcription", error)

    async def respond(self):
        stage = "chat"
        try:
            async with asyncio.timeout(50):
                if self.guide:
                    reply = await self.guide.reply(list(self.history), self.cues)
                else:
                    reply = await self.providers.answer(list(self.history))
            if reply is None:
                return
            stage = "synthesis"
            async with asyncio.timeout(20):
                pcm = await self.providers.synthesize(reply)
            stage = "playback"
            log.info("playback started")
            await self.play(pcm)
            if self.guide:
                self.guide.delivered()
            self.history.append({"role": "assistant", "content": reply})
            self.last_activity = time.monotonic()
            log.info("playback completed")
        except asyncio.CancelledError:
            log.info("%s interrupted", stage)
            raise
        except Exception as error:
            self.report(stage, error)

    @staticmethod
    def report(stage, error):
        status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else "-"
        log.warning("%s failed (%s, HTTP %s); listening for the next turn",
                    stage, type(error).__name__, status)

    async def close(self):
        await self.stop(self.candidate)
        await self.stop(self.reply)
        self.history.clear()
