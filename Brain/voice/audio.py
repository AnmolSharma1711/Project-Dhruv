import asyncio
from contextlib import asynccontextmanager


@asynccontextmanager
async def process(*args, **kwargs):
    # Keep ownership if a barge-in races with subprocess creation.
    spawn = asyncio.create_task(asyncio.create_subprocess_exec(*args, **kwargs))
    try:
        child = await asyncio.shield(spawn)
        yield child
    finally:
        child = await spawn
        if child.returncode is None:
            try:
                child.kill()
            except ProcessLookupError:
                pass
        if child.stdout is not None:
            await child.stdout.read()
        await child.wait()


FORMAT = ("--raw", "--format=s16le", "--channels=1", "--rate=16000", "--latency-msec=40")


async def frames():
    async with process("parec", "--device=dhruv_aec_mic", *FORMAT,
                       stdout=asyncio.subprocess.PIPE) as capture:
        while True:
            yield await asyncio.wait_for(capture.stdout.readexactly(640), timeout=5)


async def play(pcm):
    async with process("pacat", "--playback", "--device=dhruv_aec_speaker", *FORMAT,
                       stdin=asyncio.subprocess.PIPE) as player:
        await asyncio.wait_for(player.communicate(pcm), timeout=len(pcm) / 32000 + 5)
        if player.returncode:
            raise RuntimeError("PulseAudio playback failed")
