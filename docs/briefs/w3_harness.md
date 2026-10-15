# W3 brief: session mode, time-aware prompt, pilots and final LLM runs (suggested: the third partner)

**Read first:** `AGENTS.md`, `handoff.md` section S, `docs/direction.md`, `docs/work_split.md` (ownership and
interfaces), `docs/protocol.md` ("Model-visible information" and "Decision semantics"), and the October 9 row of
`docs/decisions.md`. The simulator already does what you are building: see `src/robot_benchmark/sim/agent.py`
(`build_content`) and `docs/env_design.md` (blocks B7 and B8).

## Update from W1, October 13 (read first)

- **Final policies (Tom):** `groot`, `groot_u30` and `pi05` (π0.5, a different architecture with a 5-step action
  chunk). Every final session has three policy workers: two GR00T and one π0.5.
  - **GPU memory:** the π0.5 worker needs `XLA_PYTHON_CLIENT_PREALLOCATE=false` (or a memory fraction) next to the
    GR00T workers.
  - **Plans:** session plans come from `scripts/make_session_plans.py --policies groot groot_u30 pi05`.
- **Monitoring mode:** W2's ceiling test found no unseen task that correct step-by-step instructions can rescue, so
  the benchmark measures monitoring, declaring and restraint. The prompt must not suggest that re-prompting fixes
  failures; describe the decisions neutrally.
- **Call charge:** each model's calibrated `call_seconds[model]` (format in `docs/work_split.md`). Your probe and pilot
  provide the medians that W1 freezes.

## Goal

The benchmark needs **one supervisor, in one context, supervising several policies, and learning from how earlier
episodes went**. Today the real harness runs every episode independently, and the model sees nothing from earlier
episodes. Build that session mode and a prompt that states the time cost, then run the pilots and the final LLM runs.

## How an episode runs today

- **Entry point:** `cli.py` `run` → `run_grid` → `run_episode(seed, policy_seed, output, task_config,
  reference_prompts, limits, policy, agent_factory, kind, contract_hash, expected_start_state)`.
- **Per decision:** `runner.Runner.observation()` builds the model-visible observation (schema 4). The adapter in
  `adapters/agents.py` turns it into one Messages API call with `SYSTEM_PROMPT` (version 5), parses one JSON decision,
  and returns a `ModelReply`.
- **Policy:** `adapters/policy.py` `RemotePolicy` talks to one policy worker URL. Its identity goes into the manifest.

## Steps

1. **Session runner.** Add `src/robot_benchmark/session.py`, plus a `session` command in `cli.py`.
   - **Input: a plan file** (JSON) with one entry per episode, in order: `{task, scene_seed, policy_seed,
     policy_label, backend, expect_state?}`. Also give a mapping from `policy_label` to the policy worker URL: one
     worker per backend on the pod, on separate ports.
   - **Episodes:** run them in order with one supervisor configuration (`--agent-config`).
   - **Experience:** before each episode, pass the records of earlier episodes in this session to the adapter.
   - **Output:** `<root>/sessions/<session_id>/session.jsonl`, in the format fixed in `docs/work_split.md`. Each
     episode folder keeps today's format.
2. **Experience records (a contract change).** Text only, no images, one record per earlier episode:
   - the anonymous policy label (K, R, T), not the backend;
   - the task goal;
   - the decisions (op, steps, prompt, at which step);
   - the outcome: success or failure, steps used, model calls, and whether the declaration was correct.

   A record must **never** contain predicates, subgoal flags, object coordinates, the scene seed or the reward. Showing
   an episode's success only *after* it ends is the one deliberate exposure, as in the simulator; log it in
   `docs/decisions.md`. Add the current episode's anonymous `policy` label to the observation.
3. **Adapter (`adapters/agents.py`).**
   - **Payload order:** put the experience before the current episode's content, with `cache_control` on the last
     experience block so earlier episodes become cheap cache reads (the pattern in `sim/agent.py` `build_content`).
   - **Size limit:** cap the experience at the last N records.
   - **Unchanged:** keep `DECISION_FORMAT`, effort `medium` and the retry logic.
4. **Time-aware system prompt (version 6, a contract change).** It must state:
   - that each response is charged the supervisor's own `call_seconds[<model id>]` on the task clock, read from
     `configs/time_pressure.json` (W1's file; the format is in `docs/work_split.md`) and not hard-coded;
   - the task's deadline (`deadline_seconds`, from step 0) and, when the task has a `story`, its `text` and, if
     `limit_seconds` is not null, the limit;
   - that several policies of different ability take turns and that records of earlier episodes come first;
   - the score, using W1's wording in `docs/time_score.md`.

   It must not mention predicates or the checker's internals. Probe it with `scripts/probe_model.py` before any GPU
   run: exit 0 means every request succeeded and every reply was strict JSON. Log the prompt version change.
5. **Baselines.** The fixed-rule baselines already exist in `baselines.py` (`always_defer`, `reissue`, `reissue_50`,
   `reissue_200`, `reissue_400`). If `docs/final_experiment.md` (W1) needs a baseline that stops at a fixed step,
   add it there to W1's specification.
6. **Tests:** `tests/test_session.py` and updates to `tests/test_cli.py`, using the existing mock environment and
   policy patterns, with no simulator. Cover:
   - the episode order and the records written;
   - labels are anonymous;
   - the experience never contains forbidden fields;
   - the payload puts experience first;
   - the prompt reads `configs/time_pressure.json`.
7. **Pilot, October 14:** `runs/stage6_pilot/`, report in `docs/stage6_pilot.md`.
   - **Session:** one short Opus session, 2 policies × 2 tasks × 2 scenes = 8 episodes, on one pod with one worker per
     backend.
   - **Check:** records, cost per call, latency, and that W1's `scripts/score_time.py` reads the session.
   - **Latency calibration for W1:** report each model's median wall-clock seconds per call (`model_timings.jsonl`)
     under prompt version 6 and effort `medium`, from the probe or pilot, for both Opus and Sonnet. W1 freezes these as
     `call_seconds` on October 14.
   - **Cost guide:** in stage 3, Opus cost $0.019 per call and about 4.7 calls per episode, without experience.
8. **Final runs, October 15.** Pod B on your credits, same GPU type as W2's pod A, at the tagged commit:
   - the baselines and the Sonnet sessions, following `docs/final_experiment.md`;
   - the baselines first, then the sessions, with each plan entry's `expect_state` taken from the baseline run on the
     same pod, so the pairs start from identical states.

   Document the exact commands in `docs/session_mode.md` so W2 can run the Opus sessions on pod A.

## Interfaces

- **You provide:** the `session` command; `session.jsonl` records; the prompt; `docs/session_mode.md`; the latency
  calibration (median seconds per call per model, prompt version 6).
- **You consume:** `configs/time_pressure.json` (W1); the policy backends and worker setup (W2);
  `docs/final_experiment.md` (W1).

## Definition of done

- Session mode, experience blocks and prompt version 6 are merged, with tests.
- The prompt probe passes.
- One real pilot session ran cleanly and was scored by W1's script.
- The final sessions ran on the tagged commit, with every attempted episode kept and infrastructure errors reported
  separately.

## Do not

- Edit W1 or W2 files.
- Expose anything privileged to the model.
- Change budgets, effort or prompt in the middle of a run.
- Use your own key for anything but this work. Set a dollar cap and stop at it.
