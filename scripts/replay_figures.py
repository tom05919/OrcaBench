#!/usr/bin/env python3
"""Figures for the replay benchmark (PNG and PDF), from scripts/replay_analyze.py's summary and the raw records.

  python3 scripts/replay_figures.py --summary runs/replay/prelim/summary.json --out runs/replay/prelim/figures [--label PRELIMINARY]

Every number drawn comes from the recorded runs; intervals are the analysis script's 95% clustered bootstraps
(sessions: clustered by task and scene; probe: by recorded run). Partial conditions are marked with their sample size."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import replay_analyze as ra  # noqa: E402
from robot_benchmark.replay_bench import FRAME_STEP, load_trajectories  # noqa: E402
from robot_benchmark.time_score import STEPS_PER_SECOND  # noqa: E402

# Palette: the validated categorical slots (blue, orange, aqua) for the three complete models; GLM, whose sessions
# may stay partial, in neutral gray (the fourth slot fails the all-pairs check beside orange in scatter plots).
MODELS = {"moonshotai/Kimi-K3": ("Kimi K3", "#2a78d6"), "google/gemma-4-31B-it": ("Gemma 4 31B", "#eb6834"),
          "deepseek-ai/DeepSeek-V4.1-Flash-1017": ("DeepSeek V4.1 Flash", "#1baf7a"),
          "zai-org/GLM-5.3-Flash": ("GLM-5.3 Flash", "#898781")}
LEVELS = ["off", "minimal", "low", "medium", "high", "default"]
LEVEL_LABEL = {"off": "off", "minimal": "min", "low": "low", "medium": "med", "high": "high", "default": "def†"}
LEVEL_LONG = {"off": "off", "minimal": "minimal", "low": "low", "medium": "medium", "high": "high", "default": "default†"}
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5, "axes.edgecolor": AXIS, "axes.linewidth": 0.6, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150,
    "savefig.dpi": 300, "savefig.bbox": "tight", "savefig.pad_inches": 0.03, "text.color": INK})


def save(fig, out, name, label):
    if label:
        fig.text(1.0, 1.0, label, ha="right", va="bottom", fontsize=6.5, color=MUTED, transform=fig.transFigure)
    out.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(out / f"{name}.{ext}")
    plt.close(fig)


def levels_of(summary_keys, model):
    return [e for e in LEVELS if any(k.startswith(f"{model}|{e}|") for k in summary_keys)]


# ---------------------------------------------------------------------------------------------------------------

def fig_probe_accuracy(summary, out, label):
    """Small multiples: probe balanced accuracy by requested reasoning level, one panel per model (pass 1)."""
    probe = summary["probe"]
    fig, axes = plt.subplots(1, len(MODELS), figsize=(7.0, 2.1), sharey=True)
    for ax, (model, (name, color)) in zip(axes, MODELS.items()):
        lv = levels_of(probe, model)
        for i, e in enumerate(lv):
            s = probe[f"{model}|{e}|pass1"]
            m, (lo, hi) = s["balanced_accuracy"]["mean"], s["balanced_accuracy"]["ci95"]
            hollow = e == "default"
            ax.errorbar(i, m, yerr=[[m - lo], [hi - m]], fmt="o", ms=5, color=color, mfc="white" if hollow else color,
                        mew=1.2, elinewidth=1.2, capsize=0)
            if s["unreadable"]:
                ax.annotate(f"{s['unreadable']} cut off", (i, lo), xytext=(0, -9), textcoords="offset points",
                            ha="center", fontsize=6, color=MUTED)
            p2 = probe.get(f"{model}|{e}|pass2")
            if p2:  # second pass of the same condition: the run-to-run noise reference
                ax.plot(i + 0.22, p2["balanced_accuracy"]["mean"], marker="o", ms=3.5, color=color, alpha=0.45,
                        mfc="white" if hollow else color, ls="none")
        ax.set_xticks(range(len(lv)), [LEVEL_LABEL[e] for e in lv])
        ax.set_xlim(-0.6, len(lv) - 0.4)
        ax.set_title(name, color=INK, loc="left", fontweight="bold")
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("Balanced accuracy, 'is it done?'")
    axes[0].set_ylim(0.6, 0.86)
    axes[0].axhline(0.5, color=AXIS, lw=0.6)
    fig.text(0.01, -0.06, "Requested reasoning level (min = minimal, med = medium). Points: 450 probes each (pass 1), 95% bootstrap "
             "CI clustered by recorded run; faint point: a second pass.\n† def = default: no level sent, 6,144-token "
             "reply limit (explicit levels: 32,768); for Gemma the default does not reason.",
             fontsize=6.5, color=INK2, va="top")
    save(fig, out, "fig1_probe_accuracy_by_reasoning", label)


def fig_probe_heatmap(rows, trajs, task_type, out, label):
    """Annotated heatmap: share of probes answered 'done', by model and level (rows) and probe moment (columns)."""
    by_id = {t["id"]: t for t in trajs}
    cols = [("10 s before\nsuccess", "neg"), ("2 s before\nsuccess", "neg"), ("run never\nsucceeds", "neg"),
            ("unseen task,\nnot done", "neg"), ("at success", "pos"), ("5 s after\nsuccess", "pos")]

    def column(r):
        t = by_id[r["traj"]]
        if r["label"]:
            first = t["first_success"]
            at = min(t["steps"], first + (-first % FRAME_STEP))
            return 4 if r["step"] == at else 5
        kind = ra.negative_kind(r, t, task_type)
        return {"10 s before success": 0, "2 s before success": 1, "run never succeeds": 2, "unseen task": 3}[kind]

    cells = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["pass_no"] != "pass1":
            continue
        cells[(r["model"], r["effort"])][column(r)].append(r["answer"] is True)
    keys = [(m, e) for m in MODELS for e in LEVELS if (m, e) in cells]
    data = [[100 * statistics.mean(cells[k][c]) if cells[k][c] else float("nan") for c in range(len(cols))]
            for k in keys]
    ns = [len(cells[keys[0]][c]) for c in range(len(cols))]
    fig, ax = plt.subplots(figsize=(5.2, 0.24 * len(keys) + 1.0))
    ax.imshow(data, cmap=matplotlib.colors.LinearSegmentedColormap.from_list(
        "blue", ["#f4f8fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]), vmin=0, vmax=100, aspect="auto")
    for i, row in enumerate(data):
        for j, v in enumerate(row):
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=6.8, color="white" if v > 55 else INK)
    ax.set_xticks(range(len(cols)), [f"{c}\n(n={n})" for (c, _), n in zip(cols, ns)], fontsize=6.6)
    ax.set_yticks(range(len(keys)), [f"{MODELS[m][0]} · {LEVEL_LONG[e]}" for m, e in keys], fontsize=6.8)
    for tick, (m, _) in zip(ax.get_yticklabels(), keys):
        tick.set_color(INK)
    ax.xaxis.tick_top()
    ax.tick_params(length=0)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.axvline(3.5, color="white", lw=3)
    for i in range(1, len(keys)):
        if keys[i][0] != keys[i - 1][0]:
            ax.axhline(i - 0.5, color="white", lw=3)
    fig.text(0.0, -0.02, "% of probes answered \"done\". Left four columns: the task is not done (a correct "
             "answer is \"not done\"); right two: it is done. Pass 1; the 2 s band\njust before success is not probed "
             "(the checker lags the images by about 1 s). † default: no level sent.", fontsize=6.5, color=INK2,
             va="top")
    save(fig, out, "fig2_probe_said_done_heatmap", label)


def fig_sessions(summary, out, label):
    """Left: value minus the held-out perfect detector (leave-alone tasks, 2 s per look), mean and 95% CI.
    Right: success on runs that do succeed against looks per episode, one labelled point per condition."""
    sessions = summary["sessions"]
    keys = [(m, e) for m in MODELS for e in LEVELS if f"{m}|{e}|c2" in sessions]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, 0.27 * len(keys) + 1.1),
                                 gridspec_kw={"width_ratios": [1.15, 1]})
    for i, (m, e) in enumerate(keys):
        la = sessions[f"{m}|{e}|c2"]["leave-alone"]
        d = la["minus_detector"]
        color = MODELS[m][1]
        a1.errorbar(d["mean"], i, xerr=[[d["mean"] - d["ci95"][0]], [d["ci95"][1] - d["mean"]]], fmt="o", ms=4.5,
                    color=color, mfc="white" if e == "default" else color, mew=1.2, elinewidth=1.2)
        full = 72 * len(la["passes"])
        if la["episodes"] < full:
            a1.annotate(f"partial: {la['episodes']}/{full}", (d["ci95"][1], i), xytext=(4, 0),
                        textcoords="offset points", va="center", fontsize=6, color=MUTED)
    a1.axvline(0, color=INK2, lw=0.8)
    a1.set_yticks(range(len(keys)), [f"{MODELS[m][0]} · {LEVEL_LONG[e]}" for m, e in keys])
    a1.invert_yaxis()
    a1.set_xlabel("Value minus perfect-perception detector\n(leave-alone tasks; 0 = matches the detector)")
    a1.grid(axis="y", visible=False)
    labels = defaultdict(list)
    for (m, e) in keys:
        la = sessions[f"{m}|{e}|c2"]["leave-alone"]
        x, y = la["looks_per_episode"], la["success_on_succeeding_runs"]
        a2.plot(x, y, marker="o", ms=5.5, color=MODELS[m][1], mfc="white" if e == "default" else MODELS[m][1],
                mew=1.2, ls="none")
        labels[(m, round(x, 0), round(y, 2))].append((x, y, LEVEL_LABEL[e]))
    for group in labels.values():  # points of one model that sit on top of each other share one label
        x, y = group[0][0], group[0][1]
        above = group[0][2] == LEVEL_LABEL["default"]  # default points crowd each other: label them above
        a2.annotate("/".join(g[2] for g in group), (x, y), xytext=(0, 5) if above else (5, -2.5),
                    textcoords="offset points", ha="center" if above else "left", fontsize=6.3, color=INK2)
    pts = sorted(((sessions[f"{m}|{e}|c2"]["leave-alone"]["looks_per_episode"],
                   sessions[f"{m}|{e}|c2"]["leave-alone"]["success_on_succeeding_runs"]) for m, e in keys))
    frontier, best = [], -1
    for x, y in pts:  # fewer looks and higher success are both better
        if y > best:
            frontier.append((x, y))
            best = y
    a2.plot(*zip(*frontier), color=MUTED, lw=0.8, ls="--", zorder=0)
    a2.set_xlabel("Looks per episode (each look costs 2 s)")
    a2.set_ylabel("Declared correctly, on runs\nthe robot finishes")
    handles = [Line2D([], [], marker="o", ls="none", color=c, label=n) for n, c in MODELS.values()]
    a2.legend(handles=handles, frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2,
              handletextpad=0.2, columnspacing=1.0, borderaxespad=0.2)
    fig.text(0.0, -0.04, "Leave-alone tasks (OpenCabinet, PickPlaceCounterToStove, CloseFridge), 2 s per look; "
             "intervals: 95% bootstrap clustered by task and scene. Hollow: default\n(no level sent). Dashed: "
             "conditions no other condition beats on both axes. Preliminary conditions may be partial.",
             fontsize=6.5, color=INK2, va="top")
    fig.tight_layout(w_pad=2.5)
    save(fig, out, "fig3_sessions_value_and_tradeoff", label)


def fig_declaration_timing(rows, trajs, task_type, out, label):
    """One row per model and level: when the model declared 'done', relative to the robot's first success (leave-alone
    runs the robot finishes, 2 s per look); negative = too early, a failure. Share early and n at the right."""
    by_id = {t["id"]: t for t in trajs}
    series = []
    for model in MODELS:
        for e in LEVELS:
            xs = [(r["final_step"] - by_id[r["traj"]]["first_success"]) / STEPS_PER_SECOND for r in rows
                  if (r["model"], r["effort"], r["cost"]) == (model, e, 2.0) and task_type.get(r["task"]) == "leave-alone"
                  and by_id[r["traj"]]["first_success"] is not None and r["outcome"] in ("success", "false_done")]
            if xs:
                series.append((model, e, xs))
    fig, ax = plt.subplots(figsize=(5.6, 0.27 * len(series) + 0.9))
    lim = 15
    for i, (model, e, xs) in enumerate(series):
        color = MODELS[model][1]
        inside = [x for x in xs if -lim <= x <= lim]
        jitter = [((k * 7919) % 100 / 100 - 0.5) * 0.42 for k in range(len(inside))]
        ax.scatter(inside, [i + j for j in jitter], s=5, color=color, alpha=0.55, linewidths=0)
        for edge, marker in ((lim, ">"), (-lim, "<")):
            n = sum(x > lim if edge > 0 else x < -lim for x in xs)
            if n:
                ax.scatter([edge], [i], marker=marker, s=12, color=color, linewidths=0, clip_on=False)
                ax.annotate(str(n), (edge, i), xytext=(5, 0), textcoords="offset points",  # inside on the left
                            ha="left", va="center", fontsize=5.8, color=MUTED)
        med = statistics.median(xs)
        if -lim <= med <= lim:
            ax.plot([med, med], [i - 0.32, i + 0.32], color=INK, lw=1.3)
        early = 100 * sum(x < 0 for x in xs) / len(xs)
        ax.annotate(f"{early:.0f}% early  (n={len(xs)})", (1.0, i), xycoords=("axes fraction", "data"),
                    xytext=(22, 0), textcoords="offset points", va="center", fontsize=6.5, color=INK2)
    ax.axvline(0, color=INK2, lw=0.8)
    ax.axvspan(-lim, 0, color="#f0efec", zorder=0)
    ax.set_xlim(-lim, lim)
    ax.set_yticks(range(len(series)), [f"{MODELS[m][0]} · {LEVEL_LONG[e]}" for m, e, _ in series])
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Declared 'done' minus the robot's first success (s)")
    ax.text(-lim + 0.4, -0.9, "too early (failure)", fontsize=6.3, color=INK2, va="bottom")
    ax.text(lim - 0.4, -0.9, "late (time lost)", fontsize=6.3, color=INK2, va="bottom", ha="right")
    fig.text(0.0, -0.02, "Leave-alone tasks, runs the robot finishes, 2 s per look; one dot per episode, black bar = "
             "median. Arrowheads: episodes beyond ±15 s, with\ntheir count. † default: no level sent.", fontsize=6.5,
             color=INK2, va="top")
    save(fig, out, "fig4_declaration_timing", label)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    selection = json.loads((ROOT / "configs/final/selection.json").read_text())
    task_type = {t: "leave-alone" for t in selection["seen_tasks"]} | {t: "unseen" for t in selection["unseen_tasks"]}
    trajs = load_trajectories(ra.POD_ROOTS)
    probe_rows, session_rows = ra.probe_rows(), ra.session_rows()
    fig_probe_accuracy(summary, args.out, args.label)
    fig_probe_heatmap(probe_rows, trajs, task_type, args.out, args.label)
    fig_sessions(summary, args.out, args.label)
    fig_declaration_timing(session_rows, trajs, task_type, args.out, args.label)
    print("wrote", sorted(p.name for p in args.out.glob("*.png")))


if __name__ == "__main__":
    main()
