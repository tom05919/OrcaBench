# Design brief: a simplified environment for LLM supervision of a learned robot policy

Written October 9, 2026, for a design decision. The user is away and will not answer questions. Decide from this
brief and the repository; state assumptions instead of asking.

## The goal (the user's words, condensed)

Test whether an LLM agent is smart enough to know **(1) when to interrupt or let a VLA keep working, and (2) how often
to observe it, learned in context from the VLA's observed performance.** The agent is much more expensive than the VLA,
so the question is how often to call it to maximize performance and minimize cost. The plan: find which real tasks make
interrupting hurt, then construct a **basic environment from the qualities of those tasks**, in which the same agent,
in one context window, supervises **different VLAs of varying ability** and shows whether it learns how often to
observe and interrupt. A simple environment is wanted because it separates the agent's ability from the VLA's and lets
us **control how much the VLA messes up**. Deliverable at the end: **the basic building blocks of this environment.**
Data must be low-noise, and cost minimal. Major design decisions go to you.

## What the real harness looks like (RoboCasa + frozen NVIDIA GR00T N1.5, repository `/Users/tomwang/robot_benchmark`)

- The agent sees three camera frames, four keyframes from the last interval, and proprioception; it answers with
  `run_policy(prompt?, steps 1..400)` or `complete`. A call that supplies any prompt, even the same text, restarts the
  policy and discards queued actions; omitting the prompt continues. 20 steps = 1 s of robot time.
- Success needs `complete` while the official checker is true. An episode ends at a step budget (450 to 1,800 steps).
  The checker is stricter than the instruction (hidden post-conditions: gripper retreat, door angle 0.9, cumulative
  contact time). The agent never sees the checker.
- Code: `src/robot_benchmark/{runner,baselines,contracts}.py`, `docs/protocol.md`, `docs/stage2_results.md`,
  `docs/stage3_plan.md`, `docs/decisions.md`.

## Evidence so far (all from real runs; one model, Opus 5.5, unless stated)

**Valid paired set.** 37 (task, scene, policy-seed) pairs over 13 tasks where the plain policy and an always-defer run
(never intervene, declare `complete` at the budget end) both succeeded from the identical starting state.

| Arm | Failures |
|---|---|
| second always-defer run (noise floor) | 1 of 36 (a success that was lost) |
| Opus 5.5 supervising | 14 of 34 usable (41%) |

- Opus's 14 failures: 5 declared `complete` 12 to 48 steps **before** the checker turned true, with **no intervention**
  (visually done, checker not yet); 9 involved rewriting the instruction (5 never achieved the goal, 2 achieved then
  lost it, 2 declared early). Left alone: 5 of 19 failed. Rewrote the instruction: 9 of 14 failed. Restated only: 0 of 1.
  Opus never failed to achieve a task, or lost one, without rewriting.
- Reasons Opus gave for its decisions (123 thinking notes, coded by a second model): rewrites are mostly "try better
  wording" (21 of 48), then "looks stalled" (7), "on track anyway" (7), "cannot tell progress" (7), "steps running
  out" (4). `complete` calls: "judges it done" 23, "budget pressure" 7.
- When Opus succeeded it stopped on average **54% earlier** than the step budget; always-defer never stops early.
- Supervisor cost: **$0.019 per call** (4,000 input and 143 output tokens), 4.6 s per call, 4.7 calls per episode,
  **$0.089 per episode**. Robot time is the other cost.

**Completion legibility (offline probe: frames from stored videos, truth from the checker, 115 + 454 Opus calls; Sonnet
agrees on the stage 2 set).** The model recognizes completion when the finished state is a visible change (CloseFridge,
toaster door, pick-and-place, drawer, faucet) and fails when it depends on hidden or cumulative state:
RinseSinkBasin, ScrubCuttingBoard and TurnOnMicrowave score 0.00 "complete" before and after the checker turns true;
KettleBoiling (burner flame not visible) 0.00 before, 0.83 after; WashLettuce says "complete" about 0.9 of the time
throughout (false positives). Around the checker's first success the model's "complete" rate is 0.26 to 0.34 more than
20 steps before, **0.66 in the last 20 steps, and about 0.7 after**: visual completion leads the checker by about
20 steps (1 s). Overall false-negative rate 36%, false-positive 11%.

**The VLA (13 tasks, 12 plain episodes each, one host).** Success probability per task ranges 0.17 to 1.00 (OpenCabinet
1.00; pick-and-place 0.75; OpenDrawer 0.67; CloseFridge 0.58; faucet, scrub, washing 0.33; kettle, rinse, toaster, mug,
microwave 0.17). Median step of first success 190 to 1,066 depending on the task; spread within a task (CV) 0.06 to
0.37, so completion time is variable, and the policy often hovers visibly before acting. Success can be lost (1 of 36).

**Stage 2, valid pairs only (17):** restarting the policy every 100 steps (reissue) failed 5 times, always-defer 2,
Opus 2. Suggestive of a restart cost; not significant.

**Not measured (lost with a pod that outlived its watchdog):** whether Opus's harm comes from the new wording or from the
restart itself (decision replays), the reissue baseline on the stage 3 pairs, Sonnet inside the supervision loop,
harm against interruption interval, whether the LLM ever succeeds where the plain policy fails. A lean replacement run
(about 4 pod-hours, about $2.2 GPU plus about $3 API) would re-measure restart cost and wording sensitivity.

**Validity facts that shape any experiment:** the scene seed does not always fix the scene (3 of 48 task-scene
combinations gave two layouts); start states are host-specific at floating-point level; one episode in about 360 had a
corrupted camera frame (now guarded); Opus's own sampling adds variance, so single runs are noisy.

## Budget and constraints

Remaining API budget about $5 (about $10 spent of a $15 cap). GPU: a pod costs $0.54/hr, and about $9.7 total GPU will
already have been spent if one more run is done; prefer not to. The user said to rent GPUs and use the API as needed
but to minimize cost. The Mac may sleep while a pod runs, so any pod must be short.

## Decisions requested

1. **Environment.** What should the simplified environment be: an abstract CPU simulator with a parametric VLA and
   latent task process calibrated to the data above, simplified real-robot tasks, or a hybrid? List its **building
   blocks** with parameters, what each is calibrated to, what the LLM observes (modality, legibility, ambiguity), and
   how the agent interface stays identical to the real harness (`run_policy(prompt?, steps)`, `complete`) so results
   transfer. Say which real-task qualities it must reproduce.
2. **Experiment protocol** for goal parts (1) and (2): how to present several VLAs of different ability to one agent in
   one context window, the VLA ability levels, tasks, number of episodes and ordering, the baselines (always-defer,
   fixed-interval observers, an oracle or hazard-optimal observer), metrics (success, robot time, calls, dollar cost,
   regret against the best fixed policy), analysis, and how to **minimize noise** (common random numbers, paired
   seeds, repeats, temperature) within about $5 of API spend.
3. **Further real-robot measurement.** Is the lean GPU run worth it for calibrating the restart-cost and wording
   dials, or should the environment take them as parameters with stated assumptions? If worth it, the minimal set.

## What to deliver

Write `docs/env_design.md` with your decisions, rationale, the building-block specification and the experiment
protocol with a cost estimate. Do not run GPU jobs or spend API money; reading local data under `runs/` and `docs/` is
fine. Return a summary of at most 400 words with the decisions in order.
