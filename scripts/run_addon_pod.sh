#!/usr/bin/env bash
# Add-on pod (docs/addon_open_models.md): open-model supervisors on the final experiment's cells, post-freeze, as
# development runs reported separately from the primary result. Run after the setup in docs/compute.md (with
# `bootstrap_gpu.py --include-pi05 --download-pi05-checkpoint` and the groot_u30 checkpoint), with `.env` sourced.
#
#   scripts/run_addon_pod.sh [PHASE ...]      default: workers defer pair sessions
#
# workers   SETS sets of three policy workers (groot, groot_u30, pi05); set k uses ports BASE_PORT + 3k + {0, 1, 2}
# defer     always_defer on every final cell (3 backends x 7 tasks x 4 scenes, policy seed 0): this pod's twins
# pair      scripts' `pair-session`: each final plan gets this pod's always-defer step-0 state hashes
# sessions  one session per scene per model in MODELS, SETS at a time, each on its own worker set and output root
#
# The sessions need configs/addon_time_pressure.json (the frozen config plus each add-on model's calibrated charge),
# so a missing file stops before any model call. Every attempted episode is kept. No new job starts after
# BUDGET_MINUTES. $OUT/PIPELINE_DONE is written on exit.
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/project_env.sh

OUT=${OUT:-runs/addon/podC}
SETS=${SETS:-2}
BASE_PORT=${BASE_PORT:-8765}
VIDEO=${VIDEO:-10}
WORKER_THREADS=${WORKER_THREADS:-2}
BUDGET_MINUTES=${BUDGET_MINUTES:-420}
SCENES=${SCENES:-1000 1001 1002 1003}
MODELS=${MODELS:-kimi-k3 glm-5-3-flash}
TIME_CONFIG=${TIME_CONFIG:-configs/addon_time_pressure.json}
SESSION_CAP=${SESSION_CAP:-4}  # dollars per session (each session has its own output root and spend ledger)
BIN=${BIN:-.venv-sim/bin/robot-benchmark}
BACKENDS=(groot groot_u30 pi05)
read -r -a TASKS <<< "$(python3 -c "import json; s = json.load(open('configs/final/selection.json')); print(' '.join(s['unseen_tasks'] + s['seen_tasks']))")"
START=$(date +%s)
mkdir -p "$OUT"
rm -f "$OUT/PIPELINE_DONE"
trap 'touch "$OUT/PIPELINE_DONE"' EXIT

in_budget() { (( $(date +%s) - START < BUDGET_MINUTES * 60 )); }
stamp() { echo "[$(date -u +%H:%M:%S)] $*"; }
port() { echo $((BASE_PORT + 3 * $1 + $2)); }  # set, backend index
checkpoint() {
  case $1 in
    groot) echo checkpoints/groot/checkpoint-120000 ;;
    groot_u30) echo checkpoints/groot_u30/composite_unseen_30p ;;
    pi05) echo checkpoints/pi05/75000 ;;
  esac
}

start_workers() {
  local s b p python waited
  for ((s = 0; s < SETS; s++)); do
    for b in 0 1 2; do
      p=$(port $s $b)
      curl -s -m 3 "localhost:$p/health" > /dev/null && continue
      python=.venv-groot/bin/python
      [[ ${BACKENDS[b]} == pi05 ]] && python=.venv-pi05/bin/python
      # pi05 is JAX: without this it takes 75% of GPU memory. Thread caps as in scripts/run_stage4.sh.
      XLA_PYTHON_CLIENT_PREALLOCATE=false OMP_NUM_THREADS=$WORKER_THREADS MKL_NUM_THREADS=$WORKER_THREADS setsid -f \
        $python -m robot_benchmark.policy_worker --backend "${BACKENDS[b]}" --checkpoint "$(checkpoint "${BACKENDS[b]}")" \
        --port "$p" > "$OUT/worker-$p.log" 2>&1 < /dev/null
    done
  done
  for ((s = 0; s < SETS; s++)); do
    for b in 0 1 2; do
      p=$(port $s $b); waited=0
      until curl -s -m 3 "localhost:$p/health" > /dev/null; do
        sleep 5
        ! grep -q Traceback "$OUT/worker-$p.log" || { stamp "worker $p died; stopping"; exit 1; }
        (( (waited += 5) < 1800 )) || { stamp "worker $p not healthy after 30 min; stopping"; exit 1; }
      done
    done
  done
  stamp "$((3 * SETS)) policy workers healthy"
}

