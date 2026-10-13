#!/usr/bin/env bash
# Stage 6 ceiling test on the GPU worker (docs/stage6_ceiling.md): can correct step-by-step instructions rescue the
# plain policy's failures on the unseen tasks? Per backend, via scripts/run_stage4.sh: one sequencer smoke episode,
# the plain reference, then the privileged sequencer on every usable plain episode with its step-0 state hash.
# Run after the setup in docs/compute.md and `scripts/download_checkpoint.py --backend groot_u30`. No model calls.
# Writes runs/stage6_ceiling/PIPELINE_DONE when every driver has finished, for scripts/pod_guard.sh.
#
#   scripts/run_stage6_ceiling.sh            build and trigger check, then both drivers in parallel
#
# Streams: four policy workers per checkpoint, eight in all (six took about 49 GB in the ladder run, so this needs
# an 80 GB GPU). Both arms of a pair run on this pod, so their start states match.
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/project_env.sh

ROOT=runs/stage6_ceiling
TASKS="PortionHotDogs GarnishPancake MakeIceLemonade SeparateFreezerRack PanTransfer"
TRIGGER_TASKS="MakeIceLemonade PanTransfer"  # ice_out_of_bowl and pan_off_stove must be false at step 0
BUDGET=${BUDGET_MINUTES:-240}
mkdir -p "$ROOT"
rm -f "$ROOT/PIPELINE_DONE"
trap 'echo "$? $(date -u +%FT%TZ)" > "$ROOT/PIPELINE_DONE"' EXIT
stamp() { echo "[$(date -u +%H:%M:%S)] $*" >> "$ROOT/driver.log"; }

# Every task must build at the four scenes; the trigger tasks are also checked over the whole evaluation range
# (configs/splits.json), four builds at a time.
stamp "build start"
for seed in $(seq 1000 1019); do
  tasks=$TRIGGER_TASKS
  (( seed <= 1003 )) && tasks=$TASKS
  .venv-sim/bin/python scripts/check_task_pool.py --seed "$seed" --tasks $tasks \
    --output "$ROOT/build-$seed.json" > "$ROOT/build-$seed.log" 2>&1 &
  (( (seed - 999) % 4 )) || wait
done
wait
stamp "build done"

# driver NAME BACKEND CHECKPOINT BASE_PORT
driver() {
  OUT=$ROOT/$1 BACKEND=$2 CHECKPOINT=$3 BASE_PORT=$4 STREAMS=4 SCENES="1000 1001 1002 1003" TASK_LIST="$TASKS" \
    POLICY_SEEDS=0,1 VIDEO=10 BUDGET_MINUTES=$BUDGET scripts/run_stage4.sh workers smoke plain sequencer \
    >> "$ROOT/$1.log" 2>&1 < /dev/null
}
pids=()
driver groot groot checkpoints/groot/checkpoint-120000 8765 &
pids+=($!)
driver groot_u30 groot_u30 checkpoints/groot_u30/composite_unseen_30p 8775 &
pids+=($!)
stamp "drivers started"
wait "${pids[@]}"
stamp "drivers done"
