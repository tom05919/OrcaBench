# W3 pilot status — October 14, 2026

**The real pilot has not run.** There are no measured version-6 latencies or
robot-policy pilot results from W3. Local test results below are implementation
evidence only.

## Evidence available

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

| Required runtime evidence | Status |
|---|---|
| Opus median seconds per call under prompt6 | Unmeasured |
| Sonnet median seconds per call under prompt6 | Unmeasured |
| Eight-episode Opus RoboCasa session | Not run |
| W1 scoring of that real pilot | Not run |
| Actual GPU/API spend from W3 | No paid calls or rentals initiated |

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
version/help checks passed without login or paid actions. Currently this checkout
has no Anthropic/Prime credentials and no
integrated frozen timing, final plans or release tag. These runtime prerequisites
remain open; successful mock tests do not complete W3's assignment.
An empty mode-600 `.env` template now exists locally for credential/cap setup;
no account key or spending limit has been supplied yet.
