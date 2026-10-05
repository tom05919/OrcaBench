# Stage 2 results: where does LLM re-prompting hurt? (October 4, 2026; corrected October 5)

A **diagnostic development run** (`llm_development`) following `docs/stage2_agent_prompt.md`. It is not a benchmark
score. It uses 13 tasks, 23 selected episodes per arm, one model and two policy seeds, so it shows direction only.
Raw episodes are in the Git-ignored `runs/stage2_remote/` (2.0 GB, 165 episodes, 495 MP4s).

**Correction (October 5).** The first version of this file reported that Opus failed on 4 of 19 pairs where
`always_defer` succeeded, mostly after prompt rewrites, and called premature completion a separate failure mode. A
validity audit of the saved records did not support that. Three of the four "clear" cases were on pairs whose
starting scene differed between arms or whose camera images were corrupted, and four of the six "false completions"
were not misjudgements of completion. The corrected findings are below; the original tables are kept where they
still hold and relabelled where they do not.

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

Each cell is 3 scenes x 2 policy seeds. Rates from six trials are rough. Across the A6000 (stage 1) and A10 (stage 2)
runs, the plain policy gave the same outcome on all 32 shared (task, scene, policy seed) combinations, with the same
first-success step on 26.

## Validity audit (added October 5)

Three problems in the saved records change how the arms can be compared.

1. **The scene seed does not always fix the scene.** Comparing the step-0 simulator state of the plain run with each
   arm on the same (task, scene seed, policy seed): all four arms started from an identical state on **17 of 23
   pairs**. On 4 pairs at least one arm got a different kitchen (RinseSinkBasin 1002 p0: layouts 29 and 41;
   ScrubCuttingBoard 1002 p0: 34 and 41; WashLettuce 1002 p0: 41 and 48, and p1: 48 and a different layout). On 2
   pairs (TurnOnSinkFaucet 1000 and 1001) the layout was the same but the initial state differed at about 1e-14 and
   the rollouts diverged. Across all 206 stage 1 and 2 episodes, 3 of 48 (task, scene) combinations produced more than
   one layout, all at scene 1002 on composite tasks. The cause is not yet established (probably randomness in layout
   selection that the seed does not control); the adapter passes the seed to `gym.make` and `reset` and nothing else.
2. **One episode had corrupted camera images.** ScrubCuttingBoard 1002 p0 (Opus): from about step 335 every camera
   returned the same noise image, in the saved model-visible frames and in the MP4s (514 of 717 video frames). The
   policy's own input was almost certainly corrupted too. Physics was normal (no NaN, no blow-up), so this is a
   rendering fault. It is the only affected episode of 206 in stages 1 and 2. The harness did not flag it: it was
   recorded as an ordinary `false_completion`.
