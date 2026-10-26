#!/usr/bin/env python3
"""Figures for the replay benchmark (PNG and PDF) from scripts/replay_analyze.py's summary and the raw records.

  python3 scripts/replay_figures.py --summary results/w1/replay/summary.json --out results/w1/replay/figures [--no-notes]

Paper figures: fig1 supervision leaderboard (the headline score), fig2 done-detection leaderboard, fig3 what the
models did (early "done", camera checks, lateness). Supplementary: fig4 answers by moment, fig5 declaration timing.
Every plotted number is also written to `figure_data.json` next to the figures. Only the final grid is drawn: reasoning
off (GLM: minimal, since the provider rejects turning its reasoning off), low and high. Intervals are the analysis
script's 95% bootstraps (sessions clustered by task and scene; probe by recorded run)."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import replay_analyze as ra  # noqa: E402
from robot_benchmark.replay_bench import FRAME_STEP, load_trajectories  # noqa: E402
from robot_benchmark.time_score import STEPS_PER_SECOND, load_config  # noqa: E402

# One colour per model: three validated categorical slots and a darker magenta that passes the all-pairs colour checks
# beside them. Every bar is also labelled with its model, so identity never rests on colour alone.
MODELS = {"moonshotai/Kimi-K3": ("Kimi K3", "#2a78d6"), "google/gemma-4-31B-it": ("Gemma 4 31B", "#eb6834"),
          "deepseek-ai/DeepSeek-V4.1-Flash-1017": ("DeepSeek V4.1 Flash", "#1baf7a"),
          "zai-org/GLM-5.3-Flash": ("GLM-5.3 Flash", "#c4417f")}
LOWEST = {"zai-org/GLM-5.3-Flash": "minimal"}  # the lowest level the provider accepts for GLM
NOTES = True  # explanatory notes under each figure; --no-notes leaves them to the paper's captions
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
REFERENCE = {"oracle": "Oracle: stops the moment\nthe robot finishes",
             "detector": "Perfect vision, fixed check interval",
             "timer": "Fixed timer: never looks at the cameras"}

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5, "axes.edgecolor": AXIS, "axes.linewidth": 0.6, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150,
    "savefig.dpi": 300, "savefig.bbox": "tight", "savefig.pad_inches": 0.03, "text.color": INK})


def grid(model):
    """The model's requested levels in the shared order off, low, high."""
    return [LOWEST.get(model, "off"), "low", "high"]


def level_name(effort):
    return f"reasoning {effort}"


def note(fig, y, text):
    if NOTES:
        fig.text(0.0, y, text, fontsize=6.5, color=INK2, va="top")


def save(fig, out, name):
    out.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(out / f"{name}.{ext}")
    plt.close(fig)


def leaderboard(ax, entries, xlabel, refs):
    """Sorted horizontal bars, best on top (leaderboard style): score at the end of each bar, 95% CI whisker,
    model-coloured and labelled. `refs` are (value, text, row, side) reference lines, each labelled next to its line
    at a row where no bar reaches it (row -1.15 is a band above the first bar)."""
    entries = sorted(entries, key=lambda e: -e["mean"])
    for i, e in enumerate(entries):
        ax.barh(i, e["mean"], height=0.66, color=MODELS[e["model"]][1], zorder=2)
        ax.errorbar(e["mean"], i, xerr=[[e["mean"] - e["ci95"][0]], [e["ci95"][1] - e["mean"]]], fmt="none",
                    ecolor=INK2, elinewidth=0.8, capsize=1.8, capthick=0.8, zorder=3)
        ax.text(e["ci95"][1] + 1.0, i, f"{e['mean']:.0f}", ha="left", va="center", fontsize=7.5, fontweight="bold",
                color=INK)
    ax.set_yticks(range(len(entries)), [f"{MODELS[e['model']][0]} · {level_name(e['effort'])}" for e in entries],
                  fontsize=7.3)
    for value, text, row, side in refs:
        ax.axvline(value, color=INK2, lw=0.8, ls=(0, (4, 3)), zorder=1)
        ax.text(value + (0.8 if side == "right" else -0.8), row, f"{text}: {value:.0f}",
                ha="left" if side == "right" else "right", va="center", fontsize=6.8, color=INK2, zorder=4)
    ax.set_ylim(len(entries) - 0.5, -1.6)
    ax.set_xlim(0, 104)
    ax.set_xlabel(xlabel)
    ax.grid(axis="y", visible=False)
    return entries


