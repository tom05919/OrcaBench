"""Encode complete per-camera episode replays from the canonical PNG frames."""
import json
from pathlib import Path
import shutil
import subprocess

from .contracts import CAMERAS


def encode_episode_videos(episode: Path, fps=20):
    """Frames are recorded every `video_record_interval` steps (manifest, default 1) and play back in real time."""
    episode = Path(episode)
    manifest = episode / "manifest.json"
    interval = json.loads(manifest.read_text()).get("video_record_interval", 1) if manifest.exists() else 1
    streams = {}
    for camera in CAMERAS:
        name = camera.removeprefix("video.")
        frames = sorted((episode / "video_frames" / name).glob("*.png"))
        if not frames:
            continue
        last = int(frames[-1].stem)
        # Steps 0, k, 2k, ... plus the episode's final step when it falls between recording steps.
        steps = list(range(0, last + 1, interval)) + ([last] if last % interval else [])
        expected = [f"{step:06d}.png" for step in steps]
        if [frame.name for frame in frames] != expected:
            raise ValueError(f"video frames are missing or misnumbered for {name}")
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg is required to encode episode videos")
        output = episode / "videos" / f"{name}.mp4"
        output.parent.mkdir(exist_ok=True)
        # Glob input (run inside the frame folder, so the path needs no escaping) accepts the 0, k, 2k, ... numbering.
        subprocess.run([ffmpeg, "-v", "error", "-y", "-framerate", f"{fps}/{interval}",
                        "-pattern_type", "glob", "-i", "*.png",
                        "-frames:v", str(len(frames)), "-an", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(output.resolve())],
                       check=True, capture_output=True, text=True, cwd=frames[0].parent)
        if output.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg produced an empty video for {name}")
        streams[camera] = {"path": str(output.relative_to(episode)),
                           "frames": len(frames), "playback_fps": fps / interval,
                           "bytes": output.stat().st_size}
    return streams
