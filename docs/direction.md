# Benchmark direction (decided October 12, 2026)

This replaces the October 1 "intervention judgement" plan (`docs/superpowers/specs/2026-10-01-intervention-judgement-design.md`)
and the October 9 plan to use the abstract simulator as the benchmark (`docs/env_design.md`). Those documents stay as
history. Every decision here came from the discussion with Tom on October 11-12 and is logged in `docs/decisions.md`.

## What the benchmark measures

A learned robot policy (a VLA) is fast but unreliable. An LLM supervisor can raise reliability, but it is slow: every
call costs seconds. The benchmark measures whether a supervisor is smart enough to choose **when to interrupt and
re-prompt the policy, and how often to check on it**, so that the pair finishes tasks **quickly and reliably**.

- **Adaptation:** the right rate depends on the policy. One supervisor, in one context, supervises several policies
  of different ability. It is scored on whether it leaves a reliable policy alone and steps in on an unreliable one.
- **Baseline to beat:** the best *fixed* supervision rate is a tuning setting, not intelligence. The skill is changing
  the rate based on what the supervisor sees, for example looking more often when the robot is close to done or stuck.

## What the evidence says so far

| Evidence | Result | Where |
|---|---|---|
| Stage 3, real robot, pairs where the plain policy **succeeded** | Opus 5.5 turned 41% into failures, against a 3% no-intervention noise floor. Much of it was declaring "done" 12-48 steps early: completion is hard to see, and the checker lags about 20 steps. | `docs/stage3_results.md` |
| Stage 4, real robot, pairs where the plain policy **failed** | Opus rescued 1 of 19. Restarting with the same instruction rescued about 1 in 20, with no repeats. | `docs/stage4_results.md` |
| Opus's actual benefit | Speed: it stopped about halfway through the step budget, because the plain policy does not know when it is done. | `docs/stage3_results.md` |
| Abstract simulator | Opus learns *when* to restart a stalled policy from records; neither Opus nor Sonnet learns to *look more often* at an unreliable one. Its rescue assumption (0.85 per restart) is about ten times too optimistic, per stage 4. | `docs/sim_results.md` |
| Stage 5, real robot, plain policies on the 16 unseen composite tasks | The multitask GR00T solved 5 of 62 (8%; 36% on seen tasks); the pretraining-only GR00T solved 0 of 62. Failures are mostly all or nothing. PortionHotDogs and GarnishPancake show partial progress that a better instruction might finish. | `docs/stage5_results.md` |

**Reading:** on tasks the policy was trained on, the orchestrator has almost nothing to add and can only hurt. A
benchmark built only there would always reward "never interrupt".

## Decisions

1. **Environment first, policies second.** First decide what the environment must contain, then pick policies that
   fit it.
2. **Real RoboCasa tasks are the benchmark.** The abstract simulator (`src/robot_benchmark/sim/`) stays as a cheap
   development tool for prompts and scoring, with each profile fitted to a measured real policy, not invented.
3. **Mix the tasks.**
   - **Unseen composite tasks:** long tasks built from learned skills in new combinations, where a policy may need
     help.
   - **Trained tasks:** where leaving the policy alone is right.

   Only trained tasks rewards "never interrupt", and only new tasks rewards "always interrupt". The skill shows only
   with a mix, ideally within one session.
4. **Make time matter through scoring, not physics.** The harness pauses physics while the model thinks, so today an
   LLM call costs nothing on the task clock.
   - **Charge per call:** each call is charged a fixed number of seconds on the task clock, set from measured latency
     (an Opus call averaged 4.6 s in stage 3). It is not live wall-clock time, which varies with API load and would
     not reproduce.
   - **Deadline:** each task gets a deadline or a score that decays with total time, declared up front.
   - **Time-sensitive stories:** five unseen tasks carry a natural story (ice melts, food cools, frozen food thaws);
     see `docs/task_catalog.md`. Their timer is a hidden rule in the success check, invisible to the cameras and
     stated in the orchestrator's instruction. Some clocks start mid-task at a trigger event, for example when the ice
     leaves the bowl, so urgency changes within an episode.
   - **Not a disturbance:** a timer changes scoring, not the world, so it is not an "artificial disturbance" under
     `AGENTS.md`. It is a change to the evaluation contract, to be logged when implemented.
5. **Several policies of different ability, from the official RoboCasa365 checkpoints, with no training.**
   - **GR00T N1.5 ladder on the unseen tasks:** pretraining-only (0 demonstrations of them), 10% (50 per task), 30%
     (150 per task), and multitask (probably all 500).
   - **Other architectures:** π0.5 (backend written, never run); π0 and the diffusion policy need adapters.
   - **What the supervisor sees:** policies are anonymous and interleaved.
   - **Old rule dropped:** this ends the earlier "do not mix GR00T and π0.5 results" rule (`docs/roadmap.md`).
6. **Scoring.**
   - **Per policy:** compare against the best fixed supervision rule. Fixed rules include always-defer and
     restart-every-N.
   - **Separate measures:** interrupting decisions, check-in cadence, and declaring "done".
   - **Always reported:** success and total time (robot time plus charged LLM time).

## Rejected alternatives

- **Custom scenes and tasks built from scratch.** The policies were trained on RoboCasa365; new tasks would likely sit
  near zero success, we cannot train, and building and validating new task classes would take days.
- **Visible physical change (ice that actually melts).** It needs simulator changes and arguably counts as an
  artificial disturbance.
- **One real policy plus invented profiles.** Measuring adaptation needs several real policies.

## Open questions, in order

1. **Can re-prompting help on unseen tasks at all?** Run the ceiling test, where the diagnostic sequencer gives
   correct step-by-step instructions, on the tasks where stage 5 shows partial progress: first PortionHotDogs and
   GarnishPancake, then MakeIceLemonade, SeparateFreezerRack and PanTransfer with the multitask checkpoint. If perfect
   instructions cannot help, no LLM can.
2. **How much ability does each checkpoint have on the chosen tasks?** Measure the 10% and 30% GR00T checkpoints, and
   π0.5 if its backend runs. The pretraining-only checkpoint (0 of 62) is too weak to be an interesting supervised
   policy. Use at least four scenes on unseen tasks, because 4 of the multitask checkpoint's 5 stage 5 successes came
   from one scene.
3. **Time parameters:** the per-call time charge, the deadlines, and the trigger events. Implement them as a scoring
   layer with tests.
4. **Sample size** per (policy, task), and the session design: number of episodes and interleaving.
5. **Models to compare:** at least Opus 5.5 and Sonnet 5.5.
