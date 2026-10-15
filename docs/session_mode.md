# W3 session mode: plan and progress

Owner: Ty / person 3. Branch: `w3-harness`. Goal: one supervisor configuration,
one accumulated text context, anonymous policies interleaved across RoboCasa
episodes, with time charged under W1's scoring contract.

New W3 sessions should read [w3_handoff.md](w3_handoff.md) for the earlier snapshot,
then this runbook and [stage6_pilot.md](stage6_pilot.md) for the current live state.
The development pilot/calibration is complete and the pod is terminated; resume
at Tom's frozen release and final pod B, preserving the existing integration tree.

**Partner update, October 14 evening (W1 `a9c88e3`):** the calibrated call
charges are now written in W1's config. Tom explicitly decided that the freeze
waits for π0.5's smoke test and ladder, then selection and story limits; the
earlier two-policy fallback is superseded. If no qualifying run yields a story
limit, W1/W2 remove that task's story before freezing, while retaining its task
deadline. W3's existing refusal of a story with a null limit remains unchanged.
No final rental or session starts before the clean integrated release tag.

## Sources and scope

Use `docs/briefs/w3_harness.md` and the fixed ownership/interfaces in
`docs/work_split.md`. The latest inspected W1 branch (`efaac23`) revises the
interface: `call_seconds` maps model identifiers to calibrated seconds; task
entries carry a deadline and an optional nested story. Its final policy set is
`groot`, `groot_u30`, `pi05`. The final scope is monitoring, declaration timing
and restraint. Re-prompting is described neutrally. π0.5 remains untested until
W2 supplies runtime evidence.

Do not change W1/W2-owned files or frozen unowned files. W1/W2 branch work stays
separate until Tom integrates it. No paid calls or GPU rentals before the account,
credential availability and spending caps are settled. Final runs also require
the common GPU type, selected plans, fixed time parameters and release tag.

## Implementation design

- `session.py` validates the complete plan and worker map before model/robot
  execution. Anonymous labels are K/R/T/V/W/Z, with a consistent one-to-one
  label/backend mapping. Seeds, task names, expected start hashes and distinct
  loopback worker URLs are checked.
- A session wrapper augments an already-public observation with the anonymous
  policy label, the last N projected completed records and public timing context.
  The low-level runner and physics semantics remain the same. Raw seeds, backend
  names, evaluator data and clock-trigger predicates never enter this context.
- Only terminal non-infrastructure outcomes become experience. Prior records
  contain native goal, accepted decisions and their step positions, success or
  failure, calls/steps and declaration correctness. A past outcome is available
  only after that episode ends. Malformed replies and exception messages are
  not copied into learning records.
- The adapter puts experience text blocks before current episode images/content,
  with caching on the final experience block. Session prompt version 6 states
  the dynamic per-model charge, deadline, public story and score. Legacy isolated
  calls keep prompt version 5. Decision schema, medium effort and retries stay.
- `session.jsonl` retains exactly the eight W1 interface fields. Each attempted
  episode gets a reserved index and conventional episode folder before execution.
  Interruptions/errors retain artifacts. Existing session directories are refused,
  avoiding silent retries or context reconstruction after a partial session.
- The contract records session implementation, plan identity, experience limit,
  model configuration, worker identities and the time configuration. Changing any
  of those starts a new session. Hashes are evaluator metadata, never model input.

## Ordered work plan

1. **Core session and privacy tests.** Ordered attempts, anonymous labels, strict
   projection, bounded experience, infra exclusions, cancellation and overwrite
   refusal. Reuse existing public observations and episode artifacts.
2. **Adapter/prompt and probe.** Cache order, dynamic prompt, strict JSON behavior,
   credential-free dry run, latency medians and append-only attempt logs.
3. **CLI integration.** Reuse `run_episode`, explicit episode-directory override,
   actual worker identity checks, fixed state hashes, session contracts and stop
   after two consecutive infrastructure errors. Provide baseline-to-plan pairing.
4. **Full verification and independent review.** Supported Python suite, no-secret
   payload assertions, actual CLI dry run, failures/interruption retention, source
   whitespace check. Record results below; mocks do not qualify a robot policy.
5. **Integration/probe/pilot.** Consume merged W1/W2 dependencies. With settled
   credentials/caps, verify live model names/prices, probe both models with prompt6,
   run the eight-episode pilot on one guarded pod, then calibrate both models on
   its representative observations. Supply those measured medians to W1, score
   using W1's script, and preserve every attempt. Synthetic preflight timings
   are access checks, not the representative calibration used to freeze scoring.
6. **Final runs.** At the agreed tag and GPU type, baselines first on pod B, attach
   same-pod step-zero hashes to plans, run Sonnet sessions, copy after each phase,
   terminate and verify. Report attempts, cost, model latency and infra exclusions
   in `docs/stage6_pilot.md`; W1 writes the combined report.

## Current progress

