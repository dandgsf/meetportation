"""Teste ponta a ponta do app real (captura do fundo, gesto, efeito, gravação).

Só a camada MediaPipe é trocada por um stub roteirizado (os modelos não estão
disponíveis no ambiente de CI). Uso:  python -m tests.e2e <pasta_saida>
"""
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import meetportation.detector as det  # noqa: E402
from meetportation.app import main  # noqa: E402
from tests.synth import hand_at, make_face, noisy, person_layer, room  # noqa: E402

FPS = 30
EMPTY, OUT_AT, IN_AT, TOTAL = 30, 70, 130, 180
CAPTURE = 20


def build_input(path):
    bg = room()
    person, _ = person_layer(bg)
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (bg.shape[1], bg.shape[0]))
    for i in range(TOTAL):
        vw.write(noisy(bg if i < EMPTY else person, 2, i))
    vw.release()


class StubDetector:
    def __init__(self, *a, **k):
        self.i = CAPTURE  # o app chama o detector só depois de capturar 20 frames de fundo
        self.face = make_face(640, 320, 64)

    def process(self, frame, ts_ms, need_mask=False):
        i, self.i = self.i, self.i + 1
        time.sleep(1 / FPS)  # ritmo de webcam (o cooldown do gatilho é em tempo real)
        faces = [self.face] if i >= EMPTY else []
        gesturing = OUT_AT <= i < OUT_AT + 8 or IN_AT <= i < IN_AT + 8
        hands = [hand_at(self.face.forehead(), scale=90)] if gesturing else []
        return det.Observation(hands=hands, faces=faces)

    def close(self):
        pass


def run(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    src = os.path.join(out_dir, "input.mp4")
    rec = os.path.join(out_dir, "output.mp4")
    build_input(src)
    det.MediaPipeDetector = StubDetector
    main(["--source", src, "--no-vcam", "--headless", "--record", rec, "--countdown", "0",
          "--recapture", "--plate", os.path.join(out_dir, "plate.png"), "--mute"])

    cap = cv2.VideoCapture(rec)
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    bg = room()
    _, gt = person_layer(bg)
    inside = gt > 0.9
    err = [float(np.abs(f.astype(int) - bg.astype(int))[inside].mean()) for f in frames]
    away = [i for i, e in enumerate(err) if e < 12]
    print(f"frames gravados: {len(frames)} | frames com a pessoa 'sumida': {len(away)} "
          f"(de {away[0] if away else '-'} a {away[-1] if away else '-'})")
    assert len(frames) == TOTAL, len(frames)
    assert away and min(i for i in away if i >= EMPTY) > OUT_AT, "sumiu cedo demais"
    assert 40 <= len([i for i in away if i >= EMPTY]) <= 70, "tempo 'fora' inesperado"
    assert err[-1] > 40, "pessoa não voltou"

    # contact sheet: só os frames de transição (sumindo e voltando) + vizinhos
    full = float(np.median(err[EMPTY + 5:OUT_AT]))
    trans = [i for i in range(EMPTY, TOTAL) if 12 <= err[i] <= 0.92 * full]
    picks = []
    for i in trans:
        for j in (i - 1, i, i + 1):
            if 0 <= j < len(frames) and j not in picks:
                picks.append(j)
    picks = picks[:20] + [picks[-1]] * (5 - len(picks[:20]) % 5 if len(picks[:20]) % 5 else 0)
    tiles = [cv2.resize(frames[i], (320, 180)) for i in picks]
    for t, i in zip(tiles, picks):
        cv2.putText(t, f"#{i}", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
        cv2.putText(t, f"#{i}", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    rows = [np.hstack(tiles[r * 5:(r + 1) * 5]) for r in range(len(tiles) // 5)]
    print(f"frames de transição: {trans}")
    sheet = os.path.join(out_dir, "contact_sheet.png")
    cv2.imwrite(sheet, np.vstack(rows))
    print("OK ->", sheet)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "e2e_out")