3. **"False completion" mixes two different things.** Opus's recorded thinking summaries show that four of its six
   false completions were declared with 1 to 10 steps left, after the goal was never reached ("no water visible and
   only one step left… I'll just go with complete"). That is giving up at the end of the budget, not misjudging
   completion. Only OpenCabinet 1000 p1 (declared at step 550 of 1,050) and WashLettuce 1002 p0 (step 1,150 of 1,650)
   were mid-episode declarations.

## Outcomes

|  | All 23 pairs, failed | The 17 pairs with identical starting scenes, failed |
|---|---|---|
| Opus 5.5 | 7 | 2 |
| `always_defer` | 4 | 2 |
| `reissue` | 7 | 5 |

A failure means the plain policy succeeded on the same scene and policy seed and the arm did not. Rejected replies:
**0 of 119** Opus calls (stage 1 Sonnet: 11 of 72). Opus used 143 output tokens per call on average, and spent 529 of
1,777 wall seconds waiting on the API.

### The 17 valid pairs

- **Opus failed 2:** OpenCabinet 1000 p1 (declared complete at step 550 while the checker was false; it had only
  re-sent the same instruction) and TurnOnMicrowave 1001 (re-prompted at step 290,
  ten steps before the plain policy succeeded at step 300, then never succeeded and declared at the last step).
- **`always_defer` failed 2:** OpenDrawer 1000 p1 and TurnOnMicrowave 1001. Both reached success at the plain run's
  step and had lost it by the end of the budget. So even a policy that is left alone does not always stay in the
  success state, and the plain run, which stops at the first success, hides that.
- **`reissue` failed 5:** OpenCabinet (both policy seeds), OpenDrawer 1002, RinseSinkBasin 1000, ScrubCuttingBoard
  1000. It never changes the wording, so this is the cost of restarting the policy every 100 steps. On these 17 pairs
  `reissue` failed 5 times where `always_defer` succeeded and succeeded 2 times where `always_defer` failed (a sign
  test on 5 against 2 gives p of about 0.45). Suggestive, not distinguishable from noise at this size.
- **Opus against `always_defer`:** failed where `always_defer` succeeded on 1 pair, succeeded where it failed on 1
  (OpenDrawer 1000 p1, where Opus declared at the moment the drawer was open). **No Opus-specific harm is established.**

### The 6 pairs with a different starting state

Opus failed 5 of these and succeeded on 1, but none can be attributed, because the arms were not on the same scene
or, for ScrubCuttingBoard 1002, saw corrupted images:

| Pair | Why invalid | Opus | What Opus did |
|---|---|---|---|
| ScrubCuttingBoard 1002 p0 | corrupted images from step 335 | false completion at step 1,190 | Rewrote the goal into "pick up the green sponge" and finer steps while the views were static; declared at the end |
| TurnOnSinkFaucet 1001 p0 | initial state differs | false completion at step 599 | Re-prompted at step 160 (the plain run succeeded at 171), five rewrites in all; declared with 1 step left |
| TurnOnSinkFaucet 1000 p0 | initial state differs | false completion at step 595 | Re-prompted at step 250; declared with 5 steps left |
| WashLettuce 1002 p0 | other arms had another layout | false completion at step 1,150 | Rewrote at step 200; later declared while the lettuce looked "close but not perfectly aligned" |
| WashLettuce 1002 p1 | Opus had another layout | step budget exhausted | Rewrote at step 200 into stepwise instructions and kept rewriting |
| RinseSinkBasin 1002 p0 | Opus and `always_defer` had another layout | success | none |

### Opus behaviour (all 23 pairs, descriptive)

- Opus left the instruction alone in 12 of 23 episodes and succeeded in 11 of those 12.
- Opus rewrote the instruction in 11 episodes and succeeded in 5 of those 11. Three of the five reached success later
  than the plain run (CloseFridge at step 592 against 472, KettleBoiling 860 against 750 and 833 against 670); the
  other two reached it at the same step (OpenCabinet 349, ScrubCuttingBoard 542 against 543), but OpenCabinet then
  ran on to step 1,040 before declaring. The rewrites cost steps even when they did not cost the task.
- Its thinking summaries cite the same cues when it intervenes: the gripper "hovering near" the target with nothing
  visibly changing (faucet, microwave, scrub), "no water visible", and the number of steps left. It also reserves a
  decision for the end ("keep a decision in reserve"), which is why so many failures end in a `complete` at the last
  step.
- On slow tasks Opus varied: it rewrote the goal at step 200 on both WashLettuce pairs (plain success at 941 and
  1,194) but never changed it on RinseSinkBasin (741 and 1,028), where it succeeded.

## What this does and does not show

- It does **not** show that Opus's interrupts or rewrites hurt. On the 17 valid pairs Opus and `always_defer` each
  failed twice, once on the same pair. The earlier "4 clear harms" were on invalid pairs.
- It gives **suggestive** evidence that blind interruption costs something: restarting the policy every 100 steps
  failed on 5 valid pairs where leaving it alone succeeded.
- It shows the harness cannot yet guarantee that two runs of one (task, scene seed) share a world, or that every
  camera frame is valid. Until it can, paired comparisons on those scenes are unreliable.
- It does **not** give rates. 17 valid pairs share scenes across policy seeds, so they are not independent.
- Rescue was not measured: no pair where the plain policy failed was selected.
- The reply-format fix worked on this model: 0 of 119 rejected. This is one model, so it says nothing about others.
- Harm is judged against one plain run per pair. A pair the plain policy solves 1 time in 6 (CloseToasterOvenDoor,
  CoffeeSetupMug, TurnOnMicrowave) counts as "leave alone" because it happened to succeed once.
- The plain reference stops at the first success, but the other arms must still be in the success state when they
  declare. Two of the `always_defer` failures are that mismatch, not intervention.

## Implications

1. **Fix validity before measuring harm.** Make scene generation reproducible (or exclude and flag scenes that are
   not), guard against corrupted frames, and only pair episodes whose starting state matches.
2. **Interruption has a price independent of the model.** `reissue` is the clearest signal in this run. A controlled
   environment needs a tunable restart cost.
3. **The step-budget convention creates end-of-episode behaviour.** A model that keeps a decision in reserve will
   declare `complete` at the last step; this should be scored separately from misjudging completion.
4. **Progress visibility looks relevant but is untested.** Opus intervenes where nothing visibly changes, and the plain
   policy sometimes succeeds a few steps later. Whether that is the mechanism needs direct tests.

## Evidence and storage

Per episode kept: manifests, results, all JSONL records, API traces (with thinking summaries), keyframes, evaluator
traces and three MP4s (video every 5 control steps). The per-step PNG sequences were not copied back and were
destroyed with the pod. The pod was terminated and confirmed gone (`prime pods list`: 0 pods; SSH timed out); the
watchdog was disarmed after. Comparison tables are in `runs/stage2_remote/compare-*.txt`.
