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

## Results (October 13, 2026)

168 finished episodes, eight stopped by the restart below and the two smoke episodes, all kept (`runs/stage6_ceiling/`, private bucket
`stage6_ceiling`). Analysis: `scripts/analyze_stage5.py --root runs/stage6_ceiling --ceiling --output
runs/stage6_ceiling/ceiling.json`. Every task built at scenes 1000-1003, and `ice_out_of_bowl` and `pan_off_stove`
were false at step 0 on all twenty evaluation scenes. Both smoke episodes ran to the step budget without an
infrastructure error, with the sequencer switching prompts as planned.

Paired episodes only (both arms usable at the same scene and policy seed); "steps done" is how many leading steps of
the sequence were true in the final state of each failed sequencer episode.

| Backend | Task | Pairs | Plain | Sequencer | Rescues | Harms | Steps done on sequencer failures | Reading |
|---|---|---|---|---|---|---|---|---|
| `groot` | GarnishPancake | 8 | 1/8 | 1/8 | 1 | 1 | 0, 0, 1, 1, 1, 1, 1 of 2 | not shown |
| `groot` | MakeIceLemonade | 8 | 0/8 | 1/8 | 1 | 0 | all 0 of 2 | not shown |
| `groot` | PanTransfer | 7 | 0/7 | 0/7 | 0 | 0 | 0 (x6), 2 of 2 | not shown |
| `groot` | PortionHotDogs | 6 | 0/6 | 1/6 | 1 | 0 | 0, 1, 2, 3, 3 of 4 | not shown |
| `groot` | SeparateFreezerRack | 8 | 0/8 | 0/8 | 0 | 0 | all 0 of 2 | not shown |
| `groot_u30` | GarnishPancake | 8 | 1/8 | 0/8 | 0 | 1 | 0, 0, 0, 1, 1, 1, 1, 1 of 2 | not shown |
| `groot_u30` | MakeIceLemonade | 8 | 0/8 | 0/8 | 0 | 0 | all 0 of 2 | not shown |
| `groot_u30` | PanTransfer | 8 | 2/8 | 0/8 | 0 | 2 | 0 (x5), 1, 1, 1 of 2 | not shown |
| `groot_u30` | PortionHotDogs | 7 | 0/7 | 0/7 | 0 | 0 | 0, 0, 1, 1, 1, 2, 3 of 4 | not shown |
| `groot_u30` | SeparateFreezerRack | 8 | 0/8 | 0/8 | 0 | 0 | all 0 of 2 | not shown |
| **All** | | **76** | **4/76** | **3/76** | **3** | **4** | | |

For comparison, the plain arm's failures on the same pairs ended with: PortionHotDogs 0, 0, 0, 1, 1, 1 of 4
(`groot`) and 0, 1, 1, 1, 2, 2, 2 (`groot_u30`); GarnishPancake four of seven at 1 of 2 for both backends;
SeparateFreezerRack and MakeIceLemonade (`groot`) at 0 throughout.

### Reading

- **Re-prompting cannot be shown to help on any task.** The rule fixed above needs the sequencer to succeed in at
  least 2 more paired episodes than plain; the largest gain is 1 (`groot` on MakeIceLemonade and PortionHotDogs).
  Over all 76 pairs the sequencer solves 3 and plain 4, with 3 rescues against 4 harms.
- **Step prompts move `groot` further on PortionHotDogs only.** Its failed sequencer episodes reached 2 or 3 of the
  4 steps in three of five, where plain never got past 1. That is the one task where step-by-step instructions
  visibly change what the multitask policy does, but they did not turn into extra successes at 6 pairs.
- **`groot_u30` does worse with step prompts.** It was post-trained on the native task instructions; with the step
  wording it loses its plain successes on PanTransfer (2) and GarnishPancake (1) and gains nothing.
- **SeparateFreezerRack shows no progress under either arm, MakeIceLemonade almost none** (one `groot` sequencer
  success, two `groot_u30` plain failures with the lemon in the glass): the policies rarely do the first step, so
  there is little for a re-prompt to continue.
- **One sequencer failure finished every step:** `groot` PanTransfer scene 1002, seed 1 had the vegetables on the
  plate and the pan back on the stove at the end, but the robot had touched the food, which the task checker forbids.

### Recommendation (for W1)

With these two policies, correct step-by-step instructions are not a lever on the unseen tasks: no task meets the
reading rule, so none can be recommended as one where re-prompting fixes failures. If the benchmark keeps a
re-prompting story, PortionHotDogs with `groot` is the only candidate with visible extra progress, and it needs more
pairs before it can be claimed. The time-story clock triggers do work as built (`ice_out_of_bowl`, `pan_off_stove`
false at step 0 on all twenty scenes), so the stories that rely on timing rather than on rescuing a failure are not
affected by this result.

### Infrastructure errors

Thirteen episodes ended as `infrastructure_error`, kept and never counted:

- **Static-noise frame guard** (`docs/decisions.md`, 2026-10-05), ten episodes, all PortionHotDogs: plain scene
  1002 seed 1 at step 146 (both backends, both reran cleanly), plain scene 1003 seed 0 at step 370 (`groot` three
  times, so that cell is unpaired; `groot_u30` once, reran cleanly), sequencer scene 1003 at step 386 (`groot` seed 1
  twice, `groot_u30` seed 0 twice, both unpaired). As in the ladder run, repeats at the same step point to a
  scene-specific render failure rather than random static.
- **Scene mismatch**, three episodes, all PanTransfer scene 1003: the scene builds into one of two start states
  (`ded7d6bbf7e6` or `7926c30679e3`), so a sequencer episode can fail `--expect-state` against its plain partner
  (`groot` seed 0 twice, unpaired; `groot_u30` seed 1 once, reran cleanly). The task's build is not deterministic at
  that scene.

### Stopped episodes and the restart

The first launch ran at about 0.3 simulator steps per second instead of the ladder's 6.8. The host showed 252 cores
to a container with a 26-CPU quota; torch and OpenMP sized each policy worker's thread pools to the host, and the
eight workers used nearly the whole quota while the simulators waited. At 19:01 the drivers, simulators and workers
were stopped (the pod guard was not), `scripts/run_stage4.sh` gained `WORKER_THREADS` (default 2, passed as
`OMP_NUM_THREADS` and `MKL_NUM_THREADS`), and the run resumed with `SKIP_BUILD=1 PHASES="workers plain sequencer"
BUDGET_MINUTES=170`; finished episodes were skipped. Each simulator then used a full core and ran at about 4.5 steps
per second. The eight PortionHotDogs plain episodes running at the stop (608-1968 steps in) have no `result.json`;
their folders are kept, and each was rerun from the start. The thread cap changes no policy input or output.

### Cost

Setup 17:13-17:27 UTC, build check 17:27-17:34, drivers 17:34-20:40 (with the restart at 19:01); the pod guard made a
final sync and terminated the pod at 20:43. Billed $8.21 (cap $10). The backstop and the Mac watchdog did not fire.
