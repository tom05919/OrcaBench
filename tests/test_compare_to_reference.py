import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_to_reference.py"


def load_script():
    spec = importlib.util.spec_from_file_location("compare_to_reference", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_episode(folder, kind, result, decisions=None):
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({
        "artifact_type": "episode", "kind": kind, "task": "OpenDrawer", "scene_seed": 1000, "policy_seed": 0,
    }))
    (folder / "result.json").write_text(json.dumps(result))
    if decisions is not None:
        (folder / "decisions.jsonl").write_text("".join(json.dumps(d) + "\n" for d in decisions))


class CompareToReferenceTests(unittest.TestCase):
    def test_infrastructure_error_episode_is_counted_not_described(self):
        finished = {"status": "budget_exhausted", "success": False, "steps": 750, "model_calls": 2, "prompt_submissions": 1,
                    "prompt_restarts": 0, "prompt_changes": 0, "discarded_actions": 0, "wall_seconds": 90.0}
        # A start-state mismatch ends before the first decision and never writes decisions.jsonl.
        mismatch = {"status": "infrastructure_error", "success": False, "steps": 0, "model_calls": 0}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_episode(root / "reference" / "a", "diagnostic_reference", dict(finished, model_calls=0))
            write_episode(root / "model" / "mismatch", "llm_development", mismatch)
            write_episode(root / "model" / "ran", "llm_development", finished,
                          decisions=[{"accepted": True}, {"accepted": False}])
            output = root / "rows.json"
            argv = ["compare_to_reference.py", "--reference-root", str(root / "reference"),
                    "--model-root", str(root / "model"), "--output", str(output)]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
                self.assertEqual(load_script().main(), 0)
            rows = json.loads(output.read_text())
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["status"], rows[0]["reference"], rows[0]["rejected_replies"]), ("budget_exhausted", "fail", 1))
        self.assertIn("infrastructure errors not compared 1", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
