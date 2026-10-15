# W3 pilot status — October 14, 2026

**The real eight-episode development pilot, W1 scoring and representative v6
replay calibration are complete.** The full-pilot replay below supersedes the
initial six-sample medians. Tom's `release-2026-10-15` now exists at `cf724d9`,
including W2's qualified π0.5 setup. Final pod B's always-defer cohort began
October 15 at 19:58 UTC on A100 80 GB SXM4. No final model API call has started
at this update. Earlier readiness and mock evidence below is historical,
separate from actual results.

## Final release readiness — October 15

The clean tagged checkout passed **387 tests in 7.418 s** and all eight actual
CLI source-plan dry runs (four plans for each model). Frozen timing is marked
`frozen`, PanTransfer's story limit is **30 s**, and MakeIceLemonade has no story.
The source-plan checks use no API calls, workers or robot episodes; final paired
checks follow the actual same-pod always-defer cohort. Receipts:
`runs/final/readiness-20261015/offline/` and
`runs/final/release-2026-10-15-suite-ready.log`. The first test attempt lacked
the ignored pinned reference registry in the new checkout; that setup failure
is retained separately and does not alter tagged source.

Pod `75b7d452b61f433b86bd3f1e636dc915`,
`robot-cereal-w3-final-20261015-1919`, is provisioned with a $30 compute allocation
and pre-armed exact-ID watchdog. Advertised resources: A100 80 GB SXM4, 32 vCPUs,
250 GB RAM, 300 GB disk. Fresh wallet/model GET checks passed; no W3 pod existed
before creation. One POST received an HTTP 307 before creation; pod absence was
verified before the successful canonical-endpoint request. Both attempts remain
in `runs/final/compute-launch-20261015/`. API allocation is $50, unchanged.

Actual hardware verified: NVIDIA A100-SXM4-80GB (81,920 MiB), with 27.2 CPU cores
available by cgroup quota. All three workers passed health/manifest identity and
CLI doctor checks. All 28 selected task/scene builds passed before execution.
These readiness checks used no model calls or learned-policy episodes.

The first two actual always-defer episodes, GR00T/ArrangeTea at scenes 1000 and
1001, finished with retained `false_completion` results and no infrastructure
errors. These are partial results, not a final score. The sequence remains
84 always-defer episodes → same-pod pairing/final dry runs → four sequential
Sonnet sessions (84 episodes) → 84 `reissue_200` episodes. The operational driver
stops on the first infrastructure error for investigation, retains every
attempt, and waits for successful artifact-copy acknowledgement after each
phase. JSON/JSONL/MP4/logs are also copied every two minutes. Live artifacts:
`runs/final/podB/`; execution/copy receipts:
`runs/final/compute-launch-20261015/`. Final counts, scoring, costs and exact-pod
termination verification remain pending.

## W1 full-pilot calibration — October 14, rule fixed before replay

W1 `4278ec7deb6a4d04ca604a29224497a351752a0a`, `docs/decisions.md`, fixes each
model's charge as the median of one replay per recorded pilot observation.
**All 27 observations of all eight episodes were replayed once per model on the
Mac, sequentially, with corrected prompt v6 and effort medium. No GPU was used.**
The observed mix is 8 first calls and 19 later calls per model; no older calibration
or ordinary pilot calls enter this new median.

| Model ID | Frozen charge by W1's rule: overall median | n / HTTP attempts | First median (n=8) | Later median (n=19) | Retries / exclusions | API dollars |
|---|---|---|---|---|---|---|
| `claude-opus-5-5` | **4.74 s** | 27 / 27 | 2.135 s | 5.05 s | 0 / 0 | 0.4354354 |
| `claude-sonnet-5-5` | **1.76 s** | 27 / 27 | 1.685 s | 1.76 s | 0 / 0 | 0.2006277 |

All **54 replies were strict and valid**, with no request errors, missing samples,
recovered replies or exclusions. Timings come from the unchanged probe's rounded
hundredth-second rows; even-sized subgroup medians can have three decimal places.

Each episode received only its own preceding projected terminal records (0 through
7 records), fixed for every observation of that episode. Before calls, all 27
Opus payloads matched the actual recorded pilot requests exactly, and every
Opus/Sonnet pair matched except model ID. Actual retained sent requests were also
checked pairwise after replay. To preserve literal identical inputs, an **artifact-
only** timing copy gives both models the recorded pilot's provisional **4.7 s**
public call charge. This common input scalar is separate from the resulting
measured charges above. No W1 timing/config/decision file was edited.

