#!/usr/bin/env bash
# Stage 6 ladder, π0.5 (docs/stage6_ladder.md; docs/final_experiment.md freeze step 0): the plain pi05 checkpoint
# on the ladder's grid, via scripts/run_stage4.sh. pi05 had not run in this project before this ladder, so one plain smoke episode runs
# first and stops the run if it ends in an infrastructure error. Run after the setup in docs/compute.md and
# `scripts/bootstrap_gpu.py --include-pi05 --download-pi05-checkpoint`. No model calls. Writes
# runs/stage6_pi05/PIPELINE_DONE when the driver has finished, for scripts/pod_guard.sh.
#
#   scripts/run_stage6_pi05.sh            build check, then the driver
#
# Streams: four pi05 workers on one GPU (run_stage4.sh turns off JAX's 75% memory preallocation for pi05).
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/project_env.sh

ROOT=runs/stage6_pi05
# One line: run_stage4.sh reads TASK_LIST with `read -a`, which stops at the first newline (the October 15 run lost
# ArrangeTea to a wrapped list and ran it separately afterwards).
STORY="MakeIceLemonade SeparateFreezerRack PanTransfer PortionHotDogs GarnishPancake HeatKebabSandwich WaffleReheat ArrangeTea"
LEAVE="OpenCabinet PickPlaceCounterToCabinet PickPlaceCounterToStove CloseFridge OpenDrawer"
BUDGET=${BUDGET_MINUTES:-200}
mkdir -p "$ROOT"
rm -f "$ROOT/PIPELINE_DONE"
trap 'echo "$? $(date -u +%FT%TZ)" > "$ROOT/PIPELINE_DONE"' EXIT
stamp() { echo "[$(date -u +%H:%M:%S)] $*" >> "$ROOT/driver.log"; }

# configs/requirements-pi05.txt pins the environment that ran this ladder on October 15 (it was rebuilt here from
# openpi's uv.lock then; docs/stage6_ladder.md). Check it before any build or episode: the imports, the training
# config, the worker and a JAX GPU device.
pi05_check() {
  .venv-pi05/bin/python -c "from openpi.policies import policy_config; from openpi.training import config
config.get_config('pi05_pretrain_human300'); import robot_benchmark.policy_worker" &&
  XLA_PYTHON_CLIENT_PREALLOCATE=false .venv-pi05/bin/python -c "import jax
assert any(d.platform == 'gpu' for d in jax.devices()), jax.devices()"
}
pi05_check >> "$ROOT/driver.log" 2>&1 || { stamp "pi05 environment check failed; stopping"; exit 1; }
stamp "pi05 environment checked"

stamp "build start"
for seed in 1000 1001 1002 1003; do
  .venv-sim/bin/python scripts/check_task_pool.py --seed $seed --tasks $STORY $LEAVE \
    --output "$ROOT/build-$seed.json" > "$ROOT/build-$seed.log" 2>&1 &
done
wait
stamp "build done"

# The smoke episode is the first task (OpenCabinet, short) at scene 1000, policy seed 0, kept in smoke/, not counted.
stamp "driver started"
OUT=$ROOT/pi05 BACKEND=pi05 CHECKPOINT=checkpoints/pi05/75000 BASE_PORT=8765 STREAMS=4 SMOKE_MODE=reference \
  SCENES="1000 1001 1002 1003" TASK_LIST="$LEAVE $STORY" POLICY_SEEDS=0,1 VIDEO=10 BUDGET_MINUTES=$BUDGET \
  scripts/run_stage4.sh workers smoke plain >> "$ROOT/pi05.log" 2>&1 < /dev/null
status=$?
stamp "driver done ($status)"
exit $status
