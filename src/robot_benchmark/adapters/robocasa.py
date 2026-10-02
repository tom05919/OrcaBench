"""RoboCasa365 PandaOmron adapter. Dependencies imported only on construction."""
import base64
import hashlib
from io import BytesIO

from ..contracts import CAMERAS, PROPRIO


class RoboCasaEnvironment:
    def __init__(self, task="CerealAndBowl", split="pretrain", camera_size=256):
        import numpy as np
        import gymnasium as gym
        import robocasa  # registers the pinned gym environments
        from robocasa.utils.dataset_registry_utils import get_task_horizon

        self.np, self.gym = np, gym
        self.task, self.split, self.camera_size = task, split, camera_size
        self.horizon = get_task_horizon(task)
        self.env = self.obs = None
        self.frame = 0

    def reset(self, seed):
        if self.env is not None:
            self.env.close()
        # Recreate per episode: constructor-level scene sampling must use the
        # same seed across model comparisons, not only the later reset call.
        self.env = self.gym.make(
            f"robocasa/{self.task}", split=self.split, seed=seed,
            enable_render=True, camera_widths=self.camera_size,
            camera_heights=self.camera_size,
        )
        self.obs, _ = self.env.reset(seed=seed)
        self.frame = 0
        raw = self.env.unwrapped.env
        self.initial_xml = raw.sim.model.get_xml()

    def sensors(self):
        from PIL import Image
        images = {}
        for key in CAMERAS:
            buffer = BytesIO()
            # RoboCasa's gym wrapper already flips raw MuJoCo camera images.
            # Do not flip again or reuse the older Lift camera conventions.
            Image.fromarray(self.obs[key]).save(buffer, format="PNG")
            images[key] = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
        return {"images": images, "proprio": {key: self.obs[key].tolist() for key in PROPRIO}}

    def native_instruction(self):
        text = self.obs["annotation.human.task_description"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("RoboCasa returned a blank task description")
        return text.strip()

    def recording_frames(self):
        return self.sensors()["images"]

    def sim_time_seconds(self):
        return float(self.env.unwrapped.env.sim.data.time)

    def policy_observation(self):
        return {key: self.obs[key].copy() for key in (*CAMERAS, *PROPRIO)}

    def step(self, action):
        converted = {key: self.np.asarray(values, dtype=self.np.float64) for key, values in action.items()}
        obs, _, terminated, truncated, _ = self.env.step(converted)
        self.obs = obs
        self.frame += 1
        if terminated or truncated:
            raise RuntimeError("unexpected upstream termination; benchmark owns episode termination")
        if not self.np.isfinite(self.env.unwrapped.env.sim.data.qpos).all():
            raise RuntimeError("nonfinite simulator state")

    def evaluate(self):
        raw = self.env.unwrapped.env
        if self.task != "CerealAndBowl":
            from ..tasks.predicates import task_predicates
            success = bool(raw._check_success())
            try:
                extra = task_predicates(self.task, raw)
            except Exception as error:  # diagnostic predicates must never break official scoring
                return {"success": success, "predicate_error": f"{type(error).__name__}: {error}"}
            if "success" in extra:
                raise RuntimeError("task predicates must not redefine success")
            return {"success": success, **extra}
        from robocasa.utils import object_utils as ou
        cereal = bool(ou.check_obj_fixture_contact(raw, "cereal", raw.counter))
        bowl = bool(ou.check_obj_fixture_contact(raw, "bowl", raw.counter))
        closed = bool(raw.cab.is_closed(env=raw))
        # Evaluate official task predicate, and assert our documented decomposition.
        success = bool(raw._check_success())
        if success != (cereal and bowl and closed):
            raise RuntimeError("task scorer changed; re-audit the benchmark contract")
        return {
            "success": success, "cereal_on_counter": cereal,
            "bowl_on_counter": bowl, "cabinet_closed": closed,
            "cabinet_open": bool(raw.cab.is_open(env=raw)),
        }

    def snapshot(self):
        raw = self.env.unwrapped.env
        state = raw.sim.get_state().flatten()
        result = {"state_sha256": hashlib.sha256(state.tobytes()).hexdigest(),
                  "sim_time_seconds": float(raw.sim.data.time)}
        if self.frame == 0:
            result.update({"initial_state": state.tolist(), "xml": self.initial_xml,
                           "episode_metadata": raw.get_ep_meta()})
        return result

    def close(self):
        if self.env is not None:
            self.env.close()
            self.env = None
