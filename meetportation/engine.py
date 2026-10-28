"""Motor do Meetportation: recebe frame + observação, devolve o frame de saída.

Sem câmera, sem janela, sem MediaPipe aqui dentro — dá pra testar com dados sintéticos.

Estados:  PRESENT --gesto--> VANISHING --(efeito)--> AWAY --gesto--> APPEARING --> PRESENT
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from .detector import Observation
from .fx import Plate, TeleportFX, diff_mask, refine_mask
from .gesture import GestureClassifier, GestureReading, Trigger

PRESENT, VANISHING, AWAY, APPEARING = "present", "vanishing", "away", "appearing"


@dataclass
class StepInfo:
    state: str
    reading: GestureReading
    fired: bool
    hold_progress: float


class Meetporter:
    def __init__(self, plate: Plate, classifier: Optional[GestureClassifier] = None,
                 trigger: Optional[Trigger] = None, fx: Optional[TeleportFX] = None,
                 away_mode: str = "static", on_teleport: Optional[Callable[[str], None]] = None):
        self.plate = plate
        self.classifier = classifier or GestureClassifier()
        self.trigger = trigger or Trigger()
        self.fx = fx or TeleportFX()
        self.away_mode = away_mode        # "static" (plate + ruído) | "live" (segmentação)
        self.on_teleport = on_teleport    # callback p/ som: recebe "out" ou "in"
        self.state = PRESENT
        self._k = 0

    # -- quanto a camada de visão precisa trabalhar neste frame -----------
    @property
    def needs_mask(self) -> bool:
        return self.state in (VANISHING, APPEARING) or (self.state == AWAY and self.away_mode == "live")

    def toggle(self):
        """Disparo manual (atalho de teclado)."""
        self._start_transition()

    def _start_transition(self):
        if self.state == PRESENT:
            self.state, self._k = VANISHING, 0
            if self.on_teleport:
                self.on_teleport("out")
        elif self.state == AWAY:
            self.state, self._k = APPEARING, 0
            if self.on_teleport:
                self.on_teleport("in")

    def _mask(self, frame: np.ndarray, obs: Observation) -> np.ndarray:
        if obs.person_mask is not None:
            return refine_mask(obs.person_mask, dilate_px=11, feather_px=11)
        return diff_mask(frame, self.plate.image)

    def _away_frame(self, frame: np.ndarray, obs: Observation) -> np.ndarray:
        if self.away_mode == "live" and obs.person_mask is not None:
            m = refine_mask(obs.person_mask, dilate_px=25, feather_px=21)
            # fundo AO VIVO onde não tem pessoa, plate onde tem (relógio, luz, janela seguem reais)
            self.plate.blend_update(frame, (m < 0.02).astype(np.float32), rate=0.03)
            a = m[..., None]
            return (frame.astype(np.float32) * (1 - a) + self.plate.image.astype(np.float32) * a).astype(np.uint8)
        return self.plate.frame()

    def step(self, frame: np.ndarray, obs: Observation, now: float):
        reading = self.classifier.evaluate(obs.hands, obs.faces)
        fired = False
        # O debounce sempre vê o gesto REAL (inclusive durante o efeito): assim ele só
        # rearma quando a mão realmente sai da testa. Alimentar "False" durante o efeito
        # rearmava o gatilho e um gesto segurado fazia sumir e voltar em sequência.
        fired = self.trigger.update(reading.active, now)
        if self.state in (PRESENT, AWAY):
            if fired:
                self._start_transition()
        else:
            fired = False                     # disparo ignorado durante o efeito

        if self.state == PRESENT:
            out = frame
        elif self.state == AWAY:
            out = self._away_frame(frame, obs)
        else:
            self._k += 1
            t = self._k / self.fx.frames
            if self.state == APPEARING:
                t = 1.0 - t
            bg = self.plate.frame()
            out = self.fx.render(frame, bg, self._mask(frame, obs), t)
            if self._k >= self.fx.frames:
                self.state = AWAY if self.state == VANISHING else PRESENT
        return out, StepInfo(self.state, reading, fired, self.trigger.progress)
