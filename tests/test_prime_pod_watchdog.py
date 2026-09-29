import json
import unittest
from subprocess import CompletedProcess

from scripts.prime_pod_watchdog import check


class PrimePodWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.config = {"deadline_unix": 100, "team_id": "team-test",
                       "pod_name": "cereal-test-unique", "prime_path": "/fake/prime"}
        self.calls = []

    def fake_run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command[1:3] == ["pods", "list"]:
            return CompletedProcess(command, 0, json.dumps({"pods": [
                {"id": "target", "name": "cereal-test-unique"},
                {"id": "other", "name": "someone-else"}]}), "")
        if command[1:3] == ["pods", "status"]:
            return CompletedProcess(command, 0, json.dumps({
                "id": "target", "name": "cereal-test-unique", "team_id": "team-test"}), "")
        return CompletedProcess(command, 0, "terminated", "")

    def test_does_nothing_before_deadline(self):
        self.assertEqual(check(self.config, now=99, run=self.fake_run), "before_deadline")
        self.assertEqual(self.calls, [])

    def test_terminates_only_exact_named_pod_after_deadline(self):
        self.assertEqual(check(self.config, now=100, run=self.fake_run),
                         "terminate_requested:target")
        self.assertEqual(self.calls[2][0],
                         ["/fake/prime", "pods", "terminate", "target", "--yes", "--plain"])
        self.assertEqual(self.calls[2][1]["env"]["PRIME_TEAM_ID"], "team-test")

    def test_rejects_id_mismatch(self):
        self.config["pod_id"] = "different"
        with self.assertRaisesRegex(RuntimeError, "unexpected ID"):
            check(self.config, now=100, run=self.fake_run)
        self.assertEqual(len(self.calls), 1)

    def test_rejects_wrong_team_before_termination(self):
        self.config["team_id"] = "another-team"
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            check(self.config, now=100, run=self.fake_run)
        self.assertEqual([call[0][2] for call in self.calls], ["list", "status"])

    def test_finds_target_on_second_page(self):
        def paged_run(command, **kwargs):
            self.calls.append((command, kwargs))
            if command[1:3] == ["pods", "list"]:
                offset = int(command[command.index("--offset") + 1])
                pods = ([{"id": str(i), "name": f"other-{i}"} for i in range(100)]
                        if offset == 0 else [{"id": "target", "name": "cereal-test-unique"}])
                return CompletedProcess(command, 0, json.dumps({"pods": pods, "total_count": 101}), "")
            return self.fake_run(command, **kwargs)

        self.assertEqual(check(self.config, now=100, run=paged_run),
                         "terminate_requested:target")
        self.assertEqual(self.calls[1][0][self.calls[1][0].index("--offset") + 1], "100")


if __name__ == "__main__":
    unittest.main()
