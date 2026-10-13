# Roadmap to October 16, 2026

Rewritten October 12. The September plan (qualify CerealAndBowl with one fixed policy, then compare two orchestrators)
and the October 1 intervention-judgement plan are superseded by `docs/direction.md`. Owners and the day-by-day plan are
in `docs/work_split.md`.

| Dates (2026) | Work | Exit criteria |
|---|---|---|
| Sep 25 - Oct 2 (done) | Harness, GR00T worker, task pool, first GPU runs | `docs/stage1_remote_results.md` |
| Oct 4 - 11 (done) | Where supervision hurts (stages 2-3), abstract simulator, whether restarts rescue (stage 4) | `docs/stage2_results.md`, `docs/stage3_results.md`, `docs/sim_results.md`, `docs/stage4_results.md` |
| Oct 12 (done) | Direction fixed; plain policies measured on the unseen composite tasks (stage 5) | `docs/direction.md`, `docs/stage5_results.md` |
| Oct 13 | Time-charged scoring layer (offline, W1); policy ladder and ceiling test (W2); session mode with experience records (W3) | Each workstream's doc and tests (`docs/briefs/`) |
| Oct 14 | Task, policy and time parameters fixed; prompt probed; release commit tagged | A decision row in `docs/decisions.md` that freezes them |
| Oct 15 | Final runs: baselines, Opus 5.5, Sonnet 5.5; one GPU type and one commit | Every attempted episode kept; infrastructure errors reported separately |
| Oct 16 | Scoring, write-up, limitations, reproduction notes | Every aggregate traceable to episode records |

## Rules that still hold

- Do not substitute scripted actions when a learned policy fails, and do not add artificial disturbances. A deadline
  in the score is not a disturbance; a physical change to the world would be.
- Results from diagnostic supervisors (reference, sequencer, replay) are never mixed with model scores.
- Treat missing and infrastructure-error trials as pending, not as pass or fail, and keep them.
- A paired comparison runs on one machine, with the start-state check (`--expect-state`).
- The final scored runs share one GPU type and one commit (the contract hash covers both).

**Replaced rule:** "do not mix GR00T and π0.5 results". The benchmark now uses several policies on purpose, each
identified in every record.
