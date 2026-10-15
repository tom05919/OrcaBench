# W1 brief: scoring, analysis, final experiment and write-up (Tom)

**Read first:** `AGENTS.md`, `handoff.md` section S, `docs/direction.md`, and `docs/work_split.md` (ownership and
interfaces). The evidence is in `docs/stage3_results.md`, `docs/stage4_results.md` and `docs/stage5_results.md`.

## Goal

Define the score that makes "fast and reliable" measurable, show on existing data that it separates supervision
strategies, fix the final experiment, and write the report. CPU only; no GPU and almost no API.

## Steps

1. **Episode time score.** Write `src/robot_benchmark/time_score.py`, analysis only; keep it out of `CONTRACT_FILES`,
   like `scorecard.py`.
   - **Inputs:** an episode folder: `result.json` (`steps`, `success`, `model_calls`, `status`),
     `decisions.jsonl`, `evaluator/events.jsonl` (per-step `success` and predicates) and `model_timings.jsonl`.
   - **Outputs:** robot seconds (`steps / 20`); charged seconds = robot seconds + LLM responses × `call_seconds[model]`;
     success; whether the task finished within its deadline; for a time-sensitive task, seconds from the clock start
     to the declaration.
   - **Clock start:** step 0, or the first step at which the trigger predicate (`ice_out_of_bowl`, `pan_off_stove`,
     from W2) is true.
   - **Tests:** `tests/test_time_score.py`, on hand-made episode folders. No simulator is needed.
2. **Time parameters.** Write `configs/time_pressure.json` in the format fixed in `docs/work_split.md`. Draft values
   by October 13:
   - `call_seconds`: **per model** (decided October 13): each model's median seconds per call, measured once under
     prompt version 6 (W3's probe and pilot) and frozen on October 14. Provisional: Opus 4.7 s, Sonnet 2.2 s.
   - `deadline_seconds` per task: **the step budget in seconds** (decided October 13). The first response is
     charged (decided). Story `limit_seconds` comes from W2's times to success; propose the rule when they exist.
   - `story`: one sentence per time-sensitive task, from `docs/task_catalog.md`.
3. **The best fixed rule, offline.** The time score penalizes always-defer heavily, because it declares only at the
   step budget. A fair fixed rule must also be able to stop.
   - **Rule family:** restart every N ∈ {never, 50, 100, 200} steps, crossed with declaring at step T. Choose T from a
     small grid, or as a quantile of the policy's time to success on that task.
   - **Offline evaluation:** for runs with no restart (plain and always-defer), "declare at T" succeeds exactly when
     `evaluator/events.jsonl` shows the checker true at step T. Calls = ⌈T / interval⌉. For `reissue_*` runs, use
     their own event logs.
   - **Output:** the best fixed rule and its expected score per (policy, task), from existing stage 3-5 runs and W2's
     ladder runs. If the best rule is the same for every policy and task, adaptation is not measurable; report that
     immediately.
4. **Supervisor measures.** For an LLM episode or session (W3's `session.jsonl`):
   - **Regret:** the best fixed rule's expected score for that (policy, task) minus the episode's score, averaged per
     (policy, task).
   - **Declaring:** declaration step minus the first step the checker was true. Early means a failure; late means
     wasted time.
   - **Cadence:** the intervals chosen, against the best fixed interval for that (policy, task), and whether intervals
     shrink near completion or after a stall.
   - **Interrupting:** restarts and prompt changes per episode, and outcome against the paired always-defer run
     (harm or rescue).
5. **Offline validation.** Write `docs/time_score.md`: the score and every measure applied to stages 3-5 (plain,
   always-defer, reissue, Opus). Show whether the score ranks Opus against the fixed rules differently from the
   success rate alone.
6. **Final experiment, October 14.** Write `docs/final_experiment.md` with W2 and W3 and add a `docs/decisions.md`
   row:
   - **Policies:** three, from W2. **Tasks:** about four unseen tasks where the ceiling test showed fixable failures,
     plus about three trained leave-alone tasks.
   - **Grid:** four scenes, policy seed 0.
   - **Systems per cell:** always-defer, `reissue` and (if affordable) `reissue_50` and `reissue_200`, plus the Opus
     and Sonnet sessions.
   - **Sessions:** order, length and interleaving (episodes per session, how many sessions per model).
   - **Fixed for all runs:** the GPU type, and the release commit tag.
7. **Report, October 16.** Write `docs/report.md`: the question, related work (`docs/benchmark_direction_research.md`),
   the environment, the policies, the scoring, the results, the limitations and how to reproduce. Update
   `handoff.md`, `README.md` and the scoring section of `docs/protocol.md`.

## Interfaces

- **You provide:** `configs/time_pressure.json` (format fixed now, values on October 14); `docs/final_experiment.md`.
- **You consume:** trigger predicate names (W2); the ability table and policy set (W2); session records (W3).

## Definition of done

- `time_score.py` and `scripts/score_time.py` score any episode folder or session, with tests.
- `docs/time_score.md` shows the offline validation.
- Time values and the final experiment are logged on October 14.
- `docs/report.md` exists on October 16, with every number traceable to `runs/`.

## Do not

- Edit W2 or W3 files.
- Mix diagnostic (reference, sequencer, replay) results with model scores.
- Normalize by a near-zero success rate, or combine success and time with weights you did not declare in advance.
