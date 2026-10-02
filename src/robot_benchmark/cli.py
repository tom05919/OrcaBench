"""Command line entry point for diagnostics, qualification, and model runs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import sys
from time import perf_counter, time_ns
import traceback
from urllib.parse import urlparse

from . import __version__
from .adapters.agents import HTTPAgent, MAX_MODEL_TOKENS, SYSTEM_PROMPT
from .adapters.policy import RemotePolicy
from .baselines import AlwaysDeferAgent, ReissueAgent
from .contracts import Limits, Skill
from .diagnostics import PrivilegedRetrySupervisor, PrivilegedSequencer
from .evaluation import summarize
from .feasibility import (
    DiagnosticSupervisor,
    OrdinaryPolicySupervisor,
    public_task_config,
    qualification_config_view,
    qualification_report,
)
from .records import Records, digest
from .runner import Runner
from .scorecard import load_scored_episodes, scorecard
from .screening import freeze_release, label_seeds, load_episodes, native_card_performance
from .tasks.predicates import SEQUENCES
from .video import encode_episode_videos

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASK = PROJECT_ROOT / "configs" / "cereal_and_bowl.json"
DEFAULT_SPLITS = PROJECT_ROOT / "configs" / "splits.json"
TASKS_DIR = PROJECT_ROOT / "configs" / "tasks"
SOURCE_LOCK = PROJECT_ROOT / "configs" / "sources.lock.json"
CONTRACT_FILES = (
    "src/robot_benchmark/contracts.py",
    "src/robot_benchmark/runner.py",
    "src/robot_benchmark/adapters/robocasa.py",
    "src/robot_benchmark/adapters/policy.py",
    "src/robot_benchmark/adapters/agents.py",
    "src/robot_benchmark/adapters/http.py",
    "src/robot_benchmark/policy_worker.py",
    "src/robot_benchmark/records.py",
    "src/robot_benchmark/video.py",
    "src/robot_benchmark/tasks/predicates.py",
    "src/robot_benchmark/diagnostics.py",
    "src/robot_benchmark/baselines.py",
    "src/robot_benchmark/feasibility.py",
)
# Analysis-only modules: they never affect an episode, so freeze-benchmark records their hashes in
# the release instead of the contract.
ANALYSIS_FILES = ("src/robot_benchmark/scorecard.py", "src/robot_benchmark/screening.py")
FULL_TASK_INSTRUCTION = (
    "Open the cabinet. Pick the cereal and bowl from the cabinet and place them "
    "on the counter next to the milk. Then close the cabinet."
)
SCORED_GOAL = (
    "Move the cereal box and the bowl from the cabinet onto the adjacent counter, "
    "and leave the cabinet closed. Declare completion when both objects are on the "
    "counter and the cabinet is closed."
)
REFERENCE_PROMPTS = {
    "open_cabinet": "Open the cabinet.",
    "transfer_cereal": "Pick the cereal box from the cabinet and place it on the counter.",
    "transfer_bowl": "Pick the bowl from the cabinet and place it on the counter.",
    "close_cabinet": "Close the cabinet.",
}
AGENT_IMAGE_HISTORY = "current_frames_plus_interval_keyframes_plus_decision_history"
TASK_CONFIG_KEYS = {"schema_version", "task", "split", "goal", "max_steps", "max_decisions", "max_interval",
                    "camera_size", "video_record_interval", "interval_keyframes", "agent_image_history",
                    "artificial_disturbances", "reference_prompts"}
PROMPT_CARD_KEYS = {"id", "prompt", "description", "performance"}
# Benchmark agents by CLI name: (record kind, factory(env, task)).
SCREEN_MODES = {
    "reference": ("diagnostic_reference", lambda env, task: OrdinaryPolicySupervisor(env)),
    "retry": ("diagnostic_retry", lambda env, task: PrivilegedRetrySupervisor(env)),
    "sequencer": ("diagnostic_sequencer", lambda env, task: PrivilegedSequencer(env, task)),
}
BASELINES = {
    "always_defer": ("baseline_always_defer", lambda env, task: AlwaysDeferAgent()),
    "reissue": ("baseline_reissue", lambda env, task: ReissueAgent()),
}


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def write_contract(output: Path, payload: dict, contract_hash: str):
    """One file per hash, so a rerun under a changed contract never overwrites the earlier payload."""
    write_json(output / f"contract-{contract_hash}.json", payload)


def positive_int(value: str) -> int:
    if not value.isdigit() or int(value) < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return int(value)


def parse_seeds(value: str) -> list[int]:
    try:
        seeds = [int(part) for part in value.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError("seeds must be comma-separated integers") from error
    if not seeds or len(set(seeds)) != len(seeds) or any(not 0 <= seed < 2**32 for seed in seeds):
        raise argparse.ArgumentTypeError("seeds must be unique integers in [0, 2**32)")
    return seeds


def validate_splits(value):
    names = ("development_seeds", "qualification_seeds", "evaluation_seeds")
    sets = {}
    for name in (*names, "screening_policy_seeds", "reference_policy_seeds"):
        seeds = value.get(name)
        if (
            not isinstance(seeds, list)
            or not seeds
            or any(type(seed) is not int or not 0 <= seed < 2**32 for seed in seeds)
            or len(set(seeds)) != len(seeds)
        ):
            raise ValueError(f"{name} must contain unique integers in [0, 2**32)")
        sets[name] = set(seeds)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            if sets[left] & sets[right]:
                raise ValueError("development, qualification, and evaluation seeds must be disjoint")
    if len(sets["evaluation_seeds"]) < 20:
        raise ValueError("the pilot evaluation set must contain at least 20 seeds")
    # Policy seeds are a separate axis and may reuse scene-seed values.
    if sets["screening_policy_seeds"] & sets["reference_policy_seeds"]:
        raise ValueError("screening and reference policy seeds must be disjoint")
    return value


def task_parts(path: Path):
    """Validate any schema-3 task config; extra keys are allowed. CerealAndBowl keeps its audited values."""
    config = read_json(path)
    if not TASK_CONFIG_KEYS <= config.keys():
        raise ValueError(f"task config is missing {sorted(TASK_CONFIG_KEYS - config.keys())}")
    positive = lambda value: type(value) is int and value >= 1
    if not (
        config["schema_version"] == 3
        and isinstance(config["task"], str) and config["task"].strip()
        and config["split"] == "pretrain"
        and positive(config["max_steps"])
        and (config["max_decisions"], config["max_interval"]) == (100, 400)
        and config["camera_size"] == 256
        and positive(config["video_record_interval"])
        and config["agent_image_history"] == AGENT_IMAGE_HISTORY
        and config["interval_keyframes"] == 4
        and config["artificial_disturbances"] is False
    ):
        raise ValueError("task config violates the schema-3 benchmark contract")
    goal = config["goal"]
    if not ((isinstance(goal, str) and goal.strip())
            or (goal is None and config.get("goal_source") == "native_instruction")):
        raise ValueError("goal must be nonblank text, or null with goal_source native_instruction")
    prompts = config["reference_prompts"]
    if not isinstance(prompts, list) or not prompts or not all(
        isinstance(item, dict) and PROMPT_CARD_KEYS <= item.keys()
        and all(isinstance(item[key], str) and item[key].strip() for key in ("id", "prompt"))
        for item in prompts
    ):
        raise ValueError("reference_prompts must be a nonempty list of prompt cards with nonblank id and prompt")
    if config["task"] == "CerealAndBowl":
        if goal != SCORED_GOAL or (config["max_steps"], config["max_decisions"], config["max_interval"]) != (4350, 100, 400):
            raise ValueError("the audited CerealAndBowl goal or budgets changed")
        if [item["id"] for item in prompts] != list(REFERENCE_PROMPTS) or any(
            item["prompt"] != REFERENCE_PROMPTS[item["id"]] for item in prompts
        ):
            raise ValueError("the CerealAndBowl reference prompts changed")
    reference_prompts = [Skill(item["id"], item["prompt"], item["description"], item["performance"])
                         for item in config["reference_prompts"]]
    limits = Limits(config["max_steps"], config["max_decisions"], config["max_interval"])
    return config, reference_prompts, limits


def implementation_hashes(files=CONTRACT_FILES):
    import hashlib
    result = {}
    for relative in files:
        data = (PROJECT_ROOT / relative).read_bytes()
        result[relative] = hashlib.sha256(data).hexdigest()
    return result


def contract_payload(task_config, policy_identity, splits=None):
    lock = read_json(SOURCE_LOCK)
    source_identity = {
        name: entry["revision"] for name, entry in lock["repositories"].items()
    }
    source_identity["checkpoint_registry_revision"] = lock["checkpoint"]["revision"]
    return {
        "schema_version": 2,
        "task_config": task_config,
        "source_revisions": source_identity,
        "policy_identity": policy_identity,
        "system_prompt": SYSTEM_PROMPT,
        "model_call_max_tokens": MAX_MODEL_TOKENS,
        "implementation_sha256": implementation_hashes(),
        "splits": splits,
    }


def task_pool():
    """Every candidate config in configs/tasks, keyed by task name."""
    pool = {}
    for path in sorted(TASKS_DIR.glob("*.json")):
        config = task_parts(path)[0]
        if pool.setdefault(config["task"], config) is not config:
            raise ValueError(f"duplicate task config for {config['task']}")
    return pool


def benchmark_contract(task_configs, policy_identity, splits):
    """One payload for screening, baselines and LLM runs. It covers the whole task pool, so every
    subset of tasks shares one hash; each config must equal its pool entry."""
    pool = task_pool()
    for config in task_configs:
        if pool.get(config["task"]) != config:
            raise ValueError(f"{config['task']} config differs from the configs/tasks pool covered by the contract")
    payload = contract_payload(None, policy_identity, splits)
    del payload["task_config"]
    payload.update(schema_version=3, task_configs=pool)
    return payload, digest(payload)


def qualification_contract_payload(task_config, policy_identity):
    return contract_payload(qualification_config_view(task_config), policy_identity)


def episode_path(output: Path, seed: int, policy_seed: int):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return output / f"seed-{seed}-p{policy_seed}-{stamp}"


def infrastructure_result(error, started_at_unix_ns=None, wall_seconds=0.0, scene_seed=None, policy_seed=None):
    return {
        "started_at_unix_ns": started_at_unix_ns,
        "ended_at_unix_ns": time_ns(),
        "status": "infrastructure_error",
        "goal": None, "scene_seed": scene_seed, "policy_seed": policy_seed,
        "success": False,
        "physical_success_final": None, "physical_success_any": False,
        "false_completion": False, "steps": 0, "model_calls": 0,
        "policy_calls": 0, "prompt_submissions": 0, "prompt_changes": 0,
        "prompt_restarts": 0, "discarded_actions": 0,
        "rejected_decisions": 0, "reply_parse": {},
        "intervals": [], "model_seconds": 0.0, "policy_seconds": 0.0,
        "simulation_seconds": 0.0, "simulated_seconds": 0.0,
        "recording_seconds": 0.0,
        "evaluation_seconds": 0.0, "wall_seconds": wall_seconds, "usage": [],
        "infrastructure_error": f"{type(error).__name__}: {error}",
    }


def resolve_audit_paths(values, project_root=PROJECT_ROOT):
    root = Path(project_root).resolve()
    resolved_paths = []
    for value in values:
        path = Path(value)
        if path.is_absolute():
            raise ValueError("qualification trace paths must be project-relative")
        resolved = (root / path).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("qualification trace paths must stay under the project root")
        resolved_paths.append(resolved)
    return resolved_paths


def run_episode(*, seed, policy_seed=None, output, task_config, reference_prompts, limits, policy, agent_factory, kind,
                contract_hash):
    """`seed` is the scene seed; `policy_seed` defaults to it."""
    policy_seed = seed if policy_seed is None else policy_seed
    started_at_unix_ns = time_ns()
    started = perf_counter()
    path = episode_path(output, seed, policy_seed)
    manifest = {
        "artifact_type": "episode", "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": __version__, "kind": kind, "seed": seed,
        "scene_seed": seed, "policy_seed": policy_seed,
        "contract_hash": contract_hash, "agent": {"kind": kind, "model": "setup_pending"},
        "policy": policy.identity,
        "task": task_config["task"], "split": task_config["split"],
        "video_record_interval": task_config["video_record_interval"],
    }
    records = Records(path, manifest)
    env = None
    try:
        from .adapters.robocasa import RoboCasaEnvironment
        env = RoboCasaEnvironment(task_config["task"], task_config["split"], task_config["camera_size"])
        if env.horizon != limits.max_steps:
            raise RuntimeError(f"upstream horizon changed: {env.horizon} != {limits.max_steps}")
        agent = agent_factory(env)
        manifest["agent"] = agent.identity
        records.write("manifest.json", manifest)
        runner = Runner(env, policy, agent, reference_prompts, task_config["goal"], limits, records,
                        recording_interval=task_config["video_record_interval"],
                        interval_keyframes=task_config["interval_keyframes"])
        result = runner.run(seed, policy_seed)
    except Exception as error:
        if env is not None:
            try:
                env.close()
            except Exception:
                pass
        result = infrastructure_result(error, started_at_unix_ns, perf_counter() - started, seed, policy_seed)
        records.append("evaluator/errors.jsonl", {"error": result["infrastructure_error"], "traceback": traceback.format_exc()})
        records.write("result.json", result)
    try:
        videos = encode_episode_videos(path)
        records.write("videos/manifest.json", videos)
    except Exception as error:
        records.append("artifact_errors.jsonl", {"kind": "video_encoding",
            "error": f"{type(error).__name__}: {error}"})
    print(json.dumps({"seed": seed, "policy_seed": policy_seed, "episode": str(path), "status": result["status"], "success": result["success"]}))
    return result


def command_doctor(args):
    task, _, limits = task_parts(args.task_config)
    lock = read_json(SOURCE_LOCK)
    checks = {
        "project_root": str(PROJECT_ROOT), "python": platform.python_version(),
        "platform": platform.platform(), "free_gib": round(shutil.disk_usage(PROJECT_ROOT).free / 1024**3, 2),
        "task": task["task"], "horizon": limits.max_steps,
        "source_lock_status": lock.get("status"), "core_import": True,
        "video_encoder": {"ok": shutil.which("ffmpeg") is not None,
                          "path": shutil.which("ffmpeg")},
    }
    try:
        import robocasa
        import robosuite
        checks["sim_import"] = {"ok": True, "robocasa": robocasa.__version__, "robosuite": robosuite.__version__}
    except Exception as error:
        checks["sim_import"] = {"ok": False, "error": f"{type(error).__name__}: {error}"}
    if args.policy_url:
        try:
            checks["policy_worker"] = {"ok": True, "identity": RemotePolicy(args.policy_url).identity}
        except Exception as error:
            checks["policy_worker"] = {"ok": False, "error": f"{type(error).__name__}: {error}"}
    write_json(args.output, checks)
    print(json.dumps(checks, indent=2))
    ok = checks["sim_import"]["ok"] and checks["video_encoder"]["ok"] and checks.get("policy_worker", {"ok": True})["ok"]
    return 0 if ok else 1


def command_smoke_sim(args):
    from .adapters.robocasa import RoboCasaEnvironment
    config, _, limits = task_parts(args.task_config)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = RoboCasaEnvironment(config["task"], config["split"], config["camera_size"])
    try:
        if env.horizon != limits.max_steps:
            raise RuntimeError(f"upstream horizon changed: {env.horizon} != {limits.max_steps}")
        env.reset(args.seed)
        public = env.sensors()
        report = {"status": "passed", "seed": args.seed, "evaluator": env.evaluate(),
                  "snapshot": env.snapshot(), "camera_data_url_lengths": {k: len(v) for k, v in public["images"].items()},
                  "proprio_dimensions": {k: len(v) for k, v in public["proprio"].items()}}
        write_json(output / "report.json", report)
    finally:
        env.close()
    print(json.dumps({"output": str(output), "status": report["status"]}))
    return 0


def seed_pairs(args):
    """Scene-major (scene, policy) pairs; without --policy-seeds the policy seed defaults to the scene seed."""
    return [(seed, policy_seed) for seed in args.seeds for policy_seed in (args.policy_seeds or [None])]


def command_feasibility(args):
    config, public_prompts, limits = task_parts(args.task_config)
    if config["task"] != "CerealAndBowl":
        raise ValueError("feasibility modes are CerealAndBowl-specific; use `screen` for native-goal tasks")
    if not 1 <= args.supervisor_interval <= limits.max_interval:
        raise ValueError(f"supervisor interval must be in [1, {limits.max_interval}]")
    policy = RemotePolicy(args.policy_url)
    if args.mode == "ordinary":
        reference_prompts = [Skill("full_task", FULL_TASK_INSTRUCTION, "Unmodified whole-task policy diagnostic.",
                                   {"status": "diagnostic"})]
        factory = lambda env: OrdinaryPolicySupervisor(env)
    else:
        reference_prompts = public_prompts
        factory = lambda env: DiagnosticSupervisor(env, interval=args.supervisor_interval)
    payload = qualification_contract_payload(config, policy.identity)
    contract_hash = digest(payload)
    args.output.mkdir(parents=True, exist_ok=True)
    write_contract(args.output, payload, contract_hash)
    for seed, policy_seed in seed_pairs(args):
        run_episode(seed=seed, policy_seed=policy_seed, output=args.output, task_config=config,
                    reference_prompts=reference_prompts, limits=limits, policy=policy, agent_factory=factory,
                    kind=f"diagnostic_{args.mode}", contract_hash=contract_hash)
    return 0


MAX_CONSECUTIVE_INFRASTRUCTURE_ERRORS = 3


def completed_episodes(root, contract_hash):
    """(task, scene_seed, policy_seed, kind, agent model) of every episode under root recorded under contract_hash
    without an infrastructure error. Episodes under other hashes stay on disk but never count as done."""
    return {(m.get("task"), m.get("scene_seed", m.get("seed")), m.get("policy_seed", m.get("seed")), m.get("kind"),
             m.get("agent", {}).get("model"))
            for m, result in load_episodes(root)
            if m.get("contract_hash") == contract_hash and result.get("status") != "infrastructure_error"}


def run_jobs(jobs, output, skip_existing, contract_hash):
    """Run (key, run_episode kwargs) jobs in order; key[0] is the task. With skip_existing, keys already completed
    under output with this contract hash are skipped. A task with 3 consecutive infrastructure errors is abandoned
    and the grid moves on; two tasks abandoned back to back (likely a dead worker) stop the grid. Written episodes
    are kept. Returns 1 if any task was abandoned."""
    done = completed_episodes(output, contract_hash) if skip_existing else set()
    errors, abandoned, streak = {}, [], 0
    for key, kwargs in jobs:
        task = key[0]
        if task in abandoned:
            continue
        if key in done:
            print(json.dumps({"skipped_existing": list(key)}))
            continue
        if run_episode(**kwargs)["status"] != "infrastructure_error":
            errors[task] = streak = 0
            continue
        errors[task] = errors.get(task, 0) + 1
        if errors[task] >= MAX_CONSECUTIVE_INFRASTRUCTURE_ERRORS:
            abandoned.append(task)
            streak += 1
            print(f"error: abandoning {task} after {errors[task]} consecutive infrastructure errors; its episodes "
                  "already written are kept. Fix it, then rerun with --skip-existing.", file=sys.stderr)
            if streak >= 2:
                print("error: stopping: two tasks in a row were abandoned, which usually means the policy worker "
                      "or simulator is down. Fix it, then rerun with --skip-existing.", file=sys.stderr)
                return 1
    return 1 if abandoned else 0


def check_frozen(release, contract_hash):
    if release.get("status") != "frozen" or release.get("contract_hash") != contract_hash:
        raise ValueError("release manifest is absent, not frozen, or does not match the current contract")


def check_release_seeds(release, task, scene_seeds, policy_seeds):
    """Official episodes use only the release's tasks, selected scene seeds and reference policy seeds."""
    entry = release["tasks"].get(task)
    if entry is None or not set(scene_seeds) <= set(entry["leave_alone"] + entry["needs_help"]):
        raise ValueError("official runs may use only the release's tasks and selected scene seeds")
    if not policy_seeds or not set(policy_seeds) <= set(release["reference_policy_seeds"]):
        raise ValueError("official runs require --policy-seeds from the release's reference_policy_seeds")


