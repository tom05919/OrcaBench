#!/usr/bin/env bash
# Stage 4 on the GPU worker: does a restart or a new wording ever rescue a plain-policy failure? Design, selection
# rule and analysis are fixed in docs/stage4_plan.md. Run after the setup in docs/compute.md, with `.env` sourced.
#
#   scripts/run_stage4.sh [PHASE ...]      default: every phase in order
#
# workers   start STREAMS policy workers on one GPU (ports BASE_PORT...)
# plain     plain policy, all 16 pool tasks x SCENES x POLICY_SEEDS, privileged stop on success
# select    failure pairs: (task, scene) where every plain episode failed, at the lowest policy seed, CAP per task
#           (select_stage3.py rescue), with the plain run's step-0 state hash
# defer     always_defer on each failure pair: continue, never restart (also checks the failure reproduces)
# reissue   reissue_50, reissue (100), reissue_200: restart with the native wording at fixed intervals
# opus      Opus 5.5 on each failure pair: it chooses when to restart and what to say
# replays   every Opus episode replayed with no model: exact, native_text, no_interruption
# compare   per-arm tables against the plain reference
# smoke     one sequencer episode (first task, first scene, policy seed 0) in $OUT/smoke; stops the run if it ends in
#           an infrastructure error (the sequencer had never run on a GPU before stage 6)
# sequencer stage 6 ceiling test (docs/stage6_ceiling.md): the privileged sequencer on every usable plain episode,
#           same scene and policy seed, with the plain run's step-0 state hash (not part of the default phases)
#
# Every phase syncs $OUT to the Hugging Face bucket when HF_DEST is set (scripts/pod_sync.sh), and the script writes
# $OUT/PIPELINE_DONE on exit so scripts/pod_guard.sh can upload and terminate the pod. Every attempted episode is
# kept. No new job starts after BUDGET_MINUTES. These are development runs, never scores.
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/project_env.sh

OUT=${OUT:-runs/stage4}
STREAMS=${STREAMS:-4}
BASE_PORT=${BASE_PORT:-8765}
VIDEO=${VIDEO:-5}
BUDGET_MINUTES=${BUDGET_MINUTES:-330}
SCENES=${SCENES:-1000 1001 1002 1003}
POLICY_SEEDS=${POLICY_SEEDS:-0,1}
CAP=${CAP:-2}
OPUS=${OPUS:-opus-5-5}
REISSUE=${REISSUE:-reissue_50 reissue reissue_200}
TASKS=(CloseFridge CloseToasterOvenDoor CoffeeSetupMug KettleBoiling LoadDishwasher OpenCabinet OpenDrawer
       PickPlaceCounterToCabinet PickPlaceCounterToStove PrepareCoffee RinseSinkBasin ScrubCuttingBoard TurnOffStove
       TurnOnMicrowave TurnOnSinkFaucet WashLettuce)
[[ -z ${TASK_LIST:-} ]] || read -r -a TASKS <<< "$TASK_LIST"
BACKEND=${BACKEND:-groot}  # stage 5 also runs groot_pretrain (checkpoints/groot_pretrain/checkpoint-80000)
CHECKPOINT=${CHECKPOINT:-checkpoints/groot/checkpoint-120000}
BIN=${BIN:-.venv-sim/bin/robot-benchmark}
PY=${PY:-.venv-sim/bin/python}
START=$(date +%s)
mkdir -p "$OUT"
rm -f "$OUT/PIPELINE_DONE"

in_budget() { (( $(date +%s) - START < BUDGET_MINUTES * 60 )); }
stamp() { echo "[$(date -u +%H:%M:%S)] $*"; }
tsv_lines() { [[ -s $1 ]] && grep -c . "$1" || echo 0; }
sync_out() { [[ -z ${HF_DEST:-} ]] || scripts/pod_sync.sh "$OUT" "$HF_DEST" || stamp "sync failed after $1"; }

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
  local jobs=$1 passes=${2:-2} p i pids
  stamp "jobs: $(tsv_lines "$jobs") from $(basename "$jobs")"
  for ((p = 0; p < passes; p++)); do
    echo 0 > "$jobs.next"
    pids=()
    for ((i = 0; i < STREAMS; i++)); do stream "$jobs" "$jobs.next" "$i" & pids+=($!); done
    wait "${pids[@]}"  # the streams only: a bare wait would also wait for the resource monitor, which never ends
  done
}

start_workers() {
  local i port
  for ((i = 0; i < STREAMS; i++)); do
    port=$((BASE_PORT + i))
    curl -s -m 3 "localhost:$port/health" > /dev/null && continue
    setsid -f .venv-groot/bin/python -m robot_benchmark.policy_worker --backend "$BACKEND" \
      --checkpoint "$CHECKPOINT" --port "$port" > "$OUT/worker-$port.log" 2>&1 < /dev/null
  done
  for ((i = 0; i < STREAMS; i++)); do
    until curl -s -m 3 "localhost:$((BASE_PORT + i))/health" > /dev/null; do sleep 5; done
  done
  stamp "$STREAMS policy workers healthy"
}

monitor() {
  while sleep 15; do
    echo "$(date -u +%T) cpu_usec=$(awk '/usage_usec/{print $2}' /sys/fs/cgroup/cpu.stat 2>/dev/null) mem_mb=$(( $(cat /sys/fs/cgroup/memory.current 2>/dev/null || echo 0) / 1048576 )) gpu=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits | tr -d ' ')"
  done >> "$OUT/resources.log"
}