# One stream: claim the next line of $1 atomically and run it against $3 (a worker URL).
stream() {
  local jobs=$1 counter=$2 url=$3 n line
  while :; do
    in_budget || { stamp "budget reached"; return; }
    n=$( (flock 9; k=$(<"$counter"); echo $((k + 1)) > "$counter"; echo "$k") 9> "$counter.lock" )
    line=$(sed -n "$((n + 1))p" "$jobs")
    [[ -n $line ]] || return
    eval "${line//@URL@/$url}" < /dev/null || stamp "nonzero exit: ${line:0:110}"
  done
}

phase_defer() {
  local b s task scene jobs pids pass
  for b in 0 1 2; do
    jobs=$OUT/jobs.defer.${BACKENDS[b]}
    : > "$jobs"
    for task in "${TASKS[@]}"; do
      for scene in $SCENES; do
        echo "$BIN baseline --task-configs configs/tasks/$task.json --scene-seeds $scene --policy-seeds 0 --agent always_defer --video-record-interval $VIDEO --skip-existing --policy-url @URL@ --output $OUT/always_defer/${BACKENDS[b]}" >> "$jobs"
      done
    done
  done
  # Two passes: with --skip-existing the second only redoes episodes that ended in an infrastructure error.
  for pass in 1 2; do
    pids=()
    for b in 0 1 2; do
      jobs=$OUT/jobs.defer.${BACKENDS[b]}
      echo 0 > "$jobs.next"
      for ((s = 0; s < SETS; s++)); do stream "$jobs" "$jobs.next" "http://127.0.0.1:$(port $s $b)" & pids+=($!); done
    done
    wait "${pids[@]}"
    stamp "always_defer pass $pass done"
  done
}

phase_pair() {
  local scene
  mkdir -p "$OUT/plans"
  for scene in $SCENES; do
    [[ -e $OUT/plans/scene$scene.json ]] && continue
    $BIN pair-session --plan configs/final/plans/scene$scene.json --reference-root "$OUT/always_defer" \
      --output "$OUT/plans/scene$scene.json" || { stamp "pairing failed for scene $scene; stopping"; exit 1; }
  done
  stamp "plans paired"
}

# Workers file for one plan on one worker set: each anonymous label -> that set's worker for the label's backend.
workers_file() {  # plan, set, output
  python3 - "$1" "$2" "$3" "$BASE_PORT" <<'PY'
import json, sys
plan, worker_set, out, base = json.load(open(sys.argv[1])), int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
index = {"groot": 0, "groot_u30": 1, "pi05": 2}
labels = {e["policy_label"]: e["backend"] for e in plan}
json.dump({l: f"http://127.0.0.1:{base + 3 * worker_set + index[b]}" for l, b in sorted(labels.items())}, open(out, "w"))
PY
}

run_session() {  # model, scene, set
  local model=$1 scene=$2 s=$3 root=$OUT/$1/scene$2
  mkdir -p "$root"
  workers_file "$OUT/plans/scene$scene.json" "$s" "$root/workers.json"
  in_budget || { stamp "budget reached before $model scene $scene"; return; }
  stamp "session $model scene $scene on worker set $s"
  $BIN session --plan "$OUT/plans/scene$scene.json" --workers "$root/workers.json" \
    --agent-config "configs/model-$model.dev.json" --time-pressure "$TIME_CONFIG" --session-id "$model-scene$scene" \
    --api-dollar-cap "$SESSION_CAP" --video-record-interval "$VIDEO" --development --output "$root" \
    > "$root/session.log" 2>&1 || stamp "session $model scene $scene: nonzero exit"
}

phase_sessions() {
  [[ -s $TIME_CONFIG ]] || { stamp "$TIME_CONFIG missing: calibrate the add-on models first; stopping"; exit 1; }
  local queue=() item s pids
  for model in $MODELS; do for scene in $SCENES; do queue+=("$model $scene"); done; done
  # SETS sessions at a time, each on its own worker set.
  while ((${#queue[@]})); do
    pids=()
    for ((s = 0; s < SETS && ${#queue[@]}; s++)); do
      read -r model scene <<< "${queue[0]}"; queue=("${queue[@]:1}")
      run_session "$model" "$scene" "$s" & pids+=($!)
    done
    wait "${pids[@]}"
  done
  stamp "sessions done"
}

PHASES=("$@")
((${#PHASES[@]})) || PHASES=(workers defer pair sessions)
for phase in "${PHASES[@]}"; do
  stamp "phase $phase"
  case $phase in
    workers) start_workers ;;
    defer) phase_defer ;;
    pair) phase_pair ;;
    sessions) phase_sessions ;;
    *) echo "unknown phase $phase" >&2; exit 2 ;;
  esac
done
stamp "finished: ${PHASES[*]}"