def command_run(args):
    config, reference_prompts, limits = task_parts(args.task_config)
    model_config = read_json(args.agent_config)
    policy = RemotePolicy(args.policy_url)
    splits = validate_splits(read_json(args.splits))
    release = read_json(args.release) if args.release else None
    # freeze-benchmark releases list "tasks"; legacy CerealAndBowl releases (freeze-release) do not.
    benchmark = "tasks" in release if release else config["task"] in task_pool()
    if benchmark:
        payload, contract_hash = benchmark_contract([config], policy.identity, splits)
    else:
        payload = contract_payload(config, policy.identity, splits)
        contract_hash = digest(payload)
    kind = "llm_development"
    if release:
        check_frozen(release, contract_hash)
        if benchmark:
            check_release_seeds(release, config["task"], args.seeds, args.policy_seeds)
            if model_config.get("model") not in release["models"]:
                raise ValueError("the agent model is not listed in the release")
        else:
            if args.policy_seeds:
                raise ValueError("legacy releases use the scene seed as the policy seed; omit --policy-seeds")
            if not set(args.seeds) <= set(release["evaluation_seeds"]):
                raise ValueError("official runs may use only frozen evaluation seeds")
        kind = "llm"
    elif not args.development:
        raise ValueError("unqualified runs require --development; official runs require --release")
    agent = HTTPAgent(model_config)
    args.output.mkdir(parents=True, exist_ok=True)
    write_contract(args.output, payload, contract_hash)
    if args.video_record_interval:
        # Recording cadence only, as in run_grid: recorded in each manifest, not hashed.
        config = {**config, "video_record_interval": args.video_record_interval}
    jobs = [((config["task"], seed, seed if policy_seed is None else policy_seed, kind, model_config.get("model")),
             dict(seed=seed, policy_seed=policy_seed, output=args.output, task_config=config,
                  reference_prompts=reference_prompts, limits=limits, policy=policy,
                  agent_factory=lambda env, value=agent: value, kind=kind, contract_hash=contract_hash))
            for seed, policy_seed in seed_pairs(args)]
    return run_jobs(jobs, args.output, args.skip_existing, contract_hash)


