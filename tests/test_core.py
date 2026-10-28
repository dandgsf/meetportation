import os
import sys
import tempfile
import unittest
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meetportation.audio import synth_teleport_wav  # noqa: E402
from meetportation.detector import Observation  # noqa: E402
from meetportation.engine import APPEARING, AWAY, PRESENT, VANISHING, Meetporter  # noqa: E402
from meetportation.fx import Plate, TeleportFX, diff_mask  # noqa: E402
from meetportation.gesture import GestureClassifier, Trigger  # noqa: E402
from tests.synth import hand_at, make_face, noisy, person_layer, room  # noqa: E402


class GestureTests(unittest.TestCase):
    def setUp(self):
        self.c = GestureClassifier()
        self.face = make_face()
        self.fh = self.face.forehead()

    def test_two_fingers_on_forehead_is_active(self):
        r = self.c.evaluate([hand_at(self.fh)], [self.face])
        self.assertTrue(r.active, r.reasons)

    def test_tilted_hand_and_slight_offset_still_active(self):
        p = (self.fh[0] + 25, self.fh[1] + 10)
        for ang in (-35, -15, 20, 40):
            r = self.c.evaluate([hand_at(p, angle=ang)], [self.face])
            self.assertTrue(r.active, f"ângulo {ang}: {r.reasons}")

    def test_right_pose_but_far_from_forehead(self):
        chest = (self.fh[0], self.fh[1] + 400)
        r = self.c.evaluate([hand_at(chest)], [self.face])
        self.assertTrue(r.pose_ok)
        self.assertFalse(r.active)

    def test_open_hand_rejected(self):
        h = hand_at(self.fh, extended=("index", "middle", "ring", "pinky"))
        self.assertFalse(self.c.evaluate([h], [self.face]).active)

    def test_single_finger_rejected(self):
        h = hand_at(self.fh, extended=("index",))
        self.assertFalse(self.c.evaluate([h], [self.face]).active)

    def test_v_sign_spread_rejected(self):
        h = hand_at(self.fh, spread=28)
        r = self.c.evaluate([h], [self.face])
        self.assertFalse(r.active)
        self.assertIn("dedos separados", r.reasons)

    def test_fist_rejected(self):
        h = hand_at(self.fh, extended=())
        self.assertFalse(self.c.evaluate([h], [self.face]).active)

    def test_no_face_never_active(self):
        self.assertFalse(self.c.evaluate([hand_at(self.fh)], []).active)

    def test_scale_invariance(self):
        small = make_face(eye_dist=35)
        r = self.c.evaluate([hand_at(small.forehead(), scale=50)], [small])
        self.assertTrue(r.active, r.reasons)


class TriggerTests(unittest.TestCase):
    def test_fires_once_per_hold_and_rearms_after_release(self):
        t = Trigger(hold_frames=5, release_frames=3, cooldown_s=0.5)
        now, fired = 0.0, []
        seq = [True] * 20 + [False] * 5 + [True] * 6
        for a in seq:
            now += 1 / 30
            fired.append(t.update(a, now))
        idx = [i for i, f in enumerate(fired) if f]
        self.assertEqual(len(idx), 2, idx)
        self.assertEqual(idx[0], 4)          # 5º frame segurando
        self.assertGreaterEqual(idx[1], 25)  # só depois de soltar e segurar de novo

    def test_single_frame_blip_ignored(self):
        t = Trigger(hold_frames=5)
        now = 0.0
        out = []
        for a in [True, False, True, False, True, True, False]:
            now += 1 / 30
            out.append(t.update(a, now))
        self.assertFalse(any(out))


class FxTests(unittest.TestCase):
    def setUp(self):
        self.bg = room()
        self.frame, self.mask = person_layer(self.bg)

    def test_diff_mask_finds_person(self):
        m = diff_mask(noisy(self.frame, 2, 1), noisy(self.bg, 2, 2)) > 0.5
        gt = self.mask > 0.5
        iou = (m & gt).sum() / max((m | gt).sum(), 1)
        self.assertGreater(iou, 0.85, iou)

    def test_fx_endpoints_and_monotonic_fade(self):
        fx = TeleportFX(frames=9)
        np.testing.assert_array_equal(fx.render(self.frame, self.bg, self.mask, 0.0), self.frame)
        np.testing.assert_array_equal(fx.render(self.frame, self.bg, self.mask, 1.0), self.bg)
        inside = self.mask > 0.9
        # diferença em relação ao fundo deve cair (considerando só frames "visíveis" do pisca)
        diffs = []
        for k in range(0, 9, 2):
            o = fx.render(self.frame, self.bg, self.mask, k / 9).astype(np.int16)
            diffs.append(np.abs(o - self.bg.astype(np.int16))[inside].mean())
        self.assertTrue(all(a >= b - 1 for a, b in zip(diffs, diffs[1:])), diffs)

    def test_plate_from_frames_estimates_noise(self):
        frames = [noisy(self.bg, 3, s) for s in range(15)]
        p = Plate.from_frames(frames)
        self.assertLess(np.abs(p.image.astype(int) - self.bg.astype(int)).mean(), 1.5)
        self.assertTrue(2.0 < p.noise_sigma < 4.0, p.noise_sigma)
        a, b = p.frame(), p.frame()
        self.assertFalse(np.array_equal(a, b))   # não é um frame congelado

    def test_plate_roundtrip(self):
        p = Plate(self.bg, 2.2)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "plate.png")
            p.save(path)
            q = Plate.load(path)
        np.testing.assert_array_equal(q.image, self.bg)
        self.assertAlmostEqual(q.noise_sigma, 2.2)


