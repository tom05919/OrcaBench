# Stage 3 results: does the LLM's intervention hurt, and where? (October 5-9, 2026)

A **diagnostic development run** (`llm_development`). It follows `docs/stage3_plan.md`, which fixed the selection
rules and analysis before any result existed. Nothing here is a benchmark score. One model (Opus 5.5), one policy
(GR00T N1.5), one machine, 13 tasks and 37 pairs: direction and mechanism, not rates to quote.

## What was run, and what was lost

Machine: one RunPod RTX A6000 container (8 vCPUs listed, 13.6-core quota), five policy workers sharing the GPU.

| Step | Episodes kept | Notes |
|---|---|---|
| Plain policy, 13 tasks x scenes 1000-1005 x policy seeds 0, 1 | 157 (68 solved) | 1 ended as an infrastructure error: the new frame guard caught a static-noise render at step 819 |
| Always-defer on 53 candidate pairs (plain successes, cap 6 per task) | 82 folders: 45 usable successes or failures, 28 `scene mismatch`, 5 killed mid-run by a restart | The start-state guard ended mismatched scenes before any work |
| **Confirmed pairs** (plain success, defer success, identical start state) | 37 pairs, 13 tasks | CloseFridge 4, toaster 2, mug 2, kettle 2, OpenCabinet 4, OpenDrawer 4, two pick-and-place 4 each, rinse 2, scrub 2, microwave 1, faucet 3, WashLettuce 3 |
| Second always-defer on the 37 pairs (noise floor) | 40 (4 `scene mismatch`) | |
| Opus 5.5, one episode per pair | 41 (7 `scene mismatch`) | 34 usable |

**Lost:** the Sonnet, reissue, Opus-repeat, decision-replay, interruption-sweep and rescue arms. They ran on the pod
after the Opus arm and were never copied back; the pod outlived its watchdog (the Mac slept) and was terminated with
its disk. The incident and its mitigations are in `docs/compute.md`. Spend: about $7.5 of GPU for 13.75 pod-hours
(cap was $5) and about $9 of API.

## Validity findings that changed the design

- **The scene seed does not always fix the scene.** In stage 2, 6 of 23 pairs started from different worlds. A probe
  showed it for the sink-related tasks at scene 1002 and for TurnOnSinkFaucet 1000 and 1001, while three controls were
  identical in every attempt. Fixing `PYTHONHASHSEED`, pinning BLAS to one thread, and seeding the global generators
  each left it unchanged; the cause is open. Stage 3 therefore passes the plain run's step-0 state hash with
  `--expect-state`, and an episode that builds a different scene ends before any model call.
- **Start states are machine-specific, but the worlds are not.** The RunPod host built the same layout and style as
  the Lambda A10 on all 39 shared (task, scene) combinations and an identical start-state hash on none. Stage 2's
  references therefore could not pair with stage 3 episodes, and every reference was rerun on this machine.
- **Renderer faults are rare but real.** Static noise appeared in 1 of 206 stage 1 and 2 episodes and 1 of 157 stage 3
  plain episodes, both sudden and full-frame. The guard (adjacent-pixel difference above 20; clean frames top out at
  12.4) ends such an episode as an infrastructure error.
- **Replay is mostly deterministic on one machine** (15 of 23 stage 2 pairs identical to the last step; the rest
  diverged at floating-point level), which is why a second no-intervention run is the right noise floor.

## Primary result: Opus against the no-intervention noise floor

On the 37 confirmed pairs, an always-defer run that never intervenes is the baseline a deployed VLA could actually
use (no oracle stop): it declares `complete` at the budget end.

| Arm | Usable | Failed | Outcomes |
|---|---|---|---|
| always-defer, first run (the confirming run) | 37 | 0 | by construction |
| always-defer, second run (noise floor) | 36 | **1 (3%)** | 1 success lost before the end |
| Opus 5.5 | 34 | **14 (41%)** | 7 declared early, 5 never achieved, 2 lost after achieving |

By task, Opus failed: CloseFridge 1 of 4, mug 1 of 2, **kettle 2 of 2**, OpenCabinet 2 of 4, OpenDrawer 1 of 4, the two
pick-and-place tasks 1 of 4 each, rinse 1 of 2, scrub 1 of 1, microwave 1 of 1, faucet 1 of 2, WashLettuce 1 of 2;
toaster 0 of 2. The 14 failures are far above the 3% noise floor in every task family, so this is not a few bad tasks.

## Where the failures come from

