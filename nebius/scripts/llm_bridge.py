"""Forward the Docker bridge address to the local llama-server (127.0.0.1 only).

llama-server listens on 127.0.0.1 so the GPU is never reachable from the network. Containers
of `make up` reach the host at host.docker.internal, which is the Docker bridge address
(docker0, e.g. 172.17.0.1): this forwarder listens there and passes connections to
127.0.0.1, so the API container can use the local model without exposing it to the LAN.

    python scripts/llm_bridge.py 172.17.0.1 8080
"""

from __future__ import annotations

import asyncio
import sys


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        writer.close()


async def _handle(client_r: asyncio.StreamReader, client_w: asyncio.StreamWriter) -> None:
    port = int(sys.argv[2])
    try:
        up_r, up_w = await asyncio.open_connection("127.0.0.1", port)
    except OSError:
        client_w.close()
        return
    await asyncio.gather(_pipe(client_r, up_w), _pipe(up_r, client_w))


async def main() -> None:
    host, port = sys.argv[1], int(sys.argv[2])
    server = await asyncio.start_server(_handle, host, port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
