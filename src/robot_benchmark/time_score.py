"""Time-charged scoring (docs/time_score.md).

An episode is worth `success x max(0, 1 - charged_seconds / deadline_seconds)`:
- `charged_seconds` is the robot time up to the end of the episode plus a fixed charge for every response from an LLM
  supervisor. Physics pauses while a model thinks, so without the charge a slow supervisor would cost nothing.
- A failure is worth 0 however long it took, whether a false "complete" or the step budget running out. Declaring
  early on a doomed episode therefore gains nothing.
- A time-sensitive task may also set a story limit: the task fails if more than `limit_seconds` of charged time pass
  between its trigger (a predicate turning true, or step 0) and the declaration.

The best fixed rule is evaluated offline from runs whose supervisor never restarts the policy, or restarts it on a
fixed schedule: "declare at step T" succeeds exactly when the checker is true at T in that run's per-step evaluator
log. Analysis only: this module reads episode folders, never runs anything, and is not in the contract hash."""
import json
from pathlib import Path

STEPS_PER_SECOND = 20


def load_config(path):
    config = json.loads(Path(path).read_text())
    if not (isinstance(config.get("call_seconds"), (int, float)) and config["call_seconds"] >= 0
            and isinstance(config.get("tasks"), dict)):
        raise ValueError("time config needs call_seconds >= 0 and a tasks mapping")
    for task, spec in config["tasks"].items():
        if not (isinstance(spec.get("deadline_seconds"), (int, float)) and spec["deadline_seconds"] > 0):
            raise ValueError(f"{task}: deadline_seconds must be positive")
        story = spec.get("story")
        if story is not None and not (isinstance(story.get("text"), str) and story.get("clock_starts")):
            raise ValueError(f"{task}: a story needs text and clock_starts")
    return config


def _jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()] if Path(path).exists() else []


def read_episode(folder):
    """The fields scoring needs from one episode folder."""
    folder = Path(folder)
    result = json.loads((folder / "result.json").read_text())
    manifest = json.loads((folder / "manifest.json").read_text())
    agent = manifest.get("agent") or {}
    events = _jsonl(folder / "evaluator" / "events.jsonl")
    first_true = {}
    for state in events:
        for name, value in state.items():
            if name != "step" and value is True and name not in first_true:
                first_true[name] = state["step"]
    llm = "provider" in agent  # a model adapter; scripted baselines and diagnostics make no LLM calls
    logged = set(events[0]) - {"step", "success"} if events else set()
    return {
        "folder": str(folder), "task": manifest["task"], "kind": manifest["kind"],
        "agent": agent.get("model"), "llm": llm, "backend": (manifest.get("policy") or {}).get("backend"),
        "scene_seed": result["scene_seed"], "policy_seed": result["policy_seed"],
        "infrastructure_error": bool(result.get("infrastructure_error")),
        "steps": result["steps"], "success": bool(result.get("success")),
        "false_completion": bool(result.get("false_completion")),
        "calls": result.get("model_calls", 0) if llm else 0,
        "prompt_changes": result.get("prompt_changes", 0), "prompt_restarts": result.get("prompt_restarts", 0),
        "intervals": result.get("intervals") or [],
        "decisions": [d for d in _jsonl(folder / "decisions.jsonl")],
        "success_by_step": [bool(state.get("success")) for state in events],
        "first_true": first_true, "logged": logged,
    }


def value(success, charged, deadline):
    return max(0.0, 1.0 - charged / deadline) if success else 0.0


def _calls_from(episode, step):
    """LLM responses made at or after `step` (every response is charged, including rejected ones)."""
    if not episode["llm"]:
        return 0
    return sum(1 for d in episode["decisions"] if d.get("step_before", 0) >= step)


def score_episode(episode, config):
    """Value and time accounting for one episode as it was run."""
    spec = config["tasks"][episode["task"]]
    robot = episode["steps"] / STEPS_PER_SECOND
    charged = robot + config["call_seconds"] * episode["calls"]
    success, story = episode["success"], None
    if spec.get("story") and spec["story"].get("limit_seconds") is not None:
        start = spec["story"]["clock_starts"]
        trigger = 0 if start == "step0" else episode["first_true"].get(start)
        if start != "step0" and start not in episode["logged"]:
            story = {"status": "trigger not logged"}  # older runs predate the trigger predicate
        else:
            story_seconds = (0.0 if trigger is None else
                             (episode["steps"] - trigger) / STEPS_PER_SECOND
                             + config["call_seconds"] * _calls_from(episode, trigger))
            story = {"status": "ok" if story_seconds <= spec["story"]["limit_seconds"] else "expired",
                     "seconds": story_seconds}
            success = success and story["status"] == "ok"
    return {"success": success, "robot_seconds": robot, "charged_seconds": charged, "calls": episode["calls"],
            "value": value(success, charged, spec["deadline_seconds"]),
            "on_time": success and charged <= spec["deadline_seconds"], "story": story}


def success_at(episode, step):
    """Checker state at `step` of a run without supervisor-dependent stopping. A run that stopped at its first success
    (the privileged reference) is assumed to stay successful afterwards; stage 3 saw success lost in 1 of 36
    no-intervention reruns."""
    by_step = episode["success_by_step"]
    if step < len(by_step):
        return by_step[step]
    return bool(by_step) and by_step[-1]


