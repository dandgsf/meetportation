"""Transmissão local de JPEG para a extensão pareada do Google Meet."""
from __future__ import annotations

import asyncio
import hmac
import re
import secrets
import threading
from typing import Optional

import cv2
import numpy as np


class WebSocketSink:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765, quality: int = 80,
                 max_width: int = 1280, fps: float = 30):
        import websockets

        if host != "127.0.0.1":
            raise ValueError("A extensão requer um endereço de loopback.")
        self._ws = websockets
        self.host, self.port, self.quality, self.max_width = host, port, quality, max_width
        self.frame_interval = 1.0 / fps
        self.pairing_code = secrets.token_urlsafe(24)
        self.clients: set = set()
        self._latest: Optional[bytes] = None
        self._loop = asyncio.new_event_loop()
        self._closed = asyncio.Event()
        self._ready = threading.Event()
        self._startup_error: Optional[Exception] = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._startup_error:
            raise self._startup_error
        print(f"[saída] WebSocket ws://{host}:{self.port} — pareie a extensão na aba do Meet.")

    def _run(self):
        try:
            self._loop.run_until_complete(self._main())
        except Exception as exc:
            self._startup_error = exc
        finally:
            self._ready.set()
            self._loop.close()

    async def _main(self):
        async with self._ws.serve(self._handler, self.host, self.port, max_size=128, max_queue=1) as server:
            self.port = server.sockets[0].getsockname()[1]
            self._ready.set()
            await self._closed.wait()

    async def _handler(self, ws):
        try:
            # websockets 12/13 exposes request_headers, newer versions expose request.headers.
            request = getattr(ws, "request", None)
            headers = request.headers if request is not None else ws.request_headers
            origins = headers.get_all("Origin")
            if len(origins) != 1 or not re.fullmatch(r"chrome-extension://[a-p]{32}", origins[0]):
                await ws.close(code=1008)
                return
            code = await asyncio.wait_for(ws.recv(), timeout=5)
            if not isinstance(code, str) or not code.isascii() or not hmac.compare_digest(code, self.pairing_code):
                await ws.close(code=1008)
                return
            await ws.send("ok")
            self.clients.add(ws)
            if self._latest:
                await ws.send(self._latest)
            await ws.wait_closed()
        except (asyncio.TimeoutError, self._ws.exceptions.ConnectionClosed):
            pass
        finally:
            self.clients.discard(ws)

    async def _broadcast(self, data: bytes):
        for client in list(self.clients):
            try:
                await client.send(data)
            except self._ws.exceptions.ConnectionClosed:
                self.clients.discard(client)

    def send(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        if w > self.max_width:
            frame = cv2.resize(frame, (self.max_width, int(h * self.max_width / w)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
        if ok:
            self._latest = buf.tobytes()
            if self.clients:
                asyncio.run_coroutine_threadsafe(self._broadcast(self._latest), self._loop)

    def wait(self):
        pass

    def close(self):
        self._loop.call_soon_threadsafe(self._closed.set)
        self._thread.join()
