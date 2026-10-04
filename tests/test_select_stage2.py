import unittest

from scripts.select_stage2 import select


class SelectStage2Tests(unittest.TestCase):
    def test_first_successes_in_ascending_order_per_task(self):
        rows = [("A", 1001, 0, True), ("A", 1000, 1, True), ("A", 1000, 0, False), ("A", 1002, 0, True),
                ("B", 1000, 0, False), ("B", 1000, 1, False), ("C", 1002, 1, True)]
        self.assertEqual(select(rows, 2), {"A": [(1000, 1), (1001, 0)], "C": [(1002, 1)]})

    def test_task_without_success_is_absent(self):
        self.assertEqual(select([("B", 1000, 0, False)], 2), {})


if __name__ == "__main__":
    unittest.main()
