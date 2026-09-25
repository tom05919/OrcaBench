"""Privileged diagnostics; never eligible as LLM benchmark submissions."""
import copy
import math

from .contracts import ModelReply
from .evaluation import wilson_interval


def _is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def qualification_config_view(config):
    """Fields that affect policy qualification, excluding measured public results."""
    value = copy.deepcopy(config)
    value.pop("status", None)
    value.pop("qualification_report_sha256", None)
    value.pop("policy_backend", None)
    value.pop("checkpoint_manifest_sha256", None)
    value.pop("diagnostic_full_task_performance", None)
    value.pop("supervisory_relevance", None)
    for skill in value["skills"]:
        skill.pop("performance", None)
    return value


def public_task_config(config, report, report_sha256):
    """Publish audited performance without exposing trace paths to model adapters."""
    if report.get("status") != "passed" or not _is_sha256(report_sha256):
        raise ValueError("a passed, hashed qualification report is required")
    value = copy.deepcopy(config)
    by_skill = {}
    for row in report["skill_conditions"]:
        by_skill.setdefault(row["skill"], []).append(row)
    for skill in value["skills"]:
        rows = sorted(by_skill.get(skill["id"], []), key=lambda row: row["condition"])
        if len(rows) != 2:
            raise ValueError(f"missing qualification rows for {skill['id']}")
        successes = sum(row["successes"] for row in rows)
        trials = sum(row["trials"] for row in rows)
        limitations = []
        for row in rows:
            for limitation in row["limitations"]:
                if limitation not in limitations:
                    limitations.append(limitation)
        skill["performance"] = {
            "status": "qualified_screening",
            "checkpoint_manifest_sha256": report["checkpoint_manifest_sha256"],
            "successes": successes,
            "trials": trials,
            "success_rate": successes / trials,
            "conditions": [
                {
                    "name": row["condition"],
                    "successes": row["successes"],
                    "trials": row["trials"],
                    "success_rate": row["successes"] / row["trials"],
                    "wilson_95": row["wilson_95"],
                    "duration_steps": copy.deepcopy(row["duration_steps"]),
                }
                for row in rows
            ],
            "observed_limitations": limitations,
            "note": "Engineering screening evidence; not a general capability estimate.",
        }
    full = report["full_task"]
    value.update({
        "status": "qualified_candidate",
        "qualification_report_sha256": report_sha256,
        "policy_backend": report["policy_backend"],
        "checkpoint_manifest_sha256": report["checkpoint_manifest_sha256"],
        "diagnostic_full_task_performance": {
            "successes": full["successes"], "trials": full["trials"],
            "success_rate": full["successes"] / full["trials"],
            "wilson_95": full["wilson_95"],
        },
        "supervisory_relevance": {"verified": True, "note": "See the private qualification report and traces."},
    })
    return value


class OrdinaryPolicySupervisor:
    identity = {"kind": "diagnostic", "model": "ordinary_full_task_policy"}

    def __init__(self, env):
        self.env = env

    def decide(self, observation):
        # Match the upstream evaluator's privileged stopping behavior. This is
        # a diagnostic reproduction and never a scored LLM run.
        if self.env.evaluate()["success"]:
            return ModelReply({"op": "complete"})
        steps = min(observation["max_interval"], observation["remaining_steps"])
        decision = {"op": "continue", "steps": steps} if observation["active_skill"] else {
            "op": "start", "skill": "full_task", "steps": steps,
        }
        return ModelReply(decision)


class DiagnosticSupervisor:
    """Hand-authored selection only: every physical action still comes from the VLA."""
    identity = {"kind": "diagnostic", "model": "privileged_predicate_supervisor_v1"}

    def __init__(self, env, interval=50):
        self.env, self.interval = env, interval

    def decide(self, observation):
        truth = self.env.evaluate()
        if truth["success"]:
            return ModelReply({"op": "complete"})
        if (not truth["cereal_on_counter"] or not truth["bowl_on_counter"]) and not truth["cabinet_open"]:
            skill = "open_cabinet"
        elif not truth["cereal_on_counter"]:
            skill = "transfer_cereal"
        elif not truth["bowl_on_counter"]:
            skill = "transfer_bowl"
        else:
            skill = "close_cabinet"
        steps = min(self.interval, observation["max_interval"], observation["remaining_steps"])
        active = observation["active_skill"]
        decision = {"op": "continue", "steps": steps} if active == skill else {
            "op": "start" if active is None else "switch", "skill": skill, "steps": steps,
        }
        return ModelReply(decision)


