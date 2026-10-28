"""Visão computacional com MediaPipe Tasks (mãos, rosto e segmentação de pessoa).

Os modelos (.task/.tflite, ~10 MB no total) são baixados na primeira execução para
./models. Tudo roda local, offline depois do download, sem GPU obrigatória.
"""
from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np

from .gesture import Face, Point

_BASE = "https://storage.googleapis.com/mediapipe-models"
MODELS = {
    "hand": ("hand_landmarker.task",
             f"{_BASE}/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"),
    "face": ("blaze_face_short_range.tflite",
             f"{_BASE}/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"),
    "seg": ("selfie_segmenter.tflite",
            f"{_BASE}/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite"),
}


def ensure_model(model_dir: str, key: str) -> str:
    name, url = MODELS[key]
    path = os.path.join(model_dir, name)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        os.makedirs(model_dir, exist_ok=True)
        print(f"[modelos] baixando {name} ...")
        tmp = path + ".part"
        urllib.request.urlretrieve(url, tmp)
        os.replace(tmp, path)
    return path


@dataclass
class Observation:
    hands: List[List[Point]] = field(default_factory=list)   # 21 pontos (px) por mão
    faces: List[Face] = field(default_factory=list)
    person_mask: Optional[np.ndarray] = None                 # float32 HxW 0..1 (resolução cheia)


class MediaPipeDetector:
    def __init__(self, model_dir: str = "models", proc_width: int = 640,
                 segmentation: bool = True):
        import mediapipe as mp
        from mediapipe.tasks import python as mpp
        from mediapipe.tasks.python import vision

        self._mp = mp
        self.proc_width = proc_width
        video = vision.RunningMode.VIDEO

        self.hands = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=ensure_model(model_dir, "hand")),
            running_mode=video, num_hands=2,
            min_hand_detection_confidence=0.5, min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5))
        self.faces = vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(
            base_options=mpp.BaseOptions(model_asset_path=ensure_model(model_dir, "face")),
            running_mode=video, min_detection_confidence=0.5))
        self.seg = None
        if segmentation:
            self.seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
                base_options=mpp.BaseOptions(model_asset_path=ensure_model(model_dir, "seg")),
                running_mode=video, output_confidence_masks=True, output_category_mask=False))
        self._ts = 0
        self._mask_inverted: Optional[bool] = None   # auto-detectado na 1ª máscara com rosto

    def _next_ts(self, ts_ms: int) -> int:
        # modo VIDEO exige timestamp estritamente crescente por tarefa
        self._ts = max(ts_ms, self._ts + 1)
        return self._ts

    def process(self, frame_bgr: np.ndarray, ts_ms: int, need_mask: bool = False) -> Observation:
        H, W = frame_bgr.shape[:2]
        scale = W / float(self.proc_width) if W > self.proc_width else 1.0
        small = frame_bgr if scale == 1.0 else cv2.resize(
            frame_bgr, (int(W / scale), int(H / scale)), interpolation=cv2.INTER_AREA)
        sh, sw = small.shape[:2]
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        ts = self._next_ts(ts_ms)
        obs = Observation()

        hr = self.hands.detect_for_video(image, ts)
        for hand in hr.hand_landmarks or []:
            obs.hands.append([(p.x * sw * scale, p.y * sh * scale) for p in hand])

        fr = self.faces.detect_for_video(image, ts)
        for det in fr.detections or []:
            bb = det.bounding_box
            kp = det.keypoints or []
            if len(kp) < 3:
                continue
            px = lambda k: (k.x * sw * scale, k.y * sh * scale)  # noqa: E731
            obs.faces.append(Face(bb.origin_x * scale, bb.origin_y * scale,
                                  bb.width * scale, bb.height * scale,
                                  right_eye=px(kp[0]), left_eye=px(kp[1]), nose=px(kp[2])))

        if need_mask and self.seg is not None:
            sr = self.seg.segment_for_video(image, ts)
            masks = sr.confidence_masks or []
            if masks:
                m = masks[-1].numpy_view().astype(np.float32)
                if m.ndim == 3:
                    m = m[..., 0]
                m = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)
                m = self._orient(m, obs.faces)
                obs.person_mask = np.clip(m, 0, 1)
        return obs

    def _orient(self, m: np.ndarray, faces: List[Face]) -> np.ndarray:
        """Garante 1 = pessoa. Calibra uma vez olhando o valor da máscara sobre o rosto."""
        if self._mask_inverted is None and faces:
            f = max(faces, key=lambda f: f.w * f.h)
            x0, y0 = int(max(f.x, 0)), int(max(f.y, 0))
            roi = m[y0:y0 + int(f.h), x0:x0 + int(f.w)]
            if roi.size:
                self._mask_inverted = float(roi.mean()) < 0.5
        return 1.0 - m if self._mask_inverted else m

    def close(self):
        for t in (self.hands, self.faces, self.seg):
            if t is not None:
                t.close()
