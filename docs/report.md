# OrcaBench: is an LLM supervisor worth its time over a learned robot policy?

**Draft, October 13, 2026 (W1).** The question, related work, the benchmark and the development evidence are written.
**Section 5 (results) is filled on October 15-16 from `runs/final/score.json`** (`scripts/score_time.py`, the analysis
plan in `docs/final_experiment.md`). No number in section 5 may come from anywhere else.

## 1. Question

A learned robot policy (a vision-language-action model, VLA) acts fast but fails often. An LLM supervisor can watch it,
re-prompt it and decide when the task is done, which might make it more reliable, but every LLM call takes seconds.
OrcaBench asks whether a supervisor is smart enough to choose **when to interrupt** and **how often to check on** a
policy, so that the pair finishes tasks quickly and reliably.

- **One supervisor, several policies:** in one context it supervises several policies of different ability, and it
  is scored on whether it adapts: leaving a reliable policy alone and stepping in on an unreliable one.
- **The bar:** the best fixed supervision rule for each policy. A good fixed rate is a tuning setting, not
  intelligence.

## 2. Related work and what is new

Our October 1 review of about 25 recent papers is in `docs/benchmark_direction_research.md`. Claims of absence are
limited to that review.

- **Supervising a pretrained VLA with LLMs is studied:**
  - Embody (Anthropic, July 2026) compares models supervising a fixed VLA, including harmful overrides.
  - *What Matters in Orchestrating Robot Policies* (June 2026) studies termination, observations and memory.
  - VoLo (June 2026) measures monitoring and recovery.
  - RoboHarness (July 2026) routes between policies with a capability memory.
- **Execution mechanics change outcomes on their own:** PACE (June 2026) shows that changing chunk execution alone
  changes results. FailBench (September 2026) scores failure detection but not what a supervisory decision causes
  next. LIBERO-MAX (September 2026) pairs continuations from identical states.

**What OrcaBench adds, as far as that review found:**
1. **How much to supervise is the scored skill.** We score when to interrupt and how often to look, against the best
   fixed rule per policy, rather than whether the supervisor can rescue a failure.
2. **Supervision time counts on the task clock.** Each model's calibrated latency is charged per call, and fast but
   wrong scores zero.
3. **Adaptation is measured.** One supervisor meets several real policies of different ability in one context.
4. **Leaving the policy alone can be right,** so needless interruptions cost as much as missed problems.

## 3. The benchmark

### 3.1 Environment and interface

- **Simulator:** RoboCasa365 kitchens in MuJoCo, with frozen official checkpoints and no training (`AGENTS.md`).
- **Supervisor actions:** one JSON decision per call (`docs/protocol.md`):
  - `run_policy` with an optional new instruction and a number of steps (1-400 at 20 Hz), which sets when it looks
    again;
  - `complete`, which ends the episode. It succeeds only if the official RoboCasa checker is true at that moment.
- **Restarts:** any instruction, even an identical one, restarts the policy and discards its queued actions.
- **What the supervisor sees:** three camera views, keyframes from the last interval and proprioception. Never
  rewards, predicates, coordinates or subtask labels.
- **Physics** pauses while the model thinks; the time charge (3.5) puts that time back on the clock.

### 3.2 Tasks

- **Mix:** unseen composite tasks, where the plain policy usually fails, and trained tasks where it usually succeeds
  (`docs/direction.md`). On trained tasks alone, "never interrupt" always wins; on new tasks alone, "always
  interrupt" does. Only the mix makes *when* a skill.
- **Time stories:** five unseen tasks carry a natural deadline, for example ice melting once it leaves the bowl. It
  is enforced as a hidden limit in the score, not a change to the world (`docs/task_catalog.md`).
- **Selection:** the final set comes from `scripts/select_final.py`, by rules fixed before the data
  (`docs/final_experiment.md`).

### 3.3 Policies

Three checkpoints from the official RoboCasa365 release with clearly different ability, chosen from GR00T N1.5:
- multitask;
- post-trained on 10% or 30% of the unseen tasks' demonstrations;
- optionally π0.5.

They are measured by W2 (`docs/stage6_ladder.md`). The pretraining-only GR00T, which solved 0 of 62 unseen-task
episodes, is excluded.

### 3.4 Sessions

- **Content:** each session runs every (policy, task) cell of one scene in task blocks. Policies carry anonymous
  labels shuffled per session.
- **Experience:** before each episode the supervisor sees text records of the earlier episodes in the session:
  decisions and outcomes, nothing privileged (`docs/session_mode.md`, W3).
- **Same plans for every model** (`scripts/make_session_plans.py`).

### 3.5 Score

**value = success × max(0, 1 − charged seconds / deadline)** (`docs/time_score.md`)

- **Charged seconds:** robot time plus each response at the model's calibrated latency (median seconds per call,
  measured once under the final prompt and frozen).
- **Deadline:** the task's step budget.
- **Failures:** a false "done" or a timeout scores 0, so speed counts only when the task is done.
- **Story tasks:** they also fail if too much charged time passes after their trigger. The limit is set from the
  policies' own success times (`scripts/set_story_limits.py`).

### 3.6 Baselines and regret

- **Fixed rules:** scripted, with no LLM. Always-defer, and re-sending the instruction every 50, 100 or 200 steps,
  each crossed with "declare at step T". They are evaluated from per-step checker logs.