def load_task_configs(paths):
    parts = [task_parts(path) for path in paths]
    if len({config["task"] for config, _, _ in parts}) != len(parts):
        raise ValueError("each task may appear only once")
    return parts


def run_grid(args, kind, factory, allowed_scenes=None, release=None):
    """Run every (task, scene seed, policy seed) episode under the shared benchmark contract.
    allowed_scenes, when given, maps each task to the scene seeds it may run."""
    parts = load_task_configs(args.task_configs)
    splits = validate_splits(read_json(args.splits))
    policy = RemotePolicy(args.policy_url)
    payload, contract_hash = benchmark_contract([config for config, _, _ in parts], policy.identity, splits)
    if release is not None:
        if "tasks" not in release:
            raise ValueError("--release requires a release written by freeze-benchmark")
        check_frozen(release, contract_hash)
        for config, _, _ in parts:
            check_release_seeds(release, config["task"], args.scene_seeds, args.policy_seeds)
    args.output.mkdir(parents=True, exist_ok=True)
    write_contract(args.output, payload, contract_hash)
    jobs = []
    for config, prompts, limits in parts:
        if args.video_record_interval:
            # Recording cadence only: run_episode writes it to each manifest; the contract hash ignores it.
            config = {**config, "video_record_interval": args.video_record_interval}
        # Agent identities do not depend on the environment, so no simulator is needed to read the model.
        model = factory(None, config["task"]).identity["model"]
        for seed in args.scene_seeds:
            if allowed_scenes is not None and seed not in allowed_scenes.get(config["task"], ()):
                continue
            for policy_seed in args.policy_seeds:
                jobs.append(((config["task"], seed, policy_seed, kind, model),
                             dict(seed=seed, policy_seed=policy_seed, output=args.output / config["task"],
                                  task_config=config, reference_prompts=prompts, limits=limits, policy=policy,
                                  agent_factory=lambda env, task=config["task"]: factory(env, task), kind=kind,
                                  contract_hash=contract_hash)))
    return run_jobs(jobs, args.output, args.skip_existing, contract_hash)


