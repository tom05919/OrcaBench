#!/usr/bin/env bash
# Stage 3 on the GPU worker (design and analysis plan: docs/stage3_plan.md). Run after the setup in docs/compute.md and
# after the Phase 0 checks: `.env` sourced, runs/stage2_reference copied over, PYTHONHASHSEED decided.
#
#   scripts/run_stage3.sh [PHASE ...]      default: every phase in order
#
# workers        start STREAMS policy workers on one GPU (ports BASE_PORT...)
# plain          plain policy on new scenes (privileged stop on success)
# defer_confirm  always-defer on each plain success; confirmed = defer also succeeds from the identical start
# defer_repeat   a second always-defer run on each confirmed pair: the no-intervention noise floor
# opus, sonnet   one LLM episode on each confirmed pair
# reissue        restart-every-100 baseline on each confirmed pair
# repeats        a second Opus episode where the first failed or changed the prompt
# replays        decision replays (exact, native_text, no_interruption) of Opus failures and some rewrite successes
# dose           reissue every 50, 200, 400 steps on the pairs of tasks where an arm failed
# compare        per-arm tables against the plain reference
#
# Jobs are shared by STREAMS streams, one policy worker each. Every attempted episode is kept. No new job starts
# after BUDGET_MINUTES. These are development runs, never scores.
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/project_env.sh

OUT=${OUT:-runs/stage3}
STAGE2_REF=${STAGE2_REF:-runs/stage2_reference}
STREAMS=${STREAMS:-3}
BASE_PORT=${BASE_PORT:-8765}
VIDEO=${VIDEO:-5}
BUDGET_MINUTES=${BUDGET_MINUTES:-330}
NEW_SCENES=${NEW_SCENES:-1003 1004 1005}
NEW_POLICY_SEEDS=${NEW_POLICY_SEEDS:-0,1}
CANDIDATE_CAP=${CANDIDATE_CAP:-6}
CONFIRMED_CAP=${CONFIRMED_CAP:-4}
OPUS=${OPUS:-opus-5-5}
SONNET=${SONNET:-sonnet-5-5}
PLAIN_TASKS=(CloseFridge CloseToasterOvenDoor CoffeeSetupMug KettleBoiling OpenCabinet OpenDrawer
             PickPlaceCounterToCabinet PickPlaceCounterToStove RinseSinkBasin ScrubCuttingBoard TurnOnMicrowave
             TurnOnSinkFaucet WashLettuce)
BIN=.venv-sim/bin/robot-benchmark
PY=.venv-sim/bin/python
SELECT="$PY scripts/select_stage3.py"
START=$(date +%s)
mkdir -p "$OUT"

in_budget() { (( $(date +%s) - START < BUDGET_MINUTES * 60 )); }
stamp() { echo "[$(date -u +%H:%M:%S)] $*"; }
tsv_lines() { [[ -s $1 ]] && grep -c . "$1" || echo 0; }

# One stream: claim the next job line atomically, run it against this stream's policy worker.
stream() {
  local jobs=$1 counter=$2 i=$3 url="http://127.0.0.1:$((BASE_PORT + $3))" n line
  while :; do
    in_budget || { stamp "stream $i: budget reached"; return; }
    n=$( (flock 9; k=$(<"$counter"); echo $((k + 1)) > "$counter"; echo "$k") 9> "$counter.lock" )
    line=$(sed -n "$((n + 1))p" "$jobs")
    [[ -n $line ]] || return
    eval "${line//@URL@/$url}" < /dev/null || stamp "stream $i: nonzero exit: ${line:0:110}"
  done
}

# Run every line of $1 across the streams, then a second pass: with --skip-existing it only redoes episodes that
# ended in an infrastructure error. Pass passes=1 for jobs without --skip-existing.
run_parallel() {
  local jobs=$1 passes=${2:-2} p i
  stamp "jobs: $(tsv_lines "$jobs") from $(basename "$jobs")"
  for ((p = 0; p < passes; p++)); do
    echo 0 > "$jobs.next"
    for ((i = 0; i < STREAMS; i++)); do stream "$jobs" "$jobs.next" "$i" & done
    wait
  done
}

