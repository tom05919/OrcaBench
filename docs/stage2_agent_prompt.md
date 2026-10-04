# Stage 2 plan: where does LLM re-prompting hurt? (October 4, 2026)

This replaces the earlier stage 2 plan, which re-ran the eight stage 1 pairs to check the reply-format fix. That
plan could not say which task qualities make intervention harmful. This one is a **diagnostic development run**
(`llm_development`): it shows where and how the LLM does worse than the plain policy, to guide the design of a
simpler controlled environment. It produces no benchmark scores or rates.

## Question

On which tasks does an LLM orchestrator (Opus 5.5) fail where the plain GR00T N1.5 policy, left alone, succeeds,
and what does it do just before it fails?

## Design

Harm is paired on the **same task, scene seed and policy seed**. Rollouts are identical until the model first
intervenes (if replay is deterministic), so each harm event has a known divergence point.

1. **Plain policy.** All 16 pool tasks x scenes 1000, 1001, 1002 x policy seeds 0, 1 = 96 episodes (privileged stop
   on success).
2. **Selection, fixed before the results exist** (`scripts/select_stage2.py`). Per task, the first 2
   (scene, policy) pairs in ascending order where the plain policy succeeded. Tasks with no success contribute none.
3. **Arms on exactly those pairs, in priority order:**
   - `opus-5-5` (`configs/model-opus-5-5.dev.json`, effort `medium`, unchanged);
   - `always_defer`: submits the goal once, never intervenes, declares completion at the end of the budget. It is
     the noise floor: if it fails where the plain run succeeded, that is replay noise (or a success that does not
     persist), not LLM harm;
   - `reissue`: re-sends the goal every 100 steps. Separates the cost of interrupting from the cost of rewording.
     Cut first if time runs short.

**Harm** = plain policy succeeded on the pair and the arm did not. Rescue is not measured: no pair is selected
where the plain policy failed.

## Output

Per task: plain successes of trials, and for each arm the outcome on each selected pair, with
`scripts/compare_to_reference.py` (status, failure label, steps, calls, rejected replies, prompts, restarts, first
re-prompt step). Per harmful episode, read `decisions.jsonl`, `observations.jsonl` and the videos and record the
mechanism: rewrote before seeing progress, interrupted mid-motion, false completion, or budget exhausted. Set that
beside task qualities (horizon, budget slack, instruction length, number of stages, whether completion is visible).
Also report: whether `always_defer` reproduced the plain result, the interrupt-versus-rewrite split from `reissue`,
rejected replies per call (stage 1: 11 of 72), and output tokens per call.

## Limits and honesty

Roughly 20 selected pairs, one model, two policy seeds: direction only. Tasks the plain policy never solves give no
harm data. The set A / set B split in `configs/splits.json` is not used; a release would need it.

## Authorization and cost

User authorized renting the GPU for this run. Caps: one pod, at most 5 hours wall time (independent launchd
watchdog) and $10 of GPU spend; at most $15 of Anthropic API spend. No second pod without asking. Expected: about
4 hours, about $2.5 GPU (RTX A6000-class at about $0.54/hr), about $3 API at list prices ($4 / $20 per million
tokens, from stage 1 token counts). `scripts/run_stage2.sh` starts no new episode after 225 minutes.

## Storage

The Mac has little free disk. Episodes record video every 5 control steps (`VIDEO=5`; the cadence changes only
what is stored). Everything is kept except the `video_frames/` PNG sequences, which the MP4s in `videos/` replace;
`rsync --exclude video_frames/` copies the rest (keyframes, evaluator traces, all JSONL, API traces, MP4s) to
`runs/stage2_remote/`. The PNGs stay on the pod until it is terminated.

## Steps

1. Probe the API on the Mac (no GPU): `scripts/probe_model.py` for Opus 5.5. Exit 1 means do not rent.
2. Arm the watchdog, rent the pod, set up the worker per `docs/compute.md`, `doctor`, `check_task_pool.py`.
3. `nohup scripts/run_stage2.sh` on the pod; sync and check every 15-20 minutes.
4. Copy results back, terminate the pod, confirm it is gone with the Prime CLI, disarm the watchdog.
5. Write `docs/stage2_results.md`; commit it (raw runs are Git-ignored).

Stop and report if: an episode ends in `infrastructure_error` twice in a row, the policy worker dies, API errors
the retries did not absorb appear, or time or spend approach the caps. Never expose keys, rewards, success flags or
predicates to a model. Do not change the harness, prompt, effort or budgets mid-run.