def low_success_scenes(groups):
    """Per task, the scene seeds whose full set-A reference has at most needs_help_max successes."""
    t = groups["thresholds"]
    return {task: {int(scene) for scene, value in g["scene_seeds"].items()
                   if value["reference"][1] >= t["trials"] and value["reference"][0] <= t["needs_help_max"]}
            for task, g in groups["tasks"].items()}


def command_screen(args):
    if args.mode == "sequencer":
        missing = sorted({config["task"] for config, _, _ in load_task_configs(args.task_configs)} - SEQUENCES.keys())
        if missing:
            raise ValueError(f"no privileged sequence for {missing}")
    allowed = None
    if args.scenes_from:
        if args.mode == "reference":
            raise ValueError("--scenes-from restricts retry/sequencer screening; run the reference on all scenes")
        allowed = low_success_scenes(read_json(args.scenes_from))
    return run_grid(args, *SCREEN_MODES[args.mode], allowed)


def command_baseline(args):
    return run_grid(args, *BASELINES[args.agent], release=read_json(args.release) if args.release else None)


def command_label_seeds(args):
    splits = validate_splits(read_json(args.splits))
    groups = label_seeds(load_episodes(args.root), splits["screening_policy_seeds"])
    write_json(args.output, groups)
    print(json.dumps({"output": str(args.output),
                      "qualified": sorted(task for task, value in groups["tasks"].items() if value["qualified"])}))
    return 0


