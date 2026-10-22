# OrcaBench final results (October 16, 2026): summary for the presentation

W1's collected numbers for the slides, with sources. Later re-analysis (no new runs) is in `docs/reanalysis.md`. The scorer is `time_score.py` at `18b90ad` (the story-limit fix, #10
and #11), applied to frozen runs of `release-2026-10-15`. Every number is from the runs below; nothing is estimated.

## The question and the score (one line each)

- **Question:** does an LLM supervising frozen robot policies (two GR00T checkpoints and π0.5, RoboCasa365) choose when
  to step in, how often to check and when to declare "done", so that tasks finish fast and reliably?
- **Score:** value = success × max(0, 1 − charged seconds / deadline); every LLM response is charged its model's
  calibrated seconds; failures score 0. **Primary result:** paired held-out regret = the always-defer twin's value under
  the best fixed "declare at step T" rule (T chosen without that scene), minus the supervisor's value, on the same pod,
  scene and seed. **Positive means the fixed rule did better.** 95% bootstrap interval, clustered by (task, scene).

## Main result

| Supervisor | Paired held-out regret | 95% interval | Episodes | Clusters | Scenes | Source |
|---|---|---|---|---|---|---|
| **Opus 5.5** | **0.053** | [0.007, 0.105] | 63 | 21 | 1000-1002 | W2, #8, 15:33Z |
| **Sonnet 5.5** | **0.071** | [0.028, 0.119] | 83 | 28 | 1000-1003 | W3, `670e075` |
| Kimi K3 (add-on, post-freeze) | 0.070 | [0.014, 0.134] | 42 | 14 | 1000-1001 | W1, `results/w1/` |

