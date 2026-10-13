#!/usr/bin/env bash
# Stage 6 ladder, third policy (docs/stage6_ladder.md): the plain groot_pretrain checkpoint on the five leave-alone
# tasks, the cells the ladder run left untested. Same grid and settings as scripts/run_stage6_ladder.sh, via
# scripts/run_stage4.sh (plain phase). Run after the setup in docs/compute.md and
# `scripts/download_checkpoint.py --backend groot_pretrain`. No model calls. Writes runs/stage6_pretrain/PIPELINE_DONE
# when the driver has finished, for scripts/pod_guard.sh.
#
#   scripts/run_stage6_pretrain.sh            build check, then the driver
#
# Streams: four policy workers (about 31 GB of GPU memory).
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/project_env.sh

ROOT=runs/stage6_pretrain
LEAVE="OpenCabinet PickPlaceCounterToCabinet PickPlaceCounterToStove CloseFridge OpenDrawer"
BUDGET=${BUDGET_MINUTES:-120}
mkdir -p "$ROOT"
rm -f "$ROOT/PIPELINE_DONE"
trap 'echo "$? $(date -u +%FT%TZ)" > "$ROOT/PIPELINE_DONE"' EXIT
stamp() { echo "[$(date -u +%H:%M:%S)] $*" >> "$ROOT/driver.log"; }

stamp "build start"
for seed in 1000 1001 1002 1003; do
  .venv-sim/bin/python scripts/check_task_pool.py --seed $seed --tasks $LEAVE \
    --output "$ROOT/build-$seed.json" > "$ROOT/build-$seed.log" 2>&1 &
done
wait
stamp "build done"

stamp "driver started"
OUT=$ROOT/groot_pretrain BACKEND=groot_pretrain CHECKPOINT=checkpoints/groot_pretrain/checkpoint-80000 BASE_PORT=8765 \
  STREAMS=4 SCENES="1000 1001 1002 1003" TASK_LIST="$LEAVE" POLICY_SEEDS=0,1 VIDEO=10 BUDGET_MINUTES=$BUDGET \
  scripts/run_stage4.sh workers plain >> "$ROOT/groot_pretrain.log" 2>&1 < /dev/null
stamp "driver done"
