# Stage 2 results: where does LLM re-prompting hurt? (October 4, 2026)

A **diagnostic development run** (`llm_development`) following `docs/stage2_agent_prompt.md`. It is not a benchmark
score. It uses 13 tasks, 23 selected episodes per arm, one model and two policy seeds, so it shows direction only.
Raw episodes are in the Git-ignored `runs/stage2_remote/` (2.0 GB, 165 episodes, 495 MP4s).

## What was run

| Item | Value |
|---|---|
| Policy | NVIDIA GR00T N1.5, `checkpoint-120000`, frozen |
| Orchestrator | Claude Opus 5.5, effort `medium`, unchanged `configs/model-opus-5-5.dev.json` |
| Plain policy | 16 pool tasks x scenes 1000, 1001, 1002 x policy seeds 0, 1 = 96 episodes, privileged stop on success: **37 solved** |
| Selection | Per task, first 2 (scene, policy) pairs, ascending, where the plain policy succeeded: **23 pairs, 13 tasks** (rule fixed in `scripts/select_stage2.py` before the results existed; LoadDishwasher, PrepareCoffee and TurnOffStove had no success) |
| Arms on those 23 pairs | Opus 5.5; `always_defer` (submits the goal once, never intervenes, declares at the end of the budget); `reissue` (re-sends the goal every 100 steps) |
| Hardware | 1 x NVIDIA A10 24 GB (Lambda, 30 vCPUs, $1.29/hr, driver 570.148.08). The $0.54/hr A6000 was out of stock |
| Time and spend | Pod up about 4.8 h (setup and 46 GB download about 1.4 h, run 3.4 h). GPU about $6.2 by price and time; the team wallet shows no billing rows, so this is an estimate. Opus API about $2.3 at list prices (480k input, 17k output tokens) |
| Episodes | 165 attempted, 0 infrastructure errors, 0 predicate errors |

Preflight: the API probe for Opus 5.5 returned strict JSON on all 4 calls. On the pod, `doctor` passed and
`check_task_pool.py` built all 16 tasks. The untested `scripts/setup_nvidia_gl.sh` fallback made headless EGL work on
this Lambda image, which failed on October 2 without it.

## Plain policy (96 episodes)

| Task | Solved of 6 | | Task | Solved of 6 |
|---|---|---|---|---|
| CloseFridge | 6 | | PickPlaceCounterToStove | 5 |
| OpenCabinet | 6 | | ScrubCuttingBoard | 3 |
| PickPlaceCounterToCabinet | 4 | | KettleBoiling, OpenDrawer, RinseSinkBasin, TurnOnSinkFaucet, WashLettuce | 2 each |
| CloseToasterOvenDoor, CoffeeSetupMug, TurnOnMicrowave | 1 each | | LoadDishwasher, PrepareCoffee, TurnOffStove | 0 |

Each cell is 3 scenes x 2 policy seeds. Rates from six trials are rough.

## Outcomes on the 23 selected pairs

|  | Succeeded | Failed |
|---|---|---|
| Opus 5.5 | 16 | 7 (6 false completion, 1 step budget exhausted) |
| `always_defer` | 19 | 4 (4 false completion) |
| `reissue` | 16 | 7 (7 false completion) |

A failure here means the plain policy succeeded on the same scene and policy seed and the arm did not. Rejected
replies: **0 of 119** Opus calls (stage 1 Sonnet: 11 of 72). Opus used 143 output tokens per call on average, and
spent 529 of 1,777 wall seconds waiting on the API.

### Replay noise floor (`always_defer`)

`always_defer` should reproduce the plain run exactly. It first reached success at the same step as the plain run on
15 of 23 pairs, within 26 steps on 3 more, and did not reproduce it on 5: RinseSinkBasin 1002, ScrubCuttingBoard 1002
and TurnOnSinkFaucet 1001 succeeded at a very different step, and TurnOnSinkFaucet 1000 and WashLettuce 1002 policy 0
never succeeded. Replay is deterministic for most pairs but not all. **4 of 23 failures appear with no
intervention at all**: OpenDrawer 1000 p1 and TurnOnMicrowave reached success at the plain run's step and had lost
it by the end of the budget, and the two never-succeeded pairs above. Plain-policy "success" is therefore not stable
on those tasks, because the plain run stops at the first success while the other arms must still be in the success
state when they declare.

### Opus failures read against `always_defer`

| Pair | Opus | `always_defer` | Opus rewrote the prompt | What Opus did |
|---|---|---|---|---|
| OpenCabinet 1000 p1 | false completion | success | 0 times | Re-sent the same instruction twice, declared complete at step 550. The plain policy needed 769 |
| ScrubCuttingBoard 1002 p0 | false completion | success | 3 | Replaced the goal with "pick up the green sponge", then "move the gripper down to the green sponge...", then restored it and declared complete |
| TurnOnSinkFaucet 1001 p0 | false completion | success | 5 | Five reworded instructions in 600 steps ("push the faucet handle", "lift the handle up", "rotate it sideways"); the plain policy succeeded at step 171 |
| WashLettuce 1002 p1 | step budget exhausted | success | 6 | Rewrote at step 200 into stepwise instructions ("grasp the lettuce in the colander..."); the plain policy succeeded at step 1194 |
| TurnOnMicrowave 1001 p0 | false completion | **false completion** | 2 | Not attributable to Opus |
| TurnOnSinkFaucet 1000 p0 | false completion | **false completion** | 2 | Not attributable to Opus |
| WashLettuce 1002 p0 | false completion | **false completion** | 4 | Not attributable to Opus |