def command_publish_cards(args):
    """Write set-A native-card performance into each screened task config in place; unscreened tasks keep untested.
    Configs are hashed, so run this before the set-B reference runs."""
    splits = validate_splits(read_json(args.splits))
    seeds = splits["screening_policy_seeds"]
    episodes = load_episodes(args.root)
    screened = {m.get("task") for m, result in episodes if m.get("kind") == "diagnostic_reference"
                and m.get("policy_seed", m.get("seed")) in seeds and result.get("status") != "infrastructure_error"}
    published = []
    for path in args.task_configs:
        config = task_parts(path)[0]
        if config["task"] not in screened:
            continue
        cards = [item for item in config["reference_prompts"] if item["id"] == "native_instruction"]
        if len(cards) != 1:
            raise ValueError(f"{config['task']} has no single native_instruction card")
        cards[0]["performance"] = native_card_performance(episodes, config["task"], seeds)
        config["status"] = "screened"
        write_json(path, config)
        published.append(config["task"])
    print(json.dumps({"published": published}))
    return 0


def check_reference_episodes(release, episodes, contract_hash):
    """Every selected (task, scene seed) x reference policy seed needs a usable set-B diagnostic_reference
    episode recorded under the hash being frozen."""
    have = {(m.get("task"), m.get("scene_seed"), m.get("policy_seed")) for m, result in episodes
            if m.get("kind") == "diagnostic_reference" and m.get("contract_hash") == contract_hash
            and result.get("status") != "infrastructure_error"}
    missing = [(task, scene, policy) for task, entry in sorted(release["tasks"].items())
               for scene in entry["leave_alone"] + entry["needs_help"] for policy in release["reference_policy_seeds"]
               if (task, scene, policy) not in have]
    if missing:
        raise ValueError(f"missing usable set-B diagnostic_reference episodes under contract {contract_hash} "
                         f"(task, scene_seed, policy_seed): {missing}")


