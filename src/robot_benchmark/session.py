"""Ordered multi-policy sessions with a deliberately narrow past-outcome channel.

The callback owns ordinary episode artifacts. This module reserves a session row
before every attempted episode and retains failures outside the model's context.
"""
import copy
from datetime import datetime, timezone
import ipaddress
import json
import math
from pathlib import Path
import re
from time import time_ns
from urllib.parse import urlparse

from . import __version__
from .contracts import Limits, validate_decision
from .records import digest

ANONYMOUS_LABELS = ("K", "R", "T", "V", "W", "Z")
DEFAULT_EXPERIENCE_LIMIT = 24
MAX_SEED = 2**32 - 1
DEFAULT_MAX_INFRASTRUCTURE_ERRORS = 2
SCORE = "success x max(0, 1 - charged_seconds / deadline_seconds)"
TERMINAL_STATUSES = frozenset({"success", "false_completion", "step_budget_exhausted", "decision_budget_exhausted"})
PLAN_FIELDS = frozenset({"task", "scene_seed", "policy_seed", "policy_label", "backend"})
EXPERIENCE_FIELDS = frozenset({"policy", "goal", "decisions", "outcome"})


def _integer(value, name, minimum=0, maximum=MAX_SEED):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")
    return value


def _label(value):
    if value not in ANONYMOUS_LABELS:
        raise ValueError("policy label must be anonymous (K, R, T, V, W or Z)")
    return value


def _worker_endpoint(value):
    if not isinstance(value, str):
        raise ValueError("worker URL must be text")
    try:
        url = urlparse(value)
        port = url.port
        host = url.hostname
        if host == "localhost":
            normalized_host = "loopback"
        elif host and ipaddress.ip_address(host).is_loopback:
            normalized_host = "loopback"
        else:
            raise ValueError("worker must be loopback")
    except (ValueError, TypeError) as error:
        raise ValueError("worker must be a valid loopback HTTP URL") from error
    if (url.scheme != "http" or not port or url.username is not None or url.password is not None
            or url.path not in ("", "/") or url.query or url.fragment):
        raise ValueError("worker must be a loopback HTTP URL without credentials, path or query")
    return normalized_host, port


def validate_plan(entries, task_names, workers):
    """Validate the whole plan before any model or worker is contacted."""
    if not isinstance(entries, list) or not entries:
        raise ValueError("plan must be a nonempty JSON list")
    if not isinstance(workers, dict):
        raise ValueError("workers must map anonymous labels to loopback URLs")
    labels, backends = {}, {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) not in (PLAN_FIELDS, PLAN_FIELDS | {"expect_state"}):
            raise ValueError("plan entries must contain exactly task, scene_seed, policy_seed, policy_label, backend and optional expect_state")
        _text(entry["task"], "task")
        if entry["task"] not in task_names:
            raise ValueError(f"unknown task: {entry['task']}")
        for field in ("scene_seed", "policy_seed"):
            _integer(entry[field], field)
        label, backend = _label(entry["policy_label"]), _text(entry["backend"], "backend")
        if label in labels and labels[label] != backend or backend in backends and backends[backend] != label:
            raise ValueError("policy labels and backends must have a bijective mapping")
        labels[label], backends[backend] = backend, label
        if "expect_state" in entry and (not isinstance(entry["expect_state"], str)
                or re.fullmatch(r"[0-9a-f]{64}", entry["expect_state"]) is None):
            raise ValueError("expect_state must be a lowercase SHA256 hash")
    if set(workers) != set(labels):
        raise ValueError("workers must exactly match labels in the plan")
    endpoints = [_worker_endpoint(workers[label]) for label in labels]
    if len(set(endpoints)) != len(endpoints):
        raise ValueError("each policy label needs a distinct worker URL")
    return copy.deepcopy(entries)


