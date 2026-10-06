# Stage 3 plan: does the LLM's interruption hurt, and through which mechanism? (October 5, 2026)

Stage 2 could not answer this (see the validity audit in `docs/stage2_results.md`): arms started from different
kitchens on 6 of 23 pairs, one episode had corrupted cameras, and most "false completions" were end-of-budget
declarations. Stage 3 first makes pairs trustworthy, then spends model money only on trustworthy pairs. It is a
**diagnostic development run** (`llm_development`, `diagnostic_replay`, baselines): no benchmark scores, no rates to
quote. The end goal is a list of task characteristics under which LLM supervision does worse than the plain VLA, in a
form that can be rebuilt as a simplified environment.

## Phase 0: validity gates (about 30 minutes, no API cost)

1. **Scene reproducibility** (`scripts/probe_scene_repro.py`). Result on the pod: the known-unstable pairs
   (WashLettuce, RinseSinkBasin and ScrubCuttingBoard at scene 1002; TurnOnSinkFaucet at 1000 and 1001) stayed
   unstable with `PYTHONHASHSEED` fixed, with BLAS pinned to one thread, and with Python's and NumPy's global
   generators seeded; three controls were identical in every attempt. The cause is open. So every model episode
   carries `--expect-state` (the plain run's step-0 state hash) and ends as an infrastructure error before any model
   call if its scene differs, and the second pass retries it. Pairs that never match simply do not become confirmed.
2. **Corrupted-frame guard** (`adapters/robocasa.py`). A camera frame whose adjacent-pixel difference exceeds 20 raises
   an error, so the episode ends as an `infrastructure_error`, is kept, and is rerun by `--skip-existing`. Threshold
   checked on 22,494 stored frames: clean frames top out at 12.4, the corrupted ones score 26.3.
3. **Streams.** Five policy workers share the GPU (5.5 GB each), one per stream. The container has a 13.6-core CPU
   quota and 62 GB RAM. `resources.log` and episode wall times from the first plain wave say whether to drop to fewer
   streams (more than about 1.5 times the single-stream time).

## Arms, in priority order (`scripts/run_stage3.sh`)

| Phase | What | Why |
|---|---|---|
| plain | 13 tasks with a plain success in stage 2 x new scenes 1003-1005 x policy seeds 0, 1, privileged stop | More independent (task, scene) clusters. Stage 2's plain episodes are reused for scenes 1000-1002 |
| defer_confirm | `always_defer` on each plain success (cap 6 per task) | Replay check on this GPU |
| **confirmed pairs** | plain success **and** defer success **and** identical step-0 simulator state; cap 4 per task, ordered by policy seed then scene | Only these get model episodes. Dropped pairs and reasons go to `confirmed_dropped.json` |
| defer_repeat | a second `always_defer` on each confirmed pair | The no-intervention noise floor. Failures here are replay noise, not LLM harm. Also shows how reproducible rollouts are from one start |
| opus, sonnet | one episode each (Opus 5.5, Sonnet 5.5, effort `medium`) | Whether harm is a task property (both models) or model-specific |
| reissue | restart every 100 steps | Cost of interruption with the wording unchanged |
| repeats | a second Opus episode where the first failed or changed the prompt | Separates the model's sampling from the pair |
| replays | with no model, replay Opus's logged decisions: `exact`, `native_text` (same timing and restarts, goal wording restored), `no_interruption` (goal once, same intervals, same final `complete`) | Attributes each failure to wording, restart or declaration |
| dose | restart every 50, 200, 400 steps on the pairs of tasks where an arm failed | Harm as a function of interruption interval |

`scripts/select_stage3.py` holds every selection rule. Outcomes are read only to find leave-alone pairs and aim the
follow-up arms.

## Analysis plan (fixed before the results)

**Unit and outcomes.** The unit is a (task, scene) cluster; pairs within it are correlated. Per episode, from the
logs alone: *success*; *never achieved* (the checker was never true; includes ending by budget or declaring with 15
or fewer steps left, which is giving up); *lost success* (true at some step, false at the end); *declared early*
(`complete` with more than 15 steps left while the checker was false); *invalid* (infrastructure error, excluded and
listed).

**Primary contrast.** Failure rate on confirmed pairs: Opus against the `always_defer` repeat (noise floor) and against
`reissue`, paired by pair, with a bootstrap over clusters. Report counts first. Opus counts as harmful on a task only
if its failures exceed the noise floor there.

**Exposure and conditional harm.** For each LLM episode record how many decisions it made before the plain run's
success step, whether it changed or restated the prompt, and the lead time (success step minus first intervention).
Report P(intervene) and P(fail | intervene) separately, by task.

**Mechanism** (replays, per Opus failure that `exact` reproduces): `native_text` succeeds, so *wording*; else
`no_interruption` succeeds, so *restart*; else the failure is the *declaration* if `complete` came before the defer
run's first success, otherwise *unattributed*. Failures `exact` does not reproduce are *not reproducible* and say how
noisy the rollouts are.

**Reasons.** Code each intervention's thinking summary (`model_api_traces.jsonl`) as: stall, ambiguity about progress,
budget pressure, or wording idea. Measure what the model saw: completion-recognition probe (offline, Opus on stored
frames, truth from the evaluator, API cost only).

**Task table.** One row per task: plain solve step and variability, budget slack, number of stages, instruction
length, success persistence, restart sensitivity (reissue minus defer), wording sensitivity (native-text replay
against exact), completion recognition, P(intervene), P(fail | intervene). Spearman rank correlations with Opus
failure, leave-one-task-out. With 13 tasks this ranks and attributes; it does not validate a model.

## What each outcome would mean

- **Opus failures at the noise floor everywhere:** no LLM-specific harm on these tasks. Report it. The simplified
  environment then has to create the harm conditions (ambiguous progress, strict completion criteria, costly
  restarts) instead of copying these tasks.
- **Restart dominates** (reissue and `no_interruption` contrast): dial = interruption cost. It also bears on how often
  to observe: the dose curve gives harm against interval.
- **Wording dominates:** dial = the VLA's brittleness to non-native instructions; a prompt-side mitigation to test.
- **Declaration dominates:** dial = completion observability and persistence; tasks with a latent or time-bounded
  success state.
- **Little reproduces:** rollout noise dominates; build the simplified environment with controlled noise.
- Whichever mechanisms appear become environment dials. The environment passes if it reproduces the real tasks' harm
  ordering and mechanism split, checked on about 6 held-out tasks whose harm is predicted before it is measured.

## Authorization, cost and stops

User approved stage 3. One pod (RunPod A6000 48 GB in the US, $0.55/hr; the $0.54 Massed Compute A6000 was no longer listed),
independent watchdog at 8 hours, run budget 300 minutes; at most $5 of GPU and $15 of Anthropic API (about $12 expected at list prices, $4 / $20 per million tokens
for Opus and $2 / $10 for Sonnet). No second pod without asking. No new job starts after `BUDGET_MINUTES`. Stop and
report if an episode is an infrastructure error twice in a row, a policy worker dies, or spend nears the caps. Never
expose keys, rewards, success flags or predicates to a model. Do not change the prompt, effort or budgets mid-run.

## Storage

Video every 5 steps, `video_frames/` PNGs not copied back, everything else kept (keyframes, evaluator traces, JSONL,
API traces with thinking summaries, MP4s). The Mac has about 8 GiB free; stage 2's results are 2 GB.