# Lines of failures.tsv are: task scene policy state. Every arm passes the plain run's step-0 state hash, so an
# episode that builds a different scene ends before any model call and the second pass redoes it.
pair_jobs() {  # $1 command prefix up to the seeds, $2 output directory
  while read -r task scene policy state; do
    echo "$BIN $1 --task-config$([[ $1 == baseline* ]] && echo s) configs/tasks/$task.json $([[ $1 == baseline* ]] && echo "--scene-seeds $scene" || echo "--seeds $scene") --policy-seeds $policy ${state:+--expect-state $state} --video-record-interval $VIDEO --skip-existing --policy-url @URL@ --output $2"
  done < "$OUT/failures.tsv"
}

phase_plain() {
  : > "$OUT/jobs.plain"
  local task scene
  for task in "${TASKS[@]}"; do
    for scene in $SCENES; do
      echo "$BIN screen --task-configs configs/tasks/$task.json --scene-seeds $scene --policy-seeds $POLICY_SEEDS --mode reference --video-record-interval $VIDEO --skip-existing --policy-url @URL@ --output $OUT/reference" >> "$OUT/jobs.plain"
    done
  done
  run_parallel "$OUT/jobs.plain"
}

phase_select() {
  $PY scripts/select_stage3.py rescue --plain-roots "$OUT/reference" --cap "$CAP" > "$OUT/failures.tsv"
  stamp "failure pairs: $(tsv_lines "$OUT/failures.tsv")"
}

phase_defer() { pair_jobs "baseline --agent always_defer" "$OUT/always_defer" > "$OUT/jobs.defer"; run_parallel "$OUT/jobs.defer"; }

phase_reissue() {
  : > "$OUT/jobs.reissue"
  local agent
  for agent in $REISSUE; do pair_jobs "baseline --agent $agent" "$OUT/$agent" >> "$OUT/jobs.reissue"; done
  run_parallel "$OUT/jobs.reissue"
}

phase_opus() {
  pair_jobs "run --agent-config configs/model-$OPUS.dev.json --development" "$OUT/$OPUS" > "$OUT/jobs.opus"
  run_parallel "$OUT/jobs.opus"
}

phase_replays() {
  # Every Opus episode: failures and successes alike, since a success here is the candidate rescue.
  $PY scripts/select_stage3.py replays --llm-roots "$OUT/$OPUS" --max-successes 999 > "$OUT/replays.tsv"
  : > "$OUT/jobs.replays"
  local ablation
  for ablation in exact native_text no_interruption; do
    while read -r task scene policy folder; do
      echo "$BIN replay --task-config configs/tasks/$task.json --source $folder --ablation $ablation --video-record-interval $VIDEO --policy-url @URL@ --output $OUT/replay_$ablation" >> "$OUT/jobs.replays"
    done < "$OUT/replays.tsv"
  done
  run_parallel "$OUT/jobs.replays" 1
}

phase_smoke() {
  local task=${TASKS[0]} scene=${SCENES%% *} status
  $BIN screen --mode sequencer --task-configs "configs/tasks/$task.json" --scene-seeds "$scene" --policy-seeds 0 \
    --video-record-interval "$VIDEO" --policy-url "http://127.0.0.1:$BASE_PORT" --output "$OUT/smoke" < /dev/null
  status=$($PY -c 'import glob, json, sys; print(*(json.load(open(f))["status"] for f in glob.glob(sys.argv[1] + "/*/*/result.json")))' "$OUT/smoke")
  stamp "smoke $task $scene: ${status:-no result}"
  [[ -n $status && $status != *infrastructure_error* ]] || { stamp "smoke failed; stopping"; exit 1; }
}

phase_sequencer() {
  # Every usable plain episode (latest per task, scene and policy seed), as task scene policy state.
  $PY - "$OUT/reference" > "$OUT/pairs.tsv" <<'PY'
import sys
sys.path.insert(0, "scripts")
from select_stage3 import collect
for (task, scene, policy), episode in sorted(collect([sys.argv[1]]).items()):
    if episode["state"]:
        print(task, scene, policy, episode["state"])
PY
  stamp "sequencer pairs: $(tsv_lines "$OUT/pairs.tsv")"
  : > "$OUT/jobs.sequencer"
  local task scene policy state
  while read -r task scene policy state; do
    echo "$BIN screen --mode sequencer --task-configs configs/tasks/$task.json --scene-seeds $scene --policy-seeds $policy --expect-state $state --video-record-interval $VIDEO --skip-existing --policy-url @URL@ --output $OUT/sequencer" >> "$OUT/jobs.sequencer"
  done < "$OUT/pairs.tsv"
  run_parallel "$OUT/jobs.sequencer"
}

phase_compare() {
  local system
  for system in always_defer $REISSUE "$OPUS" replay_exact replay_native_text replay_no_interruption; do
    [[ -d $OUT/$system ]] || continue
    $PY scripts/compare_to_reference.py --reference-root "$OUT/reference" --model-root "$OUT/$system" \
      --output "$OUT/compare-$system.json" > "$OUT/compare-$system.txt" 2>&1 || stamp "compare failed for $system"
  done
}

phases=("$@")
(( ${#phases[@]} )) || phases=(workers plain select defer reissue opus replays compare)
if [[ " ${phases[*]} " == *" opus "* ]]; then  # only the opus phase calls a model
  [[ -n ${ANTHROPIC_API_KEY:-} ]] || { echo "ANTHROPIC_API_KEY is not set; source .env first" >&2; exit 2; }
  [[ -f configs/model-$OPUS.dev.json ]] || { echo "missing configs/model-$OPUS.dev.json" >&2; exit 2; }
fi
monitor &
trap 'status=$?; kill $(jobs -p) 2>/dev/null; echo "$status $(date -u +%FT%TZ)" > "$OUT/PIPELINE_DONE"' EXIT
for phase in "${phases[@]}"; do
  stamp "phase $phase"
  if [[ $phase == workers ]]; then start_workers; else "phase_$phase"; fi
  sync_out "$phase"
done
stamp "done"
