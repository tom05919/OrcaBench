# Stage 6: the policy ladder (W2, October 13, 2026)

A **diagnostic development run** (`diagnostic_reference`): plain policies only, no model calls, nothing here is a
benchmark score. It answers W2 in `docs/work_split.md`: which three policies differ clearly in ability on the chosen
tasks, and do they still solve the trained tasks where leaving them alone is right. The plan below was fixed before
any episode ran.

## Policies

All GR00T N1.5, pinned at revision `c484448a` of `robocasa/robocasa365_checkpoints` (`configs/sources.lock.json`,
`scripts/download_checkpoint.py`, `policy_worker.py`; config and shard index are byte-identical to the multitask pin).

| Backend | Checkpoint | Training | Published average on these 16 tasks (`test` split, 30 rollouts each) |
|---|---|---|---|
| `groot_10p` | `target_fraction/composite_unseen_10p` | pretraining (80k steps), then 60k steps on the 16 `composite_unseen` tasks with 50 of 500 demos each | 22.7% |
| `groot_30p` | `target_fraction/composite_unseen_30p` | the same with 150 demos each | 30.8% |
| `groot` | `multitask_learning/checkpoint-120000` | multitask (existing pin) | not published; 5 of 62 in stage 5 on our `pretrain` split |

The published numbers come from each checkpoint's `eval_results.json` and use RoboCasa's held-out `test` kitchens.
Ours use the `pretrain` split (`task_parts` requires it), so they are not comparable. `groot_pretrain` is dropped: 0
of 62 in stage 5.

## Grid (`scripts/run_stage6_ladder.sh`)

- **Story tasks** (the eight with a time story, `docs/task_catalog.md`): MakeIceLemonade, SeparateFreezerRack,
  PanTransfer, PortionHotDogs, GarnishPancake, HeatKebabSandwich, WaffleReheat, ArrangeTea.
- **Leave-alone tasks:** the five seen tasks the multitask checkpoint solved most often in stage 4 (OpenCabinet 8/8,
  PickPlaceCounterToCabinet 6/8, PickPlaceCounterToStove 6/8, CloseFridge 4/8, OpenDrawer 4/8). Sink and scrub tasks
  are left out because their scenes do not rebuild reliably.
- **Episodes:** scenes 1000-1003 x policy seeds 0, 1 on both sets, for each of the three checkpoints (104 each, 312
  in all), on one pod so start states are comparable.
- A build check of all 13 tasks at the four scenes runs first. A scene whose checker is true at step 0 is reported
  and never counted (rule from stage 5).

## Reading (fixed before the results)

`scripts/analyze_stage5.py --root runs/stage6_ladder --backends groot groot_10p groot_30p`: successes per task and
backend, subgoal progress from the evaluator predicates, and stage 5's per-task reading (leave-alone candidate,
re-prompting candidate, unlikely to be helped, mixed).

- **Ladder:** recommend three policies whose story-task success counts are clearly separated, with partial progress
  on some failures (so supervision has something to rescue). Report counts per task, never pooled rates to quote.
- **Leave-alone:** a policy that solves fewer than half of a leave-alone task's episodes is reported as having
  forgotten it; that task is then leave-alone only for the policies that still solve it.

## Compute and guards

One Prime pod on Ranveer's personal account: RunPod A100 80 GB, 32 vCPUs, $1.81/hr (the 36-vCPU L40 and L40S
offers were out of stock). Six policy workers, two per checkpoint (four took about 35 GB in stage 4). Caps: **$10 GPU,
pod deadline 5.5 hours after creation** (about $11 if the backstop has to fire), `BUDGET_MINUTES=240` per driver.
`scripts/pod_guard.sh` syncs `runs/stage6_ladder` to the private Hugging Face bucket every 30 minutes and after the
run, then terminates the pod; the backstop and the Mac watchdog remain. The pod gets only the Hugging Face and Prime
keys, not the Anthropic key.
