"""Append-only episode records. Evaluator records never enter model payloads."""
import base64
import hashlib
import json
from pathlib import Path


def jsonable(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(v) for v in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(jsonable(value), sort_keys=True, allow_nan=False).encode()).hexdigest()


class Records:
    def __init__(self, path: Path, manifest: dict):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=False)
        (self.path / "evaluator").mkdir(mode=0o700)
        (self.path / "frames").mkdir()
        (self.path / "video_frames").mkdir()
        self.write("manifest.json", manifest)

    def write(self, name, value):
        (self.path / name).write_text(json.dumps(jsonable(value), indent=2, allow_nan=False) + "\n")

    def append(self, name, value):
        with (self.path / name).open("a") as stream:
            stream.write(json.dumps(jsonable(value), allow_nan=False) + "\n")

    def observation(self, index, value):
        # Archive camera bytes separately to avoid repeating base64 in JSONL.
        stored = dict(value)
        stored["images"] = {}
        for camera, url in value["images"].items():
            name = f"frames/{index:04d}-{camera.removeprefix('video.')}.png"
            (self.path / name).write_bytes(base64.b64decode(url.split(",", 1)[1], validate=True))
            stored["images"][camera] = name
        self.append("observations.jsonl", stored)

    def video_frame(self, step, data_url):
        if not isinstance(data_url, str) or not data_url.startswith("data:image/png;base64,"):
            raise ValueError("recording frame must be a PNG data URL")
        target = self.path / "video_frames" / f"{step:06d}.png"
        target.write_bytes(base64.b64decode(data_url.split(",", 1)[1], validate=True))
