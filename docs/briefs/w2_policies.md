# W2 brief: policy ladder, ceiling test and predicates (suggested: Ranveer)

**Read first:** `AGENTS.md`, `handoff.md` section S (S.3 has the pod lessons), `docs/direction.md`,
`docs/work_split.md` (ownership and interfaces), `docs/stage5_plan.md`, `docs/stage5_results.md`, and the unseen-task
section of `docs/task_catalog.md`.

## Update from W1, October 13 (read first)

- **Your results decided two things.**
  - **Fallback (monitoring) mode applies:** no unseen task met the ceiling rule.
  - **Final policies (Tom):** `groot`, `groot_u30` and **`pi05`**. π0.5 is now **required**, not optional.
- **Measure π0.5 before the October 14 freeze:**
  1. **Install:** `bootstrap_gpu.py --include-pi05 --download-pi05-checkpoint`.
  2. **GPU memory:** set `XLA_PYTHON_CLIENT_PREALLOCATE=false` (or `XLA_PYTHON_CLIENT_MEM_FRACTION`) whenever a π0.5
     worker shares a GPU with GR00T workers; JAX otherwise takes 75% of GPU memory.
  3. **Smoke test:** one plain episode first. The `pi05` backend in `policy_worker.py` has never run.
  4. **Ladder:** the same grid as yours (8 story tasks and 5 leave-alone tasks × scenes 1000-1003 × policy seeds 0,
     1). Add it to `runs/stage6_ladder/analysis.json`.
  5. **Story limits:** run `scripts/set_story_limits.py <ceiling plain runs> <π0.5 ladder runs> --policies groot
     groot_u30 pi05`. It is on branch `w1-scoring`. Do not pass `--write`; post the output in
     `docs/stage6_ladder.md`, and W1 writes the config.
- **If π0.5 cannot run cleanly by the freeze, tell Tom.** He decides between moving the freeze and proceeding with the
  two GR00T policies.
- **Final pod A** (October 15) runs a π0.5 worker as well (`docs/final_experiment.md`).

## Goal

Decide **which policies and which tasks** the benchmark uses, with measurements:
- three policies of clearly different ability;
- unseen tasks whose failures a correct instruction can fix;
- trained tasks where leaving the policy alone is right.

GPU work on your own credits, plus file changes in the files you own.

## Steps

1. **Pin two more GR00T checkpoints**, as `groot_pretrain` was pinned on October 12 (commit `6a5b1e0`). Use backends
   `groot_u10` and `groot_u30` for `gr00t_n1-5/target_fraction/composite_unseen_10p` and `_30p` at revision
   `c484448aba1a9b60a04c9b0ca117241518ea69f3`. They are the pretraining checkpoint post-trained on 50 or 150
   demonstrations per unseen task. The 30% checkpoint's published average on these tasks is 31%, on RoboCasa's `test`
   split, which is not comparable to our `pretrain` split.
   - **List the files:**
     `https://huggingface.co/api/models/robocasa/robocasa365_checkpoints/tree/<rev>/<subdir>?recursive=true`. The
     files sit directly in the folder. The LFS `oid` is the SHA-256 of each `.safetensors` file. Download only the
     small files (`config.json`, `experiment_cfg/metadata.json`, `model.safetensors.index.json`) and hash them.
   - **Check before pinning:** `config.json` and the shard index should equal the multitask checkpoint's, and
     `metadata.json` must have the `new_embodiment` key.
   - **Add the pins:**
     - `GROOT_U10_FILES` and `GROOT_U30_FILES` in `scripts/download_checkpoint.py`, plus their entries in
       `DEFAULT_OUTPUTS` and `EXPECTED_BY_BACKEND`;
     - `groot_u10_subdir` and `groot_u30_subdir` in `configs/sources.lock.json`;
     - the backends in `EXPECTED_CHECKPOINTS` and `GROOT_BACKENDS` in `policy_worker.py`, with `manifest_sha256`
       equal to `records.digest({repo_id, revision, subdir, files: [{path, size, sha256}] sorted by path})`;
     - the backends in the allowed list in `adapters/policy.py`.
   - **Verify:** `tests/test_policy_worker.py` checks that every downloader spec matches its worker pin.
   - **π0.5 (optional):** `bootstrap_gpu.py --include-pi05 --download-pi05-checkpoint`, then one plain episode. Add it
     to the ladder only if it runs cleanly.
