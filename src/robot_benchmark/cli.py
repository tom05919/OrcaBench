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
import traceback
from urllib.parse import urlparse

from . import __version__
from .adapters.agents import HTTPAgent, MAX_MODEL_TOKENS, SYSTEM_PROMPT
from .adapters.policy import RemotePolicy
from .contracts import Limits, Skill
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASK = PROJECT_ROOT / "configs" / "cereal_and_bowl.json"
DEFAULT_SPLITS = PROJECT_ROOT / "configs" / "splits.json"
SOURCE_LOCK = PROJECT_ROOT / "configs" / "sources.lock.json"
CONTRACT_FILES = (
    "src/robot_benchmark/contracts.py",
    "src/robot_benchmark/runner.py",
    "src/robot_benchmark/adapters/robocasa.py",
    "src/robot_benchmark/adapters/policy.py",
    "src/robot_benchmark/adapters/agents.py",
)
FULL_TASK_INSTRUCTION = (
    "Open the cabinet. Pick the cereal and bowl from the cabinet and place them "
    "on the counter next to the milk. Then close the cabinet."
)
SCORED_GOAL = (
    "Move the cereal box and the bowl from the cabinet onto the adjacent counter, "
    "and leave the cabinet closed. Declare completion when both objects are on the "
    "counter and the cabinet is closed."
)
SKILL_INSTRUCTIONS = {
    "open_cabinet": "Open the cabinet.",
    "transfer_cereal": "Pick the cereal box from the cabinet and place it on the counter.",
    "transfer_bowl": "Pick the bowl from the cabinet and place it on the counter.",
    "close_cabinet": "Close the cabinet.",
}


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


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
    for name in names:
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
    return value


def task_parts(path: Path):
    config = read_json(path)
    expected = {"task", "split", "goal", "max_steps", "max_decisions", "max_interval", "camera_size", "video_record_interval", "skills"}
    fixed = (
        config.get("task") == "CerealAndBowl"
        and config.get("split") == "pretrain"
        and config.get("goal") == SCORED_GOAL
        and (config.get("max_steps"), config.get("max_decisions"), config.get("max_interval")) == (4350, 100, 100)
        and config.get("camera_size") == 256
        and config.get("video_record_interval") == 2
        and config.get("agent_image_history") == "current_frame_only_plus_decision_history"
        and config.get("artificial_disturbances") is False
    )
    if not expected <= config.keys() or not fixed:
        raise ValueError("this pilot supports only the audited CerealAndBowl task config")
    if not isinstance(config["skills"], list) or not all(isinstance(item, dict) for item in config["skills"]):
        raise ValueError("skills must be a list of objects")
    if [item.get("id") for item in config["skills"]] != list(SKILL_INSTRUCTIONS) or any(
        item.get("instruction") != SKILL_INSTRUCTIONS[item["id"]] for item in config["skills"]
    ):
        raise ValueError("the fixed CerealAndBowl skill library changed")
    skills = [Skill(item["id"], item["instruction"], item["description"], item["performance"])
              for item in config["skills"]]
    limits = Limits(config["max_steps"], config["max_decisions"], config["max_interval"])
    return config, skills, limits


def implementation_hashes():
    import hashlib
    result = {}
    for relative in CONTRACT_FILES:
        data = (PROJECT_ROOT / relative).read_bytes()
        result[relative] = hashlib.sha256(data).hexdigest()
    return result


def contract_payload(task_config, policy_identity, splits=None):
    lock = read_json(SOURCE_LOCK)
    source_identity = {
        name: entry["revision"] for name, entry in lock["repositories"].items()
    }


def qualification_contract_payload(task_config, policy_identity):
    return contract_payload(qualification_config_view(task_config), policy_identity)
    source_identity["checkpoint_registry_revision"] = lock["checkpoint"]["revision"]
    return {
        "schema_version": 1,
        "task_config": task_config,
        "source_revisions": source_identity,
        "policy_identity": policy_identity,
        "system_prompt": SYSTEM_PROMPT,
        "model_call_max_tokens": MAX_MODEL_TOKENS,
        "implementation_sha256": implementation_hashes(),
        "splits": splits,
    }


def episode_path(output: Path, seed: int):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return output / f"seed-{seed}-{stamp}"


