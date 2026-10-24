# Ty → Tom's agent: W3 results and raw-data handoff

Prepared October 23, 2026 from this laptop's retained artifacts and GitHub evidence.
This answers Tom's request for Ty's run results. Ty was working on **W3 (harness,
session mode and LLM runs)**. The final robot-policy experiments ran on remote GPU
pod B; their copied artifacts are on this laptop. This handoff does not start new
runs or change the evaluation contract.

## Read this first

**Tom's newest request is in [issue #8, October 22](https://github.com/tom05919/OrcaBench/issues/8#issuecomment-6330819109):**
privately supply a small `podB-analysis.tgz` so W1 can rescore Sonnet on scenes
1000–1002, compute the predeclared Opus−Sonnet difference and interval, and run
the same sensitivity analysis as Kimi. Preserve the original four-scene result.
Follow W1's [current reanalysis instructions](https://github.com/tom05919/OrcaBench/blob/w1-scoring/docs/reanalysis.md),
which include common-scene filtering, sensitivity analysis and task-type breakdown.
The locally cached W1 branch was stale when this handoff was prepared; use the
current W1 scorer rather than assuming this W3 checkout supports its newer flags.
Ranveer's [pod A delivery comment](https://github.com/tom05919/OrcaBench/issues/8#issuecomment-6343436832)
records the other cohort's private delivery; it was not independently analyzed
for this handoff. **The common-scene analysis remains W1's next action.**

I created the requested small bundle locally at **`runs/final/podB-analysis.tgz`**
using the issue's inclusion/exclusion rules: 1,491 files, **1,482,762 bytes**.
Every archived member was read back and matched against its source SHA256.
Integrity receipt: `runs/final/podB-analysis.integrity.json`. Bundle SHA256:

```text
2de987df594acc643503fa87115618f445073e33436f8e4459503e955f786457
```

This small bundle is **local only**, Git-ignored, and has not been uploaded or
sent. Tom's agent on this laptop can read it immediately. On another computer,
use the existing restricted release described below to obtain the original
cohort, or arrange private transfer of this small bundle. Do not assume that
pulling this Markdown also transfers the bundle.

**The final W3 Sonnet cohort exists: 84 always-defer episodes plus 84 Sonnet
attempts, of which 83 are usable and one is an infrastructure exclusion.** All
four Sonnet sessions finished their 21 attempts. The saved primary result is
**paired held-out regret 0.071, 95% clustered interval [0.028, 0.119]**, across
83 episodes and 28 task/scene clusters. Positive regret favors the fixed
no-restart declaration rule over Sonnet.

The raw archive is available locally and was uploaded to a restricted GitHub
draft release; download instructions are below. `docs/w3_handoff.md` is an older
October 14 snapshot saying no real runs had happened. That statement is
superseded by the completed-run evidence at the top of
[docs/stage6_pilot.md](docs/stage6_pilot.md).

## Final experiment and outcomes

Runtime/tag: `release-2026-10-15`, commit
`cf724d97f84d1845227890369eff5a79bde59060`. Final hardware was A100 80 GB SXM4.
The three fixed learned policies were `groot`, `groot_u30` and `pi05`.
Scenes were 1000–1003; each Sonnet session interleaved all three policies over
seven tasks: ArrangeTea, CloseFridge, MakeIceLemonade, OpenCabinet, PanTransfer,
PickPlaceCounterToStove and WaffleReheat.

| Phase | Attempts | Raw terminal successes | Other terminal statuses | Infrastructure exclusions |
|---|---:|---:|---|---:|
| always_defer | 84 | 31 | 53 false completions | 0 |
| Sonnet (`claude-sonnet-5-5`) | 84 | 2 | 42 step-budget exhaustions; 39 false completions | 1 |
| reissue_200 | 0 | unavailable | Not executed | unavailable |

