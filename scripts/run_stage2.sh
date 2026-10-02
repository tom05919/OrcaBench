#!/usr/bin/env bash
# Stage 2 development comparison on the GPU worker. Run after the setup in
# docs/compute.md: policy worker up, `doctor` passed, `.env` sourced.
#
# For each of the eight stage 1 (task, scene) pairs at policy seed 0, run, in
# this order and interleaved so a dead pod still leaves complete pairs:
#   1. the plain-policy reference (privileged stop), fresh under this code;
#   2. the always-defer baseline (public, no API cost);
#   3. each model in MODELS (default Opus 5.5; add sonnet-5-5 to rerun Sonnet
#      under the same reply contract).
# Every attempted episode is kept. These are llm_development runs, not scores.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/project_env.sh

OUT=${OUT:-runs/stage2}
MODELS=${MODELS:-opus-5-5}
POLICY_SEED=${POLICY_SEED:-0}
BIN=.venv-sim/bin/robot-benchmark
PAIRS=(
  "CloseFridge 1000" "KettleBoiling 1000" "PickPlaceCounterToStove 1000" "ScrubCuttingBoard 1000"
  "KettleBoiling 1001" "OpenDrawer 1000" "PickPlaceCounterToCabinet 1001" "TurnOffStove 1000"
)

for model in $MODELS; do
  [[ -f configs/model-$model.dev.json ]] || { echo "missing configs/model-$model.dev.json" >&2; exit 2; }
done
[[ -n "${ANTHROPIC_API_KEY:-}" ]] || { echo "ANTHROPIC_API_KEY is not set; source .env first" >&2; exit 2; }

for pair in "${PAIRS[@]}"; do
  read -r task scene <<<"$pair"
  config=configs/tasks/$task.json
  "$BIN" screen --task-configs "$config" --scene-seeds "$scene" --policy-seeds "$POLICY_SEED" \
    --mode reference --skip-existing --output "$OUT/reference"
  "$BIN" baseline --task-configs "$config" --scene-seeds "$scene" --policy-seeds "$POLICY_SEED" \
    --agent always_defer --skip-existing --output "$OUT/always_defer"
  for model in $MODELS; do
    "$BIN" run --task-config "$config" --agent-config "configs/model-$model.dev.json" \
      --seeds "$scene" --policy-seeds "$POLICY_SEED" --development --skip-existing --output "$OUT/$model"
  done
done

for system in always_defer $MODELS; do
  .venv-sim/bin/python scripts/compare_to_reference.py --reference-root "$OUT/reference" \
    --model-root "$OUT/$system" --output "$OUT/compare-$system.json"
done
