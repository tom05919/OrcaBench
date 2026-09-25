"""Source-level checks of the pinned goal predicate; no simulator is run here."""

import ast
import copy
import hashlib
import itertools
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/cereal_and_bowl.py"
LOCK = ROOT / "configs/sources.lock.json"


class PinnedCerealAndBowlSourceTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SOURCE.is_file(), "the pinned source-contract fixture must be checked in")

    def test_checked_in_source_matches_the_locked_digest(self):
        lock = json.loads(LOCK.read_text())
        entry = lock["repositories"]["robocasa"]["files"][
            "robocasa/environments/kitchen/composite/snack_preparation/cereal_and_bowl.py"
        ]
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), entry["sha256"])

    def test_actual_check_success_ast_requires_both_objects_and_closed_cabinet(self):
        tree = ast.parse(SOURCE.read_text(), filename=str(SOURCE))
        class_node = next(
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "CerealAndBowl"
        )
        method = next(
            node
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_check_success"
        )
        module = ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(method)], type_ignores=[]))

        class ObjectUtilsStandIn:
            @staticmethod
            def check_obj_fixture_contact(task, object_name, fixture):
                self.assertIs(fixture, task.counter)
                return task.object_contacts[object_name]

        namespace = {"OU": ObjectUtilsStandIn}
        exec(compile(module, str(SOURCE), "exec"), namespace)
        check_success = namespace["_check_success"]

        class CabinetStandIn:
            def __init__(self, closed):
                self.closed = closed

            def is_closed(self, env):
                return self.closed

        class TaskStandIn:
            pass

        for cereal, bowl, cabinet_closed in itertools.product((False, True), repeat=3):
            with self.subTest(cereal=cereal, bowl=bowl, cabinet_closed=cabinet_closed):
                task = TaskStandIn()
                task.counter = object()
                task.object_contacts = {"cereal": cereal, "bowl": bowl}
                task.cab = CabinetStandIn(cabinet_closed)
                self.assertIs(
                    check_success(task),
                    cereal and bowl and cabinet_closed,
                    "source predicate must require all three upstream conditions",
                )


if __name__ == "__main__":
    unittest.main()
