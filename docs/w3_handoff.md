# W3 execution handoff — October 14, 2026

You are **W3 / person 3**, continuing an existing implementation. Execute the
remaining live work; do not restart architecture exploration or rebuild session
mode. The presentation is Friday, October 16. This file records session context;
the detailed commands, rationale and execution gates remain in
[session_mode.md](session_mode.md).

## Read first

1. Root `AGENTS.md` and `handoff.md` **section S**. Older handoff sections are
   historical and contain superseded instructions about branches and pushing.
2. `docs/direction.md`, `docs/work_split.md`, `docs/briefs/w3_harness.md`.
3. `docs/session_mode.md`, especially **Forward execution plan** and **Live
   execution gates and rationale**. This is the plan to execute, not a proposal
   awaiting another general approval.
4. `docs/stage6_pilot.md` for actual evidence and missing results.
5. Latest `origin/w1-scoring:docs/final_experiment.md` and W2's ladder/ceiling
   docs. Fetch first: the files on main/W3 may predate partner branch work.

## Objective and scientific scope

Compare LLM supervisors over the same frozen learned robot policies and harness.
One session interleaves anonymous policies and supplies text-only outcomes from
earlier completed episodes. The current final scope is monitoring, declaration
timing and restraint under charged model-call latency and task/story deadlines.
No task met W2's prespecified ceiling rescue rule; do not promise that re-prompting
fixes policy failures or present a diagnostic supervisor as a model result.

W3 must deliver actual v6 Opus/Sonnet latency medians with call counts, one scored
eight-episode Opus development pilot, and final pod B runs at Tom's frozen release.
Full commands and the reasons for this order are in `docs/session_mode.md`.

## Verified starting state

Workspace: `/Users/tylipscomb/OrcaBench`; branch `w3-harness`.
Last fetched snapshots before this handoff:

| Ref | Commit |
|---|---|
| `origin/main` | `2663171` |
| `origin/w1-scoring` | `efaac23` |
| `origin/w2-policies` | `945cb7a` |
| `origin/w3-harness` | `b8d8b65` before the handoff-document commit |

