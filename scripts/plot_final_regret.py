#!/usr/bin/env python3
"""Draw the main-result slide figure: each supervisor's paired held-out regret against the fixed declaration rule, with
its 95% clustered interval, in the presentation deck's colors.

The numbers are the reported results in docs/final_results.md: Opus from W2 (#8), Sonnet from W3 (`670e075`,
docs/session_mode.md), Kimi K3 from results/w1/addon_kimi_score.txt.

  python3 scripts/plot_final_regret.py   # writes results/w1/figures/regret_vs_timer.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "w1" / "figures" / "regret_vs_timer.png"

# (label, detail, regret, ci95)
ROWS = [
    ("Opus 5.5", "63 episodes · scenes 1000–1002", 0.053, (0.007, 0.105)),
    ("Sonnet 5.5", "83 episodes · scenes 1000–1003", 0.071, (0.028, 0.119)),
    ("Kimi K3 (add-on)", "42 episodes · scenes 1000–1001", 0.070, (0.014, 0.134)),
]

BACKGROUND, GRID, TEXT, MUTED, ACCENT = "#182339", "#2a3448", "#f5f4f0", "#9aa3b5", "#e4a46a"


def main():
    plt.rcParams["font.family"] = ["Helvetica Neue", "Helvetica", "DejaVu Sans"]
    fig, ax = plt.subplots(figsize=(12, 4.2), dpi=200)
    fig.patch.set_facecolor(BACKGROUND)
    ax.set_facecolor(BACKGROUND)

    ys = list(range(len(ROWS)))[::-1]
    for y, (label, detail, mean, (low, high)) in zip(ys, ROWS):
        ax.barh(y, mean, height=0.5, color=ACCENT, alpha=0.75 if "add-on" in label else 1.0, zorder=2)
        ax.errorbar(mean, y, xerr=[[mean - low], [high - mean]], fmt="none", ecolor=TEXT, elinewidth=2,
                    capsize=7, capthick=2, zorder=3)
        ax.text(high + 0.004, y + 0.05, f"{mean:.3f}", color=TEXT, fontsize=17, fontweight="bold", va="center")
        ax.text(high + 0.004, y - 0.22, f"95% interval {low:.3f} – {high:.3f}", color=MUTED, fontsize=11.5,
                va="center")
        ax.text(-0.075, y + 0.1, label, color=TEXT, fontsize=17, fontweight="bold", va="center", ha="left")
        ax.text(-0.075, y - 0.2, detail, color=MUTED, fontsize=11.5, va="center", ha="left")

    ax.axvline(0, color=TEXT, linestyle="--", linewidth=1.5, zorder=4)
    ax.text(0.002, len(ROWS) - 0.42, "0 = tie with the timer", color=TEXT, fontsize=12, va="center")
    ax.text(0.1, len(ROWS) - 0.42, "timer did better  →", color=ACCENT, fontsize=12, va="center")

    ax.set_xlim(-0.075, 0.185)
    ax.set_ylim(-0.6, len(ROWS) - 0.2)
    ax.set_xticks([0, 0.05, 0.10, 0.15])
    ax.set_xticklabels(["0", "0.05", "0.10", "0.15"])
    ax.tick_params(axis="x", colors=MUTED, labelsize=12, length=0)
    ax.set_yticks([])
    ax.spines[:].set_visible(False)
    for x in (0.05, 0.10, 0.15):
        ax.axvline(x, color=GRID, linewidth=1, zorder=1)
    ax.set_xlabel("Regret: how much higher the timer scored on the same robot runs (scores run from 0 to 1)",
                  color=MUTED, fontsize=12, labelpad=10, loc="right")

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, facecolor=BACKGROUND)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
