"""CPU sweep over the dials the real data does not pin down: the hesitant VLA's restart break probability, the chance a
restart undoes a completion, and the wording surcharge. For each setting it refits the best rule per VLA and the best
single rule, and reports whether the qualitative conclusions hold. No model calls."""
import json
import os
import subprocess
import sys
from pathlib import Path

SETTINGS = [("base", {}), ("z_hesitant 0.01", {"SIM_Z_HESITANT": "0.01"}), ("z_hesitant 0.05", {"SIM_Z_HESITANT": "0.05"}),
            ("z_hesitant 0.30", {"SIM_Z_HESITANT": "0.30"}), ("q_undo 0.1", {"SIM_UNDO_PROB": "0.1"}),
            ("q_undo 0.5", {"SIM_UNDO_PROB": "0.5"}), ("z_w 0.15", {"SIM_WORDING_BREAK": "0.15"})]


def rule_text(r):
    return f"F({r['t0']},{r['every']},{'never' if r['tau'] is None else r['tau']},{r['rule']})"


def main():
    out, rows = Path("runs/sim/sensitivity"), []
    out.mkdir(parents=True, exist_ok=True)
    for name, env in SETTINGS:
        path = out / (name.replace(" ", "_") + ".json")
        subprocess.run([sys.executable, "scripts/sim_calibrate.py", "--workers", "6", "--train", "500", "--heldout", "1000",
                        "--output", str(path)], env={**os.environ, **env}, capture_output=True, check=True)
        r = json.loads(path.read_text())
        adapt = {p: r["heldout"][p]["pi_star"]["utility"] - r["heldout"][p]["pi_pool"]["utility"] for p in r["heldout"]}
        restarts = {p: r["best"][p]["tau"] is not None for p in r["best"]}
        rows.append((name, r["best"], adapt, restarts))
        print(f"{name:16s} adaptation " + " ".join(f"{p[:3]}={v:+.3f}" for p, v in adapt.items()) + " | best rules: "
              + " ".join(f"{p[:3]}={rule_text(r['best'][p])}" for p in r["best"]), flush=True)
    (out / "summary.json").write_text(json.dumps([{"setting": n, "best": b, "adaptation": a} for n, b, a, _ in rows], indent=1) + "\n")
    print("\nbest rule for the hesitant VLA restarts?", {n: re["hesitant"] for n, _, _, re in rows})
    print("adaptation positive for every VLA in every setting?", all(v > 0 for _, _, a, _ in rows for v in a.values()))


if __name__ == "__main__":
    main()
