#!/bin/bash
# The replay benchmark's final grid (docs/superpowers/specs/2026-10-24-replay-benchmark-design.md, "Final grid: none,
# low, high", October 25): every model at reasoning off (GLM-5.3 Flash: minimal, since Sail rejects turning its
# reasoning off), low and high, in the probe (450 questions, pass 1) and in sessions (168 episodes at 2 s per look,
# pass 1). Every cell runs in its own loop, all in parallel, and is restarted until complete: scripts/replay_run.py
# resumes where it stopped. Costs money: needs SAIL_API_KEY (or the Git-ignored .env); nothing is sent past the ledger
# cap (CAP dollars, default 150, counted over all of runs/replay/api_spend.jsonl).
#
#   scripts/replay_grid.sh [probe|sessions|pilot] [model ...]
#
# No part: the probe and the sessions. No model: all four. `pilot` is the unscored 10-probe pilot (pass 0) of each
# cell (design decision 6), run before the scored cells. Logs: runs/replay/logs/grid-<part>-<model>-<level>.log, and
# one line per finished cell in runs/replay/logs/status.log. Replaces the one-off, Git-ignored runs/replay/run_*.sh
# scripts that produced the October 24-26 data (the last were run_grid.sh, run_kimi_high.sh, run_glm_levels.sh and
# run_finish2.sh); the settings below are theirs.
set -uo pipefail
cd "$(dirname "$0")/.."
PYTHON=${PYTHON:-python3.12}
SETTINGS="--cap ${CAP:-150} --timeout 900 --max-tokens 32768"
ALL_MODELS="moonshotai/Kimi-K3 google/gemma-4-31B-it deepseek-ai/DeepSeek-V4.1-Flash-1017 zai-org/GLM-5.3-Flash"
LOGS=runs/replay/logs

levels() {  # the model's none, low and high
  if [ "$1" = zai-org/GLM-5.3-Flash ]; then echo minimal low high; else echo off low high; fi
}

finished() {  # part path: probe answers in a file, or finished episodes in a session folder
  if [ "$1" = sessions ]; then
    find "$2" -name '*.jsonl' ! -name '*.looks.jsonl' -exec cat {} + 2>/dev/null | grep -c '"outcome"'
  elif [ -f "$2" ]; then
    wc -l < "$2" | tr -d ' '
  else
    echo 0
  fi
}

cell() {  # part model level: run the cell until it is complete, at most `tries` times
  local part=$1 model=$2 level=$3 slug=${2//\//__} path target tries args
  case $part in
    pilot) path=runs/replay/probe/effort-$level/pass0/$slug.jsonl; target=10; tries=20
           args="probe --models $model --pass 0 --limit 10 --workers 5 $SETTINGS --effort $level" ;;
    probe) path=runs/replay/probe/effort-$level/pass1/$slug.jsonl; target=450; tries=20
           args="probe --models $model --pass 1 --workers 6 $SETTINGS --effort $level" ;;
    sessions) path=runs/replay/sessions/c2/effort-$level/pass1/$slug; target=168; tries=40
              args="sessions --models $model --cost-per-look 2 --pass 1 --workers 8 $SETTINGS --effort $level" ;;
  esac
  for _ in $(seq 1 $tries); do
    # Two processes on one cell would write the same files: wait for one started elsewhere to end.
    while pgrep -f -- "replay_run.py ${args%% --workers*}.* --effort $level" > /dev/null; do sleep 60; done
    [ "$(finished $part $path)" -ge $target ] && break
    $PYTHON -B scripts/replay_run.py $args >> $LOGS/grid-$part-$slug-$level.log 2>&1
  done
  echo "$part $model $level: $(finished $part $path) of $target $(date)" | tee -a $LOGS/status.log
}

case ${1:-} in
  probe|sessions|pilot) PARTS=$1; shift ;;
  "") PARTS="probe sessions" ;;
  *) echo "usage: scripts/replay_grid.sh [probe|sessions|pilot] [model ...]" >&2; exit 2 ;;
esac
MODELS=${*:-$ALL_MODELS}
mkdir -p $LOGS
for part in $PARTS; do
  for model in $MODELS; do
    for level in $(levels $model); do
      cell $part $model $level &
    done
  done
done
wait
