"""Clean plate (fundo vazio), máscara de pessoa e o efeito visual do teletransporte."""
from __future__ import annotations

import os
from typing import List, Optional

import cv2
import numpy as np


# --------------------------------------------------------------------------
# Clean plate
# --------------------------------------------------------------------------
class Plate:
    """Foto do cenário vazio. É o que a reunião vê enquanto você está "teletransportado".

    - captura = mediana de N frames (remove ruído e qualquer coisa passando rápido)
    - estima o ruído do sensor para "dar vida" ao frame parado (um frame 100% estático
      denuncia a farsa; o ruído real da câmera não)
    """

    def __init__(self, image: np.ndarray, noise_sigma: float = 1.5):
        self.image = image
        self.noise_sigma = float(noise_sigma)
        self._noise: List[np.ndarray] = []
        self._i = 0
        self._build_noise()

    # -- construção ---------------------------------------------------------
    @classmethod
    def from_frames(cls, frames: List[np.ndarray]) -> "Plate":
        stack = np.stack(frames).astype(np.float32)
        image = np.median(stack, axis=0).astype(np.uint8)
        # ruído temporal: desvio padrão por pixel, mediana global (robusta a movimento)
        sigma = float(np.median(stack.std(axis=0))) if len(frames) > 2 else 1.5
        return cls(image, noise_sigma=min(max(sigma, 0.6), 6.0))

    def _build_noise(self, n: int = 8):
        if self.noise_sigma <= 0:
            self._noise = []
            return
        h, w = self.image.shape[:2]
        rng = np.random.default_rng(7)
        # ruído em meia resolução + upscale = granulação parecida com a de webcam
        self._noise = [
            cv2.resize(rng.normal(0, self.noise_sigma, (h // 2, w // 2, 3)).astype(np.float32),
                       (w, h), interpolation=cv2.INTER_LINEAR)
            for _ in range(n)
        ]

    # -- uso ----------------------------------------------------------------
    def frame(self) -> np.ndarray:
        """Plate + ruído rotativo (parece vídeo ao vivo, não print)."""
        if not self._noise:
            return self.image.copy()
        n = self._noise[self._i % len(self._noise)]
        self._i += 1
        return np.clip(self.image.astype(np.float32) + n, 0, 255).astype(np.uint8)

    def blend_update(self, frame: np.ndarray, bg_mask: np.ndarray, rate: float = 0.05):
        """Atualiza o plate só onde é fundo com certeza (acompanha luz do dia mudando)."""
        a = (bg_mask[..., None] * rate).astype(np.float32)
        self.image = (self.image.astype(np.float32) * (1 - a) + frame.astype(np.float32) * a).astype(np.uint8)

    def matches(self, frame: np.ndarray) -> bool:
        return self.image.shape == frame.shape

    def save(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        cv2.imwrite(path, self.image)
        with open(path + ".sigma", "w", encoding="utf-8") as fh:
            fh.write(str(self.noise_sigma))

    @classmethod
    def load(cls, path: str) -> Optional["Plate"]:
        if not os.path.exists(path):
            return None
        img = cv2.imread(path)
        if img is None:
            return None
        sigma = 1.5
        try:
            with open(path + ".sigma", encoding="utf-8") as fh:
                sigma = float(fh.read().strip())
        except (OSError, ValueError):
            pass
        return cls(img, sigma)


# --------------------------------------------------------------------------
# Máscara de pessoa
# --------------------------------------------------------------------------
def diff_mask(frame: np.ndarray, plate: np.ndarray, thresh: float = 26.0) -> np.ndarray:
    """Máscara (0..1) da pessoa por diferença contra o clean plate.

    Fallback quando o segmentador de IA não está disponível. Funciona bem porque o
    fundo é estático e a gente TEM o fundo exato — é chroma key sem tela verde.
    """
    a = cv2.GaussianBlur(frame, (5, 5), 0).astype(np.int16)
    b = cv2.GaussianBlur(plate, (5, 5), 0).astype(np.int16)
    d = np.abs(a - b).max(axis=2).astype(np.uint8)
    m = (d > thresh).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k, iterations=3)
    # mantém só os blobs grandes (pessoa), descarta ruído/sombras pequenas
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 1:
        min_area = 0.01 * m.size
        keep = np.zeros(n, np.uint8)
        keep[1:] = (stats[1:, cv2.CC_STAT_AREA] >= min_area).astype(np.uint8)
        m = (keep[lab] * 255).astype(np.uint8)
    return refine_mask(m.astype(np.float32) / 255.0)


def refine_mask(mask: np.ndarray, dilate_px: int = 9, feather_px: int = 9) -> np.ndarray:
    """Dilata (cobre cabelo/borda) e suaviza a borda da máscara."""
    m = mask.astype(np.float32)
    if dilate_px > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px, dilate_px))
        m = cv2.dilate(m, k)
    if feather_px > 0:
        f = feather_px | 1
        m = cv2.GaussianBlur(m, (f, f), 0)
    return np.clip(m, 0, 1)


# --------------------------------------------------------------------------
# Efeito do teletransporte
# --------------------------------------------------------------------------
class TeleportFX:
    """Some/aparece em ~0,3 s: tremulação, rastro horizontal, brilho ciano e flash.

    t=0 -> pessoa 100% visível | t=1 -> pessoa sumiu. "Aparecer" é o mesmo efeito
    com t indo de 1 para 0.
    """

    def __init__(self, frames: int = 9, streak_px: int = 70, flash: float = 0.22,
                 tint=(255, 245, 190)):  # BGR: branco-ciano
        self.frames = max(2, frames)
        self.streak_px = streak_px
        self.flash = flash
        self.tint = np.array(tint, np.float32)

    def _visibility(self, t: float) -> float:
        step = int(t * self.frames)
        flicker = 1.0 if step % 2 == 0 else 0.30   # pisca a cada frame
        return max(0.0, (1.0 - t) ** 0.8) * flicker

    def render(self, person_frame: np.ndarray, background: np.ndarray,
               mask: np.ndarray, t: float) -> np.ndarray:
        t = float(np.clip(t, 0.0, 1.0))
        if t <= 0.0:
            return person_frame.copy()
        if t >= 1.0:
            return background.copy()
        k = 1 + 2 * int(self.streak_px * t / 2)        # kernel ímpar, cresce com t
        person = cv2.blur(person_frame, (k, 1)).astype(np.float32)
        m = cv2.blur(mask.astype(np.float32), (k, 1))
        glow = 0.40 * t
        person = person * (1 - glow) + self.tint * glow
        alpha = (m * self._visibility(t))[..., None]
        out = background.astype(np.float32) * (1 - alpha) + person * alpha
        # flash curto no começo do efeito, concentrado ao redor da pessoa
        f = self.flash * max(0.0, 1.0 - t * 3.0)
        if f > 0:
            halo = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 25)[..., None]
            out = out + (255.0 - out) * f * np.clip(halo * 1.5, 0, 1)
        return np.clip(out, 0, 255).astype(np.uint8)