So of the 19 pairs where `always_defer` succeeded, Opus failed **4 (21%)**. Three of the four followed prompt
rewrites, one followed a premature `complete` with no rewrite. Seven of Opus's 23 failures sit on pairs where
Opus was not the only possible cause.

### What the intervention itself costs (`reissue`)

On the 19 pairs where `always_defer` succeeded, `reissue` failed on **6 (32%)**: OpenCabinet (both seeds),
OpenDrawer 1002, RinseSinkBasin 1000, ScrubCuttingBoard (both scenes). It never changes the wording, so this is the
cost of restarting the policy every 100 steps and discarding queued actions. It succeeded on 3 pairs where
`always_defer` did not (OpenDrawer 1000, TurnOnMicrowave, TurnOnSinkFaucet 1000), which fits restarts sometimes
recovering a success that did not persist. In this sample, blind interruption hurt more than Opus did.

### Opus behaviour

- Opus left the instruction alone in 12 of 23 episodes and succeeded in 11 of those 12.
- Opus rewrote the instruction in 11 episodes and succeeded in 5 of those 11. Three of the five reached success later
  than the plain run (CloseFridge at step 592 against 472, KettleBoiling 860 against 750 and 833 against 670); the
  other two reached it at the same step (OpenCabinet 349, ScrubCuttingBoard 542 against 543), but OpenCabinet then
  ran on to step 1040 before declaring. The rewrites cost steps even when they did not cost the task.
- Opus declared completion correctly where `always_defer` could not wait: OpenDrawer 1000 p1 succeeded for Opus and
  failed for `always_defer`, because Opus declared at the moment the drawer was open.

## Which task qualities go with harm

Descriptive only, 13 tasks.

| | Tasks | Pairs | Opus failures |
|---|---|---|---|
| No harm: short, single-object, completion visible | PickPlaceCounterToCabinet, PickPlaceCounterToStove, CloseToasterOvenDoor, CoffeeSetupMug, OpenDrawer, CloseFridge | 11 | 0 |
| Long tasks, harmless in this sample | KettleBoiling, RinseSinkBasin | 4 | 0 (Opus rewrote Kettle in both and finished late) |
| Harm | TurnOnSinkFaucet (2 of 2), WashLettuce (2 of 2), ScrubCuttingBoard (1 of 2), TurnOnMicrowave (1 of 1), OpenCabinet (1 of 2) | 9 | 6 |

The harmful tasks share one or more of: several stages (WashLettuce, ScrubCuttingBoard), a binary appliance state
that is hard to see from the cameras (faucet, microwave), a success that may not persist (faucet, microwave,
drawer), and a plain-policy success rate near one in three. Opus rewrote the prompt mostly where the plain policy
was slow to show progress. Whether that is the cause cannot be settled from 23 pairs.

## What this does and does not show

- It does **not** show that re-prompting is the main way Opus hurts. Four failures follow rewrites, and the
  premature declaration without a rewrite (OpenCabinet) is as real a failure. Judging completion is part of the
  task and is not separable from re-prompting in this harness.
- It does **not** give rates. 23 pairs share scenes across policy seeds, so they are not independent. Replay differs
  from the plain run on about one pair in five.
- Rescue was not measured: no pair where the plain policy failed was selected.
- The reply-format fix worked on this model: 0 of 119 rejected. This is one model, so it says nothing about others.
- Harm here is against one plain run per pair. A pair the plain policy solves 1 time in 6 (CloseToasterOvenDoor,
  CoffeeSetupMug, TurnOnMicrowave) counts as "leave alone" because it happened to succeed once.

## Implications for the simplified environment

1. **Premature completion is a separate failure from over-intervention** and should be scored separately. Tasks
   with a state the model cannot read from the images (faucet running, microwave on) produce it without any rewrite.
2. **Interruption has a price independent of the model.** `reissue` shows a policy restart is costly on tasks of
   about 1,000 steps. A controlled environment needs a tunable restart cost.
3. **Rewrites are mostly decompositions into steps.** The policy was trained on short instructions, and Opus's
   stepwise rewrites rarely helped. Whether the policy follows them at all needs a direct test.
4. **Short atomic tasks carry no information about harm.** A useful environment needs a long or multi-stage task
   and a completion state that is hard to see.

## Evidence and storage

Per episode kept: manifests, results, all JSONL records, API traces, keyframes, evaluator traces and three MP4s
(video every 5 control steps). The per-step PNG sequences were not copied back and were destroyed with the pod. The
pod was terminated and confirmed gone (`prime pods list`: 0 pods; SSH timed out); the watchdog was disarmed after.
Comparison tables are in `runs/stage2_remote/compare-*.txt`.
