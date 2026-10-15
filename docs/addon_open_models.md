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
