"""Privacidade do transporte local com clientes e imagem sintéticos."""
import asyncio
import unittest

import cv2
import numpy as np
import websockets
from websockets.exceptions import ConnectionClosed

from meetportation.wsserver import WebSocketSink

ORIGIN = "chrome-extension://" + "a" * 32


class StreamTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sink = WebSocketSink(port=0)
        self.addCleanup(self.sink.close)
        self.url = f"ws://127.0.0.1:{self.sink.port}"
        self.frame = np.full((16, 16, 3), 90, np.uint8)
        self.sink.send(self.frame)

    async def test_only_paired_client_gets_cached_and_live_video(self):
        async with websockets.connect(self.url, origin=ORIGIN) as ws:
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(ws.recv(), 0.15)
            self.sink.send(self.frame)
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(ws.recv(), 0.15)
            await ws.send(self.sink.pairing_code)
            self.assertEqual(await ws.recv(), "ok")
            for value in (90, 180):
                if value == 180:
                    self.sink.send(self.frame * 2)
                data = await asyncio.wait_for(ws.recv(), 2)
                image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                self.assertEqual(round(image.mean()), value)

    async def test_rejects_invalid_proof_or_origin_before_any_video(self):
        for origin, code in [(ORIGIN, "wrong"), (ORIGIN, b"bytes"), (ORIGIN, "ç"),
                             ("https://meet.google.com", None), (None, None)]:
            with self.subTest(origin=origin):
                async with websockets.connect(self.url, origin=origin) as ws:
                    if code is not None:
                        await ws.send(code)
                    with self.assertRaises(ConnectionClosed) as closed:
                        await asyncio.wait_for(ws.recv(), 2)
                    self.assertEqual(closed.exception.rcvd.code, 1008)

    def test_session_codes_are_unique_and_bind_is_local(self):
        other = WebSocketSink(port=0)
        self.addCleanup(other.close)
        self.assertNotEqual(self.sink.pairing_code, other.pairing_code)
        with self.assertRaises(ValueError):
            WebSocketSink(host="0.0.0.0")
