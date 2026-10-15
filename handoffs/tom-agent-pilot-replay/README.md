# W3 pilot replay handoff for Tom’s agent

This folder supplies the saved W3 pilot inputs requested in [issue #9](https://github.com/tom05919/OrcaBench/issues/9), for W1’s open-model latency calibration described on `addon-open-models` in `docs/addon_open_models.md`. Ty requested publication in this original repository on October 15, 2026, replacing the private-delivery plan for this package.

## What is included

`w3-pilot-replay-inputs-20261015.tar.gz` contains the original relative paths for:

- Eight episode folders under `runs/stage6_pilot/opus-pilot/sessions/opus-eight/episodes/0000` through `0007`, with `observations.jsonl`, `result.json`, `decisions.jsonl`, and only the referenced PNG frames.
- `runs/stage6_pilot/calibration-all-20261014T212408Z/inputs.json`.
- That calibration’s `inputs/`: eight per-episode preceding-experience files and `time-pressure-common.json`.
- An archive README, manifest, and `SHA256SUMS`.

Counts: **8 episodes, 27 observations (8 first calls and 19 later calls), 309 referenced PNG files, 343 source payload files**. The archive also includes three handoff metadata files. It excludes API credentials, checkpoints, videos, evaluator directories, and earlier model replay outputs. Original payload bytes are preserved.

## Verify and extract

Run from an OrcaBench checkout root. The extraction target below must be new; do not overwrite existing run artifacts.

Follow this outer README's extraction and delivery instructions. The archive's embedded README preserves historical private-delivery instructions and an older extraction suggestion; those instructions are superseded here.

```bash
PACKAGE=handoffs/tom-agent-pilot-replay
(cd "$PACKAGE" && shasum -a 256 -c archive.sha256)
mkdir -p runs/time_score
REPLAY_ROOT="$PWD/runs/time_score/pilot-replay-inputs-20261015"
mkdir "$REPLAY_ROOT"
tar -xzf "$PACKAGE/w3-pilot-replay-inputs-20261015.tar.gz" -C "$REPLAY_ROOT"
(cd "$REPLAY_ROOT" && shasum -a 256 -c SHA256SUMS)
```

All paths in the extracted `inputs.json` are relative to `REPLAY_ROOT`. Image paths in an observation are relative to that observation’s episode folder. Resolve those paths against these roots when calling the replay tooling. Source-hash entries describe historical provenance; they are not all files included in this archive. The original `jobs[*].output` values name historical replay outputs: use new W1 output paths for the additional models.

## Task for Tom’s agent

1. Use the W1 `addon-open-models` implementation and its existing approved model access/spend controls. This handoff provides inputs; it does not authorize extra model or GPU spending.
2. Replay **each of the 27 recorded observations once per added model**, under the same common public timing copy and prompt version 6 / medium effort. Use each job’s `experience` file for every observation in that episode. Earlier experience grows from zero to seven completed records; never substitute the final full session history for every episode.
3. Preserve original observations and images. Treat episode `result.json` and `decisions.jsonl` as reconstruction/evaluator artifacts; current-episode outcomes must not enter a model request. Only the already-projected preceding-experience files supply past outcomes.
4. The common public **4.7-second** charge is the original replay’s identical-input timing scalar. It is **not** a measured charge for Kimi or GLM. Measure and report each added model’s own median response latency, attempts, errors, parsing validity, and usage. Keep every attempt; do not silently trim or resample.
5. Keep the add-on distinct from the frozen main experiment. Do not alter the release tag, learned robot policies, task plans, prompt, or pods A/B. Saved-input calibration needs no robot simulation or new GPU rental. These development replays alone do not establish supervision performance or a final model ranking.

The extracted inputs have already passed all-file hash verification and eight actual probe dry runs covering 54 requests across the original two models, with zero paid calls during validation. Those checks establish packaging and payload construction only; they do not qualify an additional model.
