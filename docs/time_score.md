# Time-charged score (W1, draft of October 13, 2026)

The score that makes "finish fast and reliably" measurable (`docs/direction.md`). Code:
`src/robot_benchmark/time_score.py` (analysis only, outside the contract hash); script: `scripts/score_time.py`;
settings: `configs/time_pressure.json`; tests: `tests/test_time_score.py`. The parameter **values** are a draft until
they are fixed in `docs/decisions.md` on October 14.

## Definition

**value = success × max(0, 1 − charged_seconds / deadline_seconds)**

- **charged_seconds:** robot seconds up to the end of the episode (steps / 20), plus `call_seconds` for every
  response from an LLM supervisor, rejected replies included.
  - **Why charge calls:** physics pauses while a model thinks, so without the charge a slow supervisor would cost
    nothing.
  - **Who is charged:** scripted baselines and diagnostics make no LLM calls and are not charged. The `model_calls`
    field of a scripted run counts its decisions, so it is ignored.
- **call_seconds = 5.0 for every model (draft).**
  - **Measured median latency per call:** Opus 5.5 4.7 s (stage 3, 161 calls) and 4.6 s (stage 2, 119); Sonnet 5.5
    2.2 s (stage 1, 77).
  - **Why one value:** a single charge makes the score compare supervision decisions, not API speed. Measured latency
    is reported separately.
  - **Why not live wall-clock time:** it varies with API load and would not reproduce.
- **deadline_seconds = the task's step budget in seconds** (registry horizon / 20), for every task. It needs no
  calibration on any policy's results (so no circularity), and the benchmark already declares it.
- **Failures score 0** however long they took, whether a false "done" or the budget running out. There is no
  incentive to declare early on a doomed episode: it gains nothing. The false-"done" rate is reported separately.
- **Stories (five unseen tasks):** `story.limit_seconds` is a hard limit on charged seconds from the trigger
  (`story.clock_starts`: `step0`, `ice_out_of_bowl` or `pan_off_stove`) to the declaration. Past it, the task fails.
  The limits are `null` (not applied) in the draft; they will be set from the time-to-success W2 measures. Runs that
  predate a trigger predicate are reported as "trigger not logged", and the limit is not applied to them.
- **Reported with the value:** success rate; on-time success (success and charged ≤ deadline); charged seconds;
  calls; rewrites and restarts; the declaration outcome (correct, false before success, false after success was
  lost, timeout) and the declaration lag (seconds after the checker first turned true).

## The best fixed rule (what a supervisor must beat)

- **Rule family:** "declare at step T" (a 20-step grid), crossed with a restart schedule: none, or reissue every N
  steps where such runs exist. It is scripted, so it pays no call charge.
- **Evaluated offline:** in a run without supervisor-dependent stopping, declaring at T succeeds exactly when the
  per-step checker log (`evaluator/events.jsonl`) is true at T. A privileged reference run stops at its first
  success; it is assumed to stay successful afterwards (stage 3 lost success in 1 of 36 no-intervention reruns).
- **Three values per (policy, task):**
  - **hindsight:** the best T on the same runs, which flatters the rule;
  - **held-out:** leave-one-out, with T chosen on the other runs;
  - **oracle:** declare at each run's first success. This is privileged, a ceiling and not a rule.
- **Estimated from unselected runs.** Stage 3 ran always-defer only on scenes the plain policy had solved, so the
  privileged reference runs (every scene) estimate the rule when they exist.
- **Regret** = rule value − supervisor value.
  - **Paired:** against the rule applied to the unsupervised runs of the same scene and seed, on the same machine.
  - **Paired held-out:** the same, with T chosen without that scene. This is the honest comparison.

## Offline validation on stages 3 and 5

`python3 scripts/score_time.py runs/stage3_remote --call-seconds 0 2.5 5 10` (output in `runs/time_score/`).

**Stage 3: multitask GR00T on 13 seen tasks.** 12 plain runs per task estimate the rule. Opus 5.5 ran on 34 valid
pairs where the plain policy had succeeded. Charge 5 s per call.

