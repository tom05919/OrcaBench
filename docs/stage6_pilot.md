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
   model access, prices and GPU offers. Run representative prompt6 probes for
   both models, retaining every attempt. Give W1 actual medians before W2/W1
   compute and freeze story limits; historical provisional values are not
   calibration results.
3. Arm pod-side termination and an external watchdog. On one pod, run the
   prescribed development pilot: two policies × two tasks × two scenes, eight
   ordered episodes, with one supervisor and anonymous labels. Preserve results
   even when interrupted or unsuccessful.
4. Run the integrated W1 scorer on that session, inspect its accepted/excluded
   attempts and report actual usage, latency and artifact paths here.
5. After Tom merges, freezes and tags the common release, run pod B's same-pod
   always-defer baselines followed by Sonnet sessions. Copy artifacts after each
   phase and verify pod termination. Move `reissue_200` only if Tom agrees and
   records the change.

Commands and spend-guard details are in [session_mode.md](session_mode.md).
Currently this checkout has no Anthropic/Prime credentials, no Prime CLI, and no
integrated frozen timing, final plans or release tag. These runtime prerequisites
remain open; successful mock tests do not complete W3's assignment.