start_workers() {
  local i port
  for ((i = 0; i < STREAMS; i++)); do
    port=$((BASE_PORT + i))
    curl -s -m 3 "localhost:$port/health" > /dev/null && continue
    setsid -f .venv-groot/bin/python -m robot_benchmark.policy_worker --backend groot \
      --checkpoint checkpoints/groot/checkpoint-120000 --port "$port" > "$OUT/worker-$port.log" 2>&1 < /dev/null
  done
  for ((i = 0; i < STREAMS; i++)); do
    until curl -s -m 3 "localhost:$((BASE_PORT + i))/health" > /dev/null; do sleep 5; done
  done
  stamp "$STREAMS policy workers healthy"
}

# Resource log for calibrating how many streams the machine carries (cgroup CPU microseconds, memory, GPU).
monitor() {
  while sleep 15; do
    echo "$(date -u +%T) cpu_usec=$(awk '/usage_usec/{print $2}' /sys/fs/cgroup/cpu.stat 2>/dev/null) mem_mb=$(( $(cat /sys/fs/cgroup/memory.current 2>/dev/null || echo 0) / 1048576 )) gpu=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits | tr -d ' ')"
  done >> "$OUT/resources.log"
}

# The plain run's step-0 state hash for a pair (fourth column of confirmed.tsv or candidates.tsv). Passing it as
# --expect-state ends an episode that builds a different scene before any model call; the second pass redoes it.
expect_flag() {
  local state=${4:-}
  [[ -n $state ]] || state=$(awk -v t="$1" -v s="$2" -v p="$3" '$1==t && $2==s && $3==p {print $4; exit}' "$OUT/confirmed.tsv" 2>/dev/null)
  [[ -n $state ]] && echo "--expect-state $state"
}

llm_jobs() {  # $1 model name (config suffix), $2 tsv of pairs, $3 output directory
  while read -r task scene policy state; do
    echo "$BIN run --task-config configs/tasks/$task.json --agent-config configs/model-$1.dev.json --seeds $scene --policy-seeds $policy $(expect_flag "$task" "$scene" "$policy" "$state") --development --video-record-interval $VIDEO --skip-existing --policy-url @URL@ --output $3"
  done < "$2"
}

baseline_jobs() {  # $1 baseline name, $2 tsv of pairs
  while read -r task scene policy state; do
    echo "$BIN baseline --task-configs configs/tasks/$task.json --scene-seeds $scene --policy-seeds $policy --agent $1 $(expect_flag "$task" "$scene" "$policy" "$state") --video-record-interval $VIDEO --skip-existing --policy-url @URL@ --output $OUT/$1"
  done < "$2"
}

phase_plain() {
  : > "$OUT/jobs.plain"
  local task scene
  for task in "${PLAIN_TASKS[@]}"; do
    for scene in $NEW_SCENES; do
      echo "$BIN screen --task-configs configs/tasks/$task.json --scene-seeds $scene --policy-seeds $NEW_POLICY_SEEDS --mode reference --video-record-interval $VIDEO --skip-existing --policy-url @URL@ --output $OUT/reference" >> "$OUT/jobs.plain"
    done
  done
  run_parallel "$OUT/jobs.plain"
}

phase_defer_confirm() {
  $SELECT candidates --plain-roots "$STAGE2_REF" "$OUT/reference" --cap "$CANDIDATE_CAP" > "$OUT/candidates.tsv"
  baseline_jobs always_defer "$OUT/candidates.tsv" > "$OUT/jobs.defer"
  run_parallel "$OUT/jobs.defer"
  $SELECT confirmed --plain-roots "$STAGE2_REF" "$OUT/reference" --defer-roots "$OUT/always_defer" \
    --cap "$CONFIRMED_CAP" --table "$OUT/confirmed_dropped.json" > "$OUT/confirmed.tsv"
  stamp "candidates $(tsv_lines "$OUT/candidates.tsv"), confirmed $(tsv_lines "$OUT/confirmed.tsv")"
}

