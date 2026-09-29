"""Copy a running Prime experiment's append-only records into the project root."""
import json
from pathlib import Path
import subprocess
import sys
import time


def sync(config):
    if time.time() >= config["deadline_unix"]:
        return "deadline_passed"
    destination = Path(config["local_runs"])
    destination.mkdir(parents=True, exist_ok=True)
    ssh = (f"ssh -i {config['ssh_key']} -o BatchMode=yes "
           "-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10")
    source = f"{config['remote']}:{config['remote_root']}/runs/"
    completed = subprocess.run(
        ["rsync", "-a", "--partial", "--timeout=120", "-e", ssh,
         source, str(destination) + "/"],
        capture_output=True, text=True, timeout=240,
    )
    if completed.returncode:
        raise RuntimeError(f"rsync exited {completed.returncode}: {completed.stderr[-500:]}")
    return "synced"


def main():
    config_path = Path(sys.argv[1])
    config = json.loads(config_path.read_text())
    started = time.time()
    try:
        outcome = sync(config)
    except Exception as error:
        outcome = f"error:{type(error).__name__}:{error}"
    with config_path.with_suffix(".log").open("a") as stream:
        stream.write(json.dumps({"at_unix": started, "seconds": time.time() - started,
                                 "outcome": outcome}) + "\n")
    return 1 if outcome.startswith("error:") else 0


if __name__ == "__main__":
    raise SystemExit(main())