- **Regret** = the best fixed rule's value − the supervisor's value.
  - **Primary measure: paired held-out regret.** The fixed rule is applied to the always-defer run of the same scene
    and seed on the same machine, with T chosen without that scene.
  - **Adaptation:** the supervisor's value against the *pooled* rule (one declaration time for all policies) and
    against each policy's own rule.
  - **Learning:** regret in the second half of a session minus the first.

## 4. How the design was reached: development evidence

None of these are benchmark scores; each is a diagnostic or development run.

| Stage | What it showed | Consequence for the design |
|---|---|---|
| 1, Oct 2 (`docs/stage1_remote_results.md`) | Pipeline works; the plain multitask GR00T solved 14 of 32 scene pairs | |
| 2, Oct 4-5 (`docs/stage2_results.md`) | A validity audit withdrew the first harm claims: 6 of 23 pairs started from different scenes, and one episode had corrupted cameras | Start-state hash check (`--expect-state`), corrupted-frame guard, same-machine pairing |
| 3, Oct 5-9 (`docs/stage3_results.md`) | On 37 valid pairs where the plain policy succeeded, Opus 5.5 failed 14 of 34 against a 3% no-intervention noise floor. Left alone, it failed only by declaring 12-48 steps too early. Completion of hidden-state tasks is never recognized from images, and the checker lags visual completion by about 20 steps. On its successes, Opus stopped about halfway through the budget. | Supervision harms trained tasks; the LLM's real benefit is speed, so time must be scored |
| Simulator, Oct 9 (`docs/sim_results.md`) | Opus learns *when* to restart a stalled policy from past records; neither Opus nor Sonnet learns to *look more often* at an unreliable one. Its rescue assumption later proved about ten times too optimistic. | Simulator kept only as a development tool; check-in cadence becomes a scored measure |
| 4, Oct 11 (`docs/stage4_results.md`) | On 21 reproducible failures, fixed restarts rescued 4 (one episode each) and Opus rescued 1 of 19 | Rescue is rare; restart baselines as controls |
| 5, Oct 12 (`docs/stage5_results.md`) | On 16 unseen composite tasks, the multitask GR00T solved 8%, the pretraining-only 0%. Failures are mostly all or nothing; PortionHotDogs and GarnishPancake show partial progress. | Unseen tasks give "needs help" cases; ceiling test gates them; ability ladder from the 10% and 30% checkpoints |
| Score check, Oct 13 (`docs/time_score.md`) | On stage 3, the right declaration time ranges from 7 to 57 s by task. Against the held-out fixed rule, Opus's regret is 0.06 [-0.03, 0.16] with no call charge and 0.27 [0.20, 0.35] at its own 4.7 s. | The call charge decides whether supervision is worth it, which is the question asked |

## 5. Results (final runs; to be filled on October 15-16 from `runs/final/score.json`)

**5.1 Primary.** Paired held-out regret per model, with a 95% interval clustered by (task, scene), and the Opus −
Sonnet difference. A claim of "beats" or "loses to" the fixed rule only if the interval excludes 0.

| Model | Episodes | Mean value | Paired held-out regret [95%] |
|---|---|---|---|
| Opus 5.5 | | | |
| Sonnet 5.5 | | | |
| Opus − Sonnet | | | |

**5.2 Adaptation.** Per model and policy: the model's value, the policy's own best fixed rule, the pooled rule, and
learning (second-half minus first-half regret).

**5.3 Behaviour.** Per model and policy: success, false completions, declaration lag, calls, median interval,
restarts and rewrites. Story outcomes per story task.

**5.4 Fixed rules.** Best declaration time and value per (policy, task), no restart against the restart schedules
(unpaired; `reissue_50` and `reissue` on pod A, `reissue_200` on pod B).

## 6. Limitations

- **Scope:** one simulator, one model family of policies (two GR00T N1.5 checkpoints and π0.5) and two
  supervisors. Results are conditional on these.
- **Sample:** four scenes and one policy seed per cell. Per-task and per-policy numbers are descriptive.
- **Time:** the call charge is a calibrated constant, not live latency. Deadlines equal the task budgets, a stated
  choice; tighter deadlines would floor every supervisor at 0 (`docs/time_score.md`).
- **Calibration:** each model's charge is the median of one replay of each of the 27 observations of a single
  Opus-generated pilot session, with no uncertainty estimate. To keep the inputs identical, both models' replays
  stated the pilot's provisional 4.7 s charge, so Sonnet was timed while told a larger charge than its own 1.76 s.
- **Fixed rules:** they are chosen with knowledge of the other runs. The held-out version removes the hindsight on the
  paired scene, but a deployed fixed rule would need its own tuning data.
- **Pairing:** pairing holds only within one machine. Models on different pods are compared through paired regret,
  not raw values.
- **Rescue:** rescue was rare in development. If the ceiling test finds fewer than two fixable unseen tasks, the
  benchmark measures monitoring and declaring rather than rescue; section 5 must say which applied.
- **Visual judgement:** stories are hidden timers, so the cameras show nothing of them. Hidden-state completion
  (rinse, scrub, microwave) cannot be judged from images (stage 3).

## 7. Reproduction

- **Code and configs:** in this repository at tag `release-2026-10-14` (`docs/final_experiment.md`, "Freeze
  checklist").
- **Contract hash:** covers the task pool, prompt, hashed modules and GPU name.
- **Commands:** worker setup in `docs/compute.md`; the run in `docs/final_experiment.md`, "Run procedure"; scoring with
  `python3 scripts/score_time.py <pod roots> --output runs/final/score.json` (Python 3.11-3.12).
- **Raw episodes:** every attempted episode, failures and infrastructure errors included, is kept outside Git.
  Section 5 lists where.
