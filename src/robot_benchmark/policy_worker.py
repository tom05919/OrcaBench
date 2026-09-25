"""Run one frozen VLA in its own environment. No simulator or model orchestrator."""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import random
import platform

from .contracts import ACTION_DIMS, CAMERAS, PROPRIO, validate_action
from .records import digest


EXPECTED_CHECKPOINTS = {
    "groot": {
        "identity": ("robocasa/robocasa365_checkpoints", "c484448aba1a9b60a04c9b0ca117241518ea69f3", "gr00t_n1-5/multitask_learning/checkpoint-120000"),
        "manifest_sha256": "091892f3b79f8e938dd7083c3566ec1288d4c89306033a3fbf731b82cc2951b3",
    },
    "pi05": {
        "identity": ("robocasa/robocasa365_checkpoints", "c484448aba1a9b60a04c9b0ca117241518ea69f3", "pi05_pretrain_human300/multitask_learning/75000"),
        "manifest_sha256": "6cb40c35b39fea8b6f8b40a8644dfe00b7b7e54bdb8681f0b33e40a38b02c98c",
    },
}


def verify_checkpoint(path, backend=None):
    path = Path(path).resolve()
    manifest_path = path.with_name(path.name + ".manifest.json")
    manifest = json.loads(manifest_path.read_text())
    if not manifest.get("revision") or not manifest.get("files"):
        raise ValueError("checkpoint manifest must contain revision and file checksums")
    canonical = {key: manifest.get(key) for key in ("repo_id", "revision", "subdir", "files")}
    if backend:
        expected = EXPECTED_CHECKPOINTS[backend]
        if tuple(canonical[key] for key in ("repo_id", "revision", "subdir")) != expected["identity"]:
            raise ValueError(f"manifest does not identify the pinned {backend} checkpoint")
        if digest(canonical) != expected["manifest_sha256"]:
            raise ValueError(f"manifest does not contain the complete pinned {backend} file set")
    for item in manifest["files"]:
        file = (path / item["path"]).resolve()
        if not file.is_relative_to(path):
            raise ValueError("checkpoint file escapes its directory")
        sha = hashlib.sha256()
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                sha.update(block)
        if sha.hexdigest() != item["sha256"] or file.stat().st_size != item["size"]:
            raise ValueError(f"checkpoint verification failed: {item['path']}")
    return manifest


def decode_observation(payload):
    import numpy as np
    result = {}
    for key in CAMERAS:
        image = payload["images"][key]
        shape = image["shape"]
        if shape != [256, 256, 3]:
            raise ValueError("expected upstream 256x256 RGB camera images")
        data = base64.b64decode(image["data"], validate=True)
        result[key] = np.frombuffer(data, dtype=np.uint8).reshape(shape).copy()
    for key, dim in PROPRIO.items():
        values = np.asarray(payload["proprio"][key], dtype=np.float32)
        if values.shape != (dim,) or not np.isfinite(values).all():
            raise ValueError(f"invalid state input: {key}")
        result[key] = values
    return result