def fig_supervision(summary, out, data):
    """Headline: supervision score = the model's value as % of the oracle's, trained tasks, 2 s per check."""
    sessions = summary["sessions"]
    entries = [{"model": m, "effort": e, **sessions[f"{m}|{e}|c2"]["leave-alone"]["score"]}
               for m in MODELS for e in grid(m)]
    la = sessions[f"{next(iter(MODELS))}|off|c2"]["leave-alone"]
    refs = [(100, REFERENCE["oracle"], 5, "left"), (la["detector_score"]["mean"], REFERENCE["detector"], -1.15, "right"),
            (la["timer_score"]["mean"], REFERENCE["timer"], -1.15, "left")]
    fig, ax = plt.subplots(figsize=(7.0, 3.3))
    data["supervision_score"] = leaderboard(ax, entries, "Supervision score (% of the best possible value)", refs)
    data["supervision_reference"] = {k: r[0] for k, r in zip(("oracle", "detector", "timer"), refs)}
    ax.set_title("Supervision score: how much of the achievable value each model kept (higher is better)", loc="left",
                 color=INK, fontweight="bold")
    note(fig, -0.03, "72 episodes per bar on the three tasks the policies were trained on; 2 s charged per camera "
         "check. Whiskers: 95% bootstrap interval\n(clustered by task and scene). GLM-5.3 Flash cannot turn its reasoning "
         "off; minimal is its lowest setting.")
    save(fig, out, "fig1_supervision_leaderboard")


def fig_detection(summary, out, data):
    """Done-detection score: balanced accuracy (%) on 450 single 'is it done?' questions."""
    probe = summary["probe"]
    entries = []
    for m in MODELS:
        for e in grid(m):
            ba = probe[f"{m}|{e}|pass1"]["balanced_accuracy"]
            entries.append({"model": m, "effort": e, "mean": 100 * ba["mean"],
                            "ci95": [100 * ba["ci95"][0], 100 * ba["ci95"][1]]})
    fig, ax = plt.subplots(figsize=(7.0, 3.3))
    data["detection_score"] = leaderboard(ax, entries, "Done-detection score (balanced accuracy, %)",
                                          [(50, "Chance", -1.15, "left")])
    ax.set_title("Done-detection score: is the task finished in these camera images? (higher is better)", loc="left",
                 color=INK, fontweight="bold")
    note(fig, -0.03, "450 questions per bar (114 'done', 336 'not done'); balanced accuracy is the mean of the "
         "accuracy on each kind. Whiskers: 95% bootstrap\ninterval (clustered by recorded run).")
    save(fig, out, "fig2_detection_leaderboard")


def behaviour(rows, trajs, task_type, config):
    """Per configuration and for the perfect-vision baseline, on trained-task runs the robot finishes: share of
    'done' said before the robot finished, mean camera checks, median seconds late when 'done' was right."""
    by_id = {t["id"]: t for t in trajs}
    out = {}
    for m in MODELS:
        for e in grid(m):
            rs = [r for r in rows if (r["model"], r["effort"], r["cost"]) == (m, e, 2.0)
                  and task_type.get(r["task"]) == "leave-alone" and by_id[r["traj"]]["first_success"] is not None]
            early = [r["final_step"] < by_id[r["traj"]]["first_success"] for r in rs]
            late = [(r["final_step"] - by_id[r["traj"]]["first_success"]) / STEPS_PER_SECOND for r in rs
                    if r["outcome"] == "success"]
            out[(m, e)] = {"runs": len(rs), "early_pct": 100 * sum(early) / len(rs),
                           "checks": statistics.mean(r["looks"] for r in rs), "late_s": statistics.median(late)}
    finished = [t for t in trajs if task_type.get(t["task"]) == "leave-alone" and t["first_success"] is not None]
    checks, late = [], []
    for t in finished:  # the perfect-vision baseline with its held-out check interval
        others = [o for o in trajs if (o["backend"], o["task"]) == (t["backend"], t["task"]) and o["scene"] != t["scene"]]
        k = max(range(10, 401, 10), key=lambda p: (sum(ra.detector_value(o, p, config, 2.0) for o in others), -p))
        steps = list(range(0, t["steps"], k)) + [t["steps"]]
        at = next(s for s in steps if t["success_by_step"][min(s, len(t["success_by_step"]) - 1)])
        checks.append(steps.index(at) + 1)
        late.append((at - t["first_success"]) / STEPS_PER_SECOND)
    out["detector"] = {"runs": len(finished), "early_pct": 0.0, "checks": statistics.mean(checks),
                       "late_s": statistics.median(late)}
    return out