These are **raw terminal outcomes**, not deadline/story-adjusted values. Do not
substitute this success-count comparison for the primary time-charged score.
The primary comparator is a fixed declaration rule estimated on other scenes
from baseline trajectories, with held-out pairing, rather than simply the raw
always-defer terminal success count.

| Policy | always_defer raw successes / attempts | Sonnet raw successes / usable episodes |
|---|---:|---:|
| `groot` | 11 / 28 | 2 / 27 |
| `groot_u30` | 11 / 28 | 0 / 28 |
| `pi05` | 9 / 28 | 0 / 28 |

Both Sonnet successes were PickPlaceCounterToStove with `groot`, scenes 1001 and
1002. All attempts remain retained. Independent checks for this handoff matched
start-state hashes, policy identities and contracts for all 84 pairs, and all
3,593 files in the saved artifact index matched their bytes and SHA256.

**Exclusion:**
`runs/final/podB/sessions/sonnet-scene1003/episodes/0000` is OpenCabinet /
`groot`, with 950 executed steps and nine successful model responses. The
camera guard raised `corrupt camera frame: video.robot0_eye_in_hand noise 27.0
at step 951`. That attempt is excluded from primary scoring, but retained in
the archive, latency samples and costs. The session continued through index 20
and its saved status is `completed`. W3 interprets W1's complete-session rule
as completion of all planned attempts, including a retained isolated
infrastructure failure; Tom should preserve this explicit interpretation.

The operational wrapper stopped after the sessions because its post-session
check required zero infrastructure errors. This prevented `reissue_200`.
Documented replacement-pod requests later returned HTTP 503 Insufficient
Capacity. **There is no restart-baseline result; missing performance is null,
not zero.** No new capacity check or rental was made for this handoff.

## Files Tom's agent should consume

Paths below are relative to the repo root. `runs/` is Git-ignored: pulling source
alone does not bring these files onto another computer.

| Artifact | Purpose |
|---|---|
| `runs/final/podB/` | 168 attempt folders, evaluator records, manifests, session ledgers/plans, pairing audits, model traces and MP4 videos |
| `runs/final/podB-score.json` | W1 scorer output; primary result under `primary.per_model.claude-sonnet-5-5` |
| `runs/final/w1-delivery-podB.json` | Counts, exclusion, raw latency samples, usage, cost, runtime/scorer identities and completion interpretation |
| `runs/final/compute-launch-20261015/partial-closeout/latency-samples.csv` | Per-call observed latency |
| `runs/final/compute-launch-20261015/partial-closeout/` | Archive index/validation, scorer log and closeout receipts |
| `runs/final/w3-podB-main-release-2026-10-15.tar.gz` | Compact raw cohort archive for transfer |
| `runs/final/reissue-launch-20261016/` | Capacity-failure receipts and prepared secondary-run recipes |

Per-step final PNG frames were not copied from the remote pod. JSON/JSONL,
logs and MP4s were copied. Preserve evaluator records for offline analysis;
never feed their privileged contents to a model adapter.

Archive size: **1,261,516,518 bytes**. SHA256, independently recomputed for this
handoff:

```text
eb5254c73c4ebd556586e6375d7b711622df1394ba8a9ccea52f760ceb74f65c
```

## Download on Tom's computer

Use Tom's authenticated GitHub account with access to repository draft releases:

```sh
gh release download release-2026-10-15 --repo tom05919/OrcaBench --dir runs/final/w3-incoming -p podB-score.json -p w1-delivery-podB.json -p latency-samples.csv
```

For the full raw archive, download separately:

```sh
gh release download release-2026-10-15 --repo tom05919/OrcaBench --dir runs/final/w3-incoming -p w3-podB-main-release-2026-10-15.tar.gz -p SHA256SUMS
```

