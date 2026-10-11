# Stage 4 plan: does a restart or a new wording ever rescue a plain-policy failure? (October 11, 2026)

Next step 1 of `handoff.md` (A.5). The abstract environment's brittle-VLA profile assumes that a stalled policy can be
rescued by a restart; no real data shows that for GR00T, and stage 3's rewrites point the other way. This run measures
it on the real robot. It is a **diagnostic development run** (`llm_development`, `diagnostic_replay`, baselines): no
benchmark scores, no rates to quote. Selection rules and the analysis below are fixed before any result exists.

## Arms (`scripts/run_stage4.sh`), all on one pod

Start states are machine-specific (`docs/stage3_results.md`), so every arm, including the plain reference, runs on
the same pod, and every arm after `plain` passes the plain run's step-0 state hash with `--expect-state`.

| Phase | What | Approx. episodes |
|---|---|---|
| plain | all 16 pool tasks x scenes 1000-1003 x policy seeds 0, 1, privileged stop on success | 128 |
| select | **failure pairs**: (task, scene) where both plain episodes failed, taken at the lower policy seed, at most 2 per task ordered by scene (`select_stage3.py rescue --cap 2`) | about 20 pairs |
| defer | `always_defer` on each failure pair: continue, never restart | about 20 |
| reissue | `reissue_50`, `reissue` (100), `reissue_200`: restart with the native wording at a fixed interval | about 60 |
| opus | Opus 5.5 (effort `medium`, prompt v5, unchanged) on each failure pair: chooses when to restart and what to say | about 20 |
| replays | every Opus episode, no model: `exact`, `native_text` (same timing and restarts, native wording), `no_interruption` (native goal once, same intervals and final decision) | about 60 |

## Analysis (fixed before the results)

The unit is a failure pair. Per pair, from the logs alone:

- **Usable:** the arm's episode is not an infrastructure error and started from the plain run's state.
- **Reproducible failure:** `always_defer` also fails. Pairs where defer succeeds are reported as noise and not used for
  rescue claims.
- **Restart rescue:** a `reissue_*` arm succeeds on a reproducible-failure pair.
- **LLM rescue:** Opus succeeds on a reproducible-failure pair. It is attributed with the replays: `exact` fails means
  *not reproducible*; else `native_text` succeeds means the *restart timing* rescued; else `no_interruption` succeeds
  means the *intervals or declaration* did; else the *wording* did.
- **Harm on failures** is not measurable here (the plain policy already fails); it is reported only as the outcome
  kinds (declared early, never achieved, lost after achieving).

Report counts per task and arm, never pooled rates. If no restart and no Opus episode rescues any
reproducible-failure pair, per `handoff.md` the brittle profile should go and the interrupt question reduces to when
to declare and how to read completion. If restarts rescue, the measured rescue counts replace the brittle profile's
assumed rescue probability.

## Compute, guards and stops

- One Prime pod (RunPod A6000 48 GB, about $0.61/hr), user-approved caps: **$5 GPU, 7 hours, $8 Anthropic API**.
  `BUDGET_MINUTES=330` stops new jobs; the pod deadline is 7 hours after creation.
- The run must not depend on the Mac (Oct 5-6 incident). On the pod: `scripts/pod_guard.sh` syncs `runs/stage4` to a
  private Hugging Face bucket after every phase and every 30 minutes (`scripts/pod_sync.sh`, PNG frames skipped), and
  terminates the pod after the final sync or at the deadline; an independent backstop terminates it 45 minutes after
  the deadline with no sync. Both check the pod's ID and name first. The Mac's launchd watchdog stays armed as a
  further backup.
- Stop and report if an episode is an infrastructure error twice in a row, a policy worker dies, or spend nears a cap.
  Never expose keys, rewards, success flags or predicates to a model. Do not change prompt, effort or budgets mid-run.

## Contract change

`ReplayAgent` now accepts a log that ended at a budget, not only one ending in `complete` (`docs/decisions.md`,
2026-10-11). `baselines.py` is hashed, so the contract hash differs from stage 3; every stage 4 episode shares it.