def command_freeze_benchmark(args):
    groups = read_json(args.groups)
    configs = {config["task"]: config for config, _, _ in load_task_configs(args.task_configs)}
    splits = validate_splits(read_json(args.splits))
    policy = RemotePolicy(args.policy_url)
    payload, contract_hash = benchmark_contract(configs.values(), policy.identity, splits)
    release = freeze_release(groups, configs, splits["reference_policy_seeds"], args.models, contract_hash,
                             allow_fewer=args.allow_fewer)
    check_reference_episodes(release, load_episodes(args.reference_root), contract_hash)
    release.update(groups_sha256=digest(groups), contract=payload, analysis_sha256=implementation_hashes(ANALYSIS_FILES))
    write_json(args.output, release)
    print(json.dumps({"output": str(args.output), "contract_hash": contract_hash, "tasks": sorted(release["tasks"])}))
    return 0


def command_scorecard(args):
    release = read_json(args.release)
    if "tasks" not in release:
        raise ValueError("scorecard requires a release written by freeze-benchmark")
    report = scorecard(load_scored_episodes(args.root), release)
    write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "systems": len(report["systems"])}))
    return 0


def command_qualify(args):
    report = qualification_report(read_json(args.evidence))
    report.update({"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat()})
    write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "status": report["status"]}))
    return 0 if report["status"] == "passed" else 2