The documented restricted draft URL is
https://github.com/tom05919/OrcaBench/releases/tag/untagged-4cce0a405e007a44a2eb.
Authenticated GitHub inspection on October 23 confirmed that it remains a draft
and contains `podB-score.json`, `w1-delivery-podB.json`, `latency-samples.csv`,
`SHA256SUMS` and the full raw archive with the size/digest above. It does not
contain the newly prepared small bundle.
Keep the release restricted; do not publish the raw assets to fix an access error.
Verify the downloaded archive before extracting into a fresh directory:

```sh
shasum -a 256 runs/final/w3-incoming/w3-podB-main-release-2026-10-15.tar.gz
tar -tzf runs/final/w3-incoming/w3-podB-main-release-2026-10-15.tar.gz | head -40
```

Use the archive member listing to choose an extraction destination without
overwriting existing attempts. Read the separate scorer and delivery JSON assets
first; extracting the full video archive is unnecessary for the headline result.

## Scoring identity and reproduction

Use **corrected W1 analysis commit
`18b90adbe63c7820ebe65c913e2758eeeaa6179e`**, not the tagged scorer: W1 corrected
story-limit handling for fixed-rule, held-out and oracle values. This is an
analysis correction; the harness, frozen inputs and episodes stayed at `cf724d9`.
Its local analysis checkout is `runs/final/analysis-18b90ad/`.

Frozen charges remain **Sonnet 1.76 seconds/call; Opus 4.74 seconds/call**.
Observed final Sonnet latency must not replace the frozen charge.
The saved `podB-score.json` contains no Opus–Sonnet difference (`differences: {}`).
Pod B alone cannot establish a cross-model comparison. W1 must combine W2/pod A
artifacts using the completed-scene intersection required by the final protocol.

## Pilot, calibration and accounting (separate from final scores)

- Actual development Opus pilot: eight attempts, three successes, five false
  completions, zero infrastructure exclusions; 27 strict model responses.
  Artifacts: `runs/stage6_pilot/opus-pilot/`,
  `runs/stage6_pilot/w1-delivery.json`, `runs/stage6_pilot/scoring/`.
- Freeze calibration: replayed all 27 pilot observations once per model, 54
  strict valid replies, zero retries/exclusions. Pooled medians were Opus 4.74 s
  and Sonnet 1.76 s, superseding the earlier six-sample calibration. Artifacts:
  `runs/stage6_pilot/calibration-all-20261014T212408Z/` (`summary.json`,
  `samples.csv`, inputs and verification). These are replay calls, not new robot
  episodes or final Opus sessions.
- Final Sonnet: 750 successful strict-JSON responses, zero transport retries;
  749 completed decision records because the camera failure interrupted one
  accepted action. All 750 calls remain in cost/latency accounting. Observed
  overall median 1.977428486 s; first-call median 1.776215625 s (n=84), later
  median 2.008183008 s (n=666).
- Saved accounting: final API $6.8086692; project API including development and
  calibration $8.0235237. Original final-pod observed billing $23.548; project
  observed compute including the pilot $24.487. These are saved closeout billing
  snapshots, not a newly checked invoice. The closeout receipt verified exact
  pod `75b7d452b61f433b86bd3f1e636dc915` absent; this handoff makes no claim about
  the current provider account.

## Next actions for Tom's agent

1. Read the latest linked issue #8 request, then obtain the small analysis bundle
   locally or the existing release assets. Verify checksums if copying the
   cohort. Use the October 16 actual-results section of `docs/stage6_pilot.md`
   over the stale October 14 `docs/w3_handoff.md` snapshot.
2. Preserve the one infrastructure exclusion and all attempted episodes. Report
   the missing restart comparison explicitly.
3. Rescore Sonnet on scenes 1000–1002 for the requested common-scene comparison;
   retain the four-scene result separately. Use the corrected scorer identity,
   frozen charges and completed-scene rule when integrating with W2's Opus
   cohort. Tom owns the combined report and
   final cross-model effect size; neither is inferred here from pod B alone.
4. Suggested skills: `superpowers:verification-before-completion` for numerical
   claims; `handoff` if transferring this context again. No new experiment is
   required to retrieve the existing W3 result.
