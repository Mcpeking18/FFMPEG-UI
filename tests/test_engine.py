"""
Unit tests for FFmpeg UI engine, command builder, and progress parser.
"""

import os
import unittest
from core.ffmpeg_engine import (
    build_command,
    build_time_args,
    time_to_seconds,
    seconds_to_time,
    FFmpegRunner,
)
from core.presets import build_gif_filter, build_atempo_filter


class TestFFmpegEngine(unittest.TestCase):

    def test_time_conversions(self):
        self.assertEqual(time_to_seconds("00:01:30.50"), 90.5)
        self.assertEqual(time_to_seconds("01:00:00"), 3600.0)
        self.assertEqual(time_to_seconds("45.2"), 45.2)
        self.assertEqual(time_to_seconds(""), 0.0)

        self.assertEqual(seconds_to_time(90), "01:30")
        self.assertEqual(seconds_to_time(3665), "01:01:05")

    def test_gif_filter(self):
        filt = build_gif_filter(fps=20, scale_width=320)
        self.assertIn("fps=20", filt)
        self.assertIn("scale=320:-1:flags=lanczos", filt)
        self.assertIn("palettegen", filt)
        self.assertIn("paletteuse", filt)

    def test_atempo_filter(self):
        self.assertEqual(build_atempo_filter(1.5), "atempo=1.500")
        self.assertEqual(build_atempo_filter(2.0), "atempo=2.000")
        # 4x speed requires chaining atempo=2.0,atempo=2.0
        filt_4x = build_atempo_filter(4.0)
        self.assertIn("atempo=2.0", filt_4x)
        # 0.25x speed requires chaining atempo=0.5,atempo=0.5
        filt_quarter = build_atempo_filter(0.25)
        self.assertIn("atempo=0.5", filt_quarter)

    def test_build_convert_format_stream_copy(self):
        args, cmd = build_command(
            input_file="input.mp4",
            output_file="output.mkv",
            mode="convert_format",
            settings={"stream_copy": True},
        )
        self.assertEqual(args[0], "ffmpeg")
        self.assertIn("-c", args)
        self.assertIn("copy", args)
        self.assertIn("output.mkv", args)

    def test_build_make_gif(self):
        args, cmd = build_command(
            input_file="clip.mp4",
            output_file="clip.gif",
            mode="make_gif",
            settings={
                "fps": 15,
                "scale_width": 480,
                "start_time": "00:00:01",
                "end_time": "00:00:04",
                "loop": 0,
            },
        )
        self.assertIn("-ss", args)
        self.assertIn("00:00:01", args)
        self.assertIn("-to", args)
        self.assertIn("00:00:04", args)
        self.assertIn("-filter_complex", args)
        self.assertIn("-loop", args)
        self.assertIn("clip.gif", args)

    def test_build_extract_audio(self):
        args, cmd = build_command(
            input_file="video.mp4",
            output_file="audio.mp3",
            mode="extract_audio",
            settings={
                "audio_codec": "libmp3lame",
                "bitrate": "320k",
                "normalize": True,
            },
        )
        self.assertIn("-vn", args)
        self.assertIn("-c:a", args)
        self.assertIn("libmp3lame", args)
        self.assertIn("-b:a", args)
        self.assertIn("320k", args)
        self.assertIn("-af", args)
        self.assertIn("loudnorm", args)

    def test_build_advanced_mode(self):
        args, cmd = build_command(
            input_file="source.mov",
            output_file="dest.mp4",
            mode="advanced",
            settings={
                "video_codec": "libx265",
                "rate_mode": "crf",
                "crf": 24,
                "preset": "slow",
                "audio_codec": "aac",
                "audio_bitrate": "192k",
                "resolution": "1080p",
                "fps": "60",
                "extra_args": "-movflags +faststart",
            },
        )
        self.assertIn("-c:v", args)
        self.assertIn("libx265", args)
        self.assertIn("-crf", args)
        self.assertIn("24", args)
        self.assertIn("-preset", args)
        self.assertIn("slow", args)
        self.assertIn("-c:a", args)
        self.assertIn("aac", args)
        self.assertIn("-movflags", args)
        self.assertIn("+faststart", args)

    def test_progress_line_parsing(self):
        runner = FFmpegRunner()
        runner.total_duration = 100.0
        line = "frame=  250 fps= 65.2 q=28.0 size=    1250kB time=00:00:50.00 bitrate= 204.8kbits/s speed=2.5x"
        parsed = runner._parse_progress_line(line)
        self.assertIsNotNone(parsed)
        self.assertAlmostEqual(parsed["percentage"], 50.0, places=1)
        self.assertEqual(parsed["fps"], "65.2")
        self.assertEqual(parsed["speed"], "2.5x")
        self.assertEqual(parsed["time"], "00:00:50.00")


    def test_build_time_args(self):
        # Valid range: start < end
        self.assertEqual(build_time_args("00:00:01", "00:00:04"), ["-ss", "00:00:01", "-to", "00:00:04"])
        # Inverted range: user specified duration (start=5s, length=2s)
        self.assertEqual(build_time_args("00:00:05", "00:00:02"), ["-ss", "00:00:05", "-t", "00:00:02"])
        # No end time: only -ss
        self.assertEqual(build_time_args("00:00:03", ""), ["-ss", "00:00:03"])
        self.assertEqual(build_time_args("00:00:03", "00:00:00"), ["-ss", "00:00:03"])
        # Both zero: empty
        self.assertEqual(build_time_args("00:00:00", "00:00:00"), [])
        self.assertEqual(build_time_args("", ""), [])


if __name__ == "__main__":
    unittest.main()