Current live state: actual eight-episode pilot, W1 scoring and full-pilot v6
calibration completed; API $1.2148545 and compute $0.939, pod terminated. Details
are in `docs/stage6_pilot.md` and `runs/stage6_pilot/w1-delivery.json`. Final release
and policy qualification/selection remain open. Final GPU is A100 80 GB SXM4
(W1 `4278ec7`). Earlier implementation/readiness milestones:

- GitHub main pulled at `2663171`; W1 and W2 newer branches inspected read-only.
- Previous presentation work preserved in Git stash and not reapplied across the
  new file-ownership split.
- Baseline on current main: 285 tests passed under Python 3.12 after restoring
  the exact pinned external registry into the ignored vendor directory.
- Session core, prompt version 6, offline API-probe payloads and CLI integration
  implemented. Tests exercise the actual session/adapter boundary and ordered
  episode execution using test doubles. Independent review's callback-failure
  artifact issue is fixed, and the actual W1 `read_session` reads the retained
  infrastructure attempt. Initial full suite: 328 tests pass. No runtime robot
  policy or model qualification is implied by these checks.
- Initial implementation pushed as `eba35b7`, [PR #3](https://github.com/tom05919/OrcaBench/pull/3).
  The second local verification covers 350 tests, baseline pairing and spend guards.
  Actual W1 reader compatibility was checked at its latest inspected branch
  (`171eb9a`) using retained mock infrastructure attempts, never scored experiments.
- Frozen-input checks added: final timing must be marked frozen and equal the
  tagged file; model config and ordered source plan must match shipped files.
  Pairing audits are re-read against the baseline cohort, and each baseline's
  contract must match the current worker/harness before model construction.
  Final experience limit is 24 and recording interval is 10; task configs and
  splits must equal the tagged versions. Fresh full suite: 356 tests pass.
  Focused independent review found no actionable bugs. Live gates remain open.
- Initial readiness, before the credential update: no live W3 episode or paid
  model probe; this environment then had no
  `ANTHROPIC_API_KEY`, `PRIME_API_KEY`, or `PRIME_TEAM_ID` configured.
  A Git-ignored `.env` template was prepared with mode 600 and empty values;
  it contains no credentials or approved caps. Shell presence checks agree.
  Model/GPU spending caps and billing account were pending. The project-local
  Prime CLI was subsequently installed and verified as described below.

## Commands for the initial implementation

Workers are a JSON object mapping the plan's anonymous labels to distinct worker
URLs, for example `{"K":"http://127.0.0.1:8765","R":"http://127.0.0.1:8766","T":"http://127.0.0.1:8767"}`.
The mapping changes with each plan's anonymous-label permutation. Runtime health
checks verify each worker's backend and verified checkpoint identity before a
model is constructed.

Validate a plan without any worker connection, API credential or paid call:

```bash
PYTHONPATH=src python3.12 -m robot_benchmark.cli session \
  --plan configs/final/plans/scene1000.json --workers runs/final/workers-scene1000.json \
  --agent-config configs/model-sonnet-5-5.dev.json \
  --time-pressure configs/time_pressure.json --session-id sonnet-scene1000 \
  --development --dry-run --output runs/final/podB
```

The plan generator and time configuration currently live on W1's branch. These
paths are examples for the integrated checkout; do not manufacture missing
final plans or silently substitute provisional parameters.

Probe prompt6 without sending model requests:

```bash
PYTHONPATH=src python3.12 scripts/probe_model.py \
  --agent-configs configs/model-opus-5-5.dev.json configs/model-sonnet-5-5.dev.json \
  --time-pressure configs/time_pressure.json --task CloseFridge --dry-run \
  --output runs/stage6_pilot/probe-dry-run/probe.json
```

When account/key/cap readiness is settled, omit `--dry-run` and add
`--api-dollar-cap <approved total API dollars>` to send real probes.
Use final prompt6, effort medium and representative stored frames for calibration.
Synthetic probes test API mechanics and do not replace the RoboCasa pilot. The
probe preserves every call in `model_timings.jsonl` and reports per-model median
seconds. Output and timing paths must be new.

The live pilot uses `--development` without `--dry-run`, with an explicit
`--api-dollar-cap`. Final sessions use
`--release-tag release-2026-10-14` instead of `--development`, at a clean checkout
whose HEAD equals that tag. Every final plan entry must have the same-pod
baseline's `expect_state`, with the adjacent `.pairing.json` audit. Final mode
also verifies the inputs above. A final dry run rechecks local baselines and
frozen files but does not contact workers, so it cannot verify live worker
identity or the worker-specific baseline contract. Those checks run before a
model is constructed in live mode.

## Same-pod baseline pairing

Run always-defer on every frozen cell on the same pod as its LLM twin, one backend
at a time. This example uses W1's provisional task set; replace it with the frozen
selection before running. No outcome selects which cells get paired.

```bash
PYTHONPATH=src .venv-sim/bin/python -m robot_benchmark.cli baseline \
  --task-configs configs/tasks/{ArrangeTea,MakeIceLemonade,PanTransfer,WaffleReheat,OpenCabinet,PickPlaceCounterToStove,CloseFridge}.json \
  --scene-seeds 1000,1001,1002,1003 --policy-seeds 0 --agent always_defer \
  --policy-url http://127.0.0.1:8765 --video-record-interval 10 \
  --skip-existing --output runs/final/podB/always_defer/groot
```

Repeat on the other worker URLs and backend-named output folders. Point pairing
at `runs/final/podB/always_defer`, never the other pod's results or a directory
containing multiple baseline cohorts.

```bash
PYTHONPATH=src .venv-sim/bin/python -m robot_benchmark.cli pair-session \
  --plan configs/final/plans/scene1000.json --reference-root runs/final/podB/always_defer \
  --output runs/final/podB/plans/scene1000.json
```

This copies the source plan, adds each twin's step-zero hash, and writes
`scene1000.pairing.json` with the source/paired plan hashes and exact baseline
paths. It accepts baseline failures as well as successes, excludes infrastructure
errors, and refuses ambiguous/missing twins, conflicting existing hashes and
existing output files.

At the tagged, integrated release, the Sonnet command on pod B is:

```bash
PYTHONPATH=src .venv-sim/bin/python -m robot_benchmark.cli session \
  --plan runs/final/podB/plans/scene1000.json --workers runs/final/podB/workers-scene1000.json \
  --agent-config configs/model-sonnet-5-5.dev.json --time-pressure configs/time_pressure.json \
  --session-id sonnet-scene1000 --release-tag release-2026-10-14 \
  --api-dollar-cap "${W3_FINAL_API_CAP:?Set the final-session allocation within the total API cap}" --output runs/final/podB
```

Repeat for all four scene plans. W2 uses the same command on pod A with its own
paired plans and worker maps, Opus config, `opus-scene1000`, and its API cap. Both
pods use the agreed GPU type and exact tag. W3 confirms Tom's October 14 move
(`w1-scoring` commit `efaac23`): **pod B runs always-defer, Sonnet sessions and
`reissue_200`, about 252 episodes, on at least 16 CPU cores**. Pod A keeps
always-defer, Opus, `reissue_50` and `reissue`. Restart comparisons remain unpaired.

After Sonnet, run the fixed 200-step restart schedule on every frozen cell:

```bash
PYTHONPATH=src .venv-sim/bin/python -m robot_benchmark.cli baseline \
  --task-configs configs/tasks/{ArrangeTea,MakeIceLemonade,PanTransfer,WaffleReheat,OpenCabinet,PickPlaceCounterToStove,CloseFridge}.json \
  --scene-seeds 1000,1001,1002,1003 --policy-seeds 0 --agent reissue_200 \
  --policy-url http://127.0.0.1:8765 --video-record-interval 10 \
  --skip-existing --output runs/final/podB/reissue_200/groot
```

The task list above is provisional; use the frozen selection. Repeat for the
other backend worker URLs and backend-named output folders. Copy after this
phase before terminating the pod. Keep this root separate from always-defer so
baseline pairing cannot include restart episodes or duplicate cohorts.

## Eight-episode development pilot

Use the integrated W1/W2/W3 checkout after W2 qualifies both selected workers.
This recipe uses `groot` on port 8765 and `groot_u30` on port 8766; do not
substitute an untested worker. Set approved API caps before live commands and
arm both pod guards as described in `docs/compute.md`. Copy the current timing
file for the pilot so later freezing cannot rewrite its scoring inputs:

```bash
source scripts/project_env.sh
mkdir -p runs/stage6_pilot/workers
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 setsid -f \
  .venv-groot/bin/python -m robot_benchmark.policy_worker \
  --backend groot --checkpoint checkpoints/groot/checkpoint-120000 \
  --port 8765 > runs/stage6_pilot/workers/groot.log 2>&1 < /dev/null
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 setsid -f \
  .venv-groot/bin/python -m robot_benchmark.policy_worker \
  --backend groot_u30 --checkpoint checkpoints/groot_u30/composite_unseen_30p \
  --port 8766 > runs/stage6_pilot/workers/groot_u30.log 2>&1 < /dev/null

PYTHONPATH=src .venv-sim/bin/python - <<'PY'
import json
from pathlib import Path

root = Path("runs/stage6_pilot/inputs")
root.mkdir(parents=True, exist_ok=True)
plan = [{"task": task, "scene_seed": scene, "policy_seed": 0,
         "policy_label": label, "backend": backend}
        for scene in (1000, 1001)
        for task in ("PanTransfer", "CloseFridge")
        for label, backend in (("K", "groot"), ("R", "groot_u30"))]
for name, value in (
    ("plan.json", plan),
    ("workers.json", {"K": "http://127.0.0.1:8765", "R": "http://127.0.0.1:8766"}),
    ("time-pressure.json", json.loads(Path("configs/time_pressure.json").read_text())),
):
    with (root / name).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
PY

PYTHONPATH=src .venv-sim/bin/python -m robot_benchmark.cli session \
  --plan runs/stage6_pilot/inputs/plan.json \
  --workers runs/stage6_pilot/inputs/workers.json \
  --time-pressure runs/stage6_pilot/inputs/time-pressure.json \
  --agent-config configs/model-opus-5-5.dev.json --session-id opus-eight \
  --development --api-dollar-cap "${W3_PILOT_API_CAP:?Set the pilot allocation within the total API cap}" \
  --output runs/stage6_pilot/opus-pilot

PYTHONPATH=src .venv-sim/bin/python scripts/score_time.py \
  runs/stage6_pilot/opus-pilot \
  --config runs/stage6_pilot/inputs/time-pressure.json \
  --output runs/stage6_pilot/scoring/score.json
```

Before live execution, use the session command with `--dry-run`, and do a small
synthetic API preflight with `probe_model.py` to verify access and strict JSON.
For example, after setting a separately approved preflight allocation:

```bash
PYTHONPATH=src .venv-sim/bin/python scripts/probe_model.py \
  --agent-configs configs/model-opus-5-5.dev.json configs/model-sonnet-5-5.dev.json \
  --time-pressure runs/stage6_pilot/inputs/time-pressure.json --task CloseFridge \
  --api-dollar-cap "${W3_PREFLIGHT_API_CAP:?Set the approved preflight cap}" \
  --output runs/stage6_pilot/preflight/probe.json
```

The pilot deliberately uses `--development`: its provisional timing cannot be
presented as a frozen final result. W1's scorer accepts development model episodes
by their adapter identity. Without baseline roots, regret/learning comparisons
are null; this check establishes real session/scorer compatibility.

The chosen plan has one context across all eight episodes, with fixed anonymous
labels throughout. Its third episode (index 2) is CloseFridge. After it finishes,
derive only preceding terminal experience for representative calibration:

```bash
PYTHONPATH=src .venv-sim/bin/python - <<'PY'
import json
from pathlib import Path
from robot_benchmark.session import project_experience

root = Path("runs/stage6_pilot/opus-pilot/sessions/opus-eight")
rows = [json.loads(line) for line in (root / "session.jsonl").read_text().splitlines()]
assert any(row["index"] == 2 for row in rows), "Pilot stopped before calibration episode"
records = []
for row in rows:
    if row["index"] >= 2:
        break
    episode = root / row["episode_dir"]
    decisions = episode / "decisions.jsonl"
    record = project_experience(row["policy_label"], json.loads((episode / "result.json").read_text()),
        [json.loads(line) for line in decisions.read_text().splitlines()] if decisions.exists() else [])
    if record is not None:
        records.append(record)
with Path("runs/stage6_pilot/inputs/experience-before-0002.json").open("x") as stream:
    json.dump(records, stream, indent=2)
    stream.write("\n")
PY

PYTHONPATH=src .venv-sim/bin/python scripts/probe_model.py \
  --agent-configs configs/model-opus-5-5.dev.json configs/model-sonnet-5-5.dev.json \
  --episode runs/stage6_pilot/opus-pilot/sessions/opus-eight/episodes/0002 \
  --observation-indices 0 --repeats 3 \
  --time-pressure runs/stage6_pilot/inputs/time-pressure.json --task CloseFridge \
  --policy-label K --experience runs/stage6_pilot/inputs/experience-before-0002.json \
  --api-dollar-cap "${W3_CALIBRATION_FIRST_API_CAP:?Set the first-observation calibration allocation}" \
  --output runs/stage6_pilot/calibration-first/probe.json
```

Inspect the stored observation count before choosing a mid-episode index and
repeat that probe into a new directory with the corresponding index and
`W3_CALIBRATION_MID_API_CAP` as its separate allocation. A one-call
episode has no mid-episode observation; select another recorded episode and
derive its preceding experience instead of inventing frames. Record sample
counts, context lengths, retries and separate first/mid medians alongside the
pooled per-model median. W1 must receive actual calibration values before story
limits/final timing freeze. Each distinct output directory has its own cap ledger;
the sum of approved pilot and calibration caps must stay inside the total API
budget, including the preflight allocation. Keep observation PNGs until all
replay probes finish. Two consecutive infrastructure errors or an API budget
stop can leave fewer than eight attempts; report the actual retained count and
do not relabel a partial session as a completed pilot.

## API cost guard

Live probes and sessions require an explicit API-dollar cap. A shared
`api_spend.jsonl` ledger covers all models in one probe directory, or all sessions
in one session output root. Use one sequential process per ledger. The guard
reserves before every HTTP attempt, including retries, and fsyncs the ledger.
Observed usage settles actual uncached-input, cache-write/read and output costs.
Errors with unknown usage retain the whole reservation. A session stops before
another episode once it cannot reserve the next call.

The strict reservation uses the documented one-million-token context ceiling
and 4,096 maximum output tokens, not a tokenizer estimate. Required headroom per
attempt is **$5.08192 for Opus** and **$2.54096 for Sonnet** under current standard
pricing and the adapter's five-minute cache. This is reserved headroom, not an
expected cost per call. Successful usage releases unused dollars. A cap below
the required reserve refuses to start. Dry runs expose this minimum without
credentials, model requests or token-count requests.

These prices/context limits were checked against the official
[pricing](https://platform.claude.com/docs/en/about-claude/pricing),
[Opus](https://platform.claude.com/docs/en/models/opus-5-5/overview) and
[Sonnet](https://platform.claude.com/docs/en/models/sonnet-5-5/overview) pages on
October 14. Account-specific model access remains untested. The guard assumes
standard global pricing and documented provider limits; it does not cover an
account's residency/fast-mode premiums or spending by other processes/keys.
Prime GPU credits do not pay these direct Anthropic calls.

## Next continuation, without redefining completion

### Forward execution plan (October 14)

**Goal:** deliver measured v6 call charges, a scored eight-episode pilot, and
pod B's final baselines/Sonnet sessions while keeping workstream ownership intact.

**Architecture:** keep implementation on `w3-harness`. Use a detached, ignored
checkout under `runs/stage6_pilot/integration-check` to test current W1/W2/W3
snapshots together. Local validation merges are disposable; Tom owns integration
into `main`, selection, configuration freezing and the release tag.

**Spec:** `docs/briefs/w3_harness.md`, latest W1 `docs/final_experiment.md`.
**Tools:** Git, Python 3.12 unittest, existing CLI/probe/scorer, guarded Prime pods.

- [x] **1. Combined interface validation, now.** Snapshot the three branch SHAs,
  create the isolated checkout, merge the snapshots locally, and run
  `PYTHONPATH=src python -m unittest discover -s tests -v`. Retain merge conflicts
  and test output in W3's ignored run directory. Resolve only shared append-only
  decision-log conflicts; any partner-owned code issue is reported without
  rewriting their branch. Confirm W1 reads/scorers consume real W3-format mock
  sessions and all W2 worker backends validate. No runtime policy qualification
  is inferred from these checks.
- [x] **2. Fix only demonstrated W3 issues.** Write a regression test for any
  W3-owned defect, verify failure, fix, run focused/full checks and get one
  bounded review. Commit/push only W3-owned paths, then fetch partner branches.
  If no W3 issue appears, report that result without manufacturing changes.
- [x] **3. Live prerequisites.** Provision Anthropic/Prime credentials locally;
  record explicit API/GPU caps, billing account, and agreed GPU type. Confirm
  worker checkpoint qualification with W2. Check wallet/offers/model access
  before creating a guarded pod. Credentials are never printed or committed.
- [x] **4. Preflight → pilot → calibration.** Execute the exact development
  commands above. Preserve every attempt, verify eight terminal non-infra
  episodes, score with W1, and measure both models on representative first/mid
  stored observations. Give W1 sample counts, medians, config/commit identity
  and artifact paths. Missing/failed calls remain recorded, never invented.
- [ ] **5. Final release → pod B.** Consume Tom's tagged frozen release, generated
  plans and timing inputs. Run same-pod always-defer first, pair all planned
  cells, run Sonnet, copy artifacts after each phase, terminate/verify the pod.
  W2 receives the same documented session command for Opus on pod A.
- [ ] **6. Delivery audit.** Update `docs/stage6_pilot.md` with actual latency,
  usage, pilot scoring and final attempt counts. W1 writes the combined report;
  W3 checks its claims against artifacts. Completion requires real execution,
  scoring and integrated code, not only passing local tests.

**Latest freeze calibration (W1 `4278ec7`, rule fixed before replay):** replayed
all 27 observations of all eight pilot episodes once per model, sequentially on
the Mac, corrected v6, medium effort, only each episode's preceding projected
experience. All 54 replies strict/valid; no retries, errors or exclusions. Frozen
charges by the rule are **Opus 4.74 s / Sonnet 1.76 s**, n=27 each; first-call
medians 2.135/1.685 s (n=8), later medians 5.05/1.76 s (n=19). These supersede
the earlier six-sample medians below. Both models received the exact same public
pilot inputs with the original provisional 4.7-second scalar, via an artifact-only
timing copy; actual payload pairs were verified equal except model ID. W1 writes
the resulting charges before story limits; no W1 config file changed.
Raw samples, counts, cache/host limitations and costs: `docs/stage6_pilot.md`;
artifacts: `runs/stage6_pilot/calibration-all-20261014T212408Z/`.
Replay API cost $0.6360631 within the existing $20 calibration bucket; cumulative
API $1.2148545, compute $0.939. No GPU rental. Final GPU A100 80 GB SXM4 is now
fixed in W1's decision log. Final pod B still requires Tom's integrated tagged
release, qualified policy selection, frozen timing/stories and ordered plans.

**Actual development execution completed (October 14):** eight terminal episodes,
3 successes / 5 false completions / 0 infrastructure exclusions, 27 strict
Opus replies, W1 scorer consumed all eight using the retained provisional timing.
Representative replay medians from six successful calls/model are Opus **3.08 s**
and Sonnet **1.44 s**; first/mid medians are 1.85/4.34 s and 1.08/2.01 s.
Twelve replay calls were strict/valid, zero retries/exclusions, with only the
chosen episode's preceding two records and actual first/mid frames. Synthetic
preflight and ordinary pilot calls are excluded from the replay medians.
Details, sample/cache limitations, usage and paths are in `docs/stage6_pilot.md`;
machine-readable W1 delivery: `runs/stage6_pilot/w1-delivery.json`.
Actual API spend $0.5787914 and billed compute $0.939, total $1.5177914.
The exact development pod is terminated; zero active pods verified. All attempts,
frames, videos, scorer outputs, environment/checkpoint records and receipts are
copied locally. Development credential/account/cap/worker gates are met; the
common **final** GPU agreement remains open in step 3/5, alongside Tom's frozen
release. Step 6's development delivery is complete; final run audit is pending.

**Continuation receipt (October 14, 19:59 UTC):** fetched main `2663171`, W1
`efaac23`, W2 `945cb7a`, W3 `67152bb`; partner refs are unchanged and no tag is
present. Read-only inspection preserved the detached integration checkout and
presentation stash. Both keys, both total caps and phase allocations remain
absent from the process and project `.env`. Credential source location, separate
caps and billing scope are pending user inputs; no authenticated check, model
request, robot episode or rental was attempted. Official model IDs, context
bounds and standard pricing were rechecked and match the implemented guard.
W2 has actual evidence for both pilot GR00T profiles, but π0.5 and the final GPU
type remain unconfirmed. Keep step 3 open and proceed directly to preflight
once its inputs arrive. Do not repeat completed mock checks as live progress.
Receipt: `runs/stage6_pilot/continuation-20261014T195929Z/readiness.json`;
status and W1-facing null measurement table: `docs/stage6_pilot.md`.

**Credential gate update (October 14, 20:03 UTC):** the saved project `.env` now
contains both keys. Read-only authenticated Prime identity/default-wallet/pod
GETs and both Anthropic model GETs returned HTTP 200. The default Prime wallet
is personal and reports zero pods. No paid model request or rental occurred;
the v6 preflight remains unrun. Explicit compute/API totals, phase allocations
and the desired billing scope remain open, so step 3 is not yet complete. The
latest receipt is `runs/stage6_pilot/credentials-20261014T200315Z/readiness.json`;
it supersedes earlier credential-visibility findings without changing them.

**Paid execution update (October 14):** user totals are $250 Prime compute and
$100 Claude API. Allocate API $10 preflight / $20 pilot / $10 first calibration /
$10 mid calibration / $50 final, totaling $100. Personal billing is selected:
its verified wallet has $250 and no teams were returned; the user permits either
scope. The actual two-model v6 preflight completed four valid strict responses,
zero retries/errors, $0.043512 usage-based cost. Synthetic medians are excluded
from representative calibration. Receipt and complete attempts:
`runs/stage6_pilot/live-preflight-20261014T200627Z/`.
The clean-environment operational launcher solves credential/config isolation
through the existing watchdog executable hook, without tracked tooling edits.
External watchdog is armed and exact-pod bound; development rental ID
`433e8c50e3394425b4df2c2c420e2d6d` is within a $10 allocation including setup and
guard grace. Step 3 now advances through pod-side guard/bootstrap/worker checks;
step 4 resumes with the eight-episode Opus pilot. Full evidence and quote details
are in `docs/stage6_pilot.md`. Final GPU agreement/tag are still open.

### Live execution gates and rationale (October 14, refreshed)

Historical entry, superseded by the actual execution update above: the user
reported adding both keys. That presence-only check of the project
`.env` and shell still sees neither `PRIME_API_KEY` nor `ANTHROPIC_API_KEY`.
The `.env` remains mode 600. Key location and separate API/compute dollar caps
have been requested; values must not be posted in chat. No paid call or rental
has been attempted. Possessing a key is different from making it available to
this process; do not search unrelated credential stores or overwrite an account.

**1. Establish one reproducible starting point.** Fetch before each phase and
record the exact branch SHAs. The current snapshots are main `2663171`,
W1 `efaac23`, W2 `945cb7a`, and W3 `845d963`. Continue using the detached local
integration checkout for development validation; do not merge partner branches
into `w3-harness` or push the disposable merge. Tom still owns the release merge.
The three frozen learned policies are experimental subjects, not code for W3
to modify or train. The pilot needs only the already measured `groot` and
`groot_u30`; do not wait for or duplicate W2's π0.5 qualification to run it.

**Why:** this unblocks W1's calibration dependency while W2 measures π0.5,
without taking over task selection, scoring, or the policy ladder.

**2. Resolve credentials, account, allocations and API access before rental.**
Read the named local credential source without printing it. Confirm the Prime
billing scope (personal versus an explicitly selected team), wallet and current
offers with read-only requests. Check official model access/pricing, then run
the two-model v6 synthetic preflight above: one first and one mid observation
per model, four logical calls before retries, effort medium. Require successful
strict JSON and valid decisions; retain failed requests and stop to diagnose.
Do not silently substitute a model ID or effort level when access fails.

For read-only Prime checks, reuse `adapters.http.request_json` with GET and an
in-memory bearer header. Installed `prime==0.11.0` source identifies
`https://api.primeintellect.ai/api/v1/user/whoami`, `/billing/wallet`, `/pods`
and `/availability/gpus`. Keep responses in the ignored readiness directory and
only report account scope, balance, pod IDs and relevant offers. Do not print
headers. The installed CLI/SDK eagerly initializes `~/.prime` even with an
explicit key, and `prime whoami` persists identity, so neither is the mechanism
for these project-local read-only checks. Do not override `HOME`.

Use separate allocations `W3_PREFLIGHT_API_CAP`, `W3_PILOT_API_CAP`,
`W3_CALIBRATION_FIRST_API_CAP`, `W3_CALIBRATION_MID_API_CAP`, and
`W3_FINAL_API_CAP`. Their sum
must not exceed the user's total `W3_API_CAP`; different output directories
have independent ledgers. In particular, do not give the pilot the whole total
and then spend additional independent allocations. Conservative per-attempt
headroom is $5.08192 for Opus and $2.54096 for Sonnet under the currently
implemented standard-price guard; these are reservation bounds, not forecasts.
Choose actual allocations only after total caps are supplied and prices verified.

**Why:** failed API access should not consume rented GPU time. Explicit allocation
also prevents several individually capped phases from exceeding the total budget.

**3. Prepare the guarded development pod.** Compare offers with at least 16 CPU
cores, GPU memory for the qualified workers, and the GPU type agreed with W2.
Record quote, account, pod ID, hourly price, image and a hard deadline before
work begins. Include setup time, storage/other quoted charges and the pod-side
backstop's 45-minute grace in the compute allocation; do not infer a deadline
from GPU hourly price alone. Arm the existing external watchdog before rental,
bind its exact returned pod ID, then arm the pod-side backstop before experiments.
Verify the watchdog's process can actually access credentials independently of
the interactive shell. Keep account configuration and caches inside this project.
Reuse W2's pinned bootstrap/checkpoints, verify worker health and identity, and
run the existing preflight checks. Never replace a failed learned policy with a
mock or a script. Do not modify the unowned guard/bootstrap scripts without Tom.

**Why:** previous project runs lost money and data when the laptop slept. CPU
throughput matters for RoboCasa, and watchdog readiness is an execution gate,
not something to add after a run is underway.

**4. Run and score the development pilot.** Use the exact eight-entry plan above
(two tasks × two scenes × two qualified policies), one Opus configuration,
anonymous labels, and only projected earlier terminal outcomes. Copy provisional
timing inputs before starting. Preserve session/episode manifests, JSONL,
decisions, usage, timings, errors, videos and observation PNGs. Eight terminal
non-infrastructure episodes complete this pilot even if robot tasks fail; fewer
than eight are a partial pilot, not a reason to delete attempts. A dead worker,
budget exhaustion or repeated infrastructure failures stops execution. W1's
scorer must read all retained attempts and separately count exclusions. This
validates the real path, not a final score or a baseline regret comparison.

**5. Measure latency from the pilot, then hand off the freeze inputs.** Replay
one first observation and one existing mid-episode observation three times per
model (12 logical calls total before retries), with matching task, anonymous
label and only that episode's preceding projected experience. If a recorded
episode lacks a mid observation, choose another recorded episode and reconstruct
its own preceding experience; never invent an observation. Preserve per-call
durations, retries, usage and failures. Report first/mid and pooled medians,
successful/attempted call counts, experience lengths, prompt/model configuration
and source SHA to W1. Keep synthetic preflight and pilot calls out of that pooled
replay calibration. Small sample size is a limitation, not evidence of precision.
Copy back the pilot and calibration frames before terminating the pod.

**Why:** the number and size of images and earlier records affect response time.
Representative measured costs let W1 freeze charges and W2/W1 compute story
limits; historical charges and synthetic images cannot establish those costs.

**6. Run final pod B only after Tom's freeze.** Require a clean tagged checkout,
frozen timing/story configuration, selected task/policy list, ordered plans,
qualified workers and the common GPU type. Tom's W1 `d00cfd1` decision explicitly
waits for π0.5 and supersedes the earlier two-policy fallback. W3 neither chooses
a replacement nor runs the final cohort before its qualification and freeze.
Run always-defer first on every selected cell, then create same-pod paired
plans/audits, run all four Sonnet sessions in order, then `reissue_200` over the
same selected cells. With three policies and seven tasks this is 84 + 84 + 84
= 252 episodes under the current three-policy design.
Restart baselines remain unpaired. Keep sessions sequential within each context;
do not increase concurrency in a way that changes live model latency conditions.

**Why:** identical starting states and a frozen evaluation contract make the
supervisor comparison interpretable. Final episodes must not begin on provisional
parameters just to fill the presentation's results table.

**7. Deliver evidence and keep partners current.** At each completed phase,
copy JSON/JSONL/MP4 and cost receipts to W3's run directories, update
`docs/stage6_pilot.md`, run the required full unittest suite before pushing,
push only W3-owned documentation/code, and fetch partner branches again. Preserve
PNG frames through calibration; final archival follows W1's compact-copy rule.
Do not commit credentials, large artifacts, or the integration checkout. Give W2
the documented Opus command for pod A. Terminate the exact W3 pod and verify its
status before claiming completion. W1 owns the final analysis and report; W3
supplies measurements, attempt counts, exclusions and reproducible commands.

**Fresh no-spend execution:** the exact eight-entry development plan and both
models' four prompt6 first/mid payloads passed dry runs against the combined
checkout. Receipt and input hashes:
`runs/stage6_pilot/readiness-20261014T195057Z/readiness.json`.
This made zero model calls and ran zero robot episodes. The release tag is still
absent. The immediate live gates are credential visibility and dollar caps;
final execution additionally waits on partner qualification/selection/freeze.

**Review focus:** timing-schema drift; worker-label/backend mismatch; scorer
ignoring retained infrastructure attempts; cross-pod baseline pairing; partial
sessions incorrectly presented as eight completed episodes. Existing W3 tests
cover these locally; steps 1 and 4 must verify the combined and live paths.

**Execution evidence:** partner snapshots W1 `171eb9a`, W2 `945cb7a`, W3
`4c185e6` combined in a detached local checkout. Only `docs/decisions.md` needed
conflict resolution, preserving both appended histories; all code merged cleanly.
Initial combined suite passed 381 tests. W1's generator produced four 21-entry
plans; W3 validated one offline with all three backends and built both prompt6
payloads. The actual W3 CLI/HTTPAgent, with mocked transport/environment/policy,
produced one terminal and one infrastructure attempt. W1's actual `score_time.py`
read both, charged both successful episode responses and separately reported the
infrastructure attempt. Baseline regret/learning stayed null. Artifacts:
`runs/stage6_pilot/integration-check/runs/w3-interface-check/validation.json`
and `score.json`. These are explicitly mock checks, never benchmark results.

**Demonstrated W3 fix:** after an infrastructure episode, recheck that worker's
health and identity with a five-second timeout. A dead/replaced worker stops the
session immediately as `policy_worker_unavailable`, retaining the original
episode result/error. A simulator failure with a healthy worker keeps the existing
two-consecutive-error rule. Regression checks cover interleaved backends,
changed checkpoints, refused connections and truncated HTTP health responses.
This aligns the existing final stop rule and changes pre-freeze implementation
hashes; it does not change the model's observations or decision semantics.
Final verification after the review fix: **360 W3 tests and 385 combined tests
pass**, with logs `runs/stage6_pilot/w3-worker-stop-suite-final.log` and
`runs/stage6_pilot/integration-suite-final.log`. The independent reviewer's
truncated-response finding was reproduced, fixed and rechecked. No remaining
actionable review findings. The combined checkout remains local and unpushed.

**W1 clock clarification:** prompt6's story-limit sentence now specifies that
charged seconds count from the event named in the story, or from step 0 if it
names none. The wording exposes no predicate names or trigger state. Regression
cases cover the pan event, ice event and a step-zero cooling story. This is a
pre-freeze prompt correction; calibration must use this corrected prompt.
Fresh checks with W1 `efaac23`: **361 W3 tests and 386 combined tests pass**.
The bounded review found no actionable issues. Logs:
`runs/stage6_pilot/w3-story-clock-suite.log` and
`runs/stage6_pilot/integration-story-clock-suite.log`.

**Compute tooling prepared:** `.venv-prime/bin/prime` is installed at
`prime==0.11.0`, matching `scripts/pod_guard.sh`'s existing pin. Dependencies and
caches stay under this project. Version and `pods create --help` succeeded with
version checks disabled; help confirms `--team-id`. No login/account/context
commands, rentals or API calls were executed. Install receipt:
`runs/stage6_pilot/prime-cli-freeze.txt`; help:
`runs/stage6_pilot/prime-pods-create-help.txt`.

```bash
PRIME_DISABLE_VERSION_CHECK=1 .venv-prime/bin/prime --version
PRIME_DISABLE_VERSION_CHECK=1 .venv-prime/bin/prime pods create --help
```

The CLI's account configuration normally uses `~/.prime`. Before any authenticated
command, keep account setup under this project using the existing project API
tools or an explicitly supported configuration path; do not move another agent's
global account context. Actual account/credential readiness has since been
verified using the project-local operational launcher and read-only HTTP calls.

- Core and pairing/spend-guard commits are pushed to PR #3. Frozen-input and
  baseline-contract checks have passed the 356-test suite and focused review.
- W1 may review the implementation now; merging/tagging remain Tom's integration
  responsibility. The pilot status is [stage6_pilot.md](stage6_pilot.md).
- Fetch `main`, W1 and W2 again. Consume W1's merged timing/plans and W2's backends
  without editing their files. Baseline-to-plan artifact compatibility has been
  checked offline; full integrated live evidence is still required.
- Credentials/caps/account selection are external prerequisites. Once available,
  prepare the project-local Prime environment, verify wallet/offers and API access,
  run the API preflight, guarded eight-episode pilot and representative v6 latency
  probes. Deliver actual medians and scored pilot evidence through this branch.
- Run final pod B only after the agreed tag/GPU type/task plans exist. Keep the
  full W3 goal active until the code is integrated, measured timings are available,
  the pilot is scored and final sessions/artifacts are complete. Local tests alone
  do not satisfy those runtime gates.
