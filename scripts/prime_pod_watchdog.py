"""Terminate this project's Prime pod after a recorded deadline.

Install this script as a user launchd job before creating the pod. It relies on
the local Prime CLI configuration and never stores an API key in the project.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def check(config, now=None, run=subprocess.run):
    now = time.time() if now is None else now
    if now < config["deadline_unix"]:
        return "before_deadline"
    env = dict(os.environ, PRIME_TEAM_ID=config["team_id"])
    prime = config["prime_path"]
    matches = []
    offset = 0
    while True:
        listed = run([prime, "pods", "list", "--limit", "100", "--offset", str(offset),
                      "--output", "json", "--plain"],
                     capture_output=True, text=True, timeout=30, env=env, check=True)
        page = json.loads(listed.stdout)
        pods = page["pods"]
        matches.extend(pod for pod in pods if pod["name"] == config["pod_name"])
        offset += len(pods)
        if len(pods) < 100 or offset >= page.get("total_count", offset):
            break
    if len(matches) > 1:
        raise RuntimeError("multiple pods match the watchdog's exact name")
    if not matches:
        return "pod_absent"
    pod_id = matches[0]["id"]
    if config.get("pod_id") and pod_id != config["pod_id"]:
        raise RuntimeError("matching pod name has an unexpected ID")
    status = run([prime, "pods", "status", pod_id, "--output", "json", "--plain"],
                 capture_output=True, text=True, timeout=30, env=env, check=True)
    detail = json.loads(status.stdout)
    if (detail.get("id"), detail.get("name"), detail.get("team_id")) != (
        pod_id, config["pod_name"], config["team_id"]
    ):
        raise RuntimeError("pod status identity or team does not match watchdog target")
    run([prime, "pods", "terminate", pod_id, "--yes", "--plain"],
        capture_output=True, text=True, timeout=30, env=env, check=True)
    return f"terminate_requested:{pod_id}"


def main():
    config_path = Path(sys.argv[1])
    config = json.loads(config_path.read_text())
    try:
        outcome = check(config)
    except Exception as error:
        outcome = f"error:{type(error).__name__}:{error}"
    with config_path.with_suffix(".log").open("a") as stream:
        stream.write(json.dumps({"at_unix": time.time(), "outcome": outcome}) + "\n")
    return 1 if outcome.startswith("error:") else 0


if __name__ == "__main__":
    raise SystemExit(main())