phase_defer_repeat() {
  baseline_jobs always_defer "$OUT/confirmed.tsv" | sed "s#--output $OUT/always_defer#--output $OUT/always_defer-r2#" > "$OUT/jobs.defer2"
  run_parallel "$OUT/jobs.defer2"
}
phase_opus() { llm_jobs "$OPUS" "$OUT/confirmed.tsv" "$OUT/$OPUS" > "$OUT/jobs.opus"; run_parallel "$OUT/jobs.opus"; }
phase_sonnet() { llm_jobs "$SONNET" "$OUT/confirmed.tsv" "$OUT/$SONNET" > "$OUT/jobs.sonnet"; run_parallel "$OUT/jobs.sonnet"; }
phase_reissue() { baseline_jobs reissue "$OUT/confirmed.tsv" > "$OUT/jobs.reissue"; run_parallel "$OUT/jobs.reissue"; }

phase_repeats() {
  $SELECT repeats --llm-roots "$OUT/$OPUS" > "$OUT/repeats.tsv"
  llm_jobs "$OPUS" "$OUT/repeats.tsv" "$OUT/$OPUS-r2" > "$OUT/jobs.repeats"
  run_parallel "$OUT/jobs.repeats"
}

phase_replays() {
  local roots=("$OUT/$OPUS") ablation
  [[ -d $OUT/$OPUS-r2 ]] && roots+=("$OUT/$OPUS-r2")
  $SELECT replays --llm-roots "${roots[@]}" --max-successes 8 > "$OUT/replays.tsv"
  : > "$OUT/jobs.replays"
  for ablation in exact native_text no_interruption; do
    while read -r task scene policy folder; do
      echo "$BIN replay --task-config configs/tasks/$task.json --source $folder --ablation $ablation --video-record-interval $VIDEO --policy-url @URL@ --output $OUT/replay_$ablation" >> "$OUT/jobs.replays"
    done < "$OUT/replays.tsv"
  done
  run_parallel "$OUT/jobs.replays" 1
}

phase_dose() {
  $SELECT dose --confirmed-tsv "$OUT/confirmed.tsv" --arm-roots "$OUT/$OPUS" "$OUT/reissue" --max-pairs 12 > "$OUT/dose.tsv"
  : > "$OUT/jobs.dose"
  local agent
  for agent in reissue_50 reissue_200 reissue_400; do baseline_jobs "$agent" "$OUT/dose.tsv" >> "$OUT/jobs.dose"; done
  run_parallel "$OUT/jobs.dose"
}

phase_compare() {
  local system
  for system in "$OPUS" "$OPUS-r2" "$SONNET" always_defer always_defer-r2 reissue reissue_50 reissue_200 reissue_400 replay_exact replay_native_text replay_no_interruption; do
    [[ -d $OUT/$system ]] || continue
    $PY scripts/compare_to_reference.py --reference-root "$STAGE2_REF" "$OUT/reference" --model-root "$OUT/$system" \
      --output "$OUT/compare-$system.json" > "$OUT/compare-$system.txt" 2>&1 || stamp "compare failed for $system"
  done
}

[[ -n ${ANTHROPIC_API_KEY:-} ]] || { echo "ANTHROPIC_API_KEY is not set; source .env first" >&2; exit 2; }
for model in "$OPUS" "$SONNET"; do
  [[ -f configs/model-$model.dev.json ]] || { echo "missing configs/model-$model.dev.json" >&2; exit 2; }
done
monitor &
trap 'kill $(jobs -p) 2>/dev/null' EXIT

phases=("$@")
(( ${#phases[@]} )) || phases=(workers plain defer_confirm defer_repeat opus sonnet reissue repeats replays dose compare)
for phase in "${phases[@]}"; do
  stamp "phase $phase"
  if [[ $phase == workers ]]; then start_workers; else "phase_$phase"; fi
done
stamp "done"