def fig_behaviour(rows, trajs, task_type, config, out, data):
    """Three panels sharing one row per configuration: what the models did on runs the robot finishes, with the
    perfect-vision baseline as a reference line."""
    b = behaviour(rows, trajs, task_type, config)
    data["behaviour"] = {f"{k[0]}|{k[1]}": v for k, v in b.items() if k != "detector"}
    data["behaviour"]["perfect_vision_baseline"] = b["detector"]
    keys = [(m, e) for m in MODELS for e in grid(m)]
    panels = [("early_pct", "Said 'done' too early\n(% of runs; each is a failure)", "{:.0f}"),
              ("checks", "Camera checks per episode\n(each costs 2 s)", "{:.1f}"),
              ("late_s", "Seconds late when 'done'\nwas right (median)", "{:.1f}")]
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 3.0), sharey=True)
    for ax, (key, title, fmt) in zip(axes, panels):
        top = max(b[k][key] for k in b)
        for i, k in enumerate(keys):
            v = b[k][key]
            ax.barh(i, v, height=0.66, color=MODELS[k[0]][1], zorder=2)
            ax.text(v + 0.015 * top, i, fmt.format(v), ha="left", va="center", fontsize=6.2, color=INK2, zorder=4,
                    bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none"))
        ref = b["detector"][key]
        ax.axvline(ref, color=INK2, lw=0.8, ls=(0, (4, 3)), zorder=3)
        ax.text(ref + 0.015 * top, -1.05, f"perfect vision,\nfixed interval: {fmt.format(ref)}", ha="left",
                va="bottom", fontsize=6, color=INK2)
        for i in range(1, len(keys)):
            if keys[i][0] != keys[i - 1][0]:
                ax.axhline(i - 0.5, color=GRID, lw=0.6)
        ax.set_title(title, fontsize=7.5, color=INK, loc="left", pad=22)
        ax.set_xlim(0, top * 1.22)
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(range(len(keys)), [f"{MODELS[m][0]} · {level_name(e)}" for m, e in keys], fontsize=7)
    axes[0].set_ylim(len(keys) - 0.5, -0.6)
    fig.tight_layout(w_pad=1.2)
    note(fig, -0.02, "Trained tasks, the 50 runs on which the robot finishes (so a failure can only be a 'done' said "
         "too early); 2 s per camera check.")
    save(fig, out, "fig3_what_models_did")


def fig_moments(rows, trajs, task_type, out):
    """Supplementary heatmap: % of test images answered 'done', by configuration and by moment of the recording."""
    by_id = {t["id"]: t for t in trajs}
    cols = ["10 s before\nit finishes", "2 s before\nit finishes", "runs that\nnever finish", "new tasks,\nnot finished",
            "the moment\nit finishes", "5 s after\nit finishes"]

    def column(r):
        t = by_id[r["traj"]]
        if r["label"]:
            first = t["first_success"]
            return 4 if r["step"] == min(t["steps"], first + (-first % FRAME_STEP)) else 5
        kind = ra.negative_kind(r, t, task_type)
        return {"10 s before success": 0, "2 s before success": 1, "run never succeeds": 2, "unseen task": 3}[kind]

    cells = defaultdict(lambda: defaultdict(list))
    for r in rows:
        cells[(r["model"], r["effort"])][column(r)].append(r["answer"] is True)
    keys = [(m, e) for m in MODELS for e in grid(m) if (m, e) in cells]
    data = [[100 * statistics.mean(cells[k][c]) for c in range(len(cols))] for k in keys]
    ns = [len(cells[keys[0]][c]) for c in range(len(cols))]
    fig, ax = plt.subplots(figsize=(5.4, 0.24 * len(keys) + 1.1))
    ax.imshow(data, cmap=matplotlib.colors.LinearSegmentedColormap.from_list(
        "blue", ["#f4f8fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]), vmin=0, vmax=100, aspect="auto")
    for i, row in enumerate(data):
        for j, v in enumerate(row):
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=6.8, color="white" if v > 55 else INK)
    ax.set_xticks(range(len(cols)), [f"{c}\n(n={n})" for c, n in zip(cols, ns)], fontsize=6.6)
    ax.set_yticks(range(len(keys)), [f"{MODELS[m][0]} · {level_name(e)}" for m, e in keys], fontsize=6.8)
    ax.xaxis.tick_top()
    ax.tick_params(length=0)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.axvline(3.5, color="white", lw=3)
    for i in range(1, len(keys)):
        if keys[i][0] != keys[i - 1][0]:
            ax.axhline(i - 0.5, color="white", lw=3)
    ax.set_title("% of camera images answered 'done'. Left four columns: not finished (right answer: no); right two: "
                 "finished (right answer: yes)", fontsize=7, loc="left", color=INK, pad=34)
    note(fig, -0.02, "Images from the 2 s just before the robot finishes are not used, because the simulator's success "
         "signal lags the images by about 1 s.")
    save(fig, out, "fig4_answers_by_moment")


def fig_timing(rows, trajs, task_type, out):
    """Supplementary: when each configuration said 'done', relative to the robot finishing (trained-task runs the robot
    finishes); negative = too early, a failure."""
    by_id = {t["id"]: t for t in trajs}
    series = []
    for m in MODELS:
        for e in grid(m):
            xs = [(r["final_step"] - by_id[r["traj"]]["first_success"]) / STEPS_PER_SECOND for r in rows
                  if (r["model"], r["effort"], r["cost"]) == (m, e, 2.0) and task_type.get(r["task"]) == "leave-alone"
                  and by_id[r["traj"]]["first_success"] is not None]
            series.append((m, e, xs))
    fig, ax = plt.subplots(figsize=(5.6, 0.27 * len(series) + 0.9))
    lim = 15
    for i, (m, e, xs) in enumerate(series):
        color = MODELS[m][1]
        inside = [x for x in xs if -lim <= x <= lim]
        jitter = [((k * 7919) % 100 / 100 - 0.5) * 0.42 for k in range(len(inside))]
        ax.scatter(inside, [i + j for j in jitter], s=5, color=color, alpha=0.6, linewidths=0)
        for edge, marker in ((lim, ">"), (-lim, "<")):
            n = sum(x > lim if edge > 0 else x < -lim for x in xs)
            if n:
                ax.scatter([edge], [i], marker=marker, s=12, color=color, linewidths=0, clip_on=False)
                ax.annotate(str(n), (edge, i), xytext=(6 if edge > 0 else 5, 0), textcoords="offset points",
                            ha="left", va="center", fontsize=5.8, color=MUTED)
        med = statistics.median(xs)
        if -lim <= med <= lim:
            ax.plot([med, med], [i - 0.32, i + 0.32], color=INK, lw=1.3)
        ax.annotate(f"{100 * sum(x < 0 for x in xs) / len(xs):.0f}% too early", (1.0, i),
                    xycoords=("axes fraction", "data"), xytext=(20, 0), textcoords="offset points", va="center",
                    fontsize=6.5, color=INK2)
    ax.axvline(0, color=INK2, lw=0.8)
    ax.axvspan(-lim, 0, color="#f0efec", zorder=0)
    ax.set_xlim(-lim, lim)
    ax.set_yticks(range(len(series)), [f"{MODELS[m][0]} · {level_name(e)}" for m, e, _ in series])
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("When the model said 'done', minus when the robot finished (s)")
    ax.text(-lim + 0.4, -0.9, "too early (failure)", fontsize=6.3, color=INK2, va="bottom")
    ax.text(lim - 0.4, -0.9, "late (time lost)", fontsize=6.3, color=INK2, va="bottom", ha="right")
    note(fig, -0.02, "Trained tasks, the 50 runs the robot finishes, per row; one dot per episode, black bar = median. "
         "Arrowheads: episodes beyond ±15 s, with their count.")
    save(fig, out, "fig5_declaration_timing")


def main():
    global NOTES
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-notes", action="store_true", help="omit the notes under each figure (paper captions)")
    args = parser.parse_args()
    NOTES = not args.no_notes
    summary = json.loads(args.summary.read_text())
    selection = json.loads((ROOT / "configs/final/selection.json").read_text())
    task_type = {t: "leave-alone" for t in selection["seen_tasks"]} | {t: "unseen" for t in selection["unseen_tasks"]}
    config = load_config(ROOT / "configs" / "time_pressure.json")
    trajs = load_trajectories(ra.POD_ROOTS)
    probe_rows, session_rows = ra.probe_rows(), ra.session_rows()
    data = {}
    fig_supervision(summary, args.out, data)
    fig_detection(summary, args.out, data)
    fig_behaviour(session_rows, trajs, task_type, config, args.out, data)
    fig_moments(probe_rows, trajs, task_type, args.out)
    fig_timing(session_rows, trajs, task_type, args.out)
    (args.out / "figure_data.json").write_text(json.dumps(data, indent=1, default=str) + "\n")
    print("wrote", sorted(p.name for p in args.out.glob("*.png")))


if __name__ == "__main__":
    main()