2. **Ability ladder:** `runs/stage6_ladder/<backend>/`. Run `scripts/run_stage4.sh workers plain` with `OUT`,
   `BACKEND`, `CHECKPOINT`, `BASE_PORT`, `TASK_LIST`, `SCENES` and `POLICY_SEEDS`, one instance per backend, as
   `scripts/run_stage5.sh` does. Copy that script to `scripts/run_stage6_ladder.sh`.
   - **Unseen tasks (8):** MakeIceLemonade, SeparateFreezerRack, PanTransfer, PortionHotDogs, GarnishPancake,
     HeatKebabSandwich, WaffleReheat, ArrangeTea.
   - **Trained leave-alone candidates (5):** OpenCabinet, PickPlaceCounterToCabinet, PickPlaceCounterToStove,
     OpenDrawer, CloseFridge. They had the highest plain success in stage 3.
   - **Grid:** scenes 1000-1003, policy seed 0; add seed 1 if time allows.
   - **Backends:** `groot_u10`, `groot_u30`, and `groot` on the unseen tasks at scenes 1002-1003 only, since stage 5
     has 1000-1001 and stages 3-4 have the trained tasks.
   - **Analysis:** `python3 scripts/analyze_stage5.py --root runs/stage6_ladder`. Extend `BACKENDS` in that script;
     you own it.
   - **Sizing:** stage 5 ran 128 long episodes in 3.4 hours on a 7.65-core pod, CPU-bound at about 4.8 steps/s per
     stream. Each worker takes about 7.6 GB of GPU memory. Prefer 16 or more cores, and run no more than about 6
     workers on a 48 GB GPU.
3. **Ceiling test:** `runs/stage6_ceiling/`. Can correct step-by-step instructions rescue failures?
   - **What it compares:** `PrivilegedSequencer` (`diagnostics.py`) prompts the first unmet step in `SEQUENCES[task]`
     and re-prompts only when the step changes. Like the plain reference, it stops on the true checker, so the
     comparison is fair. It has never run on a GPU, so run one episode first.
   - **Add `SEQUENCES`, each step with a predicate:**
     - **PortionHotDogs:** new per-plate predicates, for example `plate1_bun`, `plate1_sausage`, `plate2_bun` and
       `plate2_sausage`, each meaning exactly one on that plate. Word the plates the way the policy can follow; look
       at the stage 5 frames in `runs/stage5/` (Tom's Mac) or at a rendered scene.
     - **GarnishPancake:** a grasp or out-of-fridge step, then `strawberry_on_pancake`.
     - **MakeIceLemonade:** `lemon_in_cup`, then `ice_in_cup`; both exist.
     - **SeparateFreezerRack:** `meat_on_freezer_rack`, then `veg_on_freezer_rack`; both exist.
     - **PanTransfer:** `vegetables_on_plate`, then `pan_on_stove`. `pan_on_stove` is true at the start, so the order
       matters.
   - **Arms on one pod, same seeds:** `screen --mode reference` first, then `screen --mode sequencer` with
     `--expect-state` from the reference episode (`scripts/select_stage3.py`'s `start_state`; the stage 4 driver's
     `pair_jobs` shows the pattern). Use the `groot` backend, plus `groot_u30` if it shows partial progress. Scenes
     1000-1003 × policy seeds 0-1.
   - **Reading rule, fixed before results:** if the sequencer succeeds in at least 2 more of 8 paired episodes than
     plain, re-prompting can help on that task.
   - **Summary for W1:** write `runs/stage6_ceiling/summary.json` in the format fixed in `docs/work_split.md`.
     `scripts/select_final.py` applies the selection rules to it and to the ladder table.
   - **Test update:** `tests/test_task_catalog.py` currently requires `SEQUENCES` to cover exactly the
     `composite_seen` tasks; update it.
4. **Trigger predicates for W1**, with the names fixed in `docs/work_split.md`:
   - `ice_out_of_bowl` (MakeIceLemonade): at least one ice cube is no longer in the bowl. Use
     `OU.check_obj_in_receptacle(raw, cube, "ice_bowl")`; check the object name in the task source.
   - `pan_off_stove` (PanTransfer): `raw._check_obj_location_on_stove("vegetable_container") is None`.

   Both must be false at step 0. Add unit tests in the style of `test_unseen_composite_progress_predicates`, and check
   them in the real simulator with `scripts/check_task_pool.py`.
5. **Recommend by October 14**, in `docs/stage6_ladder.md` and `docs/stage6_ceiling.md`:
   - the three policies (backend names, ability per task);
   - the unseen tasks with fixable failures;
   - the trained leave-alone tasks per policy.
6. **Final runs, October 15:** pod A on your credits, same GPU type as W3's pod B. Run the baselines and the Opus
   sessions with W3's `session` command, following `docs/final_experiment.md` and the tagged commit.

## Interfaces

- **You provide:** the backend names `groot_u10` and `groot_u30`; `runs/stage6_ladder/analysis.json`; the trigger
  predicates; the recommendation.
- **You consume:** `docs/final_experiment.md` (W1) and the `session` command (W3) for the final runs.

## Definition of done

- The pins, predicates and sequences have tests, and the suite passes.
- The ladder and ceiling tables are pushed with their docs.
- Every attempted episode is kept, with infrastructure errors reported separately.
- Each pod has a backstop guard, and results are copied back after every phase.

## Do not

- Edit W1 or W3 files.
- Train or fine-tune anything.
- Mix sequencer or reference results with model scores. They are diagnostics.
