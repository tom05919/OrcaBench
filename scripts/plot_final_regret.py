#!/usr/bin/env python3
"""Draw the main-result slide figure: how far each supervisor scored behind the fixed declaration rule on the same robot
runs, in points out of 100 (the paired held-out regret x 100, worded for the audience without that term and drawn without
its interval), best first, in the presentation deck's colors.

The numbers are the reported results in docs/final_results.md: Opus from W2 (#8), Sonnet from W3 (`670e075`,
docs/session_mode.md), Kimi K3 from results/w1/addon_kimi_score.txt.

  python3 scripts/plot_final_regret.py   # writes results/w1/figures/timer_vs_supervisors.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "w1" / "figures" / "timer_vs_supervisors.png"

# (label, detail, paired held-out regret, its 95% interval: kept for reference, not drawn)
ROWS = [
    ("Opus 5.5", "63 episodes · scenes 1000–1002", 0.053, (0.007, 0.105)),
    ("Sonnet 5.5", "83 episodes · scenes 1000–1003", 0.071, (0.028, 0.119)),
    ("Kimi K3 (add-on)", "42 episodes · scenes 1000–1001", 0.070, (0.014, 0.134)),
]

BACKGROUND, GRID, TEXT, MUTED, ACCENT, OTHER = "#182339", "#2a3448", "#f5f4f0", "#9aa3b5", "#e4a46a", "#6b7896"
LEFT, RIGHT = -4.8, 10.5


def main():
    plt.rcParams["font.family"] = ["Helvetica Neue", "Helvetica", "DejaVu Sans"]
    fig, ax = plt.subplots(figsize=(12, 4.2), dpi=200)
    fig.patch.set_facecolor(BACKGROUND)
    ax.set_facecolor(BACKGROUND)

    rows = sorted(ROWS, key=lambda r: r[2])  # closest to the timer first
    best = rows[0][2]
    ys = list(range(len(rows)))[::-1]
    for y, (label, detail, regret, _) in zip(ys, rows):
        points = 100 * regret
        ax.barh(y, points, height=0.5, color=ACCENT if regret == best else OTHER, zorder=2)
        ax.text(points + 0.15, y, f"{points:.1f} points behind", color=TEXT, fontsize=16, va="center")
        ax.text(LEFT, y + 0.1, label, color=TEXT, fontsize=17, va="center", ha="left")
        ax.text(LEFT, y - 0.2, detail, color=MUTED, fontsize=11.5, va="center", ha="left")

    ax.axvline(0, color=TEXT, linewidth=2, zorder=4)
    ax.text(0.12, len(rows) - 0.42, "Timer", color=TEXT, fontsize=13, fontweight="bold", va="center")
    ax.text(1.2, len(rows) - 0.42, "shorter bar = closer to the timer = better", color=MUTED, fontsize=12, va="center")

    ax.set_xlim(LEFT, RIGHT)
    ax.set_ylim(-0.6, len(rows) - 0.2)
    ticks = [0, 2, 4, 6, 8, 10]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(t) for t in ticks])
    ax.tick_params(axis="x", colors=MUTED, labelsize=12, length=0)
    ax.set_yticks([])
    ax.spines[:].set_visible(False)
    for x in ticks[1:]:
        ax.axvline(x, color=GRID, linewidth=1, zorder=1)
    ax.set_xlabel("Points behind the timer on the same robot runs (scores out of 100)",
                  color=MUTED, fontsize=12, labelpad=10, loc="right")

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, facecolor=BACKGROUND)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
