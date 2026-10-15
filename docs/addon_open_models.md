# Add-on: open-model supervisors (post-freeze, October 15, 2026)

**Not part of `release-2026-10-15` or the primary result.** Same policies (`groot`, `groot_u30`, `pi05`), tasks, plans,
prompt version 6 and scorer as the final experiment, with open-weight supervisors served by Sail Research's
Anthropic-compatible Messages API. Episodes are `llm_development` from branch `addon-open-models`, reported separately.

## Code (branch `addon-open-models`)

- The spend guard looks prices up per Messages endpoint; Sail's `asap` prices for the three candidates
  (`adapters/agents.py`, `SAIL_STANDARD_PRICES`).
- `session` and `scripts/probe_model.py` accept a priced Messages endpoint (Anthropic or Sail); Anthropic behaviour is
  unchanged.
- A Sail model receives exactly the Opus request apart from the model name (`tests/test_agents_session.py`).
- Model configs: `configs/model-kimi-k3.dev.json`, `configs/model-glm-5-3-flash.dev.json`,
  `configs/model-gemma-4-31b.dev.json` (key `SAIL_API_KEY`).

## Format check (October 15; not calibration, not a score)

Three recorded stage 3 Opus episodes (CloseFridge, OpenCabinet, PickPlaceCounterToStove, scene 1000), observations 0
and 1 each, replayed once per model under prompt version 6 with a placeholder 4.7 s charge for every model (as in
W3's calibration). 18 calls, $0.06. Local: `runs/time_score/addon-format-check/`.

| Model | Valid strict replies | Median s/call | First calls (s) | Mid-episode calls (s) |
|---|---|---|---|---|
| `moonshotai/Kimi-K3` | 6/6 | 6.9 | 21.8, 23.8, 7.8 | 6.0, 5.8, 6.1 |
| `zai-org/GLM-5.3-Flash` | 6/6 | 10.8 | 11.8, 15.8, 9.8 | 8.0, 13.9, 7.9 |
| `google/gemma-4-31B-it` | 6/6 | 31.4 | 18.7, 26.3, 20.0 | 67.2, 36.4, 72.1 |

No retries. Every model started with the task instruction (Kimi K3 once rewrote it) and then deferred, close to what
Opus did at the same observations. Mid-episode calls (15 images) used about 2,300-4,800 more input tokens than first
calls (3 images), so the images reach the models.

## Decisions (Tom, October 15; fixed before any add-on robot run)

- **Models:** Kimi K3 and GLM-5.3-Flash. Gemma 4 31B is dropped: at about 31 s per call its charge alone would use
  most deadlines, and its calls would add about 3 pod hours.
- **Call charge:** each model's `call_seconds` by the October 14 rule (median of one replay per recorded observation
  of W3's eight-episode pilot, 27 calls, the same inputs as Opus and Sonnet), written to a separate add-on time config;
  the frozen `configs/time_pressure.json` is unchanged.
- **Reporting:** each model's paired held-out regret at its **own** calibrated charge, and the same episodes rescored
  at **Opus's 4.74 s**, which separates decision quality from Sail's serving speed (`scripts/score_time.py
  --call-seconds`). Sail serves quantized (FP4/INT4/FP8) versions, so results are for those served versions.
- **Pod:** one A100 80 GB SXM4 pod on Tom's Prime account, run by W1, with its own always-defer twins (84 cells) and
  one session per scene per model from `configs/final/plans`, paired by `pair-session` against that pod's runs.
  Comparison with pods A and B is through paired regret only.

## Calibration (October 15, by the fixed rule)

W3's 27 pilot observations (handoff branch `w3-tom-agent-pilot-handoff`, `62a75d2`, all 343 files checksum-verified),
replayed once per model with each episode's own earlier experience and the common 4.7 s public charge shown to every
model, as in Opus's and Sonnet's replay. 54 calls, about $1 of actual usage (the guard recorded $3.81 because one Kimi
timeout keeps its full $2.55 reservation). Local: `runs/time_score/addon-calibration/`.

| Model | Valid strict replies | Median s/call (the charge) | First calls (n = 8) | Later calls (n = 19) |
|---|---|---|---|---|
| `moonshotai/Kimi-K3` | 27/27 (1 retry) | **5.92** | 3.78 | 5.96 |
| `zai-org/GLM-5.3-Flash` | 18/27 | none | | |

- **Kimi K3:** `call_seconds` = 5.92 s in `configs/addon_time_pressure.json` (the frozen config plus this one value).
  One call took 137 s (a 120 s timeout, then a successful retry); it is kept and does not move the median.
- **GLM-5.3-Flash is excluded, untested:** Sail rejected 9 of the 27 requests with HTTP 400, "at most 4 images per
  request" (mid-episode observations carry 15 images) and "input exceeds the model's maximum context length" on the
  two episodes with the longest history. The morning format check had passed, so the serving limit changed during the
  day. Giving it fewer images would break the identical-inputs rule, so it gets no charge and no sessions.
- **Sessions started 17:30:** Kimi K3, one per scene, two at a time on the two worker sets, `SESSION_CAP` $15 per
  session (a timeout keeps a $2.55 reservation, so the cap leaves room; expected usage is a few dollars).
- **Live latency** is recorded in every session (`model_timings.jsonl`); the report gives each model's live median next
  to its calibrated charge, as a check on the replay, for Opus and Sonnet as well. It never changes the score.

## Spend-guard accounting and the scene 1001 rule (October 15, 18:30, before scene 1001's outcome)

The guard reserves a worst case of a 1M-token context plus 4,096 output tokens per call ($2.55 for Kimi K3), and a call
that times out keeps that whole reservation as spent, because its usage is unknown. Kimi K3 timed out on about 4% of
calls (131-133 s against the 120 s limit, then a successful retry), so the ledgers ran far ahead of real usage: at
18:12, scene 1001 showed $13.80 of its $15 cap (4 timeouts) against about $3.60 of actual usage; scene 1000 showed $8.82
(2 timeouts). A real Kimi K3 call here is about 5-8K input tokens, under $0.07 even at the worst case.

- **Scenes 1002 and 1003** start with a $60 guard cap per session (the launcher was replaced at 18:13; the two running
  sessions were not touched). Expected real spend stays a few dollars per session.
- **Scene 1001 (Tom, fixed before its outcome):** if the guard stops it before all 21 episodes, it is rerun once from
  the start as a new session (`kimi-k3-scene1001-rerun`, same plan and same twins, $60 cap) on the first free worker set.
  The stopped attempt is kept and reported. The rerun replaces it in the main add-on result because the stop comes from
  the guard's accounting of Sail timeouts, not from the supervisor's decisions.
