"""Small JSON client for the isolated learned-policy worker."""
import base64
from urllib.parse import urlparse

from ..contracts import CAMERAS, PROPRIO
from .http import request_json


def encode_observation(observation):
    return {
        "images": {key: {"shape": list(observation[key].shape),
                         "data": base64.b64encode(observation[key].tobytes()).decode()}
                   for key in CAMERAS},
        "proprio": {key: observation[key].tolist() for key in PROPRIO},
    }


class RemotePolicy:
    def __init__(self, endpoint="http://127.0.0.1:8765", timeout=120):
        parsed = urlparse(endpoint)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("policy worker must be local or reached through a loopback SSH tunnel")
        self.endpoint, self.timeout = endpoint.rstrip("/"), timeout
        self.identity = request_json(self.endpoint + "/health", timeout=timeout)
        if self.identity.get("backend") not in ("groot", "pi05") or not self.identity.get("checkpoint_manifest_sha256"):
            raise RuntimeError("worker must identify a verified learned checkpoint")

    def reset_episode(self, seed):
        request_json(self.endpoint + "/reset", {"seed": seed}, timeout=self.timeout)

    def reset_skill(self):
        # Worker models have no recurrent skill state; reset clears any model
        # implementation cache while preserving the episode's random stream.
        request_json(self.endpoint + "/reset", {}, timeout=self.timeout)

    def predict(self, observation, instruction):
        result = request_json(self.endpoint + "/infer", {
            "observation": encode_observation(observation), "instruction": instruction,
        }, timeout=self.timeout)
        return result["actions"]
