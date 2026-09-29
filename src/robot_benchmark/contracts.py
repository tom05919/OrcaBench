"""Small public interface; no simulator imports or privileged fields."""
from dataclasses import dataclass
from typing import Any, Protocol
import copy
import math

CAMERAS = (
    "video.robot0_agentview_left",
    "video.robot0_agentview_right",
    "video.robot0_eye_in_hand",
)
PROPRIO = {
    "state.end_effector_position_relative": 3,
    "state.end_effector_rotation_relative": 4,
    "state.gripper_qpos": 2,
    "state.base_position": 3,
    "state.base_rotation": 4,
}
ACTION_DIMS = {
    "action.end_effector_position": 3,
    "action.end_effector_rotation": 3,
    "action.gripper_close": 1,
    "action.base_motion": 4,
    "action.control_mode": 1,
}
MAX_POLICY_PROMPT_CHARS = 512


@dataclass(frozen=True)
class Skill:
    id: str
    prompt: str
    description: str
    performance: dict

    def public(self):
        return copy.deepcopy(self.__dict__)


@dataclass(frozen=True)
class Limits:
    max_steps: int
    max_decisions: int = 100
    max_interval: int = 100

    def __post_init__(self):
        if any(type(x) is not int or x < 1 for x in self.__dict__.values()):
            raise ValueError("budgets must be positive integers")


def sensor_payload(sensor: dict) -> dict:
    """Project onto named sensors; never forward an arbitrary environment dict."""
    images = {name: sensor["images"][name] for name in CAMERAS}
    if not all(isinstance(v, str) and v.startswith("data:image/png;base64,") for v in images.values()):
        raise ValueError("camera observations must be PNG data URLs")
    proprio = {}
    for name, dim in PROPRIO.items():
        values = list(sensor["proprio"][name])
        if len(values) != dim or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError(f"invalid proprioception: {name}")
        proprio[name] = values
    return {"images": images, "proprio": proprio}


def validate_decision(value: Any, limits: Limits) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("op"), str):
        raise ValueError("decision must be an object with an op")
    op = value["op"]
    fields = set(value)
    if not (
        (op == "run_policy" and fields in ({"op", "steps"}, {"op", "prompt", "steps"}))
        or (op == "complete" and fields == {"op"})
    ):
        raise ValueError("invalid operation or fields; use the documented decision schema")
    if "prompt" in value and (
        not isinstance(value["prompt"], str)
        or not value["prompt"].strip()
        or len(value["prompt"]) > MAX_POLICY_PROMPT_CHARS
    ):
        raise ValueError(f"prompt must be nonblank text of at most {MAX_POLICY_PROMPT_CHARS} characters")
    if "steps" in value and (type(value["steps"]) is not int or not 1 <= value["steps"] <= limits.max_interval):
        raise ValueError(f"steps must be an integer in [1, {limits.max_interval}]")
    return dict(value)


def validate_action(action: dict) -> dict:
    if not isinstance(action, dict) or set(action) != set(ACTION_DIMS):
        raise ValueError("policy returned an incompatible action schema")
    result = {}
    for key, dim in ACTION_DIMS.items():
        values = list(action[key])
        if len(values) != dim or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError(f"invalid policy action: {key}")
        # Preserve upstream numerical outputs; the simulator controller applies its
        # native limits. Do not silently introduce a new policy-side clamp.
        result[key] = values
    return result


class Environment(Protocol):
    def reset(self, seed: int) -> None: ...
    def sensors(self) -> dict: ...
    def policy_observation(self) -> dict: ...
    def step(self, action: dict) -> None: ...
    def evaluate(self) -> dict: ...
    def snapshot(self) -> dict: ...
    def recording_frames(self) -> dict[str, str]: ...
    def sim_time_seconds(self) -> float: ...
    def close(self) -> None: ...


class Policy(Protocol):
    identity: dict
    def reset_episode(self, seed: int) -> None: ...
    def reset_skill(self) -> None: ...
    def predict(self, observation: dict, instruction: str) -> list[dict]: ...


@dataclass
class ModelReply:
    decision: Any
    usage: dict | None = None
    raw_text: str | None = None


class Agent(Protocol):
    identity: dict
    def decide(self, observation: dict) -> ModelReply: ...
