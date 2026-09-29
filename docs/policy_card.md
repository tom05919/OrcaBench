# Learned-policy reference prompt card

## Status

The pinned GR00T checkpoint loaded and executed on the target GPU in the
[September 27 development pass](feasibility.md#first-live-development-pass-september-27-2026).
Its four exact reference prompts remain **unqualified**: no declared entry
condition has ten valid trials. Values in the evidence table remain untested
until those conditions are run and audited; do not infer rates from one
full-task diagnostic.

## Candidate identity

| Field | GR00T candidate | π0.5 fallback |
|---|---|---|
| Checkpoint repository | `robocasa/robocasa365_checkpoints` | `robocasa/robocasa365_checkpoints` |
| Revision | `c484448aba1a9b60a04c9b0ca117241518ea69f3` | same |
| Subdirectory | `gr00t_n1-5/multitask_learning/checkpoint-120000` | `pi05_pretrain_human300/multitask_learning/75000` |
| Runtime status | loaded and executed on RTX 6000 Ada; qualification pending | fallback not started |
| Native action chunk used by adapter | 16 steps | 5 steps |

Checkpoint manifests bind the repository, revision, subdirectory, complete
inference file allowlist, sizes, and SHA-256 digests. A policy identity also
records adapter version, runtime version, and GPU identity.

## Public reference prompts

| Reference ID | Exact qualification prompt | Intended outcome | Known limitations |
|---|---|---|---|
| `open_cabinet` | “Open the cabinet.” | Task cabinet is open | No target fixture is named beyond the current task context; runtime reliability unknown. |
| `transfer_cereal` | “Pick the cereal box from the cabinet and place it on the counter.” | Cereal contacts the task counter | Release and placement stability are not scored by the upstream predicate; runtime reliability unknown. |
| `transfer_bowl` | “Pick the bowl from the cabinet and place it on the counter.” | Bowl contacts the task counter | Release and placement stability are not scored by the upstream predicate; runtime reliability unknown. |
| `close_cabinet` | “Close the cabinet.” | Task cabinet is closed | The learned action may disturb already placed objects; runtime reliability unknown. |

Preprocessing, camera names, state order, action conversion, checkpoint identity,
and these reference strings are fixed before model comparison. They are exact
diagnostic prompts to one shared checkpoint, not separately trained controllers
or an allowlist. A model may submit any nonblank prompt up to 512 characters
through `run_policy`; accepted text is preserved verbatim. Performance reported
here does not transfer automatically to a paraphrase, a composed instruction, or
a prompt introduced dynamically during execution. One unqualified Opus
run submitted dynamic prompts, but their reliability remains unmeasured until
matched, retained GPU trials are audited.

## Qualification evidence template

Record one row for every backend, reference prompt, and entry condition. Each
required row has ten valid trials. Store raw trace paths and durations alongside
the counts. The qualification evidence format retains the field names `skill`
and `skill_conditions`; within that diagnostic artifact they identify these
four exact probes.

| Backend | Reference prompt | Entry condition | Successes / trials | Wilson 95% interval | Duration distribution | Observed limitations | Trace paths |
|---|---|---|---|---|---|---|---|
| GR00T | `open_cabinet` | nominal reset | untested | null | untested | untested | none |
| GR00T | `open_cabinet` | natural intermediate | untested | null | untested | untested | none |
| GR00T | `transfer_cereal` | nominal learned prefix | untested | null | untested | untested | none |
| GR00T | `transfer_cereal` | natural stopped/failed state | untested | null | untested | untested | none |
| GR00T | `transfer_bowl` | nominal learned prefix | untested | null | untested | untested | none |
| GR00T | `transfer_bowl` | natural stopped/failed state | untested | null | untested | untested | none |
| GR00T | `close_cabinet` | nominal learned prefix | untested | null | untested | untested | none |
| GR00T | `close_cabinet` | natural intermediate | untested | null | untested | untested | none |

Add the same eight rows for π0.5 only if the fallback rule is triggered. Report
prefix failures separately; they do not become target-prompt attempts. The
screening threshold is at least 8/10 for every row and 16/20 diagnostic full
tasks, followed by the matched-continuation relevance check.