class LearnedPolicy:
    def __init__(self, backend, checkpoint):
        import numpy as np
        self.np, self.backend = np, backend
        manifest = verify_checkpoint(checkpoint, backend)
        self.identity = {
            "backend": backend, "checkpoint_repo": manifest["repo_id"],
            "checkpoint_revision": manifest["revision"],
            "checkpoint_manifest_sha256": digest({k: manifest[k] for k in ("repo_id", "revision", "subdir", "files")}),
            "checkpoint_subdir": manifest["subdir"],
            "python": platform.python_version(),
            "native_action_steps": 16 if backend == "groot" else 5,
            "adapter_version": 1,
        }
        if backend == "groot":
            import torch
            from gr00t.experiment.data_config import DATA_CONFIG_MAP
            from gr00t.model.policy import Gr00tPolicy
            if not torch.cuda.is_available():
                raise RuntimeError("GR00T feasibility requires a CUDA GPU")
            config = DATA_CONFIG_MAP["panda_omron"]
            self.policy = Gr00tPolicy(
                model_path=str(checkpoint), embodiment_tag="new_embodiment",
                modality_config=config.modality_config(), modality_transform=config.transform(),
                denoising_steps=4, device="cuda",
            )
            self.identity.update({"data_config": "panda_omron", "denoising_steps": 4,
                                  "torch": torch.__version__, "gpu": torch.cuda.get_device_name()})
        else:
            import jax
            from openpi.policies import policy_config
            from openpi.training import config
            if not any(device.platform == "gpu" for device in jax.devices()):
                raise RuntimeError("pi05 feasibility requires a JAX GPU device")
            self.policy = policy_config.create_trained_policy(
                config.get_config("pi05_pretrain_human300"), checkpoint,
            )
            gpu = next(device for device in jax.devices() if device.platform == "gpu")
            self.identity.update({"training_config": "pi05_pretrain_human300", "jax": jax.__version__,
                                  "gpu": str(gpu)})

    def reset(self, seed=None):
        if seed is not None:
            if type(seed) is not int or not 0 <= seed < 2**32:
                raise ValueError("seed must be an integer in [0, 2**32)")
            self.np.random.seed(seed)
            random.seed(seed)
            if self.backend == "groot":
                import torch
                torch.manual_seed(seed)
                torch.cuda.manual_seed_all(seed)
            else:
                import jax
                # Pinned upstream exposes no seed setter. Its Policy._rng is the
                # actual JAX action sampling stream; global numpy seeding is insufficient.
                self.policy._rng = jax.random.key(seed)
        # These pinned backends are feed-forward across calls. Queue state lives
        # in the runner. A future recurrent backend needs an explicit reset here.

    def predict(self, payload, instruction):
        obs = decode_observation(payload)
        if not isinstance(instruction, str) or not instruction:
            raise ValueError("instruction must be nonempty")
        if self.backend == "groot":
            values = {key: value[None, ...] for key, value in obs.items()}
            values["annotation.human.task_description"] = [instruction]
            output = self.policy.get_action(values)
            if set(output) != set(ACTION_DIMS):
                raise ValueError("GR00T action output schema changed")
            arrays = {key: self.np.asarray(output[key]) for key in ACTION_DIMS}
            for key, dim in ACTION_DIMS.items():
                if arrays[key].ndim != 2 or arrays[key].shape[1] != dim or arrays[key].shape[0] < 16:
                    raise ValueError(f"GR00T action shape mismatch: {key}")
            chunk = [{key: arrays[key][i].tolist() for key in ACTION_DIMS} for i in range(16)]
        else:
            from openpi_client import image_tools
            resize = lambda value: image_tools.convert_to_uint8(image_tools.resize_with_pad(value, 224, 224))
            state_order = (
                "state.end_effector_position_relative", "state.end_effector_rotation_relative",
                "state.base_position", "state.base_rotation", "state.gripper_qpos",
            )
            output = self.policy.infer({
                "observation/image": resize(obs[CAMERAS[0]]),
                "observation/right_image": resize(obs[CAMERAS[1]]),
                "observation/wrist_image": resize(obs[CAMERAS[2]]),
                "observation/state": self.np.concatenate([obs[key] for key in state_order]),
                "prompt": instruction,
            })["actions"]
            if output.ndim != 2 or output.shape[0] < 5 or output.shape[1] != 12:
                raise ValueError("pi05 must produce at least five 12-dimensional actions")
            chunk = []
            for action in output[:5]:
                offset, converted = 0, {}
                for key, dim in ACTION_DIMS.items():
                    converted[key] = action[offset:offset + dim].tolist()
                    offset += dim
                chunk.append(converted)
        return [validate_action(action) for action in chunk]


def serve(policy, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, payload):
            encoded = json.dumps(payload, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            self.respond(200, policy.identity) if self.path == "/health" else self.respond(404, {"error": "unknown endpoint"})

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4_000_000:
                    raise ValueError("invalid request size")
                value = json.loads(self.rfile.read(size))
                if self.path == "/reset":
                    if set(value) - {"seed"}:
                        raise ValueError("unexpected reset fields")
                    policy.reset(value.get("seed"))
                    self.respond(200, {"ok": True})
                elif self.path == "/infer":
                    self.respond(200, {"actions": policy.predict(value["observation"], value["instruction"])})
                else:
                    self.respond(404, {"error": "unknown endpoint"})
            except Exception as error:
                self.respond(500, {"error": f"{type(error).__name__}: {error}"})
    # Single worker serves one episode stream at a time; do not share it between runners.
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(json.dumps({"ready": True, "port": port, **policy.identity}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("groot", "pi05"), required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(LearnedPolicy(args.backend, args.checkpoint), args.port)


if __name__ == "__main__":
    main()