class EngineTests(unittest.TestCase):
    def test_full_cycle_vanish_then_reappear(self):
        bg = room()
        plate = Plate.from_frames([noisy(bg, 2, s) for s in range(10)])
        events = []
        eng = Meetporter(plate, trigger=Trigger(hold_frames=4, release_frames=3, cooldown_s=0.3),
                         fx=TeleportFX(frames=9), on_teleport=events.append)
        frame, gt = person_layer(bg)
        face = make_face(640, 320, 64)
        gesture = Observation(hands=[hand_at(face.forehead(), scale=90)], faces=[face])
        idle = Observation(hands=[], faces=[face])
        inside = gt > 0.9

        script = [gesture] * 6 + [idle] * 20 + [gesture] * 6 + [idle] * 20
        states, outs, now = [], [], 0.0
        for obs in script:
            now += 1 / 30
            f = noisy(frame, 2)
            out, info = eng.step(f, obs, now)
            states.append(info.state)
            outs.append(out)

        self.assertEqual(events, ["out", "in"])
        self.assertIn(VANISHING, states)
        self.assertIn(APPEARING, states)
        self.assertEqual(states[-1], PRESENT)
        away = [o for o, s in zip(outs, states) if s == AWAY]
        self.assertGreater(len(away), 5)
        # enquanto "fora", a região da pessoa mostra a parede, não a pessoa
        err = np.abs(away[3].astype(int) - bg.astype(int))[inside].mean()
        self.assertLess(err, 5, err)
        # no fim, pessoa de volta (saída == entrada)
        last_in = noisy(frame, 2)
        out, _ = eng.step(last_in, idle, now + 1)
        np.testing.assert_array_equal(out, last_in)

    def test_held_gesture_fires_only_once(self):
        """Mão parada na testa por 3 s: some UMA vez e não volta até soltar (bug achado no Mac)."""
        bg = room()
        events = []
        eng = Meetporter(Plate(bg, 0), trigger=Trigger(hold_frames=5, release_frames=4, cooldown_s=1.0),
                         fx=TeleportFX(frames=9), on_teleport=events.append)
        frame, _ = person_layer(bg)
        face = make_face(640, 320, 64)
        g = Observation(hands=[hand_at(face.forehead(), scale=90)], faces=[face])
        idle = Observation(hands=[], faces=[face])
        now = 0.0
        for _ in range(90):
            now += 1 / 30
            eng.step(frame, g, now)
        self.assertEqual(events, ["out"])
        self.assertEqual(eng.state, AWAY)
        for _ in range(10):              # soltou a mão
            now += 1 / 30
            eng.step(frame, idle, now)
        for _ in range(10):              # gesto de novo -> volta
            now += 1 / 30
            eng.step(frame, g, now)
        self.assertEqual(events, ["out", "in"])

    def test_gesture_ignored_during_transition(self):
        bg = room()
        eng = Meetporter(Plate(bg, 0), trigger=Trigger(hold_frames=2, release_frames=1, cooldown_s=0),
                         fx=TeleportFX(frames=20))
        frame, _ = person_layer(bg)
        face = make_face(640, 320, 64)
        g = Observation(hands=[hand_at(face.forehead(), scale=90)], faces=[face])
        now, states = 0.0, []
        for _ in range(15):
            now += 0.033
            states.append(eng.step(frame, g, now)[1].state)
        self.assertNotIn(APPEARING, states)


class AudioTests(unittest.TestCase):
    def test_synth_wav(self):
        with tempfile.TemporaryDirectory() as d:
            p = synth_teleport_wav(os.path.join(d, "t.wav"))
            with wave.open(p) as w:
                dur = w.getnframes() / w.getframerate()
        self.assertAlmostEqual(dur, 0.62, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
