# W3 session mode: plan and progress

Owner: Ty / person 3. Branch: `w3-harness`. Goal: one supervisor configuration,
one accumulated text context, anonymous policies interleaved across RoboCasa
episodes, with time charged under W1's scoring contract.

## Sources and scope

Use `docs/briefs/w3_harness.md` and the fixed ownership/interfaces in
`docs/work_split.md`. The latest inspected W1 branch (`a06b209`) revises the
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
- No live W3 episode or paid model probe yet. This environment currently has no
  `ANTHROPIC_API_KEY`, `PRIME_API_KEY`, `PRIME_TEAM_ID`, or project `.env`; no Prime
  CLI is installed. Model/GPU spending caps and billing account are pending.

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

When account/key/cap readiness is settled, omit `--dry-run` to send real probes.
Use final prompt6, effort medium and representative stored frames for calibration.
Synthetic probes test API mechanics and do not replace the RoboCasa pilot. The
probe preserves every call in `model_timings.jsonl` and reports per-model median
seconds. Output and timing paths must be new.

The live pilot uses `--development` without `--dry-run`. Final sessions use
`--release-tag release-2026-10-14` instead of `--development`, at a clean checkout
whose HEAD equals that tag. Every final plan entry must have the same-pod
baseline's `expect_state`; pairing tooling and cost-stop gates are next.
