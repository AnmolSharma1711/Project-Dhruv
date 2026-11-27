import asyncio
import logging
import os
import signal
import time
from contextlib import aclosing
from pathlib import Path

import httpx

from . import audio, pulse
from .conversation import Conversation
from .providers import Providers
from .turns import Segmenter
from .camera import Camera
from .guide import Guide
from .navigation import request

HEARTBEAT = Path("/tmp/brain-capture")


async def listen(conversation):
    import webrtcvad
    vad = webrtcvad.Vad(int(os.getenv("VAD_MODE", "2")))
    turns = Segmenter(onset=int(os.getenv("ONSET_FRAMES", "6")),
                      silence=int(os.getenv("END_SILENCE_FRAMES", "30")))
    next_heartbeat = 0
    async with aclosing(audio.frames()) as stream:
        async for frame in stream:
            now = time.monotonic()
            if now >= next_heartbeat:
                if next_heartbeat == 0:
                    logging.info("capture ready")
                HEARTBEAT.touch()
                next_heartbeat = now + 5
            event, pcm = turns.feed(frame, vad.is_speech(frame, 16000))
            if event == "onset":
                await conversation.onset()
            elif event == "turn":
                logging.info("turn captured (%d ms)", len(pcm) // 32)
                await conversation.submit(pcm)
            elif event == "too_long":
                logging.warning("speech exceeded turn limit; waiting for silence")


async def arrival(conversation, guide, point):
    try:
        text = guide.say(f"We have reached {point}.", f"हम {point} पहुँच गए हैं।")
        facts = guide.catalog[point]["facts"]
        if facts:
            try:
                async with asyncio.timeout(12):
                    text = await guide.providers.answer(
                        [{"role": "user", "content": "Announce the confirmed arrival and introduce this exhibit."}],
                        {"current_checkpoint": point, "exhibit_facts": facts})
            except Exception:
                logging.warning("Arrival introduction unavailable")
        async with asyncio.timeout(20):
            pcm = await guide.providers.synthesize(text)
        await conversation.play(pcm)
        conversation.history.append({"role": "assistant", "content": text})
        conversation.last_activity = time.monotonic()
    except Exception as exc:
        conversation.report("arrival", exc)


async def supervise(conversation, guide):
    capture = None
    previous = None
    revision = None
    try:
        while True:
            try:
                state = await request("status")
            except (OSError, ValueError, TimeoutError):
                state = {"mode": "disconnected"}
            mode = state["mode"]
            if mode != previous:
                logging.info("Navigation state: %s", mode)
            if mode in {"ready", "unlocalized"}:
                if capture is None:
                    capture = asyncio.create_task(listen(conversation))
                elif capture.done():
                    await capture  # propagate capture failure for Docker restart
                    raise RuntimeError("Capture ended unexpectedly")
                if revision and revision != state["revision"] and state["outcome"] == "arrived":
                    await conversation.stop(conversation.reply)
                    conversation.reply = asyncio.create_task(arrival(conversation, guide, state["current"]))
            else:
                if capture is not None:
                    await conversation.stop(capture)
                    capture = None
                    await conversation.stop(conversation.candidate)
                    await conversation.stop(conversation.reply)
                    guide.pending = None
                    await guide.camera.close()
                if mode == "disconnected":
                    HEARTBEAT.unlink(missing_ok=True)
                else:
                    HEARTBEAT.touch()
            previous = mode
            revision = state.get("revision", revision)
            await asyncio.sleep(0.5)
    finally:
        await conversation.stop(capture)
        await conversation.close()
        await guide.camera.close()


async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5), trust_env=False) as client:
        providers = Providers(client)
        pulse.configure()
        cues = [word.strip() for word in os.getenv("ADDRESS_CUES", "").split(",") if word.strip()]
        guide = Guide(providers, Camera(client), Path(os.getenv("GUIDE_DATA", "/app/data")))
        conversation = Conversation(providers, audio.play, cues, guide=guide)
        task = asyncio.create_task(supervise(conversation, guide))
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, task.cancel)
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            await conversation.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(main())
