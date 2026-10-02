import json
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

from robot_benchmark.contracts import CAMERAS
from robot_benchmark.video import encode_episode_videos


def png_2x2():
    def chunk(name, body):
        return struct.pack(">I", len(body)) + name + body + struct.pack(">I", zlib.crc32(name + body))
    pixels = (b"\x00" + b"\xff\x00\x00" * 2) * 2
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


class VideoTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_encodes_every_camera_and_step(self):
        with tempfile.TemporaryDirectory() as temporary:
            episode = Path(temporary)
            for camera in CAMERAS:
                folder = episode / "video_frames" / camera.removeprefix("video.")
                folder.mkdir(parents=True)
                for step in (0, 1):
                    (folder / f"{step:06d}.png").write_bytes(png_2x2())
            streams = encode_episode_videos(episode)
            self.assertEqual(set(streams), set(CAMERAS))
            for stream in streams.values():
                self.assertEqual(stream["frames"], 2)
                self.assertGreater((episode / stream["path"]).stat().st_size, 0)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not installed")
    def test_encodes_sparse_frames_at_real_time_speed(self):
        with tempfile.TemporaryDirectory() as temporary:
            episode = Path(temporary)
            (episode / "manifest.json").write_text(json.dumps({"video_record_interval": 10}))
            for camera in CAMERAS:
                folder = episode / "video_frames" / camera.removeprefix("video.")
                folder.mkdir(parents=True)
                for step in (0, 10, 20):
                    (folder / f"{step:06d}.png").write_bytes(png_2x2())
            streams = encode_episode_videos(episode)
            self.assertEqual(set(streams), set(CAMERAS))
            for stream in streams.values():
                self.assertEqual((stream["frames"], stream["playback_fps"]), (3, 2.0))
                probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                                        "-show_entries", "stream=nb_read_frames,r_frame_rate", "-of", "json",
                                        str(episode / stream["path"])], check=True, capture_output=True, text=True)
                info = json.loads(probe.stdout)["streams"][0]
                self.assertEqual((info["nb_read_frames"], info["r_frame_rate"]), ("3", "2/1"))

    def test_rejects_missing_sparse_frame_or_wrong_interval(self):
        with tempfile.TemporaryDirectory() as temporary:
            episode = Path(temporary)
            (episode / "manifest.json").write_text(json.dumps({"video_record_interval": 10}))
            folder = episode / "video_frames" / CAMERAS[0].removeprefix("video.")
            folder.mkdir(parents=True)
            for step in (0, 20):
                (folder / f"{step:06d}.png").write_bytes(png_2x2())
            with self.assertRaisesRegex(ValueError, "missing or misnumbered"):
                encode_episode_videos(episode)
            (folder / "000010.png").write_bytes(png_2x2())
            (episode / "manifest.json").write_text(json.dumps({"video_record_interval": 1}))
            with self.assertRaisesRegex(ValueError, "missing or misnumbered"):
                encode_episode_videos(episode)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_accepts_final_frame_between_recording_steps(self):
        with tempfile.TemporaryDirectory() as temporary:
            episode = Path(temporary)
            (episode / "manifest.json").write_text(json.dumps({"video_record_interval": 10}))
            for camera in CAMERAS:
                folder = episode / "video_frames" / camera.removeprefix("video.")
                folder.mkdir(parents=True)
                for step in (0, 10, 20, 23):
                    (folder / f"{step:06d}.png").write_bytes(png_2x2())
            streams = encode_episode_videos(episode)
            self.assertEqual({stream["frames"] for stream in streams.values()}, {4})
            folder = episode / "video_frames" / CAMERAS[0].removeprefix("video.")
            (folder / "000010.png").unlink()
            with self.assertRaisesRegex(ValueError, "missing or misnumbered"):
                encode_episode_videos(episode)

    def test_rejects_missing_frame(self):
        with tempfile.TemporaryDirectory() as temporary:
            episode = Path(temporary)
            folder = episode / "video_frames" / CAMERAS[0].removeprefix("video.")
            folder.mkdir(parents=True)
            (folder / "000000.png").write_bytes(png_2x2())
            (folder / "000002.png").write_bytes(png_2x2())
            with self.assertRaisesRegex(ValueError, "missing or misnumbered"):
                encode_episode_videos(episode)


if __name__ == "__main__":
    unittest.main()
