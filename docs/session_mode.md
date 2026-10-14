# W3 session mode: plan and progress

Owner: Ty / person 3. Branch: `w3-harness`. Goal: one supervisor configuration,
one accumulated text context, anonymous policies interleaved across RoboCasa
episodes, with time charged under W1's scoring contract.

## Sources and scope

Use `docs/briefs/w3_harness.md` and the fixed ownership/interfaces in
`docs/work_split.md`. The latest inspected W1 branch (`171eb9a`) revises the
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
   supply measured median latencies to W1, then run the eight-episode pilot on one
   guarded pod. Score using W1's script and preserve every attempt.
6. **Final runs.** At the agreed tag and GPU type, baselines first on pod B, attach
   same-pod step-zero hashes to plans, run Sonnet sessions, copy after each phase,
   terminate and verify. Report attempts, cost, model latency and infra exclusions
   in `docs/stage6_pilot.md`; W1 writes the combined report.

## Current progress

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
- No live W3 episode or paid model probe yet. This environment currently has no
  `ANTHROPIC_API_KEY`, `PRIME_API_KEY`, `PRIME_TEAM_ID`, or project `.env`; no Prime
  CLI is installed. Interactive-shell presence checks agree. Model/GPU spending
  caps and billing account are pending.

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
  --api-dollar-cap "${W3_API_CAP:?Set the approved total API cap first}" --output runs/final/podB
```

Repeat for all four scene plans. W2 uses the same command on pod A with its own
paired plans and worker maps, Opus config, `opus-scene1000`, and its API cap. Both
pods use the agreed GPU type and exact tag. Do not include `reissue_200` on pod B
unless W1/Tom approves the move and logs it.

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

- Core and pairing/spend-guard commits are pushed to PR #3. Frozen-input and
  baseline-contract checks have passed the 356-test suite and focused review.
- W1 may review the implementation now; merging/tagging remain Tom's integration
  responsibility. The pilot status is [stage6_pilot.md](stage6_pilot.md).
- Fetch `main`, W1 and W2 again. Consume W1's merged timing/plans and W2's backends
  without editing their files. Baseline-to-plan artifact compatibility has been
  checked offline; full integrated live evidence is still required.
- Credentials/caps/account selection are external prerequisites. Once available,
  prepare the project-local Prime environment, verify wallet/offers and API access,
  run both v6 latency probes, then the guarded eight-episode pilot. Deliver actual
  medians and scored pilot evidence to W1 through this branch.
- Run final pod B only after the agreed tag/GPU type/task plans exist. Keep the
  full W3 goal active until the code is integrated, measured timings are available,
  the pilot is scored and final sessions/artifacts are complete. Local tests alone
  do not satisfy those runtime gates.
