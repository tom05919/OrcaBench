import unittest

from scripts.probe_completion import pick_steps


class PickStepsTests(unittest.TestCase):
    def test_spans_before_during_and_after_a_success_that_is_later_lost(self):
        timeline = [(s, 200 <= s <= 400) for s in range(0, 601)]
        picks = pick_steps(timeline, 8, 600)
        self.assertEqual([l for l, _ in picks], ["before", "before", "during", "during", "during", "after_lost", "end"])
        steps = dict((l + str(i), s) for i, (l, s) in enumerate(picks))
        self.assertLess(steps["before0"], steps["before1"])
        self.assertTrue(all(timeline[s][1] for l, s in picks if l == "during"))
        self.assertTrue(all(not timeline[s][1] for l, s in picks if l in ("before", "after_lost", "end")))

    def test_an_episode_that_never_succeeds_is_spread_over_the_run(self):
        timeline = [(s, False) for s in range(0, 401)]
        self.assertEqual([s for _, s in pick_steps(timeline, 8, 400)], [100, 200, 300, 400])

    def test_the_per_episode_limit_and_distinct_steps_hold(self):
        timeline = [(s, s >= 5) for s in range(0, 11)]
        picks = pick_steps(timeline, 3, 10)
        self.assertLessEqual(len(picks), 3)
        self.assertEqual(len({s for _, s in picks}), len(picks))


if __name__ == "__main__":
    unittest.main()