- **All three supervisors lose to the best fixed declaration rule**: every interval excludes 0.
- **Not yet on the same scenes:** Sonnet's number includes scene 1003; its scenes 1000-1002 number was requested (#8).
  No Opus − Sonnet difference with an interval exists yet (it needs both pods' data in one run). Do not rank the models:
  the intervals overlap.
- **Kimi K3 is an add-on**, run after the freeze on its own pod (A100 PCIe) with its own twins and only 2 complete
  scenes; compare it only through paired regret, and descriptively.

## Raw outcomes (descriptive)

| Run | Episodes | Success | Declared "done", checker false | Ran to step budget |
|---|---|---|---|---|
| Opus sessions (scenes 1000-1002) | 63 | 8 | 55 | 0 |
| always-defer twins, pod A (1000-1002) | 63 | 22 | n/a | 41 |
| `reissue_50`, pod A | 63 | 22 | n/a | 41 |
| `reissue` (100), pod A | 63 | 23 | n/a | 40 |
| Sonnet sessions (1000-1003) | 84 (83 usable) | 2 | 39 | 42 |
| always-defer twins, pod B (1000-1003) | 84 | 31 | n/a | n/a |
| Kimi K3 sessions (1000-1001) | 42 | 7 | 15 | 20 |
| always-defer twins, add-on pod (1000-1001) | 42 | 15 | n/a | n/a |

- **Opus by task type** (W2): leave-alone tasks 8/27 against always-defer's 21/27; unseen tasks 0/36 against 1/36.
  Opus declared "done" in every episode, mostly before the policy would have finished.
- **The recurring failure is declaring too early**, as in development stage 3 (Opus left alone failed only by
  declaring 12-48 steps early). On unseen tasks an early stop costs nothing, because they fail either way.
- **Restart baselines** (pod A) did no better than always-defer (22 and 23 against 22 of 63): mechanical restarts do
  not rescue these failures, matching stage 4 (about 1 rescue in 20).

## Kimi K3 add-on details

- **Per policy** (2 scenes, 14 episodes each): regret groot 0.206, groot_u30 0.093, π0.5 0.120.
- **Learning** (second-half minus first-half regret within a session; negative = improved): groot +0.068,
  groot_u30 −0.051, π0.5 −0.037. Descriptive only, with 7 episodes per half.
- **At Opus's 4.74 s charge** the same episodes give paired held-out regret 0.054: the gap to the fixed rule is about
  decisions, not Sail's serving speed.
- **Calls:** 353 over 42 episodes (8.4 per episode, against Opus's 4.7).
- **Per-episode table:** `results/w1/addon_kimi_episodes.csv` (value at its own 5.92 s charge and at 4.74 s);
  full score report `results/w1/addon_kimi_score.txt` and `.json`.

## Call charges (frozen before the sessions) and live latency

| Model | Charge (median of 27 pilot replays) | Live median in the final sessions |
|---|---|---|
| Opus 5.5 | 4.74 s | n/a (W2 reported no timeouts in 304 calls) |
| Sonnet 5.5 | 1.76 s | 1.98 s (750 calls, W3) |
| Kimi K3 (Sail) | 5.92 s | 5.62 s (353 calls) |

GLM-5.3-Flash was dropped from the add-on: Sail rejected 9 of its 27 calibration requests (at most 4 images per request).
Gemma 4 31B was dropped after the format check (about 31 s per call). Samples: `results/w1/addon_calibration_samples.csv`
and `addon_format_check_samples.csv`.

## Rules fixed before any final result (all in `docs/decisions.md`)

- Fallback (monitoring) mode: no unseen task was rescuable by step-by-step instructions (ceiling test), so the benchmark
  measures monitoring, declaring and restraint, not rescue.
- Story limits: PanTransfer 30 s, GarnishPancake 80 s; stories with no qualifying policy removed (MakeIceLemonade).
- Scorer fix: the fixed rules obey the story limit too (W3's finding, #10).
- Cut-short rule: only scenes whose session completed count; the model comparison uses the scenes both completed.
- Spend-guard stops are rerun once (never triggered for Opus or Sonnet).

## Deviations and limitations (state them on a slide)

- **Scene 1003 is excluded for every model.** PanTransfer's start state at scene 1003 builds randomly into one of two
  states; a session stops after two consecutive start-state mismatches. Opus's scene-1003 session stopped at 6 of 21,
  Kimi K3's at 5 of 21; Sonnet's happened to complete. No reruns (Tom, October 16). This was decided after Sonnet's
  0.071 was computed, so that number still includes scene 1003 until pod B is rescored (`docs/reanalysis.md`).
- **Small samples:** 3 scenes (63 paired episodes) per main model; per-task and per-policy numbers are descriptive.
- **Two final pods,** compared only through paired regret (start states are machine-specific).
- **`reissue_200` is unavailable,** not zero: pod B's restart phase never ran (wrapper stop, then no GPU capacity).
- **Add-on:** post-freeze; one open model; 2 scenes (scene 1002's completed session was lost when the add-on pod shut
  off before its data was copied back, a W1 error); its charge reflects Sail's serving.
- **Calibration:** the charges come from one Opus-generated pilot session, replayed once per observation; Sonnet was
  timed while shown the pilot's 4.7 s charge.

## Costs

| | GPU | API |
|---|---|---|
| Pod A (W2, Opus) | $8.38 | $5.71 |
| Pod B (W3, Sonnet) | about $23.55 | $6.81 |
| Add-on pod (W1, Kimi K3) | about $14.15 | about $1-2 of Sail usage (the guard booked more for timeouts) |

## Data locations

- **Pod A:** private Hugging Face bucket `hf://buckets/rsingh135/orcabench/final-podA`; a JSON/JSONL copy on W2's Mac.
- **Pod B:** `runs/final/podB/` on W3's machine, with the archive `runs/final/w3-podB-main-release-2026-10-15.tar.gz`.
- **Add-on:** `runs/addon/podC/` on Tom's Mac (JSON, JSONL, MP4); scored copy `runs/time_score/addon-final/`; the
  summaries above in `results/w1/`.