def rule_source(episode):
    """The fixed-rule family a scripted run belongs to, or None. The privileged reference and always-defer both run the
    plain policy without interruption, so they pool as "no_restart"; each reissue period is its own family."""
    if episode["kind"] in ("diagnostic_reference", "baseline_always_defer"):
        return "no_restart"
    if episode["kind"] == "baseline_reissue":
        return episode["agent"]
    return None


def fixed_rule_values(episodes, config, task, horizon, grid_steps=20):
    """Mean value of "declare at step T" over the given runs, for T on a grid up to the horizon. Scripted rules make
    no LLM calls, so their charged time is T / 20."""
    deadline = config["tasks"][task]["deadline_seconds"]
    table = {}
    for step in range(grid_steps, horizon + 1, grid_steps):
        values = [value(success_at(e, step), step / STEPS_PER_SECOND, deadline) for e in episodes]
        table[step] = sum(values) / len(values)
    return table


def best_step(runs, config, task, horizon):
    """The declaration step with the highest mean value over `runs` (the earliest on ties), or None if no step has
    any value."""
    table = fixed_rule_values(runs, config, task, horizon)
    step = max(table, key=lambda s: (table[s], -s))
    return step if table[step] > 0 else None


def rule_value(runs, config, task, step):
    """Mean value of declaring at `step` (None: never succeeds) over `runs`."""
    if step is None:
        return 0.0
    deadline = config["tasks"][task]["deadline_seconds"]
    return sum(value(success_at(e, step), step / STEPS_PER_SECOND, deadline) for e in runs) / len(runs)


def loo_value(runs, config, task, horizon):
    """Leave-one-out value of the fixed rule: the step is chosen on the other runs and applied to the held-out one,
    which removes the hindsight advantage of `best_fixed_rules`."""
    if len(runs) < 2:
        return None
    return sum(rule_value([held_out], config, task, best_step(runs[:i] + runs[i + 1:], config, task, horizon))
               for i, held_out in enumerate(runs)) / len(runs)


def oracle_value(episodes, config, task):
    """Mean value of declaring at each run's first success: a privileged upper bound, not a rule."""
    deadline = config["tasks"][task]["deadline_seconds"]
    values = []
    for e in episodes:
        first = next((i for i, ok in enumerate(e["success_by_step"]) if ok), None)
        values.append(0.0 if first is None else value(True, first / STEPS_PER_SECOND, deadline))
    return sum(values) / len(values)


def rule_runs(episodes, config):
    """The scripted runs that estimate each fixed rule, keyed by (backend, task, rule source)."""
    cells = {}
    for e in episodes:
        source = rule_source(e)
        if source and not e["infrastructure_error"] and e["task"] in config["tasks"]:
            if e["success_by_step"] and e["success_by_step"][0]:
                continue  # solved at start: measures nothing
            cells.setdefault((e["backend"], e["task"], source), []).append(e)
    for key, runs in cells.items():
        # Baselines may have run only on selected scenes (stage 3 ran always-defer only where the plain policy had
        # succeeded). The privileged reference runs every scene, so when present it alone estimates the rule.
        unselected = [e for e in runs if e["kind"] == "diagnostic_reference"]
        cells[key] = unselected or runs
    return cells


def best_fixed_rules(episodes, config, horizons):
    """Per (backend, task, rule source): the best declaration step in hindsight and its mean value. In-sample, so it
    flatters the fixed rule; `loo_value` is the honest estimate."""
    rules = {}
    for (backend, task, source), runs in sorted(rule_runs(episodes, config).items(),
                                                key=lambda item: tuple(map(str, item[0]))):
        step = best_step(runs, config, task, horizons[task])
        rules[(backend, task, source)] = {"step": step, "value": rule_value(runs, config, task, step), "n": len(runs),
                                          "loo_value": loo_value(runs, config, task, horizons[task]),
                                          "oracle": oracle_value(runs, config, task),
                                          "reached": sum(any(r["success_by_step"]) for r in runs) / len(runs)}
    return rules


def supervisor_measures(episode):
    """How a supervisor behaved: declaration timing against the checker, check-in intervals, interruptions."""
    first_success = next((i for i, ok in enumerate(episode["success_by_step"]) if ok), None)
    declared = any(d.get("accepted") and d["decision"].get("op") == "complete" for d in episode["decisions"])
    lag = None
    if not declared:
        timing = "timeout, success was reached" if first_success is not None else "timeout, never reached"
    elif episode["success"]:
        timing = "correct"
        lag = (episode["steps"] - first_success) / STEPS_PER_SECOND  # seconds the declaration trailed the checker
    elif first_success is None:
        timing = "false: not reached yet"
    else:
        timing = "false: reached, then lost"
    return {"declaration": timing, "lag_seconds": lag, "calls": episode["calls"],
            "median_interval": sorted(episode["intervals"])[len(episode["intervals"]) // 2] if episode["intervals"] else None,
            "prompt_changes": episode["prompt_changes"], "restarts": episode["prompt_restarts"]}
