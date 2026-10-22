# Re-analysis of the final runs (W1, October 21-22, 2026)

Cleanup and re-analysis of the October 15-16 runs **with no new runs**. Everything here is analysis only:
- no hashed file, config, prompt or plan changed, so `release-2026-10-15` and every recorded episode stay valid;
- the pre-declared primary result (`docs/final_experiment.md`) is unchanged;
- the sensitivity variants below are **post-hoc** and are labeled that way wherever they are quoted.

## Tooling changes

- **`scripts/score_time.py --scenes 1000 1001 1002`** drops every episode and session entry from other scenes,
  including twins and baselines.
  - It applies Tom's October 16 decision to exclude scene 1003 for every model, without hand-made copies of the roots.
  - Check: `runs/addon/podC --scenes 1000 1001 1002` reproduces `results/w1/addon_kimi_score.txt` line for line.
- **Unfinished episodes no longer crash the scorer.** An episode a session started but never finished (no
  `result.json`) is counted as "never finished" and is not scored. This used to be a `FileNotFoundError` on the
  add-on's partial scene-1002 copy.
- **New tests:**
  - the per-episode computation behind the primary result (`score()`), checked against hand-computed held-out steps;
  - same-pod twin pairing;
  - the scene filter;
  - unfinished episodes;
  - the breakdown script.
- **`scripts/task_type_breakdown.py`** (descriptive), per model and task type:
  - the successes, and how many of them scored above 0;
  - the same-pod twins' successes, and the held-out fixed rule's value on those twins;
  - the declarations;
  - success with and without a rewritten instruction;
  - for each false "done", whether it came before the twin's first success (and by how much), or after it;
  - the steps the policy ran before the model's first check-in.

## Data in hand

- **Pod A, received from Ranveer on October 22.** 2,636 files covering 322 episodes: 85 always-defer, 84
  `reissue_50`, 84 `reissue` and 69 Opus. Before unpacking, the archive was checked: every path is under
  `runs/final/`, there are no links, and no credential patterns.
  - Scored alone on scenes 1000-1002, it reproduces W2's `runs/final/podA-score.json` exactly: 0.053 [0.007, 0.105]
    over 253 episodes, with identical fixed-rule and supervisor tables.
- **Kimi K3 add-on:** `runs/addon/podC`.
- **Pod B (Sonnet):** not yet received.

The sensitivity configs are in `results/w1/reanalysis/configs/`; outputs are in `results/w1/reanalysis/`, with copies in
`runs/time_score/reanalysis/`.

## Results so far: Opus 5.5 and Kimi K3

**Paired held-out regret [95%]**, with the model's and the fixed rule's mean values in parentheses:

| Setting | Opus 5.5 (63 episodes, scenes 1000-1002) | Kimi K3 (42 episodes, scenes 1000-1001) |
|---|---|---|
| Frozen | 0.053 [0.007, 0.105] (0.030 / 0.084) | 0.070 [0.014, 0.134] (0.003 / 0.073) |
| **Post-hoc:** no call charge | **0.017 [-0.017, 0.047]** (0.067 / 0.084) | **0.018 [-0.049, 0.084]** (0.056 / 0.073) |
| **Post-hoc:** every deadline doubled | 0.064 [0.019, 0.114] (0.078 / 0.142) | 0.099 [0.013, 0.187] (0.048 / 0.147) |

At Opus's 4.74 s charge, Kimi's frozen-deadline regret is 0.054 (a mean only).

**Leave-alone tasks** (OpenCabinet, PickPlaceCounterToStove, CloseFridge), frozen settings:

| | Opus 5.5 | Kimi K3 |
|---|---|---|
| Episodes | 27 | 18 |
| Successes (scored above 0) | 8 (8) | 5 (0) |
| Robot alone from the same start (twin) reached success | 21 of 27 | 14 of 18 |
| Model / fixed rule mean value | 0.071 / 0.195 | 0.000 / 0.171 |
| Failures | 19, all false "done" | 13: 6 false "done", 7 ran to the budget |
| False "done" before the twin's first success | 11 (median 4.55 s early) | 0 |
| False "done" after the twin had already succeeded | 2 | 3, plus 1 "reached, then lost" |
| False "done" where the twin never succeeded | 6 | 2 |
| Success when the instruction was kept / rewritten | 6 of 17 / 2 of 10 | 3 of 6 / 2 of 12 |
| First check-in, in steps (episodes) | 300 (19), 250 (3), 400 (3), 200 (2) | spread from 120 to 400 |

