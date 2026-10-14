# Work split to October 16 (revised October 12, 2026)

Three people, each with their own agent, GPU credits and API key, work in parallel toward the deliverable in
`docs/direction.md`. **Each person has a self-contained brief; point your agent at it:**

| Workstream | Owner | Brief | In one line |
|---|---|---|---|
| W1 scoring, analysis, write-up | Tom | `docs/briefs/w1_scoring.md` | Define and compute the time-charged score and the best fixed rule; design the final experiment; write the report. CPU only. |
| W2 policies and tasks | Ranveer (suggested) | `docs/briefs/w2_policies.md` | Measure the ability ladder (10% and 30% GR00T), run the step-by-step ceiling test, add predicates. GPU. |
| W3 harness and LLM runs | Third partner (suggested) | `docs/briefs/w3_harness.md` | Build session mode (one supervisor, several policies, past outcomes in context) and the time-aware prompt; run the pilots and the final LLM runs. GPU and API. |

The owners of W2 and W3 are suggestions; swap them if that fits better.

## Deliverable (October 16)

1. **Fixed task set:** unseen composite tasks with failures that a better instruction can fix (from the W2 ceiling
   test), plus trained tasks where leaving the policy alone is right. Some carry time-sensitive stories.
2. **Fixed policy set:** three policies of clearly different ability, from W2.
3. **Scoring (W1):** success and total time, with a fixed time charge per LLM call; regret against the best fixed
   supervision rule per (policy, task); separate measures for interrupting, check-in cadence and declaring "done".
4. **Baselines:** always-defer and restart-every-N.
5. **LLM sessions:** Opus 5.5 and Sonnet 5.5, in session mode (W3).
6. **Write-up** with limitations (W1).

## File ownership (one owner per file)

| Owner | Files |
|---|---|
| **W1** | New: `src/robot_benchmark/time_score.py`, `configs/time_pressure.json`, `scripts/score_time.py`, `tests/test_time_score.py`, `docs/time_score.md`, `docs/final_experiment.md`, `docs/report.md`. Existing: `docs/direction.md`, `docs/work_split.md`, `docs/briefs/*`, `handoff.md`, `README.md`, `docs/roadmap.md`, `docs/protocol.md`. |
| **W2** | `src/robot_benchmark/policy_worker.py`, `adapters/policy.py`, `tasks/predicates.py`, `diagnostics.py`, `scripts/download_checkpoint.py`, `configs/sources.lock.json`, `scripts/run_stage4.sh`, `scripts/run_stage5.sh`, `scripts/analyze_stage5.py`, new `scripts/run_stage6_*.sh`, `tests/test_policy_worker.py`, `tests/test_task_catalog.py`, `docs/task_catalog.md`, `docs/stage6_ladder.md`, `docs/stage6_ceiling.md`. |
| **W3** | `src/robot_benchmark/cli.py`, `runner.py`, `contracts.py`, `adapters/agents.py`, `baselines.py`, new `session.py`, `configs/model-*.json`, `configs/tasks/*.json`, `scripts/probe_model.py`, `tests/test_cli.py`, `tests/test_agents*.py`, `tests/test_runner*.py`, new `tests/test_session.py`, `docs/session_mode.md`, `docs/stage6_pilot.md`. |
| **Shared, append-only** | `docs/decisions.md`: add rows at the end only, and rebase if the push conflicts. |

**Asking for a change.** If you need a change in a file you do not own, ask its owner and do not edit it yourself.
The interfaces below are fixed so that nobody needs to.

**Unowned files.** A file not in the table (for example `scripts/bootstrap_gpu.py` or `src/robot_benchmark/sim/`) is
frozen. Ask Tom before touching it.

## Interfaces (fixed names; change only by agreement and a `docs/decisions.md` row)

