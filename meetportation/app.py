"""CLI do Meetportation: webcam -> gesto -> efeito -> câmera virtual."""
from __future__ import annotations

import argparse
import os
import sys
import time

import cv2

from .audio import SoundPlayer, synth_teleport_wav
from .engine import AWAY, VANISHING, Meetporter
from .fx import Plate, TeleportFX
from .gesture import GestureClassifier, Trigger
from .output import RecorderSink, Sinks, VirtualCamSink

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")

KEYS_HELP = "[espaço] teleporta manual  [b] recapturar fundo  [d] debug  [q] sair"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Meetportation — teletransporte na câmera da reunião.")
    p.add_argument("--source", default="0", help="índice da webcam (0, 1...) ou caminho de vídeo")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=float, default=30)
    p.add_argument("--no-vcam", action="store_true", help="não publica câmera virtual (só preview/gravação)")
    p.add_argument("--vcam-backend", default=None, help="pyvirtualcam backend: obs | unitycapture | v4l2loopback")
    p.add_argument("--ws", action="store_true", help="transmite para a extensão do Chrome (Meet) — sem OBS")
    p.add_argument("--ws-port", type=int, default=8765)
    p.add_argument("--record", default=None, help="grava a saída em MP4 (ex.: saida.mp4)")
    p.add_argument("--headless", action="store_true", help="sem janela de preview")
    p.add_argument("--no-mirror", action="store_true", help="preview sem espelhar")
    p.add_argument("--away", choices=["static", "live"], default="static",
                   help="static = fundo capturado + ruído | live = fundo ao vivo com IA de segmentação")
    p.add_argument("--no-seg", action="store_true", help="desliga a segmentação por IA (usa diferença vs. fundo)")
    p.add_argument("--plate", default=os.path.join(DATA, "plate.png"), help="arquivo do fundo vazio")
    p.add_argument("--recapture", action="store_true", help="força capturar o fundo de novo")
    p.add_argument("--countdown", type=float, default=4.0, help="segundos p/ sair do quadro antes de capturar")
    p.add_argument("--sound", default=None, help=".wav próprio (padrão: som sintetizado)")
    p.add_argument("--mute", action="store_true")
    p.add_argument("--hold", type=int, default=5, help="frames segurando o gesto p/ disparar")
    p.add_argument("--radius", type=float, default=0.60, help="tolerância da distância dedos→testa")
    p.add_argument("--fx-frames", type=int, default=9, help="duração do efeito em frames")
    p.add_argument("--models", default=os.path.join(HERE, "models"))
    p.add_argument("--proc-width", type=int, default=640, help="largura usada pela IA (menor = mais rápido)")
    return p.parse_args(argv)


def open_capture(args):
    src = int(args.source) if args.source.isdigit() else args.source
    if isinstance(src, int) and sys.platform.startswith("win"):
        cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)   # DirectShow abre mais rápido e respeita resolução
    else:
        cap = cv2.VideoCapture(src)
    if isinstance(src, int):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        cap.set(cv2.CAP_PROP_FPS, args.fps)
    if not cap.isOpened():
        sys.exit(f"Não consegui abrir a fonte de vídeo: {args.source}")
    return cap, isinstance(src, int)


def _color(r):
    return (0, 220, 120) if r.active else (0, 200, 255) if r.pose_ok else (180, 180, 180)


def draw_debug_marks(img, info):
    """Marcadores geométricos (desenhados ANTES do espelhamento do preview)."""
    r = info.reading
    if r.forehead is not None:
        cv2.circle(img, tuple(int(v) for v in r.forehead), 7, (255, 255, 0), -1)
    if r.tip is not None:
        cv2.circle(img, tuple(int(v) for v in r.tip), 10, _color(r), 2)
        if r.forehead is not None:
            cv2.line(img, tuple(int(v) for v in r.tip), tuple(int(v) for v in r.forehead), _color(r), 1)


