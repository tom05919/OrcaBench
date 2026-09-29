"""Arm an independent two-hour macOS launchd guard before renting a Prime pod."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def arm(pod_name, team_id, minutes=120):
    if not pod_name.startswith("robot-cereal-") or not team_id or minutes < 1:
        raise ValueError("invalid watchdog target or duration")
    prime = shutil.which("prime")
    if not prime:
        raise RuntimeError("Prime CLI is not installed")
    folder = PROJECT_ROOT / "runs" / "prime_watchdog" / pod_name
    folder.mkdir(parents=True, exist_ok=False)
    config_path = folder / "config.json"
    config = {"pod_name": pod_name, "team_id": team_id,
              "prime_path": prime, "deadline_unix": time.time() + minutes * 60}
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    label = f"ai.codex.robot-benchmark.{pod_name}"
    plist = {"Label": label,
             "ProgramArguments": ["/usr/bin/python3", str(PROJECT_ROOT / "scripts" / "prime_pod_watchdog.py"), str(config_path)],
             "RunAtLoad": True, "StartInterval": 30,
             "StandardOutPath": str(folder / "launchd.out"),
             "StandardErrorPath": str(folder / "launchd.err")}
    plist_path = folder / "watchdog.plist"
    with plist_path.open("wb") as stream:
        plistlib.dump(plist, stream)
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootstrap", domain, str(plist_path)], check=True)
    subprocess.run(["launchctl", "print", f"{domain}/{label}"],
                   check=True, stdout=subprocess.DEVNULL)
    # Avoid idle sleep if the Codex app exits. Closing the laptop lid or losing
    # network can still delay termination, so verify the pod is gone afterward.
    awake = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-t", str(minutes * 60 + 300)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    (folder / "caffeinate.pid").write_text(f"{awake.pid}\n")
    print(json.dumps({"pod_name": pod_name, "deadline_unix": config["deadline_unix"],
                      "watchdog_label": label, "watchdog_dir": str(folder)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pod-name", required=True)
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--minutes", type=int, default=120)
    args = parser.parse_args()
    arm(args.pod_name, args.team_id, args.minutes)
