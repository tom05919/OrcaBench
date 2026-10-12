# Stage 5 results: the plain policy on RoboCasa's unseen composite tasks (October 12, 2026)

A **diagnostic development run** (`diagnostic_reference`), following `docs/stage5_plan.md`. Its rules were fixed before
the results, and the two changes made during the run are recorded there. There were no model calls and nothing here is
a benchmark score: two GR00T N1.5 checkpoints, 16 tasks, 2 scenes and 2 policy seeds, one machine. These are counts,
not rates to quote.

- **Raw data:** Git-ignored in `runs/stage5/` on Tom's Mac (4.1 GB, 128 episodes, MP4s and per-interval frames).
  The per-task table is `runs/stage5/analysis.json`, from `scripts/analyze_stage5.py`.
- **Machine:** one RunPod A40 48 GB via Prime on team COS597, 7.65-core CPU quota, two policy workers per checkpoint.
  Runs went from 19:54 to 23:20 UTC; the pod was terminated by hand at 23:30 UTC.
- **Cost:** $2.72 of GPU (team wallet $227.96 to $225.24), including a duplicate pod created by mistake and terminated
  after about 10 seconds. No API.

## Result

| | Multitask GR00T (`groot`, `multitask_learning/checkpoint-120000`) | Pretraining-only GR00T (`groot_pretrain`, `foundation_model_learning/pretraining/checkpoint-80000`) |
|---|---|---|
| Solved, unseen tasks | **5 of 62 (8%; 95% interval 3-17%)** | **0 of 62 (0-6%)** |
| For scale: same checkpoint, seen tasks (stage 4 plain phase) | 46 of 128 (36%) | not run |
| Infrastructure errors | 0 | 0 |
| Solved at start (excluded) | 2 (RecycleBottlesByType, scene 1000) | 2 (same) |

Multitask successes:
- GarnishPancake: 2 of 4.
- ArrangeTea, MakeIceLemonade and SeparateFreezerRack: 1 of 4 each.
- All 12 other tasks: 0.
- Successes were slow, at steps 1,237 to 1,856 (62-93 s). Four of the five came from scene 1001, so scene matters more
  here than it did on seen tasks.

## Partial progress on the five time-sensitive candidates

Episodes (of 4) that ever reached each subgoal:

| Task | Multitask GR00T | Pretraining-only GR00T |
|---|---|---|
| GarnishPancake | strawberry reached 4, on pancake 2 (both successes) | strawberry reached 3, on pancake 0 |
| MakeIceLemonade | lemon in cup 1, ice in cup 1 (the success) | 0, 0 |
| SeparateFreezerRack | meat on rack 1, vegetables on rack 1 (the success) | 0, 0 |
| PanTransfer | vegetables on plate 1, but never success | 0 |
| PortionHotDogs | some item on a plate 4, a correct plate 0 | some item on a plate 3, a correct plate 0 |

"Strawberry reached" means the gripper came within 10 cm. It is a weaker signal than a checker conjunct.

## What this shows

- **"Near zero" holds, now measured.** The pretraining-only checkpoint, which has never seen these tasks, solved none
  of 62. The multitask checkpoint solved 8%, against 36% on seen tasks. Whether the multitask checkpoint was trained on
  these tasks is still unresolved: an 8% rate says that training, if it happened, did not carry over to these kitchens.
- **Failures are mostly all or nothing.** Both checkpoints usually fail before the first subgoal. In MakeIceLemonade
  and SeparateFreezerRack, the only episodes that reached a subgoal were the successes.
- **Two exceptions look like direction failures**, the kind a better instruction could fix:
  - **PortionHotDogs:** both checkpoints put food on plates but never one bun and one sausage per plate.
  - **GarnishPancake:** both reach the strawberry, and only the multitask checkpoint sometimes places it.

  These are the first targets for the ceiling test, which gives correct step-by-step instructions through the
  diagnostic sequencer.
- **For the benchmark:**
  - The pretraining-only checkpoint is too weak to be an interesting supervised policy. It fails almost everything,
    with little partial progress.
  - The multitask checkpoint on unseen tasks gives "needs help" situations with some partial progress.
  - The published 30% checkpoint averages 31% on these tasks, on RoboCasa's `test` split, which is not comparable to
    our `pretrain` split. The 10% and 30% checkpoints are therefore the obvious way to fill the ability ladder
    (`docs/work_split.md`, W2).
- **Scene matters.** 4 of the multitask checkpoint's 5 successes came from scene 1001. Two scenes are too few to
  separate task difficulty from kitchen layout on these tasks, so later runs should use more scenes for the unseen
  tasks.

## What this does not show

- Whether re-prompting can rescue any of these failures. That is the ceiling test, then LLM runs.
- Rates by task: 4 episodes per task, 2 scenes.
- Anything about the 10% and 30% checkpoints, π0.5, or RoboCasa's `target` and `test` kitchens.

## Run notes

- **Build check:** all 16 tasks build at scenes 1000-1001. RecycleBottlesByType at scene 1000 starts with the checker
  already true; it was reported and excluded by a rule written before any episode ran.
- **Throughput:** about 19 steps/s in total on the 7.65-core quota, CPU-bound with the GPU about 6-30% used. The plan's
  45 steps/s assumed 12 or more cores. The five time-sensitive tasks were moved to the front of the job order, and the
  deadline was extended within the $4 cap; in the end the run finished well before the deadline.
- **Procedure:**
  - Setup took 36 minutes, after one `uv` PATH fix.
  - Results were copied to the Mac every 10 minutes.
  - A pod-side backstop (`scripts/pod_guard.sh backstop`, team Prime key in a mode-600 file) and the Mac watchdog
    guarded cost.
  - A finisher script would have continued unfinished jobs after the drivers' 230-minute budget; none were left.
