#!/usr/bin/env bash
# Source this file from any directory before running benchmark commands.

_robot_benchmark_script_dir="$(
    CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd
)"
export ROBOT_BENCHMARK_ROOT="$(
    CDPATH= cd -- "${_robot_benchmark_script_dir}/.." >/dev/null 2>&1 && pwd
)"
unset _robot_benchmark_script_dir

export UV_CACHE_DIR="${ROBOT_BENCHMARK_ROOT}/.cache/uv"
export PIP_CACHE_DIR="${ROBOT_BENCHMARK_ROOT}/.cache/pip"
export XDG_CACHE_HOME="${ROBOT_BENCHMARK_ROOT}/.cache/xdg"
export HF_HOME="${ROBOT_BENCHMARK_ROOT}/.cache/huggingface"
export HUGGINGFACE_HUB_CACHE="${HF_HOME}/hub"
export TORCH_HOME="${ROBOT_BENCHMARK_ROOT}/.cache/torch"
export JAX_COMPILATION_CACHE_DIR="${ROBOT_BENCHMARK_ROOT}/.cache/jax"
export TMPDIR="${ROBOT_BENCHMARK_ROOT}/.cache/tmp"
export PYTHONNOUSERSITE=1
export HF_HUB_DISABLE_TELEMETRY=1

if [[ "$(uname -s)" == "Linux" ]]; then
    export MUJOCO_GL="${MUJOCO_GL:-egl}"
    # Present only after scripts/setup_nvidia_gl.sh, for images without NVIDIA's EGL libraries.
    if [[ -f "${ROBOT_BENCHMARK_ROOT}/.cache/nvidia-gl/10_nvidia.json" ]]; then
        export __EGL_VENDOR_LIBRARY_FILENAMES="${ROBOT_BENCHMARK_ROOT}/.cache/nvidia-gl/10_nvidia.json"
        export LD_LIBRARY_PATH="${ROBOT_BENCHMARK_ROOT}/.cache/nvidia-gl${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
    fi
fi

mkdir -p \
    "${UV_CACHE_DIR}" \
    "${PIP_CACHE_DIR}" \
    "${XDG_CACHE_HOME}" \
    "${HUGGINGFACE_HUB_CACHE}" \
    "${TORCH_HOME}" \
    "${JAX_COMPILATION_CACHE_DIR}" \
    "${TMPDIR}"