Using the logs alone (outcome, prompt changes, declaration step against the always-defer run's first success):

| What Opus did | Failed / episodes | Failure kinds |
|---|---|---|
| Left the instruction alone | 5 / 19 | all 5 **declared early**, 12 to 48 steps before the checker turned true |
| Restated it unchanged | 0 / 1 | |
| **Rewrote it** | **9 / 14** | 5 never achieved the goal, 2 achieved then lost it, 2 declared early |

- **Early declaration with no intervention** (OpenDrawer, OpenCabinet, CoffeeSetupMug, two pick-and-place pairs): the
  task looked finished at Opus's observation and the checker's hidden post-condition landed 12 to 48 steps later.
  Successful episodes declared 10 to 80 steps after the checker turned true, so success against failure is the phase
  of Opus's observation boundary relative to the checker, which makes it partly luck.
- **Rewriting.** Opus never failed to achieve a task, or lost one, without rewriting the instruction first. Whether
  the new wording or the restart does the damage is **not separable from these logs**: every rewrite also restarts the
  policy, and the one restate-only episode succeeded. That was the job of the lost replays and reissue baseline.
- **Achieved but not recognized.** OpenCabinet, ScrubCuttingBoard and TurnOnMicrowave reached the checker's success
  (steps 347, 432, 270) and Opus kept intervening until it lost the success or ran out of budget.
- **Why it rewrote** (123 thinking notes coded by Sonnet 5.5): rewrites are mostly "try better wording" (21 of 48),
  then "looks stalled" (7), "on track anyway" (7), "cannot tell progress" (7), "steps running out" (4). `complete` was
  judged done in 23 of 31 cases and pressured by the budget in 7. Opus explored wording even when it saw progress.
- **What Opus buys.** When it succeeded it stopped on average 54% earlier than the step budget (median 62%).

## Can the model tell that the task is done? (offline probes, no GPU)

Frames cut from stored always-defer videos, truth from the checker, only the goal text shown to the model. 115 calls
over 23 stage 2 episodes (Opus 76% accurate, Sonnet 69%; the same tasks fail for both) and a window of 454 Opus calls
at steps -60 to +60 around the checker's first success on 35 stage 3 episodes.

- **Visible-state tasks are recognized:** CloseFridge, toaster door, mug, pick-and-place, OpenDrawer, faucet.
- **Hidden or cumulative state is not.** RinseSinkBasin, ScrubCuttingBoard and TurnOnMicrowave: the model says
  "complete" 0.00 of the time both before and after the checker is true. KettleBoiling: 0.00 before, 0.83 after (the
  burner flame is not visible until late). WashLettuce: "complete" about 0.9 of the time throughout (false positives).
  OpenCabinet and OpenDrawer say "complete" 0.76 and 0.50 before the checker, so they are early.
- **The checker lags visual completion by about 20 steps.** P("complete") is 0.26 to 0.34 earlier than 20 steps
  before the checker, 0.66 in the last 20 steps, and about 0.70 after. Overall false negatives 36%, false positives 11%.

## The VLA's side (plain episodes, 12 per task)

Success probability 0.17 to 1.00 by task; median first-success step 190 to 1,066; spread within a task (CV) 0.06 to
0.37. OpenCabinet 12 of 12; pick-and-place and OpenDrawer 0.67 to 0.75; CloseFridge 0.58; faucet, scrub, WashLettuce
0.33; kettle, rinse, toaster, mug, microwave 0.17 to 0.25. A supervisor call costs $0.019 (4,000 input and 143 output
tokens, 4.6 s); an Opus episode costs $0.089 and 4.7 calls.

## What this does and does not show

- It **does** show that on valid, same-machine pairs an Opus supervisor fails 41% against a 3% no-intervention noise
  floor, that none of its failures to achieve a task occurred without a rewrite, and that a large share of its
  failures are completion-timing and completion-legibility problems rather than control problems.
- It does **not** attribute the rewrite harm to wording or restarts, show that Sonnet or other models behave the same
  inside the loop, give harm against interruption frequency, or show whether an LLM ever rescues a task the plain
  policy fails. All of those needed the lost arms.
- 37 pairs share scenes across policy seeds and tasks differ in count (microwave 1, toaster 2, pick-and-place 4), so
  per-task rates are anecdotes. Opus ran once per pair, so its own sampling variance is untested.
- The no-intervention baseline spends the whole budget; Opus's 54% saving is real but is a trade against a 41% failure
  rate, and the benchmark's success rule makes any early declaration a failure.
