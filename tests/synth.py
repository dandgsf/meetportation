"""Gerador de mãos/rostos/cenas sintéticas para testar sem webcam."""
from __future__ import annotations

import math

import cv2
import numpy as np

from meetportation.gesture import Face

FINGERS = {"index": (5, -0.30), "middle": (9, -0.10), "ring": (13, 0.10), "pinky": (17, 0.30)}


def _rot(v, deg):
    a = math.radians(deg)
    return (v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a))


def make_hand(extended=("index", "middle"), angle=0.0, scale=100.0, spread=0.0, wrist=(0.0, 0.0)):
    """21 landmarks. angle=0 -> dedos apontando para cima (y da imagem cresce para baixo)."""
    u = _rot((0.0, -1.0), angle)   # direção dos dedos
    v = _rot((1.0, 0.0), angle)    # largura da palma
    s = scale
    lm = [None] * 21
    lm[0] = (0.0, 0.0)
    for i, k in enumerate((1, 2, 3, 4)):  # polegar dobrado ao lado
        lm[k] = (v[0] * -0.35 * s * (1 + i * 0.3) + u[0] * 0.3 * s * i * 0.4,
                 v[1] * -0.35 * s * (1 + i * 0.3) + u[1] * 0.3 * s * i * 0.4)
    for name, (base, off) in FINGERS.items():
        mcp = (u[0] * s + v[0] * off * s, u[1] * s + v[1] * off * s)
        if name in extended:
            ang = {"index": -spread, "middle": spread}.get(name, 0.0)
            d = _rot(u, ang)
            pts = [mcp]
            for seg in (0.40, 0.25, 0.22):
                p = pts[-1]
                pts.append((p[0] + d[0] * seg * s, p[1] + d[1] * seg * s))
        else:
            pip = (mcp[0] + u[0] * 0.30 * s, mcp[1] + u[1] * 0.30 * s)
            dip = (mcp[0] + u[0] * 0.15 * s + v[0] * 0.05 * s, mcp[1] + u[1] * 0.15 * s + v[1] * 0.05 * s)
            tip = (mcp[0] - u[0] * 0.05 * s, mcp[1] - u[1] * 0.05 * s)
            pts = [mcp, pip, dip, tip]
        for j, p in enumerate(pts):
            lm[base + j] = p
    return [(p[0] + wrist[0], p[1] + wrist[1]) for p in lm]


def make_face(cx=640.0, cy=300.0, eye_dist=70.0):
    re, le = (cx - eye_dist / 2, cy), (cx + eye_dist / 2, cy)
    nose = (cx, cy + eye_dist * 0.55)
    return Face(cx - eye_dist * 1.2, cy - eye_dist * 1.1, eye_dist * 2.4, eye_dist * 2.8, re, le, nose)


def hand_at(point, **kw):
    """Mão cuja ponta média indicador/médio fica exatamente em `point`."""
    h = make_hand(**kw)
    tip = ((h[8][0] + h[12][0]) / 2, (h[8][1] + h[12][1]) / 2)
    dx, dy = point[0] - tip[0], point[1] - tip[1]
    return [(x + dx, y + dy) for x, y in h]


def room(w=1280, h=720):
    """'Escritório' sintético: parede em gradiente, estante, quadro, mesa."""
    y = np.linspace(0, 1, h)[:, None]
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (np.array([200, 210, 225]) * (1 - 0.25 * y))[..., None, :].reshape(h, 1, 3)
    img = img.astype(np.uint8)
    cv2.rectangle(img, (80, 120), (330, 560), (60, 90, 120), -1)
    for i in range(4):
        yy = 170 + i * 100
        cv2.rectangle(img, (95, yy), (315, yy + 8), (40, 60, 80), -1)
        for j in range(6):
            cv2.rectangle(img, (105 + j * 34, yy - 60), (128 + j * 34, yy - 2),
                          (int(50 + 30 * j), int(120 + 15 * i), int(200 - 25 * j)), -1)
    cv2.rectangle(img, (930, 140), (1180, 330), (30, 40, 30), -1)
    cv2.rectangle(img, (945, 155), (1165, 315), (120, 160, 110), -1)
    cv2.rectangle(img, (0, 600), (w, h), (70, 100, 140), -1)
    return img


def person_layer(frame, cx=640, cy=330):
    """Desenha um 'boneco' (cabeça + tronco) por cima do frame; devolve (frame, máscara)."""
    out = frame.copy()
    m = np.zeros(frame.shape[:2], np.uint8)
    for target, col in ((out, (90, 120, 200)), (m, 255)):
        cv2.ellipse(target, (cx, cy + 330), (230, 260), 0, 180, 360, col if target is m else (40, 40, 160), -1)
        cv2.circle(target, (cx, cy), 95, col, -1)
    cv2.circle(out, (cx - 32, cy - 10), 9, (30, 30, 30), -1)
    cv2.circle(out, (cx + 32, cy - 10), 9, (30, 30, 30), -1)
    cv2.ellipse(out, (cx, cy + 40), (35, 14), 0, 0, 180, (40, 40, 120), 3)
    return out, m.astype(np.float32) / 255.0


def noisy(img, sigma=2.0, seed=None):
    rng = np.random.default_rng(seed)
    return np.clip(img.astype(np.float32) + rng.normal(0, sigma, img.shape), 0, 255).astype(np.uint8)
