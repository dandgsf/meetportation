"""Saída sem driver: transmite os frames (JPEG) por WebSocket local para a extensão do
Chrome, que troca a câmera dentro da aba do Google Meet. Não precisa de OBS.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Optional, Set

import cv2
import numpy as np


class WebSocketSink:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765, quality: int = 80,
                 max_width: int = 1280, fps: float = 30):
        import websockets  # pip install websockets

        self._ws = websockets
        self.host, self.port, self.quality, self.max_width = host, port, quality, max_width
        self.frame_interval = 1.0 / fps
        self.clients: Set = set()
        self._latest: Optional[bytes] = None
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(5)
        print(f"[saída] WebSocket ws://{host}:{port} — instale a extensão e abra o Meet")

    # -- loop asyncio em thread própria --------------------------------
    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main())

    async def _main(self):
        async with self._ws.serve(self._handler, self.host, self.port, max_size=None):
            self._ready.set()
            await asyncio.Future()  # roda até o processo fechar

    async def _handler(self, ws):
        self.clients.add(ws)
        try:
            if self._latest:
                await ws.send(self._latest)
            async for _ in ws:      # cliente não manda nada; só mantém aberto
                pass
        except Exception:
            pass
        finally:
            self.clients.discard(ws)

    async def _broadcast(self, data: bytes):
        dead = []
        for c in list(self.clients):
            try:
                await c.send(data)
            except Exception:
                dead.append(c)
        for c in dead:
            self.clients.discard(c)

    # -- interface de sink ---------------------------------------------
    def send(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        if w > self.max_width:
            frame = cv2.resize(frame, (self.max_width, int(h * self.max_width / w)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
        if not ok:
            return
        self._latest = buf.tobytes()
        if self.clients:
            asyncio.run_coroutine_threadsafe(self._broadcast(self._latest), self._loop)

    def wait(self):
        pass

    def close(self):
        self._loop.call_soon_threadsafe(self._loop.stop)
