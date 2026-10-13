#!/usr/bin/env bash
# Stage 6 policy ladder on the GPU worker (docs/stage6_ladder.md): plain GR00T checkpoints of different ability on the
# time-story unseen tasks and on leave-alone trained tasks, all on one pod, via scripts/run_stage4.sh (plain phase).
# Run after the setup in docs/compute.md and `scripts/download_checkpoint.py --backend groot_10p` / `groot_30p`.
# No model calls. Writes runs/stage6_ladder/PIPELINE_DONE when every driver has finished, for scripts/pod_guard.sh.
#
#   scripts/run_stage6_ladder.sh            build check, then the three drivers in parallel
#
# Streams: two policy workers per checkpoint, six in all (four took about 35 GB in stage 4, so this needs an 80 GB
# GPU). Every checkpoint runs the same grid on the same pod, so their start states are comparable.
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/project_env.sh

ROOT=runs/stage6_ladder
STORY="MakeIceLemonade SeparateFreezerRack PanTransfer PortionHotDogs GarnishPancake HeatKebabSandwich WaffleReheat ArrangeTea"
LEAVE="OpenCabinet PickPlaceCounterToCabinet PickPlaceCounterToStove CloseFridge OpenDrawer"
BUDGET=${BUDGET_MINUTES:-240}
mkdir -p "$ROOT"
rm -f "$ROOT/PIPELINE_DONE"
trap 'echo "$? $(date -u +%FT%TZ)" > "$ROOT/PIPELINE_DONE"' EXIT
stamp() { echo "[$(date -u +%H:%M:%S)] $*" >> "$ROOT/driver.log"; }

# Every story task must build at every scene before any episode runs; stage 5 only checked scenes 1000-1001.
stamp "build start"
for seed in 1000 1001 1002 1003; do
  .venv-sim/bin/python scripts/check_task_pool.py --seed $seed --tasks $STORY $LEAVE \
    --output "$ROOT/build-$seed.json" > "$ROOT/build-$seed.log" 2>&1 &
done
wait
stamp "build done"

# driver NAME BACKEND CHECKPOINT BASE_PORT STREAMS SCENES TASKS
driver() {
  OUT=$ROOT/$1 BACKEND=$2 CHECKPOINT=$3 BASE_PORT=$4 STREAMS=$5 SCENES=$6 TASK_LIST=$7 POLICY_SEEDS=0,1 VIDEO=10 \
    BUDGET_MINUTES=$BUDGET scripts/run_stage4.sh workers plain >> "$ROOT/$1.log" 2>&1 < /dev/null
}
pids=()
driver groot_10p groot_10p checkpoints/groot_10p/composite_unseen_10p 8765 2 "1000 1001 1002 1003" "$LEAVE $STORY" &
pids+=($!)
driver groot_30p groot_30p checkpoints/groot_30p/composite_unseen_30p 8775 2 "1000 1001 1002 1003" "$LEAVE $STORY" &
pids+=($!)
driver groot groot checkpoints/groot/checkpoint-120000 8785 2 "1000 1001 1002 1003" "$LEAVE $STORY" &
pids+=($!)
stamp "drivers started"
wait "${pids[@]}"
stamp "drivers done"
