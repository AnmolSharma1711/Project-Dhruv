import asyncio
import json
import os

POINTS = frozenset(("center", "home", *(f"p{i}" for i in range(1, 7))))


async def request(action, socket=None, **fields):
    path = socket or os.getenv("NAV_SOCKET", "/run/dhruv/nav.sock")
    async with asyncio.timeout(3):
        reader, writer = await asyncio.open_unix_connection(path)
        try:
            writer.write(json.dumps({"action": action, **fields}).encode() + b"\n")
            await writer.drain()
            response = json.loads(await reader.readline())
            if "error" in response:
                raise ValueError(response["error"])
            return response
        finally:
            writer.close()
            await writer.wait_closed()
