#!/usr/bin/env bash
# Provide headless EGL on GPU images that ship only the NVIDIA compute libraries (no libEGL_nvidia).
# Downloads NVIDIA's data-center installer for the RUNNING kernel driver version, extracts it (nothing is
# installed system-wide, no reboot) and links the EGL user-space libraries into .cache/nvidia-gl.
# scripts/project_env.sh then points EGL at them. The user-space libraries must match the kernel driver exactly.
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd)"
VERSION="$(grep -oE '[0-9]+\.[0-9]+\.[0-9]+' /proc/driver/nvidia/version | head -1)"
[ -n "$VERSION" ] || { echo "no NVIDIA kernel driver found" >&2; exit 1; }
CACHE="$ROOT/.cache/nvidia"
GL="$ROOT/.cache/nvidia-gl"
RUN="NVIDIA-Linux-x86_64-$VERSION.run"
mkdir -p "$CACHE"

if [ ! -f "$CACHE/$RUN" ]; then
    curl -sSf -o "$CACHE/$RUN.part" "https://us.download.nvidia.com/tesla/$VERSION/$RUN"
    mv "$CACHE/$RUN.part" "$CACHE/$RUN"
fi
echo "installer: $RUN $(stat -c %s "$CACHE/$RUN") bytes sha256 $(sha256sum "$CACHE/$RUN" | cut -d' ' -f1)"
rm -rf "$CACHE/extract-$VERSION"
sh "$CACHE/$RUN" -x --target "$CACHE/extract-$VERSION" >/dev/null

rm -rf "$GL"
mkdir -p "$GL"
for lib in libEGL_nvidia libGLX_nvidia libnvidia-eglcore libnvidia-glcore libnvidia-glsi libnvidia-tls \
           libnvidia-gpucomp libnvidia-rtcore libnvidia-egl-gbm libnvidia-egl-wayland; do
    for file in "$CACHE/extract-$VERSION/$lib.so.$VERSION"; do
        [ -e "$file" ] && ln -sf "$file" "$GL/$(basename "$file")"
    done
done
ln -sf "$GL/libEGL_nvidia.so.$VERSION" "$GL/libEGL_nvidia.so.0"
cat > "$GL/10_nvidia.json" <<JSON
{"file_format_version": "1.0.0", "ICD": {"library_path": "$GL/libEGL_nvidia.so.0"}}
JSON

if LD_LIBRARY_PATH="$GL" ldd "$GL/libEGL_nvidia.so.$VERSION" | grep -q "not found"; then
    LD_LIBRARY_PATH="$GL" ldd "$GL/libEGL_nvidia.so.$VERSION" | grep "not found" >&2
    echo "libEGL_nvidia has unresolved dependencies" >&2
    exit 1
fi
echo "NVIDIA EGL libraries for $VERSION linked under $GL"
