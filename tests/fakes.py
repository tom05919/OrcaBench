"""Small deterministic test doubles for harness contract tests.

These objects exercise orchestration mechanics only.  They are not robot
policies, simulator integrations, or benchmark-scored episodes.
"""

from __future__ import annotations

import base64
import copy
from collections import deque

from robot_benchmark.contracts import CAMERAS, PROPRIO, Limits, ModelReply, Skill
from robot_benchmark.runner import Runner


SENTINEL = "DO_NOT_EXPOSE_EVALUATOR_SECRET"
PNG_BYTES = b"\x89PNG\r\n\x1a\ncontract-test"
PNG_URL = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode("ascii")


def action(marker: float = 0.0) -> dict:
    """Return a schema-valid action whose first component identifies it."""
    return {
        "action.end_effector_position": [marker, 0.0, 0.0],
        "action.end_effector_rotation": [0.0, 0.0, 0.0],
        "action.gripper_close": [0.0],
        "action.base_motion": [0.0, 0.0, 0.0, 0.0],
        "action.control_mode": [0.0],
    }


class FakeEnvironment:
    def __init__(self, success=lambda step: False, step_error: Exception | None = None):
        self.success = success
        self.step_error = step_error
        self.world_step = 0
        self.reset_seeds = []
        self.step_attempts = []
        self.evaluate_calls = 0
        self.closed = False

    def reset(self, seed: int) -> None:
        self.reset_seeds.append(seed)
        self.world_step = 0

    def sensors(self) -> dict:
        return {
            "images": {
                **{name: PNG_URL for name in CAMERAS},
                "video.privileged_overhead": SENTINEL,
            },
            "proprio": {
                **{name: [0.0] * dim for name, dim in PROPRIO.items()},
                "state.object_ground_truth": [SENTINEL],
            },
            "reward": SENTINEL,
            "nested": {"object_coordinates": SENTINEL},
        }

    def policy_observation(self) -> dict:
        return {"world_step": self.world_step, "policy_only": {"secret": SENTINEL}}

    def recording_frame(self) -> str:
        return PNG_URL

    def step(self, value: dict) -> None:
        self.step_attempts.append(copy.deepcopy(value))
        if self.step_error is not None:
            raise self.step_error
        self.world_step += 1

    def evaluate(self) -> dict:
        self.evaluate_calls += 1
        return {"success": self.success(self.world_step), "evaluator_secret": SENTINEL}

    def snapshot(self) -> dict:
        return {"world_step": self.world_step, "private": {"secret": SENTINEL}}

    def close(self) -> None:
        self.closed = True


class FakePolicy:
    identity = {"adapter": "fake-policy"}

    def __init__(self, chunks=None, predict_error: Exception | None = None):
        self.chunks = deque(copy.deepcopy(chunks or []))
        self.predict_error = predict_error
        self.reset_episode_seeds = []
        self.reset_skill_calls = 0
        self.predict_calls = []

    def reset_episode(self, seed: int) -> None:
        self.reset_episode_seeds.append(seed)

    def reset_skill(self) -> None:
        self.reset_skill_calls += 1

    def predict(self, observation: dict, instruction: str) -> list[dict]:
        self.predict_calls.append((copy.deepcopy(observation), instruction))
        if self.predict_error is not None:
            raise self.predict_error
        if self.chunks:
            return self.chunks.popleft()
        return [action(100.0 + len(self.predict_calls)) for _ in range(4)]


class FakeAgent:
    identity = {"adapter": "fake-agent"}

    def __init__(self, replies):
        self.replies = deque(replies)
        self.observations = []

    def decide(self, observation: dict) -> ModelReply:
        self.observations.append(copy.deepcopy(observation))
        if not self.replies:
            raise AssertionError("fake agent exhausted its configured replies")
        item = self.replies.popleft()
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            item = item(observation)
        if isinstance(item, ModelReply):
            return item
        return ModelReply(decision=item)


class CaptureRecords:
    """In-memory records sink for assertions that do not need filesystem I/O."""

    def __init__(self):
        self.events = []
        self.observations = []
        self.writes = {}

    def append(self, name, value):
        self.events.append((name, copy.deepcopy(value)))

    def observation(self, index, value):
        self.observations.append((index, copy.deepcopy(value)))

    def write(self, name, value):
        self.writes[name] = copy.deepcopy(value)


def skills() -> list[Skill]:
    return [
        Skill("pick", "pick the objects", "fixture skill", {"success_rate": None}),
        Skill("place", "place the objects", "fixture skill", {"success_rate": None}),
    ]


def make_runner(
    replies,
    *,
    env=None,
    policy=None,
    limits=None,
    records=None,
    skill_list=None,
) -> Runner:
    return Runner(
        env or FakeEnvironment(),
        policy or FakePolicy(),
        FakeAgent(replies),
        skill_list or skills(),
        "put the cereal and bowl on the counter and close the cabinet",
        limits or Limits(max_steps=10, max_decisions=10, max_interval=5),
        records,
    )
