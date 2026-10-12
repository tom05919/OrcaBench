# Work split to October 16 (drafted October 12, 2026)

Three people, each with their own agent and GPU credits, work in parallel toward the deliverable in
`docs/direction.md`: a benchmark someone else can run, with results for at least two LLM supervisors.

- **What is shared:** the evaluation interface and the episode records.
- **What is not shared:** no two workstreams edit the same file, and each has its own run directory and its own pods.

## Deliverable (October 16)

1. **Fixed task set:** unseen composite tasks where a policy needs help, plus trained tasks where leaving it alone
   is right. Five tasks carry time-sensitive stories.
2. **Fixed policy set:** at least three policies of clearly different ability, from the official RoboCasa365
   checkpoints.
3. **Scoring:**
   - success and total time, with a fixed time charge per LLM call;
   - regret against the best fixed supervision rule per policy;
   - separate measures for interrupting, check-in cadence and declaring "done".
4. **Baselines:** always-defer and restart-every-N.
5. **Models:** Opus 5.5 and Sonnet 5.5.
6. **Write-up** with limitations.

## Workstreams

### W1: scoring, time charge, orchestrator prompt, integration and write-up (suggested: Tom)

- **Time layer.** A scoring layer that reads episode folders and computes:
  - total time = robot time + calls × charge;
  - per-task deadlines or decay;
  - the story timers, with clocks that start at a trigger event (needs trigger predicates from W3).

  It runs offline on stages 3-5 first, to check that the best fixed rate differs by task and policy under the new
  score. CPU only.
- **Prompt.** The orchestrator prompt states the time charge and the task's deadline (`adapters/agents.py`).
  Probe it with `scripts/probe_model.py` before any GPU run.
- **Integration.** Own `docs/direction.md`, `handoff.md`, `README.md`, and the scoring section of `docs/protocol.md`.
  Review and merge the other workstreams' pull requests. Write the final report.
- **Owns:** a new module (for example `src/robot_benchmark/timing.py`), its tests and analysis scripts,
  `adapters/agents.py`, `cli.py`, `runner.py`, `contracts.py` (only if needed), and the docs named above.

### W2: policy ladder (suggested: Ranveer, who built the stage 4 pod tooling)

- **Pin more checkpoints.** Pin the GR00T `target_fraction/composite_unseen_10p` and `_30p` checkpoints, the same
  way `groot_pretrain` was pinned on October 12 (LFS hashes, digest test). Optionally pin π0.5, whose backend exists
  but has never run.
- **Measure ability.** Run each new checkpoint on the unseen tasks with `scripts/run_stage4.sh` (`BACKEND`,
  `CHECKPOINT`, `TASK_LIST`) and `scripts/analyze_stage5.py`.
  - **Scenes:** use at least four (1000-1003). Stage 5 found most successes in one scene.
  - **Tasks:** at minimum the eight with a time story (five strong, three plausible; `docs/task_catalog.md`).
  - **Leave-alone tasks:** also run every policy, including the multitask checkpoint, on 4-6 trained tasks.
- **Cost guide:** stage 5 ran 128 long episodes in 3.4 hours on a 7.65-core pod for $2.72. Throughput is CPU-bound,
  so prefer a pod with 16 or more cores.
- **Recommend:** three policies with clearly different ability on the chosen tasks.
- **Drop the pretraining-only checkpoint** as a benchmark policy: it solved 0 of 62 with little partial progress.
- **Owns:** `policy_worker.py`, `adapters/policy.py`, `scripts/download_checkpoint.py`, `configs/sources.lock.json`,
  its driver script, `runs/stage6_ladder/` and `docs/stage6_ladder.md`.

### W3: ceiling test, trigger predicates and LLM pilots (suggested: the third partner)

- **Ceiling test.** On tasks where stage 5 shows partial progress, write step-by-step instructions and run
  `screen --mode sequencer` against plain runs on the same pod.
  - **Targets:** PortionHotDogs (food reaches the plates, the portions are never right) and GarnishPancake (the
    strawberry is reached, rarely placed), then MakeIceLemonade, SeparateFreezerRack and PanTransfer, all with the
    multitask checkpoint.
  - **Predicates:** the sequencer advances on a predicate per step, so every step in `SEQUENCES` needs one; the
    existing ones are in `tasks/predicates.py`.
  - **Tests:** `tests/test_task_catalog.py` currently requires `SEQUENCES` to cover exactly the `composite_seen`
    tasks; update it.
  - **Untested code:** the sequencer itself has never run on GPU. Run one episode first.
  - **Reading:** if perfect step-by-step instructions cannot help, no LLM can, and those tasks become leave-alone or
    are dropped.
- **Trigger predicates.** Add the predicates W1's timers need, for example "ice left the bowl" and "pan left the
  stove".
- **Pilots.** Once W1's prompt and W2's policies exist, run Opus and Sonnet pilot sessions on the chosen tasks.
- **Owns:** `tasks/predicates.py`, `diagnostics.py`, its driver script, `runs/stage6_ceiling/`, `runs/stage6_pilot/`
  and `docs/stage6_ceiling.md`.

## Rules that prevent conflicts

- **One owner per file**, as listed above. If you need a change in someone else's file, ask them.
  - `configs/tasks/*.json` belongs to W1. Time parameters go in a separate file, not in the task configs.
  - `cli.py`, `runner.py` and `contracts.py` are central and hashed. Only W1 edits them, and only after telling the
    others.
- **Branches and merges.** Each workstream works on its own branch and opens small pull requests to `main`. Rebase on
  `main` at least daily and run `PYTHONPATH=src python3 -m unittest discover -s tests` before every push.
- **Shared logs.** `docs/decisions.md` is append-only: add rows at the end and rebase if the push conflicts. Only W1
  edits `handoff.md`; W2 and W3 report in their own `docs/stage6_*.md`.
- **Run directories never overlap:** `runs/stage6_ladder/`, `runs/stage6_ceiling/`, `runs/stage6_pilot/`.
- **Compute.**
  - Each person uses their own credits.
  - A paired comparison (plain against supervised, same scene and seed) must run on one pod, because start states
    are machine-specific (`docs/stage3_results.md`).
  - The **final scored runs** use one GPU type and one tagged commit, because the contract hash covers both.
  - Every pod uses a pod-side guard that terminates it (`scripts/pod_guard.sh backstop`) and copies results back after
    every phase.
- **Secrets** stay in Git-ignored files and are never printed.

## Timeline

| Day | W1 (Tom) | W2 (ladder) | W3 (ceiling and pilots) |
|---|---|---|---|
| Oct 13 | Time layer, offline rescoring of stages 3-5, prompt draft | Pin 10% and 30%, run the unseen grid | Step lists for partial-progress tasks, ceiling test |
| Oct 14 | Prompt probe; fix task, policy and time parameters with W2 and W3; tag the release commit | Leave-alone tasks for all policies; recommend the policy set | Trigger predicates; first Opus pilot |
| Oct 15 | Run scoring on the final runs | Final runs, split by policy, same GPU type | Final runs (Sonnet), same GPU type |
| Oct 16 | Write-up, limitations, reproduction notes | Review the write-up | Review the write-up |
