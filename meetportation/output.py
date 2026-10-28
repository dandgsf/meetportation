"""Saídas: câmera virtual (Teams/Zoom/Meet enxergam como webcam) e gravação em MP4."""
from __future__ import annotations

from typing import List, Optional

import cv2
import numpy as np


class VirtualCamSink:
    """Publica os frames numa câmera virtual via pyvirtualcam.

    Windows/macOS: usa o driver "OBS Virtual Camera" (basta o OBS instalado; não precisa
    estar aberto). Linux: v4l2loopback.
    """

    def __init__(self, width: int, height: int, fps: float, backend: Optional[str] = None,
                 device: Optional[str] = None):
        import pyvirtualcam
        self.cam = pyvirtualcam.Camera(width, height, fps, fmt=pyvirtualcam.PixelFormat.BGR,
                                       backend=backend, device=device)
        print(f"[saída] câmera virtual ativa: {self.cam.device} ({width}x{height}@{fps:g})")

    def send(self, frame: np.ndarray):
        self.cam.send(np.ascontiguousarray(frame))

    def wait(self):
        self.cam.sleep_until_next_frame()

    def close(self):
        self.cam.close()


class RecorderSink:
    """Grava exatamente o que a reunião vê (ótimo pra virar Reels)."""

    def __init__(self, path: str, width: int, height: int, fps: float):
        self.w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        if not self.w.isOpened():
            raise RuntimeError(f"não consegui abrir {path} para gravação")
        print(f"[saída] gravando em {path}")

    def send(self, frame: np.ndarray):
        self.w.write(frame)

    def wait(self):
        pass

    def close(self):
        self.w.release()


class Sinks:
    def __init__(self, sinks: List):
        self.sinks = sinks

    def send(self, frame):
        for s in self.sinks:
            s.send(frame)

    def wait(self):
        # quem dita o ritmo é a câmera virtual, se houver
        for s in self.sinks:
            if isinstance(s, VirtualCamSink):
                s.wait()
                return

    def close(self):
        for s in self.sinks:
            s.close()