Raw samples in seconds, in original observation order within each episode
(the first number in each cell is that episode's first call):

| Episode | Task | Opus samples | Sonnet samples |
|---|---|---|---|
| 0000 | PanTransfer | 2.89, 4.12, 6.51, 6.04, 5.26 | 1.59, 1.73, 1.60, 1.62, 1.63 |
| 0001 | PanTransfer | 2.05, 5.77 | 1.98, 1.28 |
| 0002 | CloseFridge | 2.18, 4.88, 4.74 | 1.49, 1.50, 1.94 |
| 0003 | CloseFridge | 1.78, 4.35, 3.12 | 2.11, 1.76, 1.70 |
| 0004 | PanTransfer | 2.39, 5.05, 4.92, 4.64 | 2.04, 1.75, 2.73, 5.50 |
| 0005 | PanTransfer | 3.64, 4.98, 6.13, 5.65 | 1.76, 1.66, 4.76, 5.95 |
| 0006 | CloseFridge | 1.82, 6.29, 4.15 | 1.54, 4.73, 1.97 |
| 0007 | CloseFridge | 2.09, 5.58, 6.03 | 1.61, 3.82, 7.07 |

Per model, input usage was identical: 78,892 uncached / 5,414 cache-write /
45,387 cache-read tokens. Output usage was 4,186 Opus and 2,477 Sonnet tokens.
The ordinary five-minute caching behavior is retained. This is one replay per
observation of an Opus-generated development session, not a repeated-measure
uncertainty estimate; this replay used the Mac, while the initial 12-call replay
ran on the pilot pod. No samples were trimmed or replaced.

Full replay cost **$0.6360631**, funded within the existing $20 calibration bucket
with a single $10 guard/shared ledger. Prior calibration cost was $0.096624;
combined calibration expense is $0.7326871. Total project API spend is now
**$1.2148545**, compute remains **$0.939**, combined **$2.1538545**, within the
separate $100 API / $250 compute caps. No rental was initiated for this replay.

Artifacts (local, ignored):

- Summary, all raw samples, subgroup statistics, usage and exclusions:
  `runs/stage6_pilot/calibration-all-20261014T212408Z/summary.json` and `samples.csv`.
- Prespecified rule ref, input/source/config hashes, every observation's public
  payload digest and context length, per-episode preceding experience and common
  timing copy: the same root's `inputs.json` and `inputs/`.
- Append-only call timings, redacted request/response traces and logs:
  the same root's `episode-0000/` through `episode-0007/`.
- One shared spend ledger: the same root's `api_spend.jsonl`, linked from every
  episode directory; only one probe process ran at a time.
- Updated canonical delivery: `runs/stage6_pilot/w1-delivery.json`; the original
  six-sample delivery is preserved as `w1-delivery-initial.json`.

Full W3 suite before publishing: **361 tests passed in 5.581 s**,
`runs/stage6_pilot/calibration-all-20261014T212408Z/w3-suite.log`. No harness,
adapter, runner or probe code changed. W1 now owns writing the two charges into
the frozen configuration before computing story limits.

## W1 delivery — actual development results, October 14

The Opus session completed all eight planned episodes, with **3 successes,
5 false completions and 0 infrastructure exclusions**. All 27 model responses
were strict JSON; no decisions were rejected. It used 6,160 control steps.
Every attempted episode, including failures, is retained. Both learned workers
used the pinned revision `c484448aba1a9b60a04c9b0ca117241518ea69f3`, with verified
checkpoint manifests. This is development evidence, not a frozen comparison.

W1's actual scorer (`efaac23`) read all eight episodes and the session records
using the copied **provisional** Opus charge of 4.7 seconds. Per-cell results:

| Backend | Task | Successes / attempts | Mean time-charged value |
|---|---|---|---|
| `groot` | CloseFridge | 2 / 2 | 0.142 |
| `groot_u30` | CloseFridge | 1 / 2 | 0.066 |
| `groot` | PanTransfer | 0 / 2 | 0.000 |
| `groot_u30` | PanTransfer | 0 / 2 | 0.000 |

Baseline regret, paired regret, held-out primary regret and learning remain
**null** because this pilot has no baseline cohort. No rescue or adaptation
claim follows from these eight episodes. Scorer artifact:
`runs/stage6_pilot/scoring/score.json`; copied scoring input:
`runs/stage6_pilot/inputs/time-pressure.json`.

### Initial two-observation replay — superseded by full-pilot replay above

Both models replayed the actual CloseFridge/K episode `0002`, with only its two
preceding completed PanTransfer records. First observation: index 0, step 0,
3 images. Mid observation: index 1, step 200, 15 images including interval frames.
All images are 256 × 256 PNGs; raw PNG payload totals are 167,253 and 814,832 bytes.
Each observation was replayed three times per model, sequentially on the same
pilot pod after the session ended. Effort remained medium; no frame was invented.

| Model ID | First median (n=3) | Mid median (n=3) | Pooled median (n=6) | Successful / attempted logical calls | HTTP attempts | Retries / excluded calls | Calibration API dollars |
|---|---|---|---|---|---|---|---|
| `claude-opus-5-5` | 1.85 s | 4.34 s | **3.08 s** | 6 / 6 | 6 | 0 / 0 | 0.065052 |
| `claude-sonnet-5-5` | 1.08 s | 2.01 s | **1.44 s** | 6 / 6 | 6 | 0 / 0 | 0.031572 |

All 12 replay responses were strict, valid JSON. Synthetic preflight and ordinary
pilot calls are excluded from these replay medians. Samples in seconds:
Opus first `[2.13, 1.85, 1.53]`, mid `[4.34, 4.03, 5.39]`; Sonnet first
`[1.03, 1.51, 1.08]`, mid `[2.01, 2.17, 1.37]`.

Experience: 2 records, 1,341 serialized JSON characters; model-visible experience
blocks contain 904 and 433 characters. Across its six replay calls, Opus used
12,306 uncached input / 0 cache-write / 11,040 cache-read / 681 output tokens;
Sonnet used 12,306 / 1,840 / 9,200 / 144 respectively. The five-minute cache mix
is part of the measured condition: all Opus replay calls hit the prefix cache;
Sonnet's first call wrote it and the remaining calls hit it.

This is a small calibration sample from one task/episode and a short experience
context, equally weighting first/mid calls; it does not estimate uncertainty or
the distribution of all final-session contexts. Timing rows are rounded to
hundredths of a second by the existing probe. Tom owns the frozen charges and
story limits; W3 has not rewritten W1's timing configuration.

### Spend, termination and retained artifacts

Actual Claude spend: preflight $0.043512, pilot $0.4386554, first replay $0.023550,
mid replay $0.073074; **total $0.5787914**, 43 HTTP attempts, no unknown-usage
reservations. Prime's wallet billing entry for the exact pod reports **$0.939**;
combined development spend is **$1.5177914**. Prime balance after termination:
$249.061. These are actual usage/billing amounts, within the separate $250
compute and $100 API project caps. History's raw `total_billed_price` is not
interpreted as dollars; the receipt uses the matched wallet `amount_usd` field.

Pod `433e8c50e3394425b4df2c2c420e2d6d` was terminated and a fresh authenticated
pod list reports **zero active pods**. Only this pod's launchd/caffeinate resources
were stopped. Actual hardware: A100 80 GB SXM4, driver 595.91.07, CPU quota
27.2 cores (32 advertised). The initial `/workspace` FUSE mount could not enforce
file permissions; bootstrap was moved to `/root/OrcaBench` on its 120 GB local
filesystem, with `.env` mode 600 and the mounted copy removed. Logs are retained.

All artifacts are local and Git-ignored; only small W3 documentation is pushed:

- W1-facing machine-readable delivery, samples, usage, exclusions, source/config/
  actual system-prompt/scorer/timing hashes: `runs/stage6_pilot/w1-delivery.json`.
- Eight attempts, results, manifests, decisions, observations, evaluator records,
  model traces/timings, PNGs and videos:
  `runs/stage6_pilot/opus-pilot/sessions/opus-eight/`.
- Replay reports, per-call timings, traces and spend ledgers:
  `runs/stage6_pilot/calibration-first/` and `calibration-mid/`.
- Preceding experience and retained provisional inputs: `runs/stage6_pilot/inputs/`.
- Scorer output/log: `runs/stage6_pilot/scoring/`.
- Environment freezes and checkpoint manifests: `runs/stage6_pilot/environment/`.
- Quote/create/status/termination records and actual matched compute bill:
  `runs/stage6_pilot/compute-launch-20261014T2012/final-compute-receipt.json`.
- Copy verification: `runs/stage6_pilot/delivery-integrity.json` (8 results,
  27 observations, 309 nonempty referenced frames, 12 accepted replay calls;
  all 24 camera videos also verified nonempty).

Fresh full W3 verification before delivery push: **361 tests passed in 6.665 s**,
`runs/stage6_pilot/w3-live-delivery-suite.log`. The integration checkout's diff
digest and presentation stash remain unchanged. No W1/W2-owned file was edited.

Final pod B has **not** started. It still requires Tom's clean tagged release,
qualified/selected policy set and frozen timing/stories/plans. The shared GPU
is now fixed as A100 80 GB SXM4 at W1 `4278ec7`.
W2's π0.5 remains untested in the inspected partner snapshot. W1 `d00cfd1`
records Tom's decision to wait for its qualification before freezing, replacing
the two-policy fallback. W1 `1101483` has entered the delivered 4.74/1.76-second
charges; story limits and the release tag remain pending at `a9c88e3`. A story
without a qualifying limit will be removed before freeze, retaining its task
deadline and W3's existing null-limit guard. Do not keep or re-rent development
compute while these release inputs are pending.

## Historical live preflight and pilot setup — October 14

The user authorized **$250 total Prime compute** and **$100 total Claude API**
for this project. API allocations are $10 preflight, $20 pilot, $10 first-frame
calibration, $10 mid-frame calibration and $50 final sessions (sum $100).
They are separate phase ledgers within one total, not additional budgets. The
authenticated personal wallet holds $250 and the account lists no teams; the
user permits either billing scope, so W3 uses personal billing.

**Actual prompt-v6 API preflight passed.** At W3 `395940c`, both configured model
IDs, effort medium, corrected prompt6, first and mid synthetic observations:

| Model | Successful / attempted logical calls | HTTP attempts | Retries | Strict/valid | Synthetic median seconds | Settled API dollars |
|---|---|---|---|---|---|---|
| `claude-opus-5-5` | 2 / 2 | 2 | 0 | 2 / 2 | 6.205 | 0.030468 |
| `claude-sonnet-5-5` | 2 / 2 | 2 | 0 | 2 / 2 | 5.010 | 0.013044 |

Total usage-based cost: **$0.043512**. No request errors, recovered replies or
invalid decisions. These synthetic access/serialization timings are **excluded
from representative calibration and benchmark scoring**. Real RoboCasa medians
and pilot score remain unmeasured. Calls, usage, per-call timing, spend ledger,
input/source hashes and console log are retained under
`runs/stage6_pilot/live-preflight-20261014T200627Z/`.

Guard preparation found that launchd does not inherit a sourced project `.env`
and Prime 0.11.0 eagerly initializes global account config. An ignored operational
launcher uses the guard's existing executable hook, independently reads the
designated `.env`, pins personal billing, and initializes CLI config under
`.cache/prime-w3`. No tracked guard/bootstrap or installed package changed, and
`HOME` was not overridden. Six launcher tests passed after the expected missing-
launcher failure. An actual clean-environment pod-list call authenticated;
the actual watchdog returned `pod_absent` without changing global Prime metadata.
Evidence: `runs/stage6_pilot/compute-launch-20261014T2012/verification.json`.

The external watchdog is armed for the development pod, exact returned ID
`433e8c50e3394425b4df2c2c420e2d6d`, name
`robot-cereal-w3-pilot-20261014-2016`. Rental: RunPod A100 80 GB SXM4, 32 advertised
vCPUs, 250 GB RAM, 300 GB requested disk, `ubuntu_22_cuda_12`, US-WA-1. Quoted
offer $1.8068/hr; conservative full-disk bound $1.8488/hr. The $10 pilot compute
allocation includes setup, the 120-minute watchdog deadline, 45-minute pod-side
grace and 30-minute termination retries (quoted bound $6.0086 for 3.25 hours).
This is a quote/allocation, not a billed receipt. The development hardware
matches W2's measured ladder type; final common-GPU agreement remains pending.
Pod-side backstop, bootstrap, learned-worker checks and the eight episodes are
next. Source bundle/dirty-overlay hashes, quote, creation attempt and bound ID
are retained in `runs/stage6_pilot/compute-launch-20261014T2012/`.

## Historical credential check — October 14, 20:03 UTC

After the user saved `.env`, both API keys are now present in that mode-600 file.
Read-only authenticated GETs succeeded with HTTP 200 for Prime identity, its
default wallet and pod list, and Anthropic's individual Opus/Sonnet model
endpoints. Both returned the configured model IDs. Prime's default wallet has
`team_id: null` (personal scope) and its pod list reports zero pods. This does
not establish the user's desired billing scope or an authorized dollar cap.

The separate total compute/API caps and phase allocations remain unset; requested
those totals and the desired personal/team billing choice. No paid Messages
request, prompt-v6 preflight, robot-policy episode or rental has occurred.
Read-only model access is not a successful v6 payload/strict-JSON preflight and
provides no latency calibration. Medians, pilot scores and exclusions remain
null/unmeasured. GPU agreement and Tom's frozen release are still pending.

Receipt: `runs/stage6_pilot/credentials-20261014T200315Z/readiness.json`.
Account/model responses are retained beside it in ignored mode-600 files; keys
and request headers were not printed or saved in those artifacts. This supersedes
the credential-absence finding below. Resume with phase allocations and the live
two-model preflight once the separate caps and billing scope are supplied.

## Historical continuation check — October 14, 19:59 UTC

Fetched GitHub before proceeding. Main remains `2663171`, W1 `efaac23`, W2
`945cb7a`; W3 started this continuation at `67152bb`. No release tag exists.
The integration checkout remains detached at `53e96be` with its six deliberate
modified source/test files; it was inspected without edits, resets or merges.
The prior presentation stash is preserved.

Fresh presence-only checks still find neither `ANTHROPIC_API_KEY` nor
`PRIME_API_KEY` in the process environment or project `.env` (mode 600).
Neither total spending cap nor any phase allocation is set. Requested only the
local credential source location, separate compute/API dollar caps and Prime
billing scope; no key values were requested. Wallet, offers, billing identity
and account-specific model access remain unverified because no authenticated
request was attempted. A Prime balance is not spending authorization.

Bounded read-only partner inspection confirms actual runtime evidence for the
pilot's `groot` and `groot_u30` profiles. π0.5 remains untested/null. No task met
the ceiling rescue rule. The final GPU type is still unconfirmed: W2's historical
A100 80 GB ladder and L40S 48 GB pretrain rentals are not an agreement for pods
A/B. Tom still owns qualification/selection/freeze decisions. These gates do
not require redesigning or rerunning the passed mock interface checks.

Official [pricing](https://platform.claude.com/docs/en/about-claude/pricing),
[Opus](https://platform.claude.com/docs/en/models/opus-5-5/overview) and
[Sonnet](https://platform.claude.com/docs/en/models/sonnet-5-5/overview) references
were rechecked. Model IDs, one-million-token context bounds and standard rates
match the existing guard; no code/config change is needed. This documentation
check does not establish credential validity or paid API access.

| W3 live evidence in this continuation | Value |
|---|---|
| Model requests / robot-policy episodes attempted | 0 / 0 |
| Opus / Sonnet representative v6 medians | null / null (unmeasured) |
| Pilot score / scorer exclusions | null / null (pilot not run) |
| Initiated API / compute spending | $0 / $0 |
| Rentals initiated | 0 |

Presence booleans, exact refs, integration diff digest, standard prices and
unresolved gates are retained in
`runs/stage6_pilot/continuation-20261014T195929Z/readiness.json`; bounded partner
findings are in the adjacent `partner-state.txt`. These are readiness artifacts,
not experimental results. Resume at the existing live prerequisites, then run
the two-model preflight before rental; final pod B additionally requires Tom's
frozen release and the common GPU type. All earlier artifacts remain intact.
Fresh W3 full-suite verification passed: 361 tests in 6.624 seconds, retained in
`runs/stage6_pilot/continuation-20261014T195929Z/w3-suite.log`. Only W3 status/runbook
documentation changed; this test result supplies no robot-policy qualification.

## Offline implementation evidence

- Session mode, prompt6, privacy projection, retained attempts, baseline pairing,
  API attempt ledger and final frozen-input checks are implemented on
  `w3-harness`, [PR #3](https://github.com/tom05919/OrcaBench/pull/3).
- Fresh Python 3.12 suite: 356 tests pass, log
  `runs/stage6_pilot/w3-freeze-suite.log` (local, Git-ignored).
- Both model configurations build prompt6 payloads in credential-free dry runs.
  No model requests were sent by these checks.
- W1's actual session reader was checked against retained mock infrastructure
  attempts at W1 commit `171eb9a`. This verifies artifact compatibility only.
- Combined W1 `171eb9a`, W2 `945cb7a` and W3 `4c185e6` snapshots passed
  381 tests in an isolated, detached local checkout. W1-generated 21-entry plans
  and both W3 prompt6 payloads validated offline. W1's full scorer consumed a
  W3 CLI/HTTPAgent mock session containing one terminal and one infrastructure
  attempt, preserving the exclusion and null baseline comparisons. No actual
  model/robot requests or partner-branch changes occurred.
- Integration review found and fixed W3's worker-death stop gap. The session now
  stops after the failed worker's health/identity check fails, including truncated
  HTTP responses. Healthy workers still allow the existing simulator-error rule.
  Final fresh checks after the fix: 360 W3 tests and 385 combined tests pass.
  Independent review confirmed its finding resolved. Logs:
  `runs/stage6_pilot/w3-worker-stop-suite-final.log` and
  `runs/stage6_pilot/integration-suite-final.log`.
- Applied W1's requested story-clock wording and confirmed pod B's expanded
  assignment at W1 `efaac23`. Fresh checks: 361 W3 and 386 combined tests pass;
  review found no actionable issues. Calibration must use this corrected prompt.
- Refetched GitHub: main `2663171`, W1 `efaac23`, W2 `945cb7a`, W3 `845d963`;
  no newer partner commits or release tag were present. A fresh offline readiness
  check validated the exact eight-entry pilot plan and four v6 payloads covering
  both models' first/mid synthetic observations. Both commands exited 0, with
  zero real model calls and zero robot episodes. Input hashes and commands:
  `runs/stage6_pilot/readiness-20261014T195057Z/readiness.json` (local, ignored).
- Full W3 suite rerun before publishing the execution plan: 361 tests passed
  in 6.613 seconds; log `runs/stage6_pilot/w3-execution-plan-suite.log`.

| Required runtime evidence | Status |
|---|---|
| Opus representative median under prompt6 | 4.74 s, 27 full-pilot replay calls |
| Sonnet representative median under prompt6 | 1.76 s, 27 full-pilot replay calls |
| Eight-episode Opus RoboCasa session | Complete: 3 success, 5 false completion, 0 infrastructure |
| W1 scoring of that real pilot | Complete with retained provisional inputs; regret/learning null |
| Actual compute/API spend from W3 | $0.939 / $1.2148545; pod terminated |

## Execution order

1. Provision credentials locally and settle API/GPU caps and the Prime billing
   account. No keys should be put in chat, Git, logs or the model payload.
2. Use merged W1 timing schema and W2's qualified worker backends. Check current
   model access, prices and GPU offers. Run a small synthetic API preflight;
   this checks access/JSON mechanics, not representative robot-call latency.
3. Arm pod-side termination and an external watchdog. On one pod, run the
   prescribed development pilot: two policies × two tasks × two scenes, eight
   ordered episodes, with one supervisor and anonymous labels. Preserve results
   even when interrupted or unsuccessful.
4. Replay representative first/mid observations for both models with only earlier
   projected experience; preserve all attempts and provide measured medians to
   W1 before story limits/final timing freeze. Run the W1 scorer on the pilot's
   retained provisional timing inputs and inspect accepted/excluded attempts.
   Historical provisional charges are not calibration results. Report usage,
   sample counts, latency and artifact paths here.
5. After Tom merges, freezes and tags the common release, run pod B's same-pod
   always-defer baselines followed by Sonnet sessions. Copy artifacts after each
   phase and verify pod termination. Tom approved moving `reissue_200` to pod B
   in W1 commit `efaac23`; W3 confirms always-defer, Sonnet and `reissue_200`,
   about 252 episodes with at least 16 cores.

Commands and spend-guard details are in [session_mode.md](session_mode.md).
The project-local Prime CLI is installed at the pod guard's `0.11.0` pin;
the operational launcher, authenticated account checks, guards and development
execution have now been verified as described above. Both local keys and explicit
caps are available. Integrated frozen timing, final plans, qualified final policy
selection and the release tag remain open. The final GPU type is fixed at
A100 80 GB SXM4 by W1 `4278ec7`.
The earlier credential visibility discrepancy is resolved. The expanded
execution gates, phase allocations and reasoning are in `session_mode.md`.
