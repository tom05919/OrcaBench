#!/bin/bash
# Stage 5 on the GPU worker (docs/stage5_plan.md): build check of the 16 unseen composite tasks at scenes 1000-1001,
# then the plain phase for both GR00T checkpoints in parallel, two policy workers each, via scripts/run_stage4.sh.
# Run after the setup in docs/compute.md and `scripts/download_checkpoint.py --backend groot_pretrain`. No model calls.
cd ~/robot_benchmark; export PATH="$HOME/.local/bin:$PATH"
source scripts/project_env.sh
TASKS="ArrangeBreadBasket ArrangeTea BreadSelection CategorizeCondiments CuttingToolSelection GarnishPancake GatherTableware HeatKebabSandwich MakeIceLemonade PanTransfer PortionHotDogs RecycleBottlesByType SeparateFreezerRack WaffleReheat WashFruitColander WeighIngredients"
mkdir -p runs/stage5
{
  echo "build start $(date -u +%FT%TZ)"
  for seed in 1000 1001; do
    .venv-sim/bin/python scripts/check_task_pool.py --seed $seed --tasks $TASKS --output runs/stage5/build-$seed.json \
      > runs/stage5/build-$seed.log 2>&1 &
  done
  wait
  echo "build done $(date -u +%FT%TZ)"
} > runs/stage5/driver.log 2>&1
common="TASK_LIST='$TASKS' SCENES='1000 1001' POLICY_SEEDS=0,1 VIDEO=10 STREAMS=2 BUDGET_MINUTES=${BUDGET_MINUTES:-270}"
eval "$common OUT=runs/stage5/groot BACKEND=groot CHECKPOINT=checkpoints/groot/checkpoint-120000 BASE_PORT=8765 \
  setsid -f scripts/run_stage4.sh workers plain > runs/stage5/groot.log 2>&1 < /dev/null"
eval "$common OUT=runs/stage5/groot_pretrain BACKEND=groot_pretrain CHECKPOINT=checkpoints/groot_pretrain/checkpoint-80000 \
  BASE_PORT=8775 setsid -f scripts/run_stage4.sh workers plain > runs/stage5/groot_pretrain.log 2>&1 < /dev/null"
echo "drivers started $(date -u +%FT%TZ)" >> runs/stage5/driver.log