| Task | Best T (s) | Hindsight | Held-out | Oracle | Plain reached | Opus n | Opus success | Opus value | Paired held-out regret | Opus calls |
|---|---|---|---|---|---|---|---|---|---|---|
| CloseFridge | 23 | 0.16 | 0.06 | 0.31 | 0.67 | 4 | 0.75 | 0.14 | -0.04 | 3.75 |
| CloseToasterOvenDoor | 14 | 0.06 | 0.03 | 0.10 | 0.17 | 2 | 1.00 | 0.00 | 0.19 | 3.5 |
| CoffeeSetupMug | 14 | 0.09 | 0.04 | 0.10 | 0.17 | 2 | 0.50 | 0.04 | 0.23 | 3 |
| KettleBoiling | 43 | 0.07 | 0.04 | 0.08 | 0.17 | 2 | 0.00 | 0.00 | 0.21 | 9 |
| OpenCabinet | 23 | 0.52 | 0.47 | 0.70 | 1.00 | 4 | 0.50 | 0.13 | 0.43 | 4 |
| OpenDrawer | 11 | 0.41 | 0.41 | 0.48 | 0.67 | 4 | 0.75 | 0.16 | 0.37 | 3.25 |
| PickPlaceCounterToCabinet | 12 | 0.45 | 0.45 | 0.54 | 0.75 | 4 | 0.75 | 0.25 | 0.43 | 2.5 |
| PickPlaceCounterToStove | 12 | 0.40 | 0.40 | 0.48 | 0.75 | 4 | 0.75 | 0.11 | 0.49 | 3 |
| RinseSinkBasin | 46 | 0.08 | 0.05 | 0.10 | 0.25 | 2 | 0.50 | 0.00 | 0.32 | 8 |
| ScrubCuttingBoard | 31 | 0.12 | 0.08 | 0.16 | 0.42 | 1 | 0.00 | 0.00 | 0.48 | 11 |
| TurnOnMicrowave | 7 | 0.11 | 0.06 | 0.16 | 0.33 | 1 | 0.00 | 0.00 | 0.00 | 6 |
| TurnOnSinkFaucet | 19 | 0.12 | 0.06 | 0.19 | 0.50 | 2 | 0.50 | 0.04 | 0.14 | 4.5 |
| WashLettuce | 57 | 0.08 | 0.05 | 0.10 | 0.33 | 2 | 0.50 | 0.00 | 0.15 | 11 |

**Sensitivity to the call charge.** All 34 Opus episodes pooled; the 95% intervals are a bootstrap over episodes.

| Charge per call | Opus mean value | Paired regret (hindsight) | Paired regret (held-out) | Held-out: Opus worse / better / tie |
|---|---|---|---|---|
| 0 s | 0.32 | 0.13 | **0.06 [-0.03, 0.16]** | 14 / 13 / 7 |
| 2.5 s | 0.20 | 0.25 | 0.19 | |
| 5 s | 0.10 | 0.35 | **0.29 [0.21, 0.36]** | 24 / 1 / 9 |
| 10 s | 0.01 | 0.44 | 0.38 | |

**What this shows.**
1. **The right moment to declare differs a lot by task:** from 7 to 57 s for one policy. A non-adaptive rule must be
   tuned per task (and, with several policies, per policy). An adaptive supervisor has something real to gain.
2. **The call charge decides the verdict.**
   - **No charge:** Opus is statistically indistinguishable from the best fixed rule on the same scenes.
   - **5 s per call:** it is clearly worse (worse on 24 of 34 scenes, better on 1).

   This is what the benchmark is meant to expose: whether supervision is worth its time. It also means the charge is
   a central parameter that must be fixed and justified, not tuned after seeing results.
3. **Short tasks are dominated by the charge.** On CloseToasterOvenDoor (22.5 s budget), Opus succeeded 2 of 2 and
   scored 0. Any supervisor needs at least two responses (start and declare), which is 10 s at 5 s each. For the final
   task set, prefer budgets of about 60 s or more: every unseen composite and most seen composites. Otherwise, short
   tasks only test "supervise as little as possible".
4. **The hindsight rule flatters itself.** Held-out values are up to 60% lower (CloseFridge 0.16 → 0.06), so every
   claim against a fixed rule uses the held-out comparison.
5. **Unseen tasks (stage 5).** A fixed rule has value only where the multitask GR00T succeeded: ArrangeTea 0.09,
   GarnishPancake 0.21, MakeIceLemonade 0.10, SeparateFreezerRack 0.11. The pretraining-only GR00T has none. There are
   no supervisor runs yet.

## Not yet measured

- **Restart rules.** Stage 2's reissue arm has 1-2 runs per task on unreliable pairs. Stage 4's 50/100/200-step
  restarts on failure pairs are on Ranveer's machine and his Hugging Face bucket. The final baselines will run on
  every cell.
- **Differences between policies:** this needs W2's ladder (`groot_u10`, `groot_u30`).
- **Story limits:** these need W2's trigger predicates and times to success.
- **Sonnet as a supervisor in stages 3-5:** none; the final runs will have it.
- **The deadline choice.** "Deadline = budget" is a choice. A tighter deadline sharpens time pressure but makes more
  tasks zero for everyone.

## Decisions to fix on October 14

`call_seconds`; the deadline rule (budget, or a stated fraction of it); `story.limit_seconds` for the five story
tasks; the rule family for the final baselines (`always_defer`, `reissue` and which N); and whether the first response
of an episode is charged. It currently is, because the supervisor chooses the first instruction and interval.