def command_publish_policy_card(args):
    qualification = read_json(args.qualification)
    config = read_json(args.task_config)
    published = public_task_config(config, qualification, digest(qualification))
    write_json(args.output, published)
    print(json.dumps({"output": str(args.output), "status": published["status"]}))
    return 0


def command_release(args):
    qualification = read_json(args.qualification)
    if qualification.get("status") != "passed":
        raise ValueError("qualification report has not passed")
    config, _, _ = task_parts(args.task_config)
    splits = validate_splits(read_json(args.splits))
    policy = RemotePolicy(args.policy_url)
    expected_checkpoint = qualification.get("checkpoint_manifest_sha256")
    if not expected_checkpoint or expected_checkpoint != policy.identity["checkpoint_manifest_sha256"]:
        raise ValueError("qualification is not bound to the connected checkpoint")
    if qualification.get("policy_backend") != policy.identity["backend"]:
        raise ValueError("qualification is not bound to the connected policy backend")
    if config.get("status") != "qualified_candidate" or config.get("qualification_report_sha256") != digest(qualification):
        raise ValueError("task config must be published from this qualification report")
    if config != public_task_config(config, qualification, digest(qualification)):
        raise ValueError("published task performance does not match the qualification report")
    qualification_contract_hash = digest(qualification_contract_payload(config, policy.identity))
    if qualification.get("contract_hash") != qualification_contract_hash:
        raise ValueError("qualification is not bound to the current task and policy contract")
    paths = []
    for row in qualification["skill_conditions"]:
        paths.extend(row.get("trace_paths", []))
    paths.extend(qualification["full_task"].get("trace_paths", []))
    paths.extend(qualification["supervisory_relevance"].get("paired_trace_paths", []))
    resolved_paths = resolve_audit_paths(paths)
    if not resolved_paths or any(not path.is_file() for path in resolved_paths):
        raise ValueError("all audited qualification and relevance trace paths must exist under the project")
    payload = contract_payload(config, policy.identity, splits)
    release = {"schema_version": 2, "status": "frozen", "created_at": datetime.now(timezone.utc).isoformat(),
               "contract_hash": digest(payload), "qualification_report_sha256": digest(qualification),
               "evaluation_seeds": splits["evaluation_seeds"], "contract": payload}
    write_json(args.output, release)
    print(json.dumps({"output": str(args.output), "contract_hash": release["contract_hash"]}))
    return 0


def command_summarize(args):
    report = summarize(args.root)
    if args.output:
        write_json(args.output, report)
    print(json.dumps(report, indent=2))
    return 0


