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
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.offsetbox import AnnotationBbox, OffsetImage  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import replay_analyze as ra  # noqa: E402
from robot_benchmark.replay_bench import FRAME_STEP, load_trajectories  # noqa: E402
from robot_benchmark.time_score import STEPS_PER_SECOND, load_config  # noqa: E402

# One colour per model: the palette's blue and its deeper orange and aqua steps, plus a plum, chosen so that all four
# pass the all-pairs colour checks (colour-blind and normal vision) and white score text has at least 3.4:1 contrast on
# every bar. Every bar also carries its model's logo and name, so identity never rests on colour alone.
MODELS = {"moonshotai/Kimi-K3": ("Kimi K3", "#2a78d6"), "google/gemma-4-31B-it": ("Gemma 4 31B", "#d95926"),
          "deepseek-ai/DeepSeek-V4.1-Flash-1017": ("DeepSeek V4.1 Flash", "#199e70"),
          "zai-org/GLM-5.3-Flash": ("GLM-5.3 Flash", "#9c3c94")}
LOGOS = {"moonshotai/Kimi-K3": "kimi-color", "google/gemma-4-31B-it": "google-color",
         "deepseek-ai/DeepSeek-V4.1-Flash-1017": "deepseek-color", "zai-org/GLM-5.3-Flash": "zai"}  # replay_logos/
LOWEST = {"zai-org/GLM-5.3-Flash": "minimal"}  # the lowest level the provider accepts for GLM
NOTES = True  # explanatory notes under each figure; --no-notes leaves them to the paper's captions
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
REFERENCE = {"oracle": "Oracle: stops the moment\nthe robot finishes",
             "detector": "Perfect vision, fixed check interval",
             "timer": "Fixed timer: never looks at the cameras"}

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5, "axes.edgecolor": AXIS, "axes.linewidth": 0.6, "axes.labelcolor": INK2, "grid.linestyle": (0, (1, 2.5)),
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


def shade(color, amount):
    """`color` mixed with white: amount 1 is the colour itself, smaller is lighter (opaque, so overlaps never darken)."""
    r, g, b = matplotlib.colors.to_rgb(color)
    return (1 - amount * (1 - r), 1 - amount * (1 - g), 1 - amount * (1 - b))


def rounded_bar(ax, x, height, width, color, radius=3.0):
    """A vertical bar from 0 to `height` with its top corners rounded by `radius` points and a square base. Call after
    the axes limits and the figure layout are fixed (the radius is converted to data units)."""
    if height <= 0:
        return
    to_data = ax.transData.inverted()
    px = radius * ax.figure.dpi / 72
    (x0, y0), (x1, y1) = to_data.transform([(0, 0), (px, px)])
    rx, ry = min(abs(x1 - x0), width / 2), min(abs(y1 - y0), height / 2)
    ax.add_patch(FancyBboxPatch((x - width / 2, 0), width, height, boxstyle=f"round,pad=0,rounding_size={rx}",
                                mutation_aspect=ry / rx, fc=color, ec="none", zorder=2))
    ax.add_patch(Rectangle((x - width / 2, 0), width, height - ry, fc=color, ec="none", zorder=2))


def logo(ax, x, model, size=13, y_offset=-3):
    """The model's logo under position `x`, `size` points tall, `y_offset` points below the axis."""
    image = plt.imread(ROOT / "scripts" / "replay_logos" / f"{LOGOS[model]}.png")
    box = OffsetImage(image, zoom=size / image.shape[0])  # drawn at `size` points whatever the output resolution
    ax.add_artist(AnnotationBbox(box, (x, 0), xycoords=("data", "axes fraction"), xybox=(0, y_offset),
                                 boxcoords="offset points", box_alignment=(0.5, 1), frameon=False, annotation_clip=False))


