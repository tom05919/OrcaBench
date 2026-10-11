#!/usr/bin/env bash
# Pod-side cost and data guard, so a run never depends on the Mac staying awake (docs/compute.md, Oct 5-6 incident).
#
#   scripts/pod_guard.sh install      project-local hf and prime CLIs (.venv-hf, .venv-prime)
#   scripts/pod_guard.sh start        launch `watch` and `backstop` detached from the SSH session
#   scripts/pod_guard.sh watch        every minute: when the pipeline wrote $OUT/PIPELINE_DONE, sync and terminate;
#                                     at DEADLINE_UNIX, stop the pipeline, sync what exists, terminate
#   scripts/pod_guard.sh backstop     independent: terminate at DEADLINE_UNIX + BACKSTOP_MINUTES with no sync
#
# Environment: POD_ID and POD_NAME (the pod must match both before termination), DEADLINE_UNIX, OUT, HF_DEST,
# HF_TOKEN, PRIME_API_KEY. Nothing here prints a key. The Mac's launchd watchdog stays armed as a further backup.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=${OUT:-runs/stage4}
PRIME=${PRIME:-.venv-prime/bin/prime}
POLL_SECONDS=${POLL_SECONDS:-60}
PERIODIC_SYNC_SECONDS=${PERIODIC_SYNC_SECONDS:-1800}
BACKSTOP_MINUTES=${BACKSTOP_MINUTES:-45}
export PRIME_DISABLE_VERSION_CHECK=1

log() { echo "$(date -u +%FT%TZ) $*" >> "$OUT/guard.log"; }
need() { for v in "$@"; do [[ -n ${!v:-} ]] || { echo "$v is not set" >&2; exit 2; }; done; }

# Terminate this pod, and only this pod: its status must report both the expected ID and name.
terminate() {
  local why=$1 attempt detail
  for attempt in $(seq 1 30); do
    detail=$("$PRIME" pods status "$POD_ID" --output json --plain 2>/dev/null)
    if [[ $(jq -r '.id + " " + .name' <<< "$detail" 2>/dev/null) == "$POD_ID $POD_NAME" ]]; then
      log "terminating ($why), attempt $attempt"
      "$PRIME" pods terminate "$POD_ID" --yes --plain >> "$OUT/guard.log" 2>&1 && { log "terminate requested"; exit 0; }
    else
      log "status check failed or identity mismatch, attempt $attempt"
    fi
    sleep "${TERMINATE_RETRY_SECONDS:-60}"
  done
  log "gave up terminating after 30 attempts"
  exit 1
}

sync_now() { scripts/pod_sync.sh "$OUT" "$HF_DEST" >> "$OUT/guard.log" 2>&1; }

stop_pipeline() {
  pkill -f scripts/run_stage4.sh; pkill -f robot-benchmark; sleep 15
  pkill -9 -f scripts/run_stage4.sh; pkill -9 -f robot-benchmark
}

watch() {
  need POD_ID POD_NAME DEADLINE_UNIX HF_DEST HF_TOKEN PRIME_API_KEY
  local last_sync=$(date +%s) now
  log "watch: pod $POD_ID ($POD_NAME), deadline $(date -u -d "@$DEADLINE_UNIX" +%FT%TZ 2>/dev/null || echo "$DEADLINE_UNIX")"
  while :; do
    now=$(date +%s)
    if (( now >= DEADLINE_UNIX )); then
      log "deadline reached: stopping the pipeline and syncing what exists"
      stop_pipeline
      sync_now && log "final sync ok" || log "final sync failed"
      terminate deadline
    elif [[ -f $OUT/PIPELINE_DONE ]]; then
      log "pipeline done ($(cat "$OUT/PIPELINE_DONE")): final sync"
      if sync_now; then log "final sync ok"; terminate pipeline_done; fi
      log "final sync failed; retrying until the deadline"
    elif (( now - last_sync >= PERIODIC_SYNC_SECONDS )); then
      sync_now && log "periodic sync ok" || log "periodic sync failed"
      last_sync=$now
    fi
    sleep "$POLL_SECONDS"
  done
}

backstop() {
  need POD_ID POD_NAME DEADLINE_UNIX PRIME_API_KEY
  local until=$((DEADLINE_UNIX + BACKSTOP_MINUTES * 60))
  log "backstop: terminates at $(date -u -d "@$until" +%FT%TZ 2>/dev/null || echo "$until") regardless"
  while (( $(date +%s) < until )); do sleep "$POLL_SECONDS"; done
  terminate backstop
}

case ${1:-} in
  install)
    export UV_CACHE_DIR=$PWD/.cache/uv
    uv venv -q .venv-hf && uv pip install -q -p .venv-hf 'huggingface_hub[cli]==2.2.0'
    uv venv -q .venv-prime && uv pip install -q -p .venv-prime 'prime==0.11.0'
    command -v jq > /dev/null || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq jq > /dev/null
    .venv-hf/bin/hf version && "$PRIME" --version ;;
  start)
    mkdir -p "$OUT"
    setsid -f "$0" watch > /dev/null 2>&1 < /dev/null
    setsid -f "$0" backstop > /dev/null 2>&1 < /dev/null
    sleep 2; tail -n 2 "$OUT/guard.log" ;;
  watch) mkdir -p "$OUT"; watch ;;
  backstop) mkdir -p "$OUT"; backstop ;;
  *) echo "usage: $0 install|start|watch|backstop" >&2; exit 2 ;;
esac
