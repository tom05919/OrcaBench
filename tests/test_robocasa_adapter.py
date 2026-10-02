"""RoboCasa adapter logic with fake simulator objects; no simulator is imported."""

import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock

from robot_benchmark.adapters.robocasa import RoboCasaEnvironment


def make_env(task="OpenDrawer", success=True, description=" Open the left drawer. "):
    env = object.__new__(RoboCasaEnvironment)
    raw = SimpleNamespace(_check_success=lambda: success)
    env.env = SimpleNamespace(unwrapped=SimpleNamespace(env=raw))
    env.task = task
    env.obs = {"annotation.human.task_description": description}
    return env


def fake_predicates(value):
    module = types.ModuleType("robot_benchmark.tasks.predicates")
    def task_predicates(task, raw):
        if isinstance(value, Exception):
            raise value
        return dict(value)
    module.task_predicates = task_predicates
    return mock.patch.dict(sys.modules, {
        "robot_benchmark.tasks": types.ModuleType("robot_benchmark.tasks"),
        "robot_benchmark.tasks.predicates": module,
    })


class NativeInstructionTests(unittest.TestCase):
    def test_returns_stripped_task_description(self):
        self.assertEqual(make_env().native_instruction(), "Open the left drawer.")

    def test_blank_description_is_rejected(self):
        with self.assertRaises(ValueError):
            make_env(description="   ").native_instruction()


class GenericEvaluateTests(unittest.TestCase):
    def test_success_is_merged_with_task_predicates(self):
        with fake_predicates({"kettle_on_stove": True}):
            self.assertEqual(make_env(success=0).evaluate(), {"success": False, "kettle_on_stove": True})

    def test_predicate_error_is_isolated_from_official_success(self):
        with fake_predicates(KeyError("burner")):
            self.assertEqual(make_env(success=1).evaluate(), {"success": True, "predicate_error": "KeyError: 'burner'"})

    def test_official_checker_error_is_not_caught(self):
        env = make_env()
        env.env.unwrapped.env._check_success = lambda: 1 / 0
        with fake_predicates({"kettle_on_stove": True}), self.assertRaises(ZeroDivisionError):
            env.evaluate()

    def test_predicate_named_success_is_rejected(self):
        with fake_predicates({"success": True}), self.assertRaises(RuntimeError):
            make_env().evaluate()


if __name__ == "__main__":
    unittest.main()