def qualification_report(evidence):
    """Missing evidence blocks a gate; it is not a measured policy failure."""
    required = {(skill, condition) for skill in ("open_cabinet", "transfer_cereal", "transfer_bowl", "close_cabinet")
                for condition in ("nominal_entry", "natural_intermediate")}
    observed = {}
    missing_metadata = []
    for row in evidence.get("skill_conditions", []):
        key = (row["skill"], row["condition"])
        if key not in required:
            raise ValueError("unexpected skill condition")
        if key in observed:
            raise ValueError("duplicate skill condition")
        successes, trials = row["successes"], row["trials"]
        if type(successes) is not int or type(trials) is not int or not 0 <= successes <= trials:
            raise ValueError("invalid skill counts")
        duration = row.get("duration_steps")
        duration_valid = (
            isinstance(duration, dict)
            and set(duration) == {"min", "median", "max"}
            and all(
                type(duration[name]) in (int, float)
                and math.isfinite(duration[name])
                and duration[name] >= 0
                for name in duration
            )
            and duration["min"] <= duration["median"] <= duration["max"]
        )
        limitations = row.get("limitations")
        trace_paths = row.get("trace_paths")
        if not duration_valid or not isinstance(limitations, list) or not all(isinstance(item, str) for item in limitations):
            missing_metadata.append(f"{row['skill']}:{row['condition']}:performance_card")
        if not isinstance(trace_paths, list) or not trace_paths or not all(isinstance(item, str) and item for item in trace_paths):
            missing_metadata.append(f"{row['skill']}:{row['condition']}:trace_paths")
        observed[key] = {**row, "wilson_95": wilson_interval(successes, trials)}
    missing = sorted(required - observed.keys())
    missing_identity = [
        name for name in ("contract_hash", "checkpoint_manifest_sha256") if not _is_sha256(evidence.get(name))
    ]
    if evidence.get("policy_backend") not in ("groot", "pi05"):
        missing_identity.append("policy_backend")
    complete = not missing and not missing_identity and not missing_metadata and all(
        observed[key]["trials"] >= 10 for key in required
    )
    full = evidence.get("full_task", {"successes": 0, "trials": 0})
    successes, trials = full["successes"], full["trials"]
    if type(successes) is not int or type(trials) is not int or not 0 <= successes <= trials:
        raise ValueError("invalid full-task counts")
    full_trace_paths = full.get("trace_paths")
    if not isinstance(full_trace_paths, list) or not full_trace_paths or not all(
        isinstance(item, str) and item for item in full_trace_paths
    ):
        missing_metadata.append("full_task:trace_paths")
        complete = False
    complete &= trials >= 20
    skill_pass = complete and all(observed[key]["successes"] / observed[key]["trials"] >= .8 for key in required)
    full_pass = trials >= 20 and successes / trials >= .8
    relevance = evidence.get("supervisory_relevance", {})
    relevance_verified = relevance.get("verified") is True and bool(relevance.get("paired_trace_paths"))
    state = "insufficient_evidence" if not complete else "failed" if not (skill_pass and full_pass) else "pending_relevance" if not relevance_verified else "passed"
    return {"status": state, "contract_hash": evidence.get("contract_hash"),
            "policy_backend": evidence.get("policy_backend"),
            "checkpoint_manifest_sha256": evidence.get("checkpoint_manifest_sha256"),
            "missing_conditions": missing, "missing_identity": missing_identity,
            "missing_metadata": missing_metadata,
            "skill_conditions": list(observed.values()),
            "full_task": {**full, "wilson_95": wilson_interval(successes, trials)},
            "supervisory_relevance": relevance, "evidence_type": "operator_supplied_audit_counts_not_automatic_certification"}
