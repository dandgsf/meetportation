"""Efeito sonoro do teletransporte (Shunkan Idō / Instant Transmission).

Síntese original (sem áudio de terceiros) modelada no perfil do som do anime:
  1. "zip" que SOBE de tom muito rápido (sweep exponencial ~350 Hz → ~3,2 kHz em ~120 ms),
     com harmônicos e ring-modulation para dar o timbre metálico/brilhante;
  2. sopro de ar (ruído passa-banda que acompanha o sweep subindo);
  3. "cintilado" no final: micro-blips agudos (5–9 kHz) em cascata, como o brilho do efeito visual;
  4. cauda curta com eco/reverb leve.
Para usar outro som: --sound caminho/arquivo.wav  (ou substitua data/teleport.wav).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import wave

import numpy as np


def _env(t, attack, decay_rate):
    return np.minimum(t / max(attack, 1e-4), 1.0) * np.exp(-t * decay_rate)


def _bandpass_noise(n, sr, f_center, bw, rng):
    """Ruído branco filtrado numa banda que varia no tempo (f_center é um array)."""
    noise = rng.normal(0, 1, n)
    # filtro por FFT em blocos curtos para acompanhar a frequência variável
    out = np.zeros(n)
    block = 512
    win = np.hanning(block)
    for start in range(0, n - block, block // 2):
        seg = noise[start:start + block] * win
        spec = np.fft.rfft(seg)
        freqs = np.fft.rfftfreq(block, 1 / sr)
        fc = float(f_center[min(start + block // 2, n - 1)])
        mask = np.exp(-0.5 * ((freqs - fc) / bw) ** 2)
        out[start:start + block] += np.fft.irfft(spec * mask, block) * win
    return out


def synth_teleport_wav(path: str, sr: int = 44100, seconds: float = 0.62, variant: str = "anime") -> str:
    n = int(sr * seconds)
    t = np.arange(n) / sr
    rng = np.random.default_rng(7)

    # --- 1. zip ascendente (o "vwip") ----------------------------------------
    sweep_len = 0.13 if variant == "anime" else 0.18
    f0, f1 = 350.0, 3200.0
    prog = np.clip(t / sweep_len, 0, 1) ** 0.6              # começa lento, acelera
    freq = f0 * (f1 / f0) ** prog
    freq = np.where(t > sweep_len, f1 * np.exp(-(t - sweep_len) * 3.0), freq)  # cai suave no fim
    phase = 2 * np.pi * np.cumsum(freq) / sr
    zip_tone = (np.sin(phase) + 0.45 * np.sin(2 * phase) + 0.25 * np.sin(3 * phase + 0.5))
    ring = 1.0 + 0.55 * np.sin(2 * np.pi * 1900 * t)        # ring-mod: timbre metálico
    zip_tone = zip_tone * ring * _env(t, 0.004, 9.0)

    # --- 2. sopro de ar acompanhando o sweep ---------------------------------
    whoosh = _bandpass_noise(n, sr, freq * 1.3, 900.0, rng) * _env(t, 0.02, 10.0)

    # --- 3. cintilado final (sparkle) ----------------------------------------
    sparkle = np.zeros(n)
    for i in range(10):
        st = sweep_len + 0.02 + i * 0.022
        fr = rng.uniform(5000, 9000)
        m = t >= st
        sparkle[m] += np.sin(2 * np.pi * fr * (t[m] - st)) * np.exp(-(t[m] - st) * 90.0) * (0.9 - i * 0.06)

    # --- 4. transiente de ataque (o "v" do vwip) -----------------------------
    click = _bandpass_noise(n, sr, np.full(n, 2500.0), 1500.0, rng) * _env(t, 0.001, 140.0)

    sig = 0.60 * zip_tone + 0.28 * whoosh + 0.22 * sparkle + 0.35 * click

    # --- eco/reverb leve -----------------------------------------------------
    out = sig.copy()
    for delay_ms, gain in ((23, 0.30), (47, 0.18), (71, 0.10), (113, 0.05)):
        d = int(sr * delay_ms / 1000)
        out[d:] += sig[:-d] * gain
    out = out / max(np.abs(out).max(), 1e-6) * 0.9
    # fade-out
    fade = int(sr * 0.06)
    out[-fade:] *= np.linspace(1, 0, fade)

    pcm = (out * 32767).astype(np.int16)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


class SoundPlayer:
    """Toca um .wav sem bloquear o loop de vídeo."""

    def __init__(self, path: str | None, enabled: bool = True):
        self.path = path
        self.enabled = enabled and bool(path) and os.path.exists(path)
        self._cmd = None
        if self.enabled and not sys.platform.startswith("win"):
            for c in (["afplay"], ["paplay"], ["aplay", "-q"]):
                if shutil.which(c[0]):
                    self._cmd = c
                    break
            if self._cmd is None:
                self.enabled = False

    def play(self):
        if not self.enabled:
            return
        if sys.platform.startswith("win"):
            import winsound  # stdlib no Windows
            winsound.PlaySound(self.path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            threading.Thread(
                target=subprocess.run,
                args=(self._cmd + [self.path],),
                kwargs={"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL},
                daemon=True,
            ).start()
