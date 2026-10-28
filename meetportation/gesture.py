"""Reconhecimento do gesto do Teletransporte (dois dedos na testa).

Lógica 100% geométrica sobre os 21 landmarks da mão (MediaPipe) + a caixa/keypoints
do rosto. Não depende do MediaPipe em si, então é testável com landmarks sintéticos.

Landmarks da mão (MediaPipe): 0 punho | 1-4 polegar | 5-8 indicador | 9-12 médio
13-16 anelar | 17-20 mínimo. Em cada dedo: MCP, PIP, DIP, TIP.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple

Point = Tuple[float, float]

WRIST = 0
INDEX = (5, 6, 7, 8)
MIDDLE = (9, 10, 11, 12)
RING = (13, 14, 15, 16)
PINKY = (17, 18, 19, 20)


def _d(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _mid(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


@dataclass
class Face:
    """Rosto em pixels da imagem cheia (BlazeFace: olhos, nariz, boca, orelhas)."""
    x: float
    y: float
    w: float
    h: float
    right_eye: Point
    left_eye: Point
    nose: Point

    def forehead(self, k: float = 1.35) -> Point:
        """Ponto da testa: prolonga o vetor nariz→olhos acima dos olhos.

        Usar o vetor (em vez de "topo da bbox") mantém o ponto correto com a
        cabeça inclinada.
        """
        eyes = _mid(self.right_eye, self.left_eye)
        return (eyes[0] + (eyes[0] - self.nose[0]) * k,
                eyes[1] + (eyes[1] - self.nose[1]) * k)

    @property
    def size(self) -> float:
        # distância entre olhos é mais estável que a bbox; escala ~2.4x para "largura de rosto"
        return max(_d(self.right_eye, self.left_eye) * 2.4, 1.0)


@dataclass
class GestureReading:
    score: float = 0.0            # 0..1 (1 = gesto perfeito)
    pose_ok: bool = False         # dois dedos esticados e juntos, anelar/mínimo dobrados
    near_forehead: bool = False
    distance_ratio: float = math.inf  # distância pontas→testa / tamanho do rosto
    tip: Optional[Point] = None
    forehead: Optional[Point] = None
    reasons: list = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.pose_ok and self.near_forehead


class GestureClassifier:
    def __init__(self,
                 forehead_radius: float = 0.60,
                 extend_ratio: float = 1.10,
                 curl_ratio: float = 1.02,
                 together_ratio: float = 0.85):
        self.forehead_radius = forehead_radius   # raio aceito em "larguras de rosto"
        self.extend_ratio = extend_ratio         # ponta mais longe do punho que o PIP
        self.curl_ratio = curl_ratio             # ponta mais perto do punho que o PIP
        self.together_ratio = together_ratio     # pontas indicador/médio juntas (x largura da palma)

    # ---- dedos ---------------------------------------------------------
    def _extended(self, lm: Sequence[Point], f) -> bool:
        w = lm[WRIST]
        return _d(w, lm[f[3]]) > _d(w, lm[f[1]]) * self.extend_ratio

    def _curled(self, lm: Sequence[Point], f) -> bool:
        w = lm[WRIST]
        return _d(w, lm[f[3]]) < _d(w, lm[f[1]]) * self.curl_ratio

    def pose(self, lm: Sequence[Point]) -> Tuple[bool, list]:
        reasons = []
        if not self._extended(lm, INDEX):
            reasons.append("indicador dobrado")
        if not self._extended(lm, MIDDLE):
            reasons.append("médio dobrado")
        if not self._curled(lm, RING):
            reasons.append("anelar esticado")
        if not self._curled(lm, PINKY):
            reasons.append("mínimo esticado")
        palm = max(_d(lm[INDEX[0]], lm[PINKY[0]]), 1.0)
        if _d(lm[INDEX[3]], lm[MIDDLE[3]]) > palm * self.together_ratio:
            reasons.append("dedos separados")
        return (not reasons), reasons

    # ---- leitura completa ---------------------------------------------
    def read_hand(self, lm: Sequence[Point], face: Optional[Face]) -> GestureReading:
        r = GestureReading()
        r.pose_ok, r.reasons = self.pose(lm)
        r.tip = _mid(lm[INDEX[3]], lm[MIDDLE[3]])
        if face is None:
            r.reasons.append("sem rosto")
            r.score = 0.4 if r.pose_ok else 0.0
            return r
        r.forehead = face.forehead()
        r.distance_ratio = _d(r.tip, r.forehead) / face.size
        r.near_forehead = r.distance_ratio <= self.forehead_radius
        if not r.near_forehead:
            r.reasons.append("longe da testa")
        prox = max(0.0, 1.0 - r.distance_ratio / (self.forehead_radius * 2))
        r.score = (0.5 if r.pose_ok else 0.0) + 0.5 * prox
        return r

    def evaluate(self, hands: Sequence[Sequence[Point]], faces: Sequence[Face]) -> GestureReading:
        """Melhor leitura entre todas as mãos, usando o maior rosto (quem está na câmera)."""
        face = max(faces, key=lambda f: f.w * f.h) if faces else None
        best = GestureReading(reasons=["sem mão"])
        for lm in hands:
            if len(lm) < 21:
                continue
            r = self.read_hand(lm, face)
            if (r.active, r.score) > (best.active, best.score):
                best = r
        return best


class Trigger:
    """Debounce: dispara 1x quando o gesto é sustentado; rearma só depois de soltar.

    Evita disparo duplo (sumir e voltar na mesma "pose") e falso positivo de 1 frame.
    """

    def __init__(self, hold_frames: int = 5, release_frames: int = 4, cooldown_s: float = 1.0):
        self.hold_frames = hold_frames
        self.release_frames = release_frames
        self.cooldown_s = cooldown_s
        self._on = 0
        self._off = 0
        self._armed = True
        self._last_fire = -math.inf

    @property
    def progress(self) -> float:
        return min(1.0, self._on / max(self.hold_frames, 1)) if self._armed else 0.0

    def update(self, active: bool, now: float) -> bool:
        if active:
            self._on += 1
            self._off = 0
        else:
            self._off += 1
            self._on = 0
            if self._off >= self.release_frames:
                self._armed = True
        if (self._armed and self._on >= self.hold_frames
                and now - self._last_fire >= self.cooldown_s):
            self._armed = False
            self._on = 0
            self._last_fire = now
            return True
        return False
