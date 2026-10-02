# Stage 1 remote test results (October 2, 2026)

First run of the intervention-judgement benchmark on a real GPU. This is a **pipeline check with a small sample**, not a measurement of Sonnet 5.5. Raw episodes (2.3 GB, 41 episodes, 123 MP4s) are in the Git-ignored `runs/stage1_remote/`; this file records what they show.

## What was run

| Step | What | Result |
|---|---|---|
| 1. Preflight | `doctor`, then `scripts/check_task_pool.py` builds all 16 pool tasks in the real simulator | All 16 build, horizons match, official checker and private subgoal predicates evaluate with no errors |
| 2. Plain policy | 16 tasks x scenes 1000 and 1001 x policy seed 0, privileged stop on success, video every 10 steps | 14 of 32 solved, 0 infrastructure errors, 0 predicate errors |
| 3. First Sonnet 5.5 episode | OpenDrawer, scene 1000, policy seed 5 (prompt v4, video every 10 steps) | Solved in 260 steps, 5 calls |
| 4. Sonnet 5.5 batch | 8 (task, scene) pairs at policy seed 0, prompt v5, video every step; each has a plain-policy episode with the same scene and policy seed | 2 solved, 6 not (below) |

Hardware: one RTX A6000 48 GB (Massed Compute, $0.54/hr), GR00T N1.5 checkpoint `checkpoint-120000`. GPU spend: $0.76 for this pod ($6.36 for an earlier abandoned pod, see `docs/compute.md`).

## Plain policy alone (step 2)

| Task | Type | Scene 1000 | Scene 1001 |
|---|---|---|---|
| CloseFridge | atomic | solved, 500 steps | solved, 400 steps |
| CloseToasterOvenDoor | atomic | solved, 200 steps | not solved |
| CoffeeSetupMug | atomic | solved, 200 steps | not solved |
| KettleBoiling | composite | solved, 800 steps | not solved |
| LoadDishwasher | composite | not solved | not solved |
| OpenCabinet | atomic | solved, 400 steps | solved, 300 steps |
| OpenDrawer | atomic | not solved | not solved |
| PickPlaceCounterToCabinet | atomic | solved, 200 steps | not solved |
| PickPlaceCounterToStove | atomic | solved, 200 steps | solved, 300 steps |
| PrepareCoffee | composite | not solved | not solved |
| RinseSinkBasin | composite | not solved | not solved |
| ScrubCuttingBoard | composite | solved, 700 steps | not solved |
| TurnOffStove | atomic | not solved | not solved |
| TurnOnMicrowave | atomic | not solved | solved, 300 steps |
| TurnOnSinkFaucet | atomic | solved, 300 steps | solved, 200 steps |
| WashLettuce | composite | not solved | not solved |

Six tasks were solved on one scene and not the other (same task, same wording, different starting layout), four on both, six on neither. This is a single policy seed per scene, so it is a glimpse of the spread, not a seed label. The first Sonnet episode solved OpenDrawer scene 1000 with policy seed 5 while the plain policy failed it with seed 0, so policy noise matters and real labels need several policy seeds.

## Sonnet 5.5 against the plain policy (step 4)

| Task | Scene | Plain policy | Sonnet | Steps used / budget | Calls | Rewrote or re-sent | Rejected replies |
|---|---|---|---|---|---|---|---|
| CloseFridge | 1000 | solved | success | 550 / 900 | 8 | 3 | 2 |
| KettleBoiling | 1000 | solved | step budget exhausted | 1500 / 1500 | 12 | 5 | 4 |
| PickPlaceCounterToStove | 1000 | solved | success | 200 / 600 | 5 | 0 | 1 |
| ScrubCuttingBoard | 1000 | solved | false completion | 300 / 1200 | 3 | 1 | 0 |
| KettleBoiling | 1001 | failed | step budget exhausted | 1500 / 1500 | 14 | 10 | 1 |
| OpenDrawer | 1000 | failed | step budget exhausted | 750 / 750 | 11 | 7 | 1 |
| PickPlaceCounterToCabinet | 1001 | failed | step budget exhausted | 750 / 750 | 9 | 7 | 1 |
| TurnOffStove | 1000 | failed | step budget exhausted | 750 / 750 | 10 | 7 | 1 |

|  | Sonnet solved | Sonnet failed |
|---|---|---|
| Plain policy solved | 2 | 2 (harm) |
| Plain policy failed | 0 (rescue) | 4 |

- **Harm, KettleBoiling 1000:** Sonnet started with the original instruction and left it running for 400 steps, then replaced it with its own "turn on the burner by twisting the knob" and kept rewriting it. The policy never followed those instructions. The plain policy finished the task on the original wording at step 794.
- **Harm, ScrubCuttingBoard 1000:** Sonnet rewrote the instruction at the start, let it run 300 steps and declared completion. The goal was not met (the plain policy needed 680 steps).
- **No rescue in four attempts.** On scenes the plain policy failed, Sonnet re-sent or rewrote the instruction in 31 of 44 calls (70%), against 8 of 28 (29%) on scenes the plain policy solved. Its rewrites were long and procedural (about 18 to 32 words for tasks whose original instruction is 4 to 18 words). A hypothesis, not tested here: this policy was trained on short imperative instructions, so long rewrites may be out of distribution.
- **Format failures:** 11 of 72 calls (15%) were rejected because the reply had prose or a code fence around the JSON. They cost a call but no physics, and the 100-call limit was never close (at most 14 calls used).

## Time

Robot time (simulated clock) was 10 to 75 s per episode; real time was 52 to 210 s, roughly 2.5 to 5 times longer. Waiting for Sonnet was 10 to 34 s per episode and policy inference 2 to 12 s; the rest is simulation, rendering, every-step video and scoring. Across the 8 episodes: 315 s robot time, 926 s real time, 171 s waiting for Sonnet, 282k input tokens and 4.9k output tokens.

## What this does and does not show

- It shows the pipeline works end to end on a GPU with a real model: the observation (with keyframe proprioception), the loop, scoring, both clocks, and the private predicates all ran without infrastructure or predicate errors.
- It shows both failure types the benchmark targets can occur (an unnecessary rewrite and a premature completion), once each.
- It does **not** show how often either happens, or that Sonnet is better or worse than another model. Eight episodes, one policy seed, no repeats.
- The "plain policy failed" label for these four scenes comes from one run each. Some may be scenes the policy usually solves.

## Decisions pending

1. Whether to record a rejected-reply count in every `result.json` (currently derivable only from `decisions.jsonl`).
2. Whether to keep strict reply parsing (current) or accept a JSON object surrounded by prose. Lenient parsing would change the contract.
3. Full screening (5 policy seeds x 10 scenes x 16 tasks, about 800 episodes at about 72 s, roughly 16 hours and $9).
