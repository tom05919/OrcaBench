"""Encode complete per-camera episode replays from the canonical PNG frames."""
from pathlib import Path
import shutil
import subprocess

from .contracts import CAMERAS


def encode_episode_videos(episode: Path, fps=20):
    episode = Path(episode)
    streams = {}
    for camera in CAMERAS:
        name = camera.removeprefix("video.")
        frames = sorted((episode / "video_frames" / name).glob("*.png"))
        if not frames:
            continue
        expected = [f"{step:06d}.png" for step in range(len(frames))]
        if [frame.name for frame in frames] != expected:
            raise ValueError(f"video frames are missing or misnumbered for {name}")
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg is required to encode episode videos")
        output = episode / "videos" / f"{name}.mp4"
        output.parent.mkdir(exist_ok=True)
        subprocess.run([ffmpeg, "-v", "error", "-y", "-framerate", str(fps),
                        "-start_number", "0", "-i", str(frames[0].parent / "%06d.png"),
                        "-frames:v", str(len(frames)), "-an", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(output)],
                       check=True, capture_output=True, text=True)
        if output.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg produced an empty video for {name}")
        streams[camera] = {"path": str(output.relative_to(episode)),
                           "frames": len(frames), "playback_fps": fps,
                           "bytes": output.stat().st_size}
    return streams
