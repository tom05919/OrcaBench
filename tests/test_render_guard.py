import unittest

try:
    import numpy as np
except ImportError:  # the core environment has no numpy; the check runs where the simulator does
    np = None

from robot_benchmark.adapters.robocasa import CORRUPT_FRAME_SCORE, RoboCasaEnvironment, frame_noise
from robot_benchmark.contracts import CAMERAS


@unittest.skipIf(np is None, "numpy not installed")
class RenderGuardTests(unittest.TestCase):
    def smooth(self):
        ramp = np.tile(np.linspace(40, 200, 256), (256, 1))
        return np.stack([ramp, ramp * 0.8, ramp * 0.6], axis=-1).astype("uint8")

    def static(self):
        return np.random.default_rng(0).integers(90, 170, size=(256, 256, 3)).astype("uint8")

    def test_rendered_scene_scores_below_and_static_above_the_threshold(self):
        self.assertLess(frame_noise(self.smooth()), CORRUPT_FRAME_SCORE)
        self.assertGreater(frame_noise(self.static()), CORRUPT_FRAME_SCORE)

    def environment(self, image):
        env = RoboCasaEnvironment.__new__(RoboCasaEnvironment)
        env.obs, env.frame = {key: image for key in CAMERAS}, 7
        return env

    def test_corrupt_frame_raises_so_the_episode_ends_as_an_infrastructure_error(self):
        with self.assertRaisesRegex(RuntimeError, "corrupt camera frame.*at step 7"):
            self.environment(self.static())._check_frames()

    def test_clean_frames_pass(self):
        self.environment(self.smooth())._check_frames()


if __name__ == "__main__":
    unittest.main()


class StartStateGuardTests(unittest.TestCase):
    def environment(self, expected):
        env = RoboCasaEnvironment.__new__(RoboCasaEnvironment)
        env.expected_start_state = expected
        return env

    def test_matching_or_unrequested_start_passes(self):
        self.environment("a" * 64)._check_start_state("a" * 64)
        self.environment(None)._check_start_state("b" * 64)

    def test_a_different_scene_raises_before_any_model_call(self):
        with self.assertRaisesRegex(RuntimeError, "scene mismatch: start state bbbbbbbbbbbb is not the expected aaaaaaaaaaaa"):
            self.environment("a" * 64)._check_start_state("b" * 64)
