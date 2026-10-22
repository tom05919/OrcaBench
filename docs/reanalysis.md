# Re-analysis of the final runs (W1, October 21, 2026)

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
- **`scripts/task_type_breakdown.py`** (descriptive): per model and task type, the successes, how many of them scored
  above 0, the same-pod twins' successes, the held-out fixed rule's value, the declarations, and success with and
  without a rewritten instruction.

## Kimi K3 add-on (the only session data on this Mac)

The episodes are 42 Kimi K3 episodes, scenes 1000-1001, from `runs/addon/podC` with `--scenes 1000 1001 1002`. The
configs are `results/w1/reanalysis/configs/`. Outputs are in `results/w1/reanalysis/`, with full copies in
`runs/time_score/reanalysis/`.

| Setting | Paired held-out regret [95%] | Kimi mean value | Fixed rule mean value |
|---|---|---|---|
| Frozen: 5.92 s per call, frozen deadlines | 0.070 [0.014, 0.134] | 0.003 | 0.073 |
| Opus's charge, 4.74 s (mean only) | 0.054 | | |
| **Post-hoc:** no call charge | **0.018 [-0.049, 0.084]** | 0.056 | 0.073 |
| **Post-hoc:** every deadline doubled | 0.099 [0.013, 0.187] | 0.048 | 0.147 |

**By task type, frozen settings** (`scripts/task_type_breakdown.py`):

| | Leave-alone (OpenCabinet, PickPlaceCounterToStove, CloseFridge) | Unseen (ArrangeTea, MakeIceLemonade, PanTransfer, WaffleReheat) |
|---|---|---|
| Kimi episodes | 18 | 24 |
| Kimi successes (scored above 0) | 5 (0) | 1 (1) |
| Same-pod twins (robot alone) that reached success | 14 of 18 | 1 of 24 |
| Fixed rule mean value (held-out) / Kimi mean value | 0.171 / 0.000 | 0.000 / 0.006 |
| Kimi success: kept the instruction / rewrote it | 3 of 6 / 2 of 12 | 0 of 2 / 1 of 22 |
| Declarations | 5 correct, 5 false (not reached), 1 false (reached, then lost), 7 ran to the budget | 2 correct (one broke PanTransfer's 30 s limit), 9 false, 13 ran to the budget |

**What this shows** (descriptive; one model and 2 scenes):

1. **All of the signal is on the 3 leave-alone tasks.** On the unseen tasks the fixed rule and the model are both
   about 0, so 12 of the 21 cells per session add only noise around zero.
2. **The call charge decides "loses" against "ties".**
   - With no charge, Kimi is statistically tied with the fixed rule.
   - At the frozen charge, every leave-alone success ran past its deadline. Example: CloseFridge on π0.5, 760 steps
     (38 s) plus 5 × 5.92 s = 67.6 s, against 45 s.
   - The leave-alone deadlines (30, 45 and 52.5 s) are all below the 60 s that `docs/time_score.md` recommended.
3. **Longer deadlines do not close the gap.** Doubling them widens it (0.099), because successes then count. Kimi
   failed 13 of 18 leave-alone episodes; the robot alone, from the same start states, solved 14 of 18:
   - 6 by declaring "done" too early, 4 of them after rewriting the instruction;
   - 7 by running to the budget without the task done, 6 of them after rewriting the instruction.
4. **Rewriting the instruction goes with failure:** 3 of 6 successes when kept, 2 of 12 when rewritten. Stage 3 showed
   the same pattern: Opus failed 9 of 14 pairs where it rewrote. This is a small, unpaired comparison: harder
   episodes may draw more rewrites.

## Blocked on data from W2 and W3

Pods A (Opus) and B (Sonnet) are not on this Mac. Until they arrive, these remain open:

- **Sonnet on scenes 1000-1002.** Its reported 0.071 still includes scene 1003, which was excluded for every model on
  October 16.
- **The Opus − Sonnet difference with its interval.** This is the pre-declared model comparison.
- **Opus and Sonnet:** the no-charge and deadline sensitivities, and the task-type breakdown.
- **Section 5 of `docs/report.md`.**

**Scoring both pods together can move Opus's 0.053 slightly.** The held-out declaration step is chosen on the twins
of the *other scenes in every root passed in*, so adding pod B's twins changes the steps available to Opus's episodes.
The analysis plan scores both roots together, so that is the number to report; the per-pod numbers stay as recorded in
`docs/final_results.md`.

### Exactly what to send

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