def infrastructure_result(error):
    return {
        "status": "infrastructure_error", "success": False,
        "physical_success_final": None, "physical_success_any": False,
        "false_completion": False, "steps": 0, "model_calls": 0,
        "policy_calls": 0, "switches": 0, "retries": 0, "interrupts": 0,
        "intervals": [], "model_seconds": 0.0, "policy_seconds": 0.0,
        "wall_seconds": 0.0, "usage": [],
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


def run_episode(*, seed, output, task_config, skills, limits, policy, agent_factory, kind, contract_hash):
    path = episode_path(output, seed)
    manifest = {
        "artifact_type": "episode", "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": __version__, "kind": kind, "seed": seed,
        "contract_hash": contract_hash, "agent": {"kind": kind, "model": "setup_pending"},
        "policy": policy.identity,
        "task": task_config["task"], "split": task_config["split"],
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
        runner = Runner(env, policy, agent, skills, task_config["goal"], limits, records,
                        recording_interval=task_config["video_record_interval"])
        result = runner.run(seed)
    except Exception as error:
        if env is not None:
            try:
                env.close()
            except Exception:
                pass
        result = infrastructure_result(error)
        records.append("evaluator/errors.jsonl", {"error": result["infrastructure_error"], "traceback": traceback.format_exc()})
        records.write("result.json", result)
    print(json.dumps({"seed": seed, "episode": str(path), "status": result["status"], "success": result["success"]}))
    return result


def command_doctor(args):
    task, _, limits = task_parts(args.task_config)
    lock = read_json(SOURCE_LOCK)
    checks = {
        "project_root": str(PROJECT_ROOT), "python": platform.python_version(),
        "platform": platform.platform(), "free_gib": round(shutil.disk_usage(PROJECT_ROOT).free / 1024**3, 2),
        "task": task["task"], "horizon": limits.max_steps,
        "source_lock_status": lock.get("status"), "core_import": True,
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
    ok = checks["sim_import"]["ok"] and checks.get("policy_worker", {"ok": True})["ok"]
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


def command_feasibility(args):
    config, public_skills, limits = task_parts(args.task_config)
    if not 1 <= args.supervisor_interval <= limits.max_interval:
        raise ValueError(f"supervisor interval must be in [1, {limits.max_interval}]")
    policy = RemotePolicy(args.policy_url)
    if args.mode == "ordinary":
        skills = [Skill("full_task", FULL_TASK_INSTRUCTION, "Unmodified whole-task policy diagnostic.",
                        {"status": "diagnostic"})]
        factory = lambda env: OrdinaryPolicySupervisor(env)
    else:
        skills = public_skills
        factory = lambda env: DiagnosticSupervisor(env, interval=args.supervisor_interval)
    payload = qualification_contract_payload(config, policy.identity)
    contract_hash = digest(payload)
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "contract.json", payload)
    for seed in args.seeds:
        run_episode(seed=seed, output=args.output, task_config=config, skills=skills, limits=limits,
                    policy=policy, agent_factory=factory, kind=f"diagnostic_{args.mode}", contract_hash=contract_hash)
    return 0


def command_run(args):
    config, skills, limits = task_parts(args.task_config)
    model_config = read_json(args.agent_config)
    policy = RemotePolicy(args.policy_url)
    splits = validate_splits(read_json(args.splits))
    payload = contract_payload(config, policy.identity, splits)
    contract_hash = digest(payload)
    kind = "llm_development"
    if args.release:
        release = read_json(args.release)
        if release.get("status") != "frozen" or release.get("contract_hash") != contract_hash:
            raise ValueError("release manifest is absent, not frozen, or does not match the current contract")
        allowed = set(release["evaluation_seeds"])
        if not set(args.seeds) <= allowed:
            raise ValueError("official runs may use only frozen evaluation seeds")
        kind = "llm"
    elif not args.development:
        raise ValueError("unqualified runs require --development; official runs require --release")
    agent = HTTPAgent(model_config)
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "contract.json", payload)
    for seed in args.seeds:
        run_episode(seed=seed, output=args.output, task_config=config, skills=skills, limits=limits,
                    policy=policy, agent_factory=lambda env, value=agent: value, kind=kind,
                    contract_hash=contract_hash)
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
    release = {"schema_version": 1, "status": "frozen", "created_at": datetime.now(timezone.utc).isoformat(),
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
    feasibility.add_argument("--policy-url", default="http://127.0.0.1:8765")
    feasibility.add_argument("--supervisor-interval", type=int, default=50)
    feasibility.add_argument("--output", type=Path, required=True)
    feasibility.set_defaults(function=command_feasibility)
    run = commands.add_parser("run")
    run.add_argument("--task-config", type=Path, default=DEFAULT_TASK)
    run.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    run.add_argument("--agent-config", type=Path, required=True)
    run.add_argument("--seeds", type=parse_seeds, required=True)
    run.add_argument("--policy-url", default="http://127.0.0.1:8765")
    run.add_argument("--output", type=Path, required=True)
    modes = run.add_mutually_exclusive_group(required=True)
    modes.add_argument("--development", action="store_true")
    modes.add_argument("--release", type=Path)
    run.set_defaults(function=command_run)
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
