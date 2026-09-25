import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from robot_benchmark.policy_worker import EXPECTED_CHECKPOINTS, verify_checkpoint
from robot_benchmark.records import digest


class CheckpointManifestTests(unittest.TestCase):
    def test_downloader_specs_match_worker_canonical_digests(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "download_checkpoint.py"
        spec = importlib.util.spec_from_file_location("checkpoint_downloader", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for backend, files in module.EXPECTED_BY_BACKEND.items():
            repo, revision, subdir = module.load_source(backend)
            canonical = {
                "repo_id": repo,
                "revision": revision,
                "subdir": subdir,
                "files": [
                    {"path": name, "size": files[name]["size"], "sha256": files[name]["sha256"]}
                    for name in sorted(files)
                ],
            }
            self.assertEqual(digest(canonical), EXPECTED_CHECKPOINTS[backend]["manifest_sha256"])

    def test_verifies_size_and_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = root / "checkpoint-120000"
            checkpoint.mkdir()
            data = b"fixed checkpoint bytes"
            (checkpoint / "weights.bin").write_bytes(data)
            manifest = {
                "repo_id": "robocasa/robocasa365_checkpoints",
                "revision": "c484448aba1a9b60a04c9b0ca117241518ea69f3",
                "subdir": "gr00t_n1-5/multitask_learning/checkpoint-120000",
                "files": [{
                    "path": "weights.bin",
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }],
            }
            checkpoint.with_name("checkpoint-120000.manifest.json").write_text(json.dumps(manifest))

            self.assertEqual(verify_checkpoint(checkpoint), manifest)

            (checkpoint / "weights.bin").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "verification failed"):
                verify_checkpoint(checkpoint)

    def test_rejects_wrong_backend_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = root / "checkpoint-120000"
            checkpoint.mkdir()
            outside = root / "outside.bin"
            outside.write_bytes(b"data")
            manifest = {
                "repo_id": "robocasa/robocasa365_checkpoints",
                "revision": "c484448aba1a9b60a04c9b0ca117241518ea69f3",
                "subdir": "gr00t_n1-5/multitask_learning/checkpoint-120000",
                "files": [{
                    "path": "../outside.bin",
                    "size": 4,
                    "sha256": hashlib.sha256(b"data").hexdigest(),
                }],
            }
            checkpoint.with_name("checkpoint-120000.manifest.json").write_text(json.dumps(manifest))

            with self.assertRaisesRegex(ValueError, "pinned pi05"):
                verify_checkpoint(checkpoint, "pi05")
            with self.assertRaisesRegex(ValueError, "escapes"):
                verify_checkpoint(checkpoint)

    def test_backend_requires_complete_canonical_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = root / "checkpoint-120000"
            checkpoint.mkdir()
            data = b"one valid but incomplete file"
            (checkpoint / "config.json").write_bytes(data)
            manifest = {
                "repo_id": "robocasa/robocasa365_checkpoints",
                "revision": "c484448aba1a9b60a04c9b0ca117241518ea69f3",
                "subdir": "gr00t_n1-5/multitask_learning/checkpoint-120000",
                "files": [{
                    "path": "config.json",
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }],
            }
            checkpoint.with_name("checkpoint-120000.manifest.json").write_text(json.dumps(manifest))

            with self.assertRaisesRegex(ValueError, "complete pinned groot file set"):
                verify_checkpoint(checkpoint, "groot")


if __name__ == "__main__":
    unittest.main()
