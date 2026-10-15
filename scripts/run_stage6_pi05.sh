#!/usr/bin/env bash
# Stage 6 ladder, π0.5 (docs/stage6_ladder.md; docs/final_experiment.md freeze step 0): the plain pi05 checkpoint
# on the ladder's grid, via scripts/run_stage4.sh. pi05 has never run in this project, so one plain smoke episode runs
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
STORY="MakeIceLemonade SeparateFreezerRack PanTransfer PortionHotDogs GarnishPancake HeatKebabSandwich WaffleReheat
  ArrangeTea"
LEAVE="OpenCabinet PickPlaceCounterToCabinet PickPlaceCounterToStove CloseFridge OpenDrawer"
BUDGET=${BUDGET_MINUTES:-200}
mkdir -p "$ROOT"
rm -f "$ROOT/PIPELINE_DONE"
trap 'echo "$? $(date -u +%FT%TZ)" > "$ROOT/PIPELINE_DONE"' EXIT
stamp() { echo "[$(date -u +%H:%M:%S)] $*" >> "$ROOT/driver.log"; }

# configs/requirements-pi05.txt lists openpi's direct dependencies without its lock, so a fresh resolve drifts far from
# what openpi tested (October 14: 34 lock packages missing, 125 at other versions). Both pi05 attempts died at import:
# first on pytest (openpi's dev group, imported by gemma_pytorch.py), then on chex (pulled in only by the locked optax
# 0.2.4). openpi's training config also imports robocasa (groot_utils), which bootstrap leaves out of .venv-pi05, and
# robocasa asserts numpy 2.2.5 and mujoco 3.3.1 at import. Upstream installs openpi into the RoboCasa environment, so
# until those files are fixed, rebuild .venv-pi05 from the pinned openpi's uv.lock plus robocasa's and robosuite's
# requirements (configs/requirements-sim.txt, robocasa's pins winning; lerobot stays at openpi's commit; tianshou is
# left out because nothing on this path imports it and it needs protobuf 3), then the editable installs of
# scripts/bootstrap_gpu.py plus robosuite and robocasa. Verified on a Mac (CPU jax) on October 14: the imports and
# config.get_config('pi05_pretrain_human300') load. av is overridden to 14.2.0 because PyPI now has only the source
# tarball of the locked 14.4.0, which fails to build without ffmpeg 7 (October 15); openpi and robocasa import av only
# to decode training videos.
OPENPI=vendor/src/openpi
pi05_env() {
  (cd "$OPENPI" && uv export --frozen --no-dev --no-emit-workspace --no-hashes --no-header) > "$ROOT/openpi-lock.txt" &&
  grep -vE '^(numpy|mujoco|lerobot|tianshou|pytest)\b' configs/requirements-sim.txt > "$ROOT/robocasa-extra.txt" &&
  printf 'numpy==2.2.5\nmujoco==3.3.1\nav==14.2.0\n' > "$ROOT/overrides.txt" &&
  uv venv --clear --python 3.11 .venv-pi05 &&
  uv pip install --python .venv-pi05/bin/python -r "$ROOT/openpi-lock.txt" -r "$ROOT/robocasa-extra.txt" \
    --override "$ROOT/overrides.txt" pytest==8.3.5 &&
  uv pip install --python .venv-pi05/bin/python --no-deps -e "$OPENPI/packages/openpi-client" -e "$OPENPI" \
    -e vendor/src/robosuite -e vendor/src/robocasa -e . &&
  uv pip freeze --python .venv-pi05/bin/python > "$ROOT/pi05-freeze.txt" &&
  .venv-pi05/bin/python -c "from openpi.policies import policy_config; from openpi.training import config
config.get_config('pi05_pretrain_human300'); import robot_benchmark.policy_worker" &&
  XLA_PYTHON_CLIENT_PREALLOCATE=false .venv-pi05/bin/python -c "import jax
assert any(d.platform == 'gpu' for d in jax.devices()), jax.devices()"
}
pi05_env >> "$ROOT/driver.log" 2>&1 || { stamp "pi05 environment from openpi's lock failed; stopping"; exit 1; }
stamp "pi05 environment rebuilt from openpi's lock"

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
