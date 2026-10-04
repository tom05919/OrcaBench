#!/usr/bin/env bash
# Stage 2 harm-diagnosis run on the GPU worker. Run after the setup in docs/compute.md: policy worker up, `doctor`
# passed, `.env` sourced. See docs/stage2_agent_prompt.md for the design.
#
# Phase 1: plain policy (privileged stop on success) on every pool task, SCENES x POLICY_SEEDS.
# Phase 2: select, by a rule fixed in advance, up to PER_TASK pairs per task where the plain policy succeeded.
# Phase 3: on exactly those (task, scene, policy seed) pairs run, in priority order, the LLM, always-defer and
#          reissue. Harm = plain succeeded, the LLM did not. All are development runs, not scores.
# Every attempted episode is kept. No new episode starts after BUDGET_MINUTES; reissue is cut first.
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/project_env.sh

OUT=${OUT:-runs/stage2}
SCENES=${SCENES:-1000,1001,1002}
POLICY_SEEDS=${POLICY_SEEDS:-0,1}
PER_TASK=${PER_TASK:-2}
VIDEO=${VIDEO:-5}
MODEL=${MODEL:-opus-5-5}
BUDGET_MINUTES=${BUDGET_MINUTES:-225}
BIN=.venv-sim/bin/robot-benchmark
START=$(date +%s)
mkdir -p "$OUT"

[[ -f configs/model-$MODEL.dev.json ]] || { echo "missing configs/model-$MODEL.dev.json" >&2; exit 2; }
[[ -n "${ANTHROPIC_API_KEY:-}" ]] || { echo "ANTHROPIC_API_KEY is not set; source .env first" >&2; exit 2; }

in_budget() { (( $(date +%s) - START < BUDGET_MINUTES * 60 )); }
stamp() { echo "[$(date -u +%H:%M:%S)] $*"; }

stamp "phase 1: plain policy, scenes $SCENES, policy seeds $POLICY_SEEDS"
for config in configs/tasks/*.json; do
  in_budget || { stamp "budget reached, stopping phase 1"; break; }
  "$BIN" screen --task-configs "$config" --scene-seeds "$SCENES" --policy-seeds "$POLICY_SEEDS" \
    --mode reference --video-record-interval "$VIDEO" --skip-existing --output "$OUT/reference" \
    || stamp "screen exited nonzero for $config"
done

stamp "phase 2: selection"
.venv-sim/bin/python scripts/select_stage2.py --reference-root "$OUT/reference" --per-task "$PER_TASK" \
  --output "$OUT/selection.json" > "$OUT/selection.tsv"
cat "$OUT/selection.tsv"

# Priority order: the LLM first, so a cut run still has complete LLM pairs.
for arm in llm always_defer reissue; do
  stamp "phase 3: $arm"
  while read -r task scene policy; do
    in_budget || { stamp "budget reached, stopping $arm"; break; }
    config=configs/tasks/$task.json
    if [[ $arm == llm ]]; then
      "$BIN" run --task-config "$config" --agent-config "configs/model-$MODEL.dev.json" --seeds "$scene" \
        --policy-seeds "$policy" --development --video-record-interval "$VIDEO" --skip-existing \
        --output "$OUT/$MODEL" < /dev/null || stamp "run exited nonzero for $task $scene $policy"
    else
      "$BIN" baseline --task-configs "$config" --scene-seeds "$scene" --policy-seeds "$policy" --agent "$arm" \
        --video-record-interval "$VIDEO" --skip-existing --output "$OUT/$arm" < /dev/null \
        || stamp "baseline exited nonzero for $arm $task $scene $policy"
    fi
  done < "$OUT/selection.tsv"
done

for system in "$MODEL" always_defer reissue; do
  [[ -d $OUT/$system ]] || continue
  .venv-sim/bin/python scripts/compare_to_reference.py --reference-root "$OUT/reference" \
    --model-root "$OUT/$system" --output "$OUT/compare-$system.json" > "$OUT/compare-$system.txt" \
    || stamp "compare failed for $system"
done
stamp "done"
