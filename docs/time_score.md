# Time-charged score (W1, October 13, 2026)

The score that makes "finish fast and reliably" measurable (`docs/direction.md`). Code:
`src/robot_benchmark/time_score.py` (analysis only, outside the contract hash); script: `scripts/score_time.py`;
settings: `configs/time_pressure.json`; tests: `tests/test_time_score.py`. Tom decided the score's form on October 13
(`docs/decisions.md`). The calibrated latencies and the story limits are fixed on October 14.

## Definition

**value = success × max(0, 1 − charged_seconds / deadline_seconds)**

- **Fast but wrong scores 0.** Any failure is worth 0 however fast it was: a false "done", or the step budget running
  out. Declaring early to save time is a false completion, so it also scores 0. Checking in rarely to save time is a
  real risk: the supervisor notices completion later or misses a stall. Speed only counts when the task is done.
- **charged_seconds:** robot seconds up to the end of the episode (steps / 20), plus `call_seconds[model]` for every
  response from an LLM supervisor, rejected replies included. Scripted baselines and diagnostics make no LLM calls and
  are not charged.
- **call_seconds is per model** (decided October 13). A faster model really does finish sooner, so the score reflects
  the whole system.
  - **Calibration:** each model's charge is its median wall-clock seconds per call, measured **once** under the run's
    exact settings (final prompt, effort `medium`), then frozen. Live latency is not used: it varies with API load,
    and it would let a model look faster by thinking less during a run.
  - **Provisional values:** Opus 5.5 4.7 s (stage 3, 161 calls) and Sonnet 5.5 2.2 s (stage 1, 77 calls, older
    prompt). They are re-measured from W3's probe and pilot with prompt version 6 and frozen on October 14.
  - **Unlisted model:** scoring a model with no calibrated value is an error.
- **deadline_seconds = the task's step budget in seconds** (registry horizon / 20), for every task (decided). It needs
  no calibration on any policy's results.
- **The first response is charged** (decided). It is a real decision: the first instruction and when to check in.
- **Stories (five unseen tasks).** `story.limit_seconds` is a hard limit on charged seconds from the trigger
  (`story.clock_starts`: `step0`, `ice_out_of_bowl` or `pan_off_stove`) to the declaration. Past it, the task fails.
  - The limits are `null` until W2's times to success exist; the rule for setting them comes then.
  - Runs that predate a trigger predicate are reported as "trigger not logged", and the limit is not applied.
- **Reported with the value:** success rate; on-time success; charged seconds; calls; rewrites and restarts; the
  declaration outcome (correct, false before success, false after success was lost, timeout); and the declaration
  lag (seconds after the checker first turned true).

## The best fixed rule (what a supervisor must beat)

- **Rule family:** "declare at step T" (a 20-step grid), crossed with a restart schedule. It is scripted, so it pays no
  call charge.
- **Restart schedules in the final runs** (decided October 13):
  - **always-defer (no restart) on both pods,** so every LLM episode has a paired no-intervention twin on the same
    machine.
  - **`reissue_50`, `reissue` (100) and `reissue_200` on one pod** (unpaired). A restart baseline re-sends the
    original instruction every N steps without looking at anything. It is the control for the "when to interrupt"
    half of the skill: the LLM gets credit only for interruptions that are better timed than mechanical ones.
- **Evaluated offline:** in a run without supervisor-dependent stopping, declaring at T succeeds exactly when the
  per-step checker log (`evaluator/events.jsonl`) is true at T. A privileged reference run stops at its first
  success; it is assumed to stay successful afterwards (stage 3 lost success in 1 of 36 no-intervention reruns).
- **Three values per (policy, task, schedule):**
  - **hindsight:** the best T on the same runs, which flatters the rule;
  - **held-out:** leave-one-out, with T chosen on the other runs;
  - **oracle:** declare at each run's first success. This is privileged, a ceiling and not a rule.
- **Estimated from unselected runs.** Stage 3 ran always-defer only on scenes the plain policy had solved, so the
  privileged reference runs (every scene) estimate the no-restart rule when they exist.
- **Regret** = rule value − supervisor value.
  - **Regret:** against the best schedule (unpaired, since the restart schedules run on one pod).
  - **Paired:** against the no-restart rule on the same scene and seed, on the same machine.
  - **Paired held-out:** the same, with T chosen without that scene. This is the honest comparison.

## Offline validation on stages 3 and 5

`python3 scripts/score_time.py runs/stage3_remote --call-seconds 0 2.2 4.7 10` (output in `runs/time_score/`; use
Python 3.11-3.12).

**Stage 3: multitask GR00T on 13 seen tasks.** 12 plain runs per task estimate the rule. Opus 5.5 ran on 34 valid
pairs where the plain policy had succeeded. Opus charged 4.7 s per call.

