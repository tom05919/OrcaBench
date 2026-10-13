# Stage 6: the ceiling test (W2, October 13, 2026)

A **diagnostic development run**: the plain policy and a privileged sequencer, no model calls, nothing here is a
benchmark score. It answers W2 step 3 in `docs/briefs/w2_policies.md`: on which unseen tasks can correct
step-by-step instructions rescue the plain policy's failures? A task where they can is one where a supervisor has
something to do. The plan below was fixed before any episode ran.

## Arms

- **Plain reference:** `screen --mode reference`, the native instruction for the whole episode, stopped on the true
  checker every 100 steps.
- **Sequencer:** `screen --mode sequencer`, `PrivilegedSequencer` (`diagnostics.py`, `privileged_sequencer_v1`). Every
  50 steps it reads the task's step predicates, prompts the first unmet step of `SEQUENCES[task]` and re-prompts only
  when that step changes; it stops on the same checker. It reads simulator truth, so it is an upper bound for what
  re-prompting can do, never a model result. Every physical action still comes from the frozen policy.
- **Pairs:** each sequencer episode uses the scene, policy seed and step-0 state hash (`--expect-state`) of a usable
  plain episode on the same pod. A scene that builds differently ends as an infrastructure error before step 1.

## Sequences (`tasks/predicates.py`)

A sequence is fixed per task, so a prompt never names a sampled object or a plate side.

| Task | Steps (predicate: prompt) |
|---|---|
| PortionHotDogs | `bun_on_plate`: a bun on a plate; `portion_on_plate`: a sausage on the plate with the bun; `bun_on_each_plate`: the other bun on the empty plate; `both_plates_portioned`: the other sausage on the plate with only a bun |
| GarnishPancake | `strawberry_out_of_fridge`: pick the strawberry from the fridge; `strawberry_on_pancake`: place it on the pancake |
| MakeIceLemonade | `lemon_in_cup`: the lemon wedge into the glass; `ice_in_cup`: an ice cube into the glass |
| SeparateFreezerRack | `meat_on_freezer_rack`: meat container to the second highest rack; `veg_on_freezer_rack`: vegetable container to the highest rack |
| PanTransfer | `vegetables_on_plate`: dump the vegetables onto the plate; `pan_on_stove`: return the pan to the stove (true at step 0, so it comes second) |

The PortionHotDogs steps count buns and portions on either plate, so the order of plates does not matter. "Portioned"
means exactly one bun and one sausage, as in the upstream checker. `strawberry_out_of_fridge` tests the
strawberry's centre against the fridge interior.

## Grid (`scripts/run_stage6_ceiling.sh`)

- **Tasks:** the five above (the unseen tasks with step predicates).
- **Backends:** `groot` and `groot_u30` (the ladder's two ability profiles, `docs/stage6_ladder.md`).
- **Episodes:** scenes 1000-1003 x policy seeds 0, 1, both arms: 40 pairs per backend, 160 episodes, on one pod.
- **First:** a build check of the five tasks at the four scenes, and of MakeIceLemonade and PanTransfer at all
  twenty evaluation scenes (1000-1019) to confirm that the clock triggers `ice_out_of_bowl` and `pan_off_stove` are
  false at step 0; then one sequencer smoke episode per backend (PortionHotDogs, scene 1000, seed 0, kept in
  `smoke/`, not counted), which stops that backend's run if it ends in an infrastructure error.

## Reading (fixed before the results; from the W2 brief)

- Per task and backend, over the pairs where both arms are usable: if the sequencer succeeds in **at least 2 more of
  8 paired episodes** than plain, re-prompting can help on that task.
- Report both arms' successes, rescues (sequencer success, plain failure) and harms (the reverse), and how far the
  sequencer got on failures (the last step reached). Counts, not pooled rates.
- Infrastructure errors are listed separately and never counted.

## Compute and guards

One Prime pod on Ranveer's personal account, the same setup as the ladder run (80 GB GPU, eight policy workers).
Caps: **$10 GPU, pod deadline 5 hours after creation**, `BUDGET_MINUTES=240` per driver (no new episode after
that). `scripts/pod_guard.sh` syncs `runs/stage6_ceiling` to the private Hugging Face bucket every 30 minutes and
after the run, then terminates the pod; the backstop and the Mac watchdog remain. The pod gets only the Hugging Face
and Prime keys.