**Unseen tasks** (ArrangeTea, MakeIceLemonade, PanTransfer, WaffleReheat):

| | Opus 5.5 | Kimi K3 |
|---|---|---|
| Successes | 0 of 36 | 1 of 24 (value 0.133) |
| Twins that reached success | 1 of 36 | 1 of 24 |
| Declarations | 36 false "done" | 2 correct (one broke PanTransfer's 30 s limit), 9 false, 13 ran to the budget |
| First check-in | 400 steps, the maximum, in 33 of 36 | |

**What this shows** (descriptive: 3 scenes for Opus, 2 for Kimi):

1. **All of the signal is on the 3 leave-alone tasks.** On the unseen tasks the fixed rule and both models are about
   0, so 12 of the 21 cells per session add only noise around zero.
2. **The call charge decides "loses" against "ties", for both models.**
   - With no charge, both are statistically tied with the fixed rule.
   - At the frozen charge, every Kimi leave-alone success ran past its deadline. Example: CloseFridge on π0.5, 760
     steps (38 s) plus 5 × 5.92 s = 67.6 s, against 45 s.
   - The leave-alone deadlines (30, 45 and 52.5 s) are all below the 60 s that `docs/time_score.md` recommended.
3. **The charge is not the whole story.** Doubling the deadlines widens the gap for both models, because successes
   then count, and both fail leave-alone tasks the robot alone finishes: Opus 19 of 27, Kimi 13 of 18.
4. **The two models fail in different ways.**
   - **Opus acts like a fixed timer that does not adapt.**
     - Its first check came at 300 steps in 19 of 27 leave-alone episodes, whatever the policy.
     - In 14 of 27 it made only two calls: one run, then "done".
     - In 7 of the 9 leave-alone task blocks (a task run with each of the three policies in turn), the first check
       came at the same step for all three, even right after one had failed with it. For example, scene 1002
       OpenCabinet: one 400-step run for each policy; GR00T succeeded, π0.5 and GR00T-30% did not.
     - In 11 of its 19 failures, the robot alone finished later, a median of 4.55 s after Opus declared.
     - On the unseen tasks, its first check came at the maximum 400 steps in 33 of 36 episodes, and every episode
       ended in a false "done". That costs nothing, since the robot alone fails there too (1 of 36).
   - **Kimi breaks runs rather than declaring early.**
     - None of its false "done" came before the robot alone finished.
     - In 3 of them, the robot alone had already succeeded by that step, but Kimi's own run had not.
     - 7 runs went to the step budget, 6 of them after a rewrite.
5. **Rewriting the instruction goes with failure, for both models:**
   - Opus: 6 of 17 kept against 2 of 10 rewritten.
   - Kimi: 3 of 6 against 2 of 12.
   - Stage 3 showed the same: Opus failed 9 of 14 pairs where it rewrote.
   - This is a small, unpaired comparison: harder episodes may draw more rewrites.

## Blocked on pod B (W3)

- **Sonnet on scenes 1000-1002.** Its reported 0.071 still includes scene 1003, which was excluded for every model on
  October 16.
- **The Opus − Sonnet difference with its interval.** This is the pre-declared model comparison.
- **Sonnet's sensitivities and task-type breakdown.**
- **Section 5 of `docs/report.md`.** 5.4, the fixed rules including pod A's `reissue_50` and `reissue`, can be filled
  now; the rest needs pod B.

**Scoring both pods together can move Opus's 0.053 slightly.** The held-out declaration step is chosen on the twins
of the *other scenes in every root passed in*, so adding pod B's twins changes the steps available to Opus's episodes.
The analysis plan scores both roots together, so that is the number to report; the per-pod numbers stay as recorded in
`docs/final_results.md`.

### Exactly what to send

**Status:** pod A was received on October 22 and checked (above); pod B is pending.

Run these from the root of the OrcaBench checkout that holds the run folder. Each command packs the JSON, JSONL, log
and CSV files the analysis reads, and leaves out images, videos, full API request traces and per-step action logs.
On the add-on data this was about 1 MB per 130 episodes, and the unpacked copy scored identically.

**Ranveer (W2), pod A: Opus sessions, always-defer, `reissue_50`, `reissue`.** The source is `runs/final/podA/` and
`runs/final/podA-score.json` on Ranveer's Mac; the HF bucket `final-podA` has the same files.

```bash
find runs/final/podA runs/final/podA-score.json -type f \( -name '*.json' -o -name '*.jsonl' -o -name '*.log' -o -name '*.csv' \) ! -name model_api_traces.jsonl ! -name states.jsonl ! -name observations.jsonl ! -name 'action*.jsonl' ! -name 'policy_*.jsonl' ! -name step_timings.jsonl -print0 | tar --null -czf podA-analysis.tgz -T -
```

**W3, pod B: Sonnet sessions and always-defer.** The source is `runs/final/` on W3's machine.

```bash
find runs/final/podB runs/final/podB-score.json runs/final/w1-delivery-podB.json runs/final/compute-launch-20261015/partial-closeout/latency-samples.csv -type f \( -name '*.json' -o -name '*.jsonl' -o -name '*.log' -o -name '*.csv' \) ! -name model_api_traces.jsonl ! -name states.jsonl ! -name observations.jsonl ! -name 'action*.jsonl' ! -name 'policy_*.jsonl' ! -name step_timings.jsonl -print0 | tar --null -czf podB-analysis.tgz -T -
```

**Before sending,** check for credentials. This should print 0:

```bash
tar -xzOf podA-analysis.tgz | grep -c -E 'sk-ant-|hf_[A-Za-z0-9]{30}|PRIME_API_KEY='
```

The repository is public, so send the archives privately, not through Git. Tom unpacks them at the project root, which
recreates `runs/final/podA/` and `runs/final/podB/` (`runs/` is Git-ignored).

**What the analysis reads from each file:**

| Files | Where | Used for |
|---|---|---|
| `result.json`, `manifest.json` | every episode | outcome, steps, calls, task, policy, model, scene |
| `decisions.jsonl` | every episode | declaration time, rewrites, restarts |
| `evaluator/events.jsonl` | every episode | the per-step checker: the fixed rule, the held-out step, declaration timing |
| `decision_attempts.jsonl`, `model_replies.jsonl`, `model_timings.jsonl` | model episodes | rejected replies and live latency |
| `session.jsonl`, `session_result.json`, `manifest.json`, `errors.jsonl` | every session | order, anonymous labels, completion |
| `contract-*.json`, `plans/*.json`, `*.pairing.json`, `api_spend.jsonl`, `*.log` | every root | hashes, twin-pairing audit, cost, what stopped when |
| `podA-score.json`, `podB-score.json`, `w1-delivery-podB.json`, `latency-samples.csv` | `runs/final/` | to check the re-score against W2's and W3's own outputs, and latency |

### Commands once the data are here

The first two commands give the pre-declared primary result (Opus, Sonnet and their difference) under the frozen
`configs/time_pressure.json`; the loop gives the post-hoc variants. For a descriptive three-model table, add
`runs/addon/podC` to the roots and pass `--config configs/addon_time_pressure.json`: the same frozen tasks and charges
plus Kimi's.

```bash
python3 scripts/score_time.py runs/final/podA runs/final/podB --scenes 1000 1001 1002 --call-seconds 0 --output runs/time_score/reanalysis/main.json
python3 scripts/task_type_breakdown.py runs/final/podA runs/final/podB --scenes 1000 1001 1002 --output runs/time_score/reanalysis/main_task_types.json
for v in zero_charge deadline_x2; do python3 scripts/score_time.py runs/final/podA runs/final/podB --scenes 1000 1001 1002 --config results/w1/reanalysis/configs/$v.json --output runs/time_score/reanalysis/main_$v.json; done
```

Then check that each pod scored alone reproduces its recorded number: pod A 0.053 on scenes 1000-1002, and pod B 0.071
on all four scenes.