def _seconds(value, name, allow_zero=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (not allow_zero and value == 0):
        raise ValueError(f"{name} must be a finite {'nonnegative' if allow_zero else 'positive'} number")
    return float(value)


def _public_pressure(value):
    if not isinstance(value, dict):
        raise ValueError("time pressure must be an object")
    public = {"call_seconds": _seconds(value.get("call_seconds"), "call_seconds", allow_zero=True),
              "deadline_seconds": _seconds(value.get("deadline_seconds"), "deadline_seconds"), "score": SCORE}
    if "story" in value:
        story = value["story"]
        if not isinstance(story, dict):
            raise ValueError("story must be an object")
        limit = story.get("limit_seconds")
        public["story"] = {"text": _text(story.get("text"), "story text"),
                           "limit_seconds": None if limit is None else _seconds(limit, "story limit_seconds")}
    return public


def public_time_context(config, model, task):
    """Project W1's private time configuration onto the version-6 model fields."""
    try:
        task_config = config["tasks"][task]
        value = {"call_seconds": config["call_seconds"][model],
                 "deadline_seconds": task_config["deadline_seconds"]}
        if "story" in task_config:
            value["story"] = task_config["story"]
    except (KeyError, TypeError) as error:
        raise ValueError(f"missing time configuration for model {model!r}, task {task!r}") from error
    return _public_pressure(value)


def _public_decisions(entries, steps):
    public = []
    if not isinstance(entries, list):
        raise ValueError("decisions must be a list")
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("accepted") is not True:
            continue
        try:
            step = _integer(entry.get("step_before"), "step_before", maximum=steps)
            decision = validate_decision(entry.get("decision"), Limits(max_steps=max(1, steps), max_interval=max(1, steps)))
        except ValueError:
            continue
        if decision.get("steps", 0) > steps - step:
            continue
        public.append({**decision, "step_before": step})
    return public


def project_experience(policy_label, result, decision_entries):
    """Only a completed, non-infrastructure episode may reveal its outcome."""
    _label(policy_label)
    if not isinstance(result, dict) or result.get("status") not in TERMINAL_STATUSES or result.get("infrastructure_error"):
        return None
    goal = _text(result.get("goal"), "goal")
    steps = _integer(result.get("steps"), "steps")
    calls = _integer(result.get("model_calls"), "model_calls")
    if type(result.get("success")) is not bool or result["success"] != (result["status"] == "success"):
        raise ValueError("terminal success must be a boolean consistent with status")
    decisions = _public_decisions(decision_entries, steps)
    declared = any(item["op"] == "complete" for item in decisions)
    return {"policy": policy_label, "goal": goal, "decisions": decisions,
            "outcome": {"success": result["success"], "steps": steps, "model_calls": calls,
                        "declaration_correct": result["success"] if declared else None}}


def _sanitize_experience(record):
    if not isinstance(record, dict) or not EXPERIENCE_FIELDS <= set(record):
        raise ValueError("experience must contain the documented public fields")
    label, goal = _label(record["policy"]), _text(record["goal"], "goal")
    outcome = record["outcome"]
    if not isinstance(outcome, dict):
        raise ValueError("experience outcome must be an object")
    steps = _integer(outcome.get("steps"), "steps")
    calls = _integer(outcome.get("model_calls"), "model_calls")
    declaration = outcome.get("declaration_correct")
    if type(outcome.get("success")) is not bool or (declaration is not None and type(declaration) is not bool):
        raise ValueError("experience outcomes must be boolean or a null declaration")
    if not isinstance(record["decisions"], list):
        raise ValueError("experience decisions must be a list")
    entries = []
    for decision in record["decisions"]:
        if not isinstance(decision, dict):
            continue
        entries.append({"accepted": True, "step_before": decision.get("step_before"),
                        "decision": {key: value for key, value in decision.items() if key in ("op", "prompt", "steps")}})
    return {"policy": label, "goal": goal, "decisions": _public_decisions(entries, steps),
            "outcome": {"success": outcome["success"], "steps": steps, "model_calls": calls,
                        "declaration_correct": declaration}}


class SessionAgent:
    """Wrap one shared agent with immutable, bounded public session context."""
    def __init__(self, agent, policy_label, experience, time_pressure, experience_limit=DEFAULT_EXPERIENCE_LIMIT):
        _integer(experience_limit, "experience_limit", minimum=1, maximum=DEFAULT_EXPERIENCE_LIMIT)
        self.agent = agent
        self.policy_label = _label(policy_label)
        if not isinstance(experience, list):
            raise ValueError("experience must be a list")
        self.experience = [_sanitize_experience(record) for record in experience[-experience_limit:]]
        self.time_pressure = _public_pressure(time_pressure)

    @property
    def identity(self):
        return self.agent.identity

    @property
    def last_trace(self):
        return getattr(self.agent, "last_trace", None)

    def decide(self, observation):
        public = copy.deepcopy(observation)
        public.update({"policy": self.policy_label, "experience": copy.deepcopy(self.experience),
                       "time_pressure": copy.deepcopy(self.time_pressure)})
        return self.agent.decide(public)


def _write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def _append(path, value):
    with path.open("a") as stream:
        stream.write(json.dumps(value, allow_nan=False) + "\n")


def _retain_setup_failure(episode_dir, entry, agent, session_contract, session_id, index, error):
    """Fill only missing conventional episode artifacts after callback setup fails."""
    episode_dir.mkdir(parents=True, exist_ok=True)
    if not (episode_dir / "manifest.json").exists():
        task_config = session_contract.get("task_configs", {}).get(entry["task"], {})
        policy_identity = session_contract.get("policy_identities", {}).get(entry["policy_label"])
        manifest = {
            "artifact_type": "episode", "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(), "benchmark_version": __version__,
            "kind": session_contract.get("kind", "llm_development"),
            "seed": entry["scene_seed"], "scene_seed": entry["scene_seed"], "policy_seed": entry["policy_seed"],
            "contract_hash": session_contract.get("episode_contract_hashes", {}).get(entry["policy_label"]),
            "agent": copy.deepcopy(agent.identity),
            "policy": copy.deepcopy(policy_identity) if policy_identity is not None else {
                "backend": entry["backend"], "status": "setup_unavailable"},
            "task": entry["task"], "split": task_config.get("split", "pretrain"),
            "policy_label": entry["policy_label"], "session_id": session_id, "session_index": index,
        }
        if "video_record_interval" in task_config:
            manifest["video_record_interval"] = task_config["video_record_interval"]
        _write(episode_dir / "manifest.json", manifest)
    if not (episode_dir / "result.json").exists():
        _write(episode_dir / "result.json", {
            "started_at_unix_ns": None, "ended_at_unix_ns": time_ns(),
            "status": "infrastructure_error", "goal": None,
            "scene_seed": entry["scene_seed"], "policy_seed": entry["policy_seed"],
            "success": False, "physical_success_final": None, "physical_success_any": False,
            "false_completion": False, "steps": 0, "model_calls": 0, "policy_calls": 0,
            "prompt_submissions": 0, "prompt_changes": 0, "prompt_restarts": 0,
            "discarded_actions": 0, "rejected_decisions": 0, "reply_parse": {}, "intervals": [],
            "model_seconds": 0.0, "policy_seconds": 0.0, "simulation_seconds": 0.0,
            "simulated_seconds": 0.0, "recording_seconds": 0.0, "evaluation_seconds": 0.0,
            "wall_seconds": 0.0, "usage": [],
            "infrastructure_error": f"{type(error).__name__}: {error}",
            "interrupted": not isinstance(error, Exception),
        })


def run_session(*, output, session_id, plan, workers, task_names, agent, run_entry, session_contract,
                experience_limit=DEFAULT_EXPERIENCE_LIMIT, max_infrastructure_errors=DEFAULT_MAX_INFRASTRUCTURE_ERRORS):
    """Run one new session; no silent resume or outcome-dependent plan changes."""
    if not isinstance(session_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", session_id) is None:
        raise ValueError("session_id must be a safe directory name")
    plan = validate_plan(plan, task_names, workers)
    _integer(experience_limit, "experience_limit", minimum=1, maximum=DEFAULT_EXPERIENCE_LIMIT)
    _integer(max_infrastructure_errors, "max_infrastructure_errors", minimum=1)
    session_dir = Path(output) / "sessions" / session_id
    if session_dir.exists():
        raise FileExistsError(f"session already exists; resume is unsupported: {session_dir}")
    pressure = session_contract.get("time_pressure", {})
    contexts = {entry["task"]: _public_pressure(pressure.get(entry["task"])) for entry in plan}
    manifest = {"session_id": session_id, "plan_hash": digest(plan), "contract_hash": digest(session_contract),
                "agent": copy.deepcopy(agent.identity), "plan": plan, "session_contract": session_contract,
                "experience_limit": experience_limit, "max_infrastructure_errors": max_infrastructure_errors}
    session_dir.mkdir(parents=True, exist_ok=False)
    _write(session_dir / "manifest.json", manifest)
    _write(session_dir / "session_result.json", {"status": "running", "attempted_episodes": 0})
    rows, experience, consecutive_errors = [], [], 0
    status = "completed"
    for index, entry in enumerate(plan):
        episode_dir = session_dir / "episodes" / f"{index:04d}"
        episode_dir.parent.mkdir(exist_ok=True)
        row = {"session_id": session_id, "index": index,
               **{field: entry[field] for field in ("policy_label", "backend", "task", "scene_seed", "policy_seed")},
               "episode_dir": str(episode_dir.relative_to(session_dir))}
        _append(session_dir / "session.jsonl", row)
        rows.append(row)
        wrapper = SessionAgent(agent, entry["policy_label"], experience, contexts[entry["task"]], experience_limit)
        try:
            actual_dir, result, decisions = run_entry(copy.deepcopy(entry), wrapper, episode_dir, index)
            if Path(actual_dir).resolve() != episode_dir.resolve():
                raise ValueError("callback must use the reserved episode directory")
            if not isinstance(result, dict) or not isinstance(decisions, list):
                raise ValueError("callback must return result dict and decisions list")
            if result.get("interrupted"):
                raise KeyboardInterrupt("episode interrupted")
            infrastructure = result.get("status") == "infrastructure_error" or bool(result.get("infrastructure_error"))
            if infrastructure:
                _append(session_dir / "errors.jsonl", {"index": index, "error": result.get("infrastructure_error") or "infrastructure_error"})
            else:
                record = project_experience(entry["policy_label"], result, decisions)
                if record is None:
                    raise ValueError("callback returned an unknown or nonterminal status")
                experience.append(record)
                experience = experience[-experience_limit:]
        except BaseException as error:
            # SystemExit/KeyboardInterrupt are retained but always re-raised.
            infrastructure = True
            description = f"{type(error).__name__}: {error}"
            _retain_setup_failure(episode_dir, entry, agent, session_contract, session_id, index, error)
            _append(session_dir / "errors.jsonl", {"index": index, "error": description})
            if not isinstance(error, Exception):
                _write(session_dir / "session_result.json", {"status": "interrupted", "attempted_episodes": len(rows)})
                raise
        consecutive_errors = consecutive_errors + 1 if infrastructure else 0
        if consecutive_errors >= max_infrastructure_errors:
            status = "infrastructure_error"
            break
    _write(session_dir / "session_result.json", {"status": status, "attempted_episodes": len(rows),
           "consecutive_infrastructure_errors": consecutive_errors})
    return rows
