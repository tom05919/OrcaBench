import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "analyze_stage5.py"


def load_script():
    spec = importlib.util.spec_from_file_location("analyze_stage5", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(module)
    return module


def write_episode(root, arm, task, scene, policy, status, events):
    folder = root / "groot" / arm / task / f"seed-{scene}-p{policy}-{arm}"
    (folder / "evaluator").mkdir(parents=True)
    (folder / "result.json").write_text(json.dumps({
        "scene_seed": scene, "policy_seed": policy, "steps": events[-1]["step"], "status": status,
        "success": status == "success", "infrastructure_error": status == "infrastructure_error"}))
    (folder / "evaluator" / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def pan(step, plate, stove, success=False):
    # pan_off_stove is a clock trigger: logged, but never task progress.
    return {"step": step, "success": success, "vegetables_on_plate": plate, "pan_on_stove": stove,
            "pan_off_stove": not stove, "food_untouched": True}


class CeilingTests(unittest.TestCase):
    def test_pairs_rescues_harms_and_where_failures_ended(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start = pan(0, False, True)
            fail, win = "step_budget_exhausted", "success"
            # Pair 1000/0: plain fails, sequencer succeeds (a rescue).
            write_episode(root, "reference", "PanTransfer", 1000, 0, fail, [start, pan(100, False, False)])
            write_episode(root, "sequencer", "PanTransfer", 1000, 0, win, [start, pan(100, True, True, True)])
            # Pair 1001/0: plain fails; the sequencer dumps the vegetables but never returns the pan (1 step done).
            write_episode(root, "reference", "PanTransfer", 1001, 0, fail, [start, pan(100, False, True)])
            write_episode(root, "sequencer", "PanTransfer", 1001, 0, fail, [start, pan(100, True, False)])
            # Pair 1002/0: plain succeeds, the sequencer fails with the pan still on the stove (0 steps done: the
            # pan step is true from step 0 but comes second).
            write_episode(root, "reference", "PanTransfer", 1002, 0, win, [start, pan(100, True, True, True)])
            write_episode(root, "sequencer", "PanTransfer", 1002, 0, fail, [start, pan(100, False, True)])
            # 1003/0: the sequencer hit a different scene, so the pair is not counted.
            write_episode(root, "reference", "PanTransfer", 1003, 0, "success", [start, pan(100, True, True, True)])
            write_episode(root, "sequencer", "PanTransfer", 1003, 0, "infrastructure_error", [start])
            # 1003/1: a sequencer episode without a usable plain partner.
            write_episode(root, "sequencer", "PanTransfer", 1003, 1, "success", [start, pan(100, True, True, True)])
            report = load_script().ceiling(root, ["groot", "groot_u30"])
        self.assertEqual(list(report), ["groot"])
        task = report["groot"]["PanTransfer"]
        self.assertEqual({k: task[k] for k in ("pairs", "plain_successes", "sequencer_successes", "rescues", "harms",
                                                "steps_done_on_sequencer_failures", "unpaired_sequencer_episodes")},
                         {"pairs": 3, "plain_successes": 1, "sequencer_successes": 1, "rescues": 1, "harms": 1,
                          "steps_done_on_sequencer_failures": [0, 1], "unpaired_sequencer_episodes": 1})
        self.assertEqual(task["reading"], "not shown")

    def test_reading_needs_two_more_sequencer_successes(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start = pan(0, False, True)
            for scene in (1000, 1001):
                write_episode(root, "reference", "PanTransfer", scene, 0, "step_budget_exhausted", [start])
                write_episode(root, "sequencer", "PanTransfer", scene, 0, "success",
                              [start, pan(100, True, True, True)])
            reading = module.ceiling(root, ["groot"])["groot"]["PanTransfer"]["reading"]
        self.assertEqual(reading, "re-prompting can help")

    def test_triggers_are_not_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_episode(root, "reference", "PanTransfer", 1000, 0, "step_budget_exhausted",
                          [pan(0, False, True), pan(100, False, False)])
            row = load_script().episode(next((root / "groot" / "reference" / "PanTransfer").iterdir()))
        self.assertEqual(row["subgoals"], {"vegetables_on_plate": None})


if __name__ == "__main__":
    unittest.main()
