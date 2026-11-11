"""
Integration tests for media probe, thumbnail generation, and end-to-end FFmpeg execution.
"""

import os
import time
import unittest
from core.ffmpeg_engine import FFmpegRunner, build_command
from core.media_probe import generate_thumbnail, probe_media_file


class TestFFmpegIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.sample_video = os.path.abspath("test_sample.mp4")
        cls.output_dir = os.path.abspath("outputs")
        os.makedirs(cls.output_dir, exist_ok=True)

    def test_media_probe(self):
        info = probe_media_file(self.sample_video)
        self.assertIsNotNone(info)
        self.assertGreater(info.duration, 0.0)
        self.assertIsNotNone(info.video_stream)
        self.assertEqual(info.video_stream.codec_name, "h264")
        self.assertEqual(info.video_stream.width, 320)
        self.assertEqual(info.video_stream.height, 240)
        self.assertIn("H264", info.summary)

    def test_generate_thumbnail(self):
        thumb = generate_thumbnail(self.sample_video, timestamp=0.5)
        self.assertIsNotNone(thumb)
        self.assertTrue(os.path.isfile(thumb))
        self.assertGreater(os.path.getsize(thumb), 0)

    def test_convert_format_remux(self):
        dest = os.path.join(self.output_dir, "integration_remux.mkv")
        if os.path.isfile(dest):
            os.remove(dest)

        args, cmd = build_command(
            input_file=self.sample_video,
            output_file=dest,
            mode="convert_format",
            settings={"stream_copy": True},
        )
        runner = FFmpegRunner()
        results = {"finished": False, "success": False}

        def on_finish(s, c, m):
            results["finished"] = True
            results["success"] = s

        runner.start(args, total_duration=2.0, on_finish=on_finish)

        start = time.time()
        while not results["finished"] and (time.time() - start < 10):
            time.sleep(0.05)

        self.assertTrue(results["success"])
        self.assertTrue(os.path.isfile(dest))
        self.assertGreater(os.path.getsize(dest), 0)

    def test_gif_conversion(self):
        dest = os.path.join(self.output_dir, "integration_test.gif")
        if os.path.isfile(dest):
            os.remove(dest)

        args, cmd = build_command(
            input_file=self.sample_video,
            output_file=dest,
            mode="make_gif",
            settings={"fps": 15, "scale_width": 240, "loop": 0},
        )
        runner = FFmpegRunner()
        results = {"finished": False, "success": False}

        def on_finish(s, c, m):
            results["finished"] = True
            results["success"] = s

        runner.start(args, total_duration=2.0, on_finish=on_finish)

        start = time.time()
        while not results["finished"] and (time.time() - start < 15):
            time.sleep(0.05)

        self.assertTrue(results["success"])
        self.assertTrue(os.path.isfile(dest))
        self.assertGreater(os.path.getsize(dest), 0)


if __name__ == "__main__":
    unittest.main()