W3 [PR #3](https://github.com/tom05919/OrcaBench/pull/3) is open and pushed.
Tom owns merging and tagging. No release tag was present at the last fetch.
Refresh these facts rather than assuming the snapshots are still current.

Session mode, v6 prompt, privacy projection, attempt retention, worker-death stop,
baseline pairing, frozen-input checks and conservative API spend guard are
implemented. W1 requested the story-clock clarification; it is in W3 `845d963`:
the limit counts from the event in the story, or step 0 if none is named.
Calibration must use this corrected prompt.

Evidence already obtained:

- W3 full suite: **361 passing tests**, most recently
  `runs/stage6_pilot/w3-execution-plan-suite.log`.
- Combined W1/W2/W3 suite: **386 passing tests**,
  `runs/stage6_pilot/integration-story-clock-suite.log`.
- Actual W3 CLI/HTTPAgent with test doubles produced terminal and infrastructure
  attempts consumed by W1's actual reader/scorer. This is explicitly mock evidence.
- Fresh eight-entry pilot-plan and four two-model v6 payload dry runs passed:
  `runs/stage6_pilot/readiness-20261014T195057Z/readiness.json`.
- **No real W3 model calls, robot-policy pilot episodes, GPU rentals or measured
  v6 medians have occurred.** Do not report historical/provisional charges as
  current calibration or local tests as policy qualification.

## Immediate unresolved prerequisites

The user says both Prime and Claude keys have been added. Fresh checks of both
the unsourced process environment and the project `.env` still find neither
`PRIME_API_KEY` nor `ANTHROPIC_API_KEY`. This is a visibility discrepancy, not an
authentication failure: no authenticated request was attempted. `.env` exists,
is ignored and mode 600. Do not print it or overwrite it.

Two questions were asked but remain unanswered in this handoff:

1. Where were the keys added? Request only a local file path/integration name,
   never secret values in chat. Check current presence again before asking.
2. What are the separate total compute and Claude API dollar caps?
   `W3_GPU_CAP` / `W3_API_CAP` were unset. The user's possible ~$250 Prime credit
   balance is not a specified spending cap and does not pay direct Claude calls.

Once totals are supplied, allocate preflight, pilot, first/mid calibration and
final-session API caps within that one total, as documented in the runbook.
Different output roots have independent ledgers. Do not allocate the entire
total separately to each phase. Confirm personal versus team billing and the
GPU type with W2. Do not rent while an essential execution prerequisite is open.

## Local tools and artifacts to reuse

- Python: `.venv-presentation/bin/python` is 3.12 with the local test dependencies.
  Full check: `PYTHONPATH=src .venv-presentation/bin/python -m unittest discover -s tests -v`.
- `.venv-prime/bin/prime` is installed at `prime==0.11.0`, matching pod guard's
  pin. Version/help checks passed; it has not authenticated. The CLI/SDK eagerly
  initializes global `~/.prime`; `whoami` also persists identity. Do not change
  another session's global account context or override `HOME`. For read-only
  account/wallet/pod/offer checks reuse `adapters.http.request_json` with GET and
  an in-memory bearer header; endpoint details are in the runbook.
- No `.venv-sim` / `.venv-groot` GPU runtime exists on this Mac. Use the existing
  pinned pod bootstrap and W2 checkpoint instructions, not local mock policies.
- Detached integration worktree:
  `runs/stage6_pilot/integration-check`, local HEAD `53e96be` plus deliberate
  uncommitted copies of the latest W3 source/tests. **Do not reset, clean, blindly
  rerun merge recipes, or push this checkout.** Inspect it before refreshing.
  It contains W1 timing/scorer and W2 dependencies missing from W3/main. Resolve
  only shared append-only decision-log conflicts; refer partner code issues to
  their owners. Fresh final runs instead require the clean tagged release.
- Existing mock interface artifacts:
  `runs/stage6_pilot/integration-check/runs/w3-interface-check/`.
  Some generators refuse existing paths: do not rerun blindly or erase attempts.
- All project data, environments and caches stay under this project root.
  Keep artifacts ignored; only small W3 documentation/code belongs in Git.
- Earlier presentation work is preserved in Git stash. Do not restore it over
  the three-way ownership split or drop it as cleanup.

## Execute next, with ownership intact

Proceed through the runbook's live gates. The pilot uses the two already measured
GR00T profiles and need not wait for π0.5. API preflight comes before rental;
the guarded pilot supplies real observations for calibration. Score the pilot
with its copied provisional configuration; do not label it final benchmark data.

For calibration deliver model ID, prompt/config/source identity, first/mid/pooled
medians, successful and attempted call counts, retries, usage, experience lengths
and artifact paths. Retain observation PNGs through replay calibration. Never
invent mid-episode images if the chosen episode ended after one observation.

W1 owns score code, timing/story config, selection, plans, report and final
experiment; W2 owns learned policies, checkpoint qualification and task predicates.
W3 owns session/runner/CLI/agent/probe work and its two status/runbook docs.
The exact ownership table is authoritative. `docs/decisions.md` is append-only.
Do not edit W1's root `handoff.md`. Unowned compute tooling is frozen; if an
actual guard/bootstrap defect requires changes, document the concrete issue
for Tom instead of quietly modifying it.

W2's π0.5 is still unqualified in the inspected snapshots; its ability is null.
Tom decides whether a release waits or uses two policies. W3 does not make that
design decision. At the three-policy freeze, pod B is always-defer → same-pod
pairing → four Sonnet sessions → `reissue_200`, approximately 252 episodes on
at least 16 CPU cores. Use the same GPU type as pod A. Preserve all attempts,
copy results after every phase, and verify exact-pod termination.

## Autonomy and communication

The user authorized autonomous W3 execution and periodic fetches/pushes. Do not
ask again for general permission to implement or push this work. Spending still
requires the missing explicit caps and functioning credentials. Ask concise
questions only for genuinely missing inputs, and continue useful independent
work while waiting. Avoid repeating passed mock checks as a substitute for live
progress. Explain decisions and give brief progress updates during work.

Run the required full unittest suite after runner changes and before every push;
push only W3-owned changes to `w3-harness`, then fetch partner branches. Update
`docs/stage6_pilot.md` with measurements, exclusions, costs and artifact locations
so W1/W2 can consume the evidence. Never claim completion until real calibration,
scored pilot, integrated release and final retained runs exist. If external inputs
block progress, leave an accurate status and next action rather than fabricating
results or keeping a rental idle.

## Suggested skills

- `superpowers:executing-plans` to execute the existing runbook.
- `superpowers:verification-before-completion` before evidence/completion claims.
- `superpowers:systematic-debugging` for demonstrated live failures.
- `superpowers:resolving-merge-conflicts` only if an actual conflict appears.
- Relevant prompt-design/test skills only if a demonstrated W3 defect needs a fix;
  do not redesign the prompt or alter frozen behavior as preparation.

Respect the user's instruction to delegate broad research to subagents. Keep
research bounded and avoid full-history forks when a short brief is sufficient.
