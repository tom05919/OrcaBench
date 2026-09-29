import copy
import math
import unittest

from robot_benchmark.contracts import (
    ACTION_DIMS,
    CAMERAS,
    PROPRIO,
    Limits,
    Skill,
    sensor_payload,
    validate_action,
    validate_decision,
)

from tests.fakes import SENTINEL, action


class LimitsContractTests(unittest.TestCase):
    def test_budgets_are_positive_non_boolean_integers(self):
        self.assertEqual(Limits(1, 2, 3), Limits(max_steps=1, max_decisions=2, max_interval=3))
        for field in ("max_steps", "max_decisions", "max_interval"):
            for invalid in (0, -1, True, 1.0):
                values = {"max_steps": 1, "max_decisions": 1, "max_interval": 1}
                values[field] = invalid
                with self.subTest(field=field, invalid=invalid):
                    with self.assertRaisesRegex(ValueError, "positive integers"):
                        Limits(**values)


class DecisionContractTests(unittest.TestCase):
    def setUp(self):
        self.limits = Limits(10, 10, 3)

    def test_each_operation_requires_its_exact_schema(self):
        valid = [
            {"op": "run_policy", "prompt": "Pick either object.", "steps": 1},
            {"op": "run_policy", "steps": 3},
            {"op": "complete"},
        ]
        for decision in valid:
            with self.subTest(decision=decision):
                self.assertEqual(validate_decision(decision, self.limits), decision)

        invalid = [
            None,
            [],
            {"op": 1},
            {"op": "unknown"},
            {"op": "complete", "steps": 1},
            {"op": "run_policy"},
            {"op": "run_policy", "steps": 1, "skill": "pick"},
            {"op": "run_policy", "steps": 1, "prompt": "ok", "extra": True},
        ]
        for decision in invalid:
            with self.subTest(decision=decision):
                with self.assertRaises(ValueError):
                    validate_decision(decision, self.limits)

    def test_step_count_rejects_booleans_and_out_of_range_values(self):
        for value in (True, False, 0, 4, 1.0):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "steps must be an integer"):
                    validate_decision({"op": "run_policy", "steps": value}, self.limits)

    def test_prompt_must_be_nonblank_text_within_the_length_limit(self):
        for value in (None, True, 1, "", " \t\n", "x" * 513):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "prompt"):
                    validate_decision(
                        {"op": "run_policy", "prompt": value, "steps": 1},
                        self.limits,
                    )

        prompt = "  preserve my spacing exactly  "
        self.assertEqual(
            validate_decision(
                {"op": "run_policy", "prompt": prompt, "steps": 1},
                self.limits,
            )["prompt"],
            prompt,
        )


class ActionContractTests(unittest.TestCase):
    def test_action_requires_exact_keys_dimensions_and_finite_real_scalars(self):
        valid = action(2.5)
        self.assertEqual(validate_action(valid), valid)

        cases = []
        missing = copy.deepcopy(valid)
        missing.pop(next(iter(ACTION_DIMS)))
        cases.append(missing)
        extra = copy.deepcopy(valid)
        extra["reward"] = [1.0]
        cases.append(extra)
        wrong_dimension = copy.deepcopy(valid)
        wrong_dimension["action.gripper_close"] = [0.0, 0.0]
        cases.append(wrong_dimension)
        for bad_scalar in (True, math.nan, math.inf, "0"):
            bad = copy.deepcopy(valid)
            bad["action.gripper_close"] = [bad_scalar]
            cases.append(bad)

        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_action(value)


class ObservationProjectionTests(unittest.TestCase):
    def test_sensor_projection_allowlists_fields_and_copies_nested_vectors(self):
        sensor = {
            "images": {
                **{name: "data:image/png;base64,AA==" for name in CAMERAS},
                "video.secret": SENTINEL,
            },
            "proprio": {
                **{name: [0.0] * dim for name, dim in PROPRIO.items()},
                "state.secret": [SENTINEL],
            },
            "reward": SENTINEL,
            "nested": {"object_positions": SENTINEL},
        }

        projected = sensor_payload(sensor)

        self.assertEqual(set(projected), {"images", "proprio"})
        self.assertEqual(set(projected["images"]), set(CAMERAS))
        self.assertEqual(set(projected["proprio"]), set(PROPRIO))
        self.assertNotIn(SENTINEL, repr(projected))
        first = next(iter(PROPRIO))
        projected["proprio"][first][0] = 99.0
        self.assertEqual(sensor["proprio"][first][0], 0.0)

    def test_sensor_projection_rejects_non_png_or_invalid_proprioception(self):
        images = {name: "data:image/png;base64,AA==" for name in CAMERAS}
        proprio = {name: [0.0] * dim for name, dim in PROPRIO.items()}
        bad_images = dict(images)
        bad_images[CAMERAS[0]] = "data:image/jpeg;base64,AA=="
        with self.assertRaisesRegex(ValueError, "PNG data URLs"):
            sensor_payload({"images": bad_images, "proprio": proprio})

        bad_proprio = copy.deepcopy(proprio)
        bad_proprio[next(iter(PROPRIO))][0] = True
        with self.assertRaisesRegex(ValueError, "invalid proprioception"):
            sensor_payload({"images": images, "proprio": bad_proprio})

    def test_reference_prompt_public_value_is_a_deep_copy(self):
        performance = {"metric": {"trials": [1]}}
        reference = Skill("id", "instruction", "description", performance)
        public = reference.public()
        public["performance"]["metric"]["trials"].append(2)
        self.assertEqual(public["prompt"], "instruction")
        self.assertEqual(reference.performance, {"metric": {"trials": [1]}})


if __name__ == "__main__":
    unittest.main()
