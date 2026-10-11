#!/usr/bin/env bash
# Copy a run folder to a private Hugging Face bucket, so results survive the pod. Needs HF_TOKEN in the environment
# and the hf CLI in .venv-hf (scripts/pod_guard.sh installs it). Rendered per-step PNGs (video_frames/) are skipped;
# the MP4s, keyframes, JSONL records and API traces are kept. One sync at a time: concurrent callers wait.
#
#   scripts/pod_sync.sh runs/stage4 hf://buckets/<owner>/<bucket>/stage4
set -euo pipefail
cd "$(dirname "$0")/.."
src=${1:?run folder} dest=${2:?hf://buckets/... destination}
[[ -n ${HF_TOKEN:-} ]] || { echo "HF_TOKEN is not set" >&2; exit 2; }
HF=${HF:-.venv-hf/bin/hf}
exec 9> "$src/.sync.lock"
flock 9
for attempt in 1 2 3; do
  if timeout 1800 "$HF" sync "$src" "$dest" --exclude '*video_frames/*' --exclude '.sync.lock' --format quiet; then
    echo "$(date -u +%FT%TZ) ok" >> "$src/sync.log"
    exit 0
  fi
  echo "$(date -u +%FT%TZ) attempt $attempt failed" >> "$src/sync.log"
  sleep $((attempt * 30))
done
exit 1