def leaderboard(fig, ax, entries, ylabel, refs, scale=1.0, whiskers=False):
    """Vertical leaderboard (Artificial Analysis style): bars sorted best first, rounded tops, the score in white
    inside the bar (above it when the bar is too short), its 95% interval as small text above the bar, the model's logo
    and name underneath. `refs` are (value, label, vertical alignment) reference lines, labelled in the right margin.
    `scale` shrinks text and logos for a single-column figure; `whiskers` draws the interval as a thin whisker instead
    of text (only where every whisker stays clear of the score inside its bar)."""
    entries = sorted(entries, key=lambda e: -e["mean"])
    ax.set_xlim(-0.6, len(entries) - 0.4)
    ax.set_ylim(0, 106)
    for i, e in enumerate(entries):
        color = MODELS[e["model"]][1]
        h, (lo, hi) = e["mean"], e["ci95"]
        rounded_bar(ax, i, h, 0.72, color)
        interval = f"{lo:.0f}–{hi:.0f}"
        if whiskers:
            ax.vlines(i, lo, hi, color=INK2, lw=0.7, zorder=3)
            ax.hlines([lo, hi], i - 0.09, i + 0.09, color=INK2, lw=0.7, zorder=3)
            interval = ""
        if h >= 12:
            ax.text(i, h / 2, f"{h:.0f}", ha="center", va="center", fontsize=10.5 * scale, fontweight="bold",
                    color="white", zorder=4)
            ax.annotate(interval, (i, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom",
                        fontsize=6.3 * scale, color=MUTED)
        else:
            ax.annotate(f"{h:.0f}", (i, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom",
                        fontsize=10.5 * scale, fontweight="bold", color=INK)
            ax.annotate(interval, (i, h), xytext=(0, 15 * scale), textcoords="offset points", ha="center",
                        va="bottom", fontsize=6.3 * scale, color=MUTED)
        logo(ax, i, e["model"], size=13 * scale)
    ax.set_xticks(range(len(entries)), [f"{MODELS[e['model']][0]} ({e['effort']})" for e in entries],
                  rotation=45, ha="right", rotation_mode="anchor", fontsize=7.2 * scale, color=INK)
    ax.tick_params(axis="x", length=0, pad=19 * scale)
    ax.set_xlabel("Model (reasoning setting)", color=INK2, fontsize=7.5 * scale, labelpad=3)
    ax.tick_params(axis="y", length=0, labelsize=7 * scale, colors=MUTED)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", visible=False)
    for value, label, va in refs:
        ax.axhline(value, color=INK2, lw=0.8, ls=(0, (4, 3)), zorder=0.6)  # behind the bars
        ax.annotate(f"{label}: {value:.0f}", (1.0, value), xycoords=("axes fraction", "data"), xytext=(6 * scale, 0),
                    textcoords="offset points", ha="left", va=va, fontsize=7 * scale, color=INK2, annotation_clip=False)
    ax.set_ylabel(ylabel, color=INK2, fontsize=8 * scale)
    return entries


def fig_supervision(summary, out, data):
    """Headline: supervision score = the model's value as % of the oracle's, trained tasks, 2 s per check."""
    sessions = summary["sessions"]
    entries = [{"model": m, "effort": e, **sessions[f"{m}|{e}|c2"]["leave-alone"]["score"]}
               for m in MODELS for e in grid(m)]
    la = sessions[f"{next(iter(MODELS))}|off|c2"]["leave-alone"]
    refs = [(100, "Oracle: stops the\nmoment the robot\nfinishes", "center"),
            (la["detector_score"]["mean"], "Perfect vision,\nfixed check\ninterval", "bottom"),
            (la["timer_score"]["mean"], "Fixed timer:\nnever looks at\nthe cameras", "top")]
    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    fig.subplots_adjust(left=0.08, right=0.83, top=0.9, bottom=0.34)
    data["supervision_score"] = leaderboard(fig, ax, entries, "Supervision score\n(% of the best possible value)", refs)
    data["supervision_reference"] = {k: r[0] for k, r in zip(("oracle", "detector", "timer"), refs)}
    fig.text(0.08, 0.97, "Supervision score: how much of the achievable value each model kept (higher is better)",
             fontsize=9, fontweight="bold", color=INK, va="top")
    note(fig, 0.0, "72 episodes per bar on the three tasks the policies were trained on; 2 s charged per camera "
         "check. Small numbers above the bars: 95% bootstrap\ninterval (clustered by task and scene). GLM-5.3 Flash "
         "cannot turn its reasoning off; minimal is its lowest setting.")
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
    fig, ax = plt.subplots(figsize=(3.45, 3.0))  # single column in the paper
    fig.subplots_adjust(left=0.16, right=0.84, top=0.88, bottom=0.4)
    data["detection_score"] = leaderboard(fig, ax, entries, "Done-detection score\n(balanced accuracy, %)",
                                          [(50, "Chance", "center")], scale=0.82, whiskers=True)
    fig.text(0.02, 0.985, "Done-detection score: is the task finished\nin these camera images? (higher is better)",
             fontsize=7, fontweight="bold", color=INK, va="top")
    note(fig, -0.02, "450 questions per bar (114 'done', 336 'not done');\nbalanced accuracy is the mean of the "
         "accuracy on each kind.\nWhiskers: 95% bootstrap interval (clustered by recorded run).")
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
    """Three panels of vertical bars, grouped by model (logo underneath), one bar per reasoning setting from light
    (off) to dark (high): what the models did on runs the robot finishes, with the perfect-vision baseline dashed."""
    b = behaviour(rows, trajs, task_type, config)
    data["behaviour"] = {f"{k[0]}|{k[1]}": v for k, v in b.items() if k != "detector"}
    data["behaviour"]["perfect_vision_baseline"] = b["detector"]
    panels = [("early_pct", "Said 'done' too early\n(% of runs; each is a failure)", "{:.0f}"),
              ("checks", "Camera checks per episode\n(each costs 2 s)", "{:.1f}"),
              ("late_s", "Seconds late when 'done' was\nright (median)", "{:.0f}")]
    amounts, width = (0.42, 0.7, 1.0), 0.26
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.85))
    fig.subplots_adjust(left=0.05, right=0.995, top=0.7, bottom=0.17, wspace=0.22)
    for ax, (key, title, fmt) in zip(axes, panels):
        top = max(v[key] for v in b.values()) * 1.15
        ax.set_xlim(-0.55, len(MODELS) - 0.45)
        ax.set_ylim(0, top)
        for j, (m, (name, color)) in enumerate(MODELS.items()):
            for k, e in enumerate(grid(m)):
                x, v = j + (k - 1) * (width + 0.02), b[(m, e)][key]
                rounded_bar(ax, x, v, width, shade(color, amounts[k]), radius=2.0)
                ax.text(x, v + 0.012 * top, fmt.format(v), ha="center", va="bottom", fontsize=5.6, color=INK2, zorder=4,
                        bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none"))
            logo(ax, j, m, size=10, y_offset=-3)
            ax.annotate(name.replace(" V4.1 Flash", "\nV4.1 Flash").replace("-5.3 Flash", "-5.3\nFlash")
                        .replace(" 4 31B", " 4\n31B"), (j, 0), xycoords=("data", "axes fraction"), xytext=(0, -15),
                        textcoords="offset points", ha="center", va="top", fontsize=6, color=INK, annotation_clip=False)
        ax.axhline(b["detector"][key], color=INK2, lw=0.8, ls=(0, (4, 3)), zorder=3)
        ax.set_xticks([])
        ax.tick_params(axis="y", length=0, labelsize=6.5, colors=MUTED)
        ax.spines["left"].set_visible(False)
        ax.grid(axis="x", visible=False)
        ax.set_title(title, fontsize=7.5, color=INK, loc="left")
    handles = [Patch(fc=shade(INK2, a), ec="none", label=lab) for a, lab in
               zip(amounts, ("reasoning off (GLM: minimal)", "reasoning low", "reasoning high"))]
    handles.append(Line2D([], [], color=INK2, lw=0.8, ls=(0, (4, 3)),
                          label=f"perfect vision, fixed check interval ({b['detector']['early_pct']:.0f}% too early, "
                                f"{b['detector']['checks']:.1f} checks, {b['detector']['late_s']:.0f} s late)"))
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.05, 1.0), ncol=2, frameon=False, fontsize=6.8,
               handlelength=1.6, columnspacing=1.4)
    note(fig, 0.0, "Trained tasks, the 50 runs on which the robot finishes (so a failure can only be a 'done' said "
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