| Task | Best T (s) | Hindsight | Held-out | Oracle | Plain reached | Opus n | Opus success | Opus value | Paired held-out regret | Opus calls |
|---|---|---|---|---|---|---|---|---|---|---|
| CloseFridge | 23 | 0.16 | 0.06 | 0.31 | 0.67 | 4 | 0.75 | 0.15 | -0.05 | 3.75 |
| CloseToasterOvenDoor | 14 | 0.06 | 0.03 | 0.10 | 0.17 | 2 | 1.00 | 0.00 | 0.19 | 3.5 |
| CoffeeSetupMug | 14 | 0.09 | 0.04 | 0.10 | 0.17 | 2 | 0.50 | 0.06 | 0.21 | 3 |
| KettleBoiling | 43 | 0.07 | 0.04 | 0.08 | 0.17 | 2 | 0.00 | 0.00 | 0.21 | 9 |
| OpenCabinet | 23 | 0.52 | 0.47 | 0.70 | 1.00 | 4 | 0.50 | 0.14 | 0.42 | 4 |
| OpenDrawer | 11 | 0.41 | 0.41 | 0.48 | 0.67 | 4 | 0.75 | 0.18 | 0.35 | 3.25 |
| PickPlaceCounterToCabinet | 12 | 0.45 | 0.45 | 0.54 | 0.75 | 4 | 0.75 | 0.27 | 0.41 | 2.5 |
| PickPlaceCounterToStove | 12 | 0.40 | 0.40 | 0.48 | 0.75 | 4 | 0.75 | 0.14 | 0.47 | 3 |
| RinseSinkBasin | 46 | 0.08 | 0.05 | 0.10 | 0.25 | 2 | 0.50 | 0.00 | 0.32 | 8 |
| ScrubCuttingBoard | 31 | 0.12 | 0.08 | 0.16 | 0.42 | 1 | 0.00 | 0.00 | 0.48 | 11 |
| TurnOnMicrowave | 7 | 0.11 | 0.06 | 0.16 | 0.33 | 1 | 0.00 | 0.00 | 0.00 | 6 |
| TurnOnSinkFaucet | 19 | 0.12 | 0.06 | 0.19 | 0.50 | 2 | 0.50 | 0.06 | 0.13 | 4.5 |
| WashLettuce | 57 | 0.08 | 0.05 | 0.10 | 0.33 | 2 | 0.50 | 0.00 | 0.15 | 11 |

**Sensitivity to the call charge.** All 34 Opus episodes pooled; the 95% intervals are a bootstrap over episodes.

| Charge per call | Opus mean value | Paired regret (hindsight) | Paired regret (held-out) | Held-out: Opus worse / better / tie |
|---|---|---|---|---|
| 0 s | 0.32 | 0.13 | **0.06 [-0.03, 0.16]** | 14 / 13 / 7 |
| 2.2 s (Sonnet's provisional) | 0.21 | 0.24 | 0.17 [0.10, 0.25] | 23 / 3 / 8 |
| 4.7 s (Opus's provisional) | 0.11 | 0.34 | **0.27 [0.20, 0.35]** | 24 / 1 / 9 |
| 10 s | 0.01 | 0.44 | 0.38 | |

**What this shows.**
1. **The right moment to declare differs a lot by task:** from 7 to 57 s for one policy. A non-adaptive rule must be
   tuned per task (and, with several policies, per policy). An adaptive supervisor has something real to gain.
2. **The call charge decides the verdict.**
   - **No charge:** Opus is statistically indistinguishable from the best fixed rule on the same scenes.
   - **At its own latency:** it is clearly worse (worse on 24 of 34 scenes, better on 1).

   This is what the benchmark is meant to expose: whether supervision is worth its time. With per-model charges, a
   faster model gains, but only on episodes it gets right.
3. **Short tasks are dominated by the charge.** On CloseToasterOvenDoor (22.5 s budget), Opus succeeded 2 of 2 and
   scored 0. Any supervisor needs at least two responses (start and declare), about 9 s for Opus. For the final task
   set, prefer budgets of about 60 s or more: every unseen composite and most seen composites.
4. **The hindsight rule flatters itself.** Held-out values are up to 60% lower (CloseFridge 0.16 → 0.06), so every
   claim against a fixed rule uses the held-out comparison.
5. **Unseen tasks (stage 5).** A fixed rule has value only where the multitask GR00T succeeded: ArrangeTea 0.09,
   GarnishPancake 0.21, MakeIceLemonade 0.10, SeparateFreezerRack 0.11. The pretraining-only GR00T has none. There are
   no supervisor runs yet.

## Not yet measured

- **Restart rules.** Stage 2's reissue arm has 1-2 runs per task on unreliable pairs. Stage 4's 50/100/200-step
  restarts on failure pairs are on Ranveer's machine and his Hugging Face bucket. The final baselines will cover
  them.
- **Differences between policies:** this needs W2's ladder (`groot_u10`, `groot_u30`).
- **Story limits:** these need W2's trigger predicates and times to success.
- **Calibrated latencies with prompt version 6:** these need W3's probe and pilot.
- **Sonnet as a supervisor in stages 3-5:** none; the final runs will have it.