def draw_debug_text(img, info, extra=""):
    """Texto/HUD (desenhado DEPOIS do espelhamento, pra não sair invertido)."""
    r = info.reading
    color = _color(r)
    h = img.shape[0]
    cv2.rectangle(img, (10, h - 40), (10 + int(200 * info.hold_progress), h - 25), (0, 220, 120), -1)
    cv2.rectangle(img, (10, h - 40), (210, h - 25), (255, 255, 255), 1)
    dist = f" | dist testa {r.distance_ratio:.2f}" if r.forehead is not None else ""
    lines = [f"estado: {info.state}{dist}",
             "gesto: OK" if r.active else "gesto: " + (", ".join(r.reasons[:2]) or "-")]
    if extra:
        lines.append(extra)
    for i, s in enumerate(lines):
        cv2.putText(img, s, (10, 26 + 24 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, s, (10, 26 + 24 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)


def banner(img, text, sub=""):
    out = img.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], 90), (20, 20, 20), -1)
    cv2.putText(out, text, (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 243, 190), 3, cv2.LINE_AA)
    if sub:
        cv2.putText(out, sub, (20, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1, cv2.LINE_AA)
    return out


def main(argv=None):
    args = parse_args(argv)
    cap, is_cam = open_capture(args)
    ok, frame = cap.read()
    if not ok:
        sys.exit("A câmera abriu mas não entregou frame.")
    H, W = frame.shape[:2]
    print(f"[entrada] {W}x{H}")

    from .detector import MediaPipeDetector
    detector = MediaPipeDetector(args.models, proc_width=args.proc_width, segmentation=not args.no_seg)
    away_mode = args.away if not args.no_seg else "static"

    # ordem: --sound > data/teleport.wav (seu som) > assets/teleport.wav (som do repo) > sintetizado
    bundled = os.path.join(HERE, "assets", "teleport.wav")
    sound_path = args.sound or os.path.join(DATA, "teleport.wav")
    if not args.sound and not os.path.exists(sound_path) and os.path.exists(bundled):
        sound_path = bundled
    if not args.sound and not os.path.exists(sound_path):
        synth_teleport_wav(sound_path)
    player = SoundPlayer(sound_path, enabled=not args.mute)

    sinks = []
    if not args.no_vcam:
        sinks.append(VirtualCamSink(W, H, args.fps, backend=args.vcam_backend))
    if args.ws:
        from .wsserver import WebSocketSink
        sinks.append(WebSocketSink(port=args.ws_port, fps=args.fps))
    if args.record:
        sinks.append(RecorderSink(args.record, W, H, args.fps))
    out = Sinks(sinks)

    plate = None if args.recapture else Plate.load(args.plate)
    if plate is not None and not plate.matches(frame):
        print("[fundo] resolução mudou — vou recapturar.")
        plate = None

    engine = None if plate is None else Meetporter(
        plate, GestureClassifier(forehead_radius=args.radius), Trigger(hold_frames=args.hold),
        TeleportFX(frames=args.fx_frames), away_mode=away_mode, on_teleport=lambda _d: player.play())

    capture_until = time.monotonic() + args.countdown if plate is None else None
    captured = []
    debug, win = True, "Meetportation (preview)"
    if plate is None:
        print(f"[fundo] SAIA DO ENQUADRAMENTO — capturando em {args.countdown:.0f}s...")

    try:
        while True:
            if frame is None:
                ok, frame = cap.read()
                if not ok:
                    break
            now = time.monotonic()
            preview, banner_args = None, None

            if engine is None:  # ---- captura do clean plate ------------------
                left = capture_until - now
                output = frame
                preview = frame.copy()
                if left > 0:
                    banner_args = (f"Saia do quadro: {left:0.1f}s",
                                   "capturando o fundo vazio (o que a reuniao vai ver quando voce sumir)")
                else:
                    captured.append(frame.copy())
                    banner_args = (f"Capturando fundo... {len(captured)}/20",)
                    if len(captured) >= 20:
                        plate = Plate.from_frames(captured)
                        plate.save(args.plate)
                        print(f"[fundo] salvo em {args.plate} (ruído do sensor σ={plate.noise_sigma:.2f}). Pode voltar!")
                        engine = Meetporter(
                            plate, GestureClassifier(forehead_radius=args.radius), Trigger(hold_frames=args.hold),
                            TeleportFX(frames=args.fx_frames), away_mode=away_mode,
                            on_teleport=lambda _d: player.play())
                        captured = []
            else:  # ---- operação normal --------------------------------------
                obs = detector.process(frame, int(now * 1000), need_mask=engine.needs_mask)
                output, info = engine.step(frame, obs, now)
                if info.fired:
                    print(f"[teleporte] {'sumiu' if info.state == VANISHING else 'voltou'}")
                if not args.headless:
                    preview = output.copy() if engine.state == AWAY else frame.copy()
                    if debug:
                        draw_debug_marks(preview, info)

            out.send(output)

            if not args.headless and preview is not None:
                if not args.no_mirror:
                    preview = cv2.flip(preview, 1)
                if banner_args:
                    preview = banner(preview, *banner_args)
                elif engine is not None and debug:
                    draw_debug_text(preview, info, KEYS_HELP)
                pw = 960
                ph = int(preview.shape[0] * pw / preview.shape[1])
                cv2.imshow(win, cv2.resize(preview, (pw, ph)))
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if key == ord("d"):
                    debug = not debug
                if key == ord(" ") and engine is not None:
                    engine.toggle()
                if key == ord("b"):
                    engine, plate, captured = None, None, []
                    capture_until = time.monotonic() + args.countdown
            out.wait()
            frame = None
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        out.close()
        detector.close()
        if not args.headless:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