| From → to | What | Exact form |
|---|---|---|
| W2 → all | Policy backends | `--backend` names: `groot` (multitask, existing), `groot_pretrain` (existing, not a benchmark policy), `groot_u10`, `groot_u30` (new: `target_fraction/composite_unseen_10p` and `_30p`), `pi05` (existing, untested). Checkpoint paths `checkpoints/<backend>/...`. |
| W2 → all | Ability table | `runs/stage6_ladder/analysis.json`, written by `scripts/analyze_stage5.py` (same schema as stage 5's), summarized in `docs/stage6_ladder.md`. |
| W2 → W1 | Trigger predicates for time-sensitive clocks | Logged per step in `evaluator/events.jsonl` like the other predicates: `ice_out_of_bowl` (MakeIceLemonade: at least one ice cube has left the ice bowl) and `pan_off_stove` (PanTransfer: the pan is not on a burner). All other time-sensitive tasks start their clock at step 0. |
| W1 → W3 | Time parameters | `configs/time_pressure.json` (format revised October 13; `docs/time_score.md`): `{"call_seconds": <float>, "tasks": {"<Task>": {"deadline_seconds": <float, counted from step 0>, "story": {"text": "<one sentence shown to the supervisor>", "clock_starts": "step0" or "<predicate name>", "limit_seconds": <float or null>}}}}`. `story` exists only for the five time-sensitive tasks. Values are fixed on October 14; read them from the file, never hard-code them. |
| W3 → W1 | Session records | `<run root>/sessions/<session_id>/session.jsonl`, one line per episode in order: `{"session_id", "index", "policy_label", "backend", "task", "scene_seed", "policy_seed", "episode_dir"}`. Episode folders keep today's format. |

## Rules

- **Branches.** Work on your own branch (`w1-scoring`, `w2-policies`, `w3-harness`) and open small pull requests to
  `main`. Rebase on `main` at least daily. Run `PYTHONPATH=src python3 -m unittest discover -s tests` before every
  push. Tom merges.
- **Contract changes.** Any change to a hashed file (`CONTRACT_FILES` in `cli.py`, plus `configs/tasks/*.json` and the
  system prompt) changes the contract hash. That is fine until October 14. After the release commit is tagged, nobody
  changes them.
- **Run directories never overlap:**
  - W1: `runs/time_score/`.
  - W2: `runs/stage6_ladder/`, `runs/stage6_ceiling/`.
  - W3: `runs/stage6_pilot/`, `runs/final/`.
- **Compute.**
  - **Credits:** each person uses their own credits.
  - **Pairing:** a paired comparison (same scene and seed, different supervisor) must run on one pod, because start
    states are machine-specific. Use `--expect-state`.
  - **Final runs:** one GPU type and the tagged commit.
  - **Cost guard:** every pod runs `scripts/pod_guard.sh backstop` and copies results back after every phase
    (`handoff.md` S.3).
- **Secrets** stay in Git-ignored files and are never printed.
- **Reporting.** W2 and W3 report in their own docs; only Tom edits `handoff.md`.

## Timeline

| Day | W1 (Tom) | W2 (policies and tasks) | W3 (harness and LLM) |
|---|---|---|---|
| Oct 13 | `time_score.py` with tests; offline rescoring of stages 3-5; `configs/time_pressure.json` format and draft values | Pin `groot_u10` and `groot_u30`; start the ladder run; write `SEQUENCES` for PortionHotDogs and GarnishPancake | Session mode with tests; experience blocks in `adapters/agents.py` |
| Oct 14 | Fix time values and the final experiment (`docs/final_experiment.md`, a `docs/decisions.md` row); tag the release commit with W2 and W3 | Ceiling test; trigger predicates; recommend the policy and task set | Time-aware prompt; `probe_model.py`; one short Opus pilot session on a pod |
| Oct 15 | Score the final runs as they arrive | Final pod A (W2's credits): baselines and the Opus sessions, using W3's `session` command | Final pod B (W3's credits, same GPU type): baselines and the Sonnet sessions |
| Oct 16 | Report, limitations, reproduction notes | Review the report | Review the report |