def parser():
    root = argparse.ArgumentParser(prog="robot-benchmark", description=__doc__)
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--task-config", type=Path, default=DEFAULT_TASK)
    doctor.add_argument("--policy-url")
    doctor.add_argument("--output", type=Path, default=PROJECT_ROOT / "runs" / "preflight.json")
    doctor.set_defaults(function=command_doctor)
    smoke = commands.add_parser("smoke-sim")
    smoke.add_argument("--task-config", type=Path, default=DEFAULT_TASK)
    smoke.add_argument("--seed", type=int, default=0)
    smoke.add_argument("--output", type=Path, required=True)
    smoke.set_defaults(function=command_smoke_sim)
    feasibility = commands.add_parser("feasibility")
    feasibility.add_argument("--task-config", type=Path, default=DEFAULT_TASK)
    feasibility.add_argument("--mode", choices=("ordinary", "supervisor"), required=True)
    feasibility.add_argument("--seeds", type=parse_seeds, required=True)
    feasibility.add_argument("--policy-seeds", type=parse_seeds)
    feasibility.add_argument("--policy-url", default="http://127.0.0.1:8765")
    feasibility.add_argument("--supervisor-interval", type=int, default=50)
    feasibility.add_argument("--output", type=Path, required=True)
    feasibility.set_defaults(function=command_feasibility)
    run = commands.add_parser("run")
    run.add_argument("--task-config", type=Path, default=DEFAULT_TASK)
    run.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    run.add_argument("--agent-config", type=Path, required=True)
    run.add_argument("--seeds", type=parse_seeds, required=True)
    run.add_argument("--policy-seeds", type=parse_seeds)
    run.add_argument("--policy-url", default="http://127.0.0.1:8765")
    run.add_argument("--video-record-interval", type=positive_int)
    run.add_argument("--skip-existing", action="store_true")
    run.add_argument("--output", type=Path, required=True)
    modes = run.add_mutually_exclusive_group(required=True)
    modes.add_argument("--development", action="store_true")
    modes.add_argument("--release", type=Path)
    run.set_defaults(function=command_run)
    for name, choices, function in (("screen", SCREEN_MODES, command_screen),
                                    ("baseline", BASELINES, command_baseline)):
        grid = commands.add_parser(name)
        grid.add_argument("--task-configs", type=Path, nargs="+", required=True)
        grid.add_argument("--scene-seeds", type=parse_seeds, required=True)
        grid.add_argument("--policy-seeds", type=parse_seeds, required=True)
        grid.add_argument("--mode" if name == "screen" else "--agent", choices=tuple(choices), required=True)
        grid.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
        grid.add_argument("--policy-url", default="http://127.0.0.1:8765")
        grid.add_argument("--video-record-interval", type=positive_int)
        grid.add_argument("--skip-existing", action="store_true")
        if name == "screen":
            grid.add_argument("--scenes-from", type=Path, help="groups.json from label-seeds (retry/sequencer only)")
        else:
            grid.add_argument("--release", type=Path)
        grid.add_argument("--output", type=Path, required=True)
        grid.set_defaults(function=function)
    labels = commands.add_parser("label-seeds")
    labels.add_argument("root", type=Path)
    labels.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    labels.add_argument("--output", type=Path, required=True)
    labels.set_defaults(function=command_label_seeds)
    cards = commands.add_parser("publish-cards")
    cards.add_argument("root", type=Path)
    cards.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    cards.add_argument("--task-configs", type=Path, nargs="+", required=True)
    cards.set_defaults(function=command_publish_cards)
    freeze = commands.add_parser("freeze-benchmark")
    freeze.add_argument("--groups", type=Path, required=True)
    freeze.add_argument("--task-configs", type=Path, nargs="+", required=True)
    freeze.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    freeze.add_argument("--models", nargs="+", required=True)
    freeze.add_argument("--policy-url", default="http://127.0.0.1:8765")
    freeze.add_argument("--allow-fewer", action="store_true")
    freeze.add_argument("--reference-root", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.set_defaults(function=command_freeze_benchmark)
    card = commands.add_parser("scorecard")
    card.add_argument("root", type=Path)
    card.add_argument("--release", type=Path, required=True)
    card.add_argument("--output", type=Path, required=True)
    card.set_defaults(function=command_scorecard)
    qualify = commands.add_parser("qualify")
    qualify.add_argument("--evidence", type=Path, required=True)
    qualify.add_argument("--output", type=Path, required=True)
    qualify.set_defaults(function=command_qualify)
    publish = commands.add_parser("publish-policy-card")
    publish.add_argument("--qualification", type=Path, required=True)
    publish.add_argument("--task-config", type=Path, default=DEFAULT_TASK)
    publish.add_argument("--output", type=Path, required=True)
    publish.set_defaults(function=command_publish_policy_card)
    release = commands.add_parser("freeze-release")
    release.add_argument("--qualification", type=Path, required=True)
    release.add_argument("--task-config", type=Path, default=DEFAULT_TASK)
    release.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    release.add_argument("--policy-url", default="http://127.0.0.1:8765")
    release.add_argument("--output", type=Path, required=True)
    release.set_defaults(function=command_release)
    summary = commands.add_parser("summarize")
    summary.add_argument("root", type=Path)
    summary.add_argument("--output", type=Path)
    summary.set_defaults(function=command_summarize)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return args.function(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
