#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 22.04 CUDA worker (run from the project root as a sudo-capable user).
# Installs system libraries and uv, then makes headless EGL work if the image lacks NVIDIA's EGL libraries.
# Afterwards: source scripts/project_env.sh && python3 scripts/bootstrap_gpu.py --download-assets --download-checkpoint
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    libegl1 libgles2 libglvnd0 libgl1 libglx-mesa0 libosmesa6 libglfw3 libxrender1 libxext6 \
    build-essential cmake pkg-config ffmpeg git curl >/dev/null
command -v uv >/dev/null 2>&1 || [ -x "$HOME/.local/bin/uv" ] || curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
if ! ldconfig -p | grep -q libEGL_nvidia; then
    bash scripts/setup_nvidia_gl.sh
fi
echo "worker setup complete"
