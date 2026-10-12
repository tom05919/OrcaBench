# Stage 5 plan: how does the plain policy do on RoboCasa's unseen composite tasks? (October 12, 2026)

We have never run an unseen composite task. The October 1 design spec says the plain policy is "near zero" on them,
with no source. The benchmark direction now depends on that number: if a policy fails these tasks in ways a new
instruction could fix, they are where an orchestrator can be useful, and five of them can carry a time limit
(audit of October 12). This run measures plain policies only. It is a **diagnostic development run**
(`diagnostic_reference`): no model calls, no benchmark scores. The analysis below is fixed before any result exists.

## Policies

Both are GR00T N1.5 from the official RoboCasa365 release at the pinned revision, with the same code path:

| Backend | Checkpoint | Training on the 16 tasks |
|---|---|---|
| `groot` | `multitask_learning/checkpoint-120000` (stages 1-4) | **Probably trained on them.** RoboCasa's multitask setting uses all 50 target tasks, which include these 16. Its training log implies about 58M frames, which fits those 25,000 demonstrations. Not stated explicitly. |
| `groot_pretrain` | `foundation_model_learning/pretraining/checkpoint-80000` | **None.** Trained on the 300 pretraining tasks only; none of the 16 is among them (checked against the registry). |

## Tasks

The 16 `composite_unseen` tasks of `TARGET_TASKS` in the pinned `robocasa/utils/dataset_registry.py`:
ArrangeBreadBasket, ArrangeTea, BreadSelection, CategorizeCondiments, CuttingToolSelection, GarnishPancake,
GatherTableware, HeatKebabSandwich, MakeIceLemonade, PanTransfer, PortionHotDogs, RecycleBottlesByType,
SeparateFreezerRack, WaffleReheat, WashFruitColander, WeighIngredients. None has pretraining demonstrations.

- Instruction: the task's default native instruction (`use_novel_instructions` stays off).
- Step budget: the registry horizon, 1,200 to 4,350 steps (60 to 218 s).
- Scene split: `pretrain`, the same kitchens and object instances as every seen-task run in stages 1-4, so the task is
  the only thing that changes. RoboCasa's published numbers use the `test` split (the 30% checkpoint averages 30.8%
  there), so they need not match ours.

## Phases (one pod; `scripts/run_stage5.sh` runs two instances of `scripts/run_stage4.sh`, one per backend)

| Phase | What | Episodes |
|---|---|---|
| build | `scripts/check_task_pool.py` builds each task at scenes 1000-1001 and evaluates the checker and predicates; no stepping | none |
| plain | each backend, native instruction, privileged stop on success, 16 tasks x scenes 1000-1001 x policy seeds 0, 1 | 64 per backend, 128 total |

Two scenes rather than four: on stage 3's seen tasks, changing the scene changed the outcome about as often as
changing the policy seed (agreement 0.59 against 0.62), so two scenes by two seeds loses little. A task that does
not build at a scene is reported for that scene, never replaced.

**Added after the build check, before any episode result (October 12, 19:54 UTC).** RecycleBottlesByType at scene
1000 builds with the checker already true at step 0. An episode whose first success is at step 0 measures nothing,
so it is reported as "solved at start" and excluded from success counts. The scene is not replaced.

**Changed after the first 16 minutes, before any task beyond ArrangeBreadBasket had a result (October 12, 20:12
UTC).**
- **Pod:** no 12-core 48 GB pod was in stock. The run is on a RunPod A40 48 GB at $0.61/hr with a 7.65-core CPU quota.
- **Throughput:** about 19 steps/s across four streams, not the 45 estimated. At that rate the pretraining-only
  checkpoint needs about 4.9 hours if every episode runs to its limit.
- **Job order:** the remaining jobs were reordered so the five time-sensitive candidates run first. This is a
  priority order, not chosen by outcomes.
- **Deadline:** extended from 00:30 to 01:15 UTC, about $3.75 in total, within the $4 cap. Jobs left when the drivers'
  230-minute budget ends are run by a second driver instance with `--skip-existing`.

## Measurements (fixed before the results)

- Per task and backend: successes of 4, and the first-success step. Pooled per backend, with a Wilson 95% interval.
  The backend difference per task uses the same scenes and seeds, so it is paired on the scene, but not on the start
  state.
- **Subgoal progress** for the five time-sensitive candidates. Diagnostic predicates mirror conjuncts of each task's
  own `_check_success`, plus one gripper-distance signal for GarnishPancake. They are logged every step and never
  shown to any model:
  - MakeIceLemonade: lemon in cup, ice in cup.
  - SeparateFreezerRack: meat container on its rack, vegetable container on its rack.
  - PanTransfer: vegetables on plate, pan on stove, food untouched by the gripper.
  - PortionHotDogs: plate 1 portioned, plate 2 portioned, any item on a plate.
  - GarnishPancake: gripper within 10 cm of the strawberry, strawberry on pancake.

  For each subgoal: how many episodes ever reached it, and the first step.
- Reading, by task and backend:
  - **Leave-alone candidate:** success at least 3 of 4.
  - **Re-prompting candidate:** some subgoal reached in at least 2 of 4 episodes, with success at most 1 of 4. These
    go to the ceiling test, which gives correct step-by-step instructions through the diagnostic sequencer.
  - **Unlikely to be helped by re-prompting:** no success and no subgoal progress.

## Compute, guards and stops

- **Pod:** one Prime pod on team COS597, a 48 GB GPU with at least 12 vCPUs (RTX 6000 Ada, about $0.75/hr, was
  available). Three policy workers per backend, six streams in all.
- **Time and cost:** if every episode fails, the run is 332,400 steps. At about 45 steps/s that is about 2 hours of
  episodes, plus about 45 minutes of setup (two checkpoint downloads): about 3 hours and about $2.30.
- **Caps:** $4 GPU and a 5-hour deadline from pod creation. API $0: there are no model calls, and the Anthropic key is
  not copied to the pod.
- **Guards:**
  - The Mac launchd watchdog is armed, with `caffeinate`.
  - On the pod, the `backstop` mode of `scripts/pod_guard.sh` terminates at the deadline. It uses the team's Prime
    API key in a mode-600 file, never printed (user-approved October 12).
- **Data:** results are copied to the Mac after each phase as JSON, JSONL and MP4 (`VIDEO=10`), with no PNG frames.
  Sizes are checked first, because the Mac has about 7.8 GiB free.
- **Stops:** stop and report if a task fails to build at every scene, a policy worker dies, or two infrastructure
  errors occur in a row. Every attempted episode is kept.

## Code and contract changes

- **Task pool:** 16 task configs in `configs/tasks/` (`task_set` `composite_unseen`), with `CANDIDATE_TASKS` extended
  and the catalog tests updated.
- **Predicates:** five diagnostic predicate functions in `tasks/predicates.py`, with unit tests.
- **Second checkpoint:** backend `groot_pretrain`, pinned in `policy_worker.py`, `scripts/download_checkpoint.py` and
  `configs/sources.lock.json`. The pin is computed from the LFS hashes at the pinned revision, and the same method
  reproduces the existing `groot` pin. Both GR00T backends use one code path.
- **Driver:** `scripts/run_stage4.sh` takes `BACKEND` and `CHECKPOINT`, and requires the Anthropic key only for its
  `opus` phase.
- The pool and the hashed modules change the contract hash; this is recorded in `docs/decisions.md`. The runner,
  prompt, scoring and budgets do not change.
