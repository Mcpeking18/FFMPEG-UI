"""
FFmpeg execution engine and command builder with real-time progress parsing.
"""

import os
import re
import shlex
import subprocess
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple, Any

from core.presets import build_gif_filter, build_atempo_filter


def time_to_seconds(time_str: str) -> float:
    """
    Convert FFmpeg time format (HH:MM:SS.ms or SS.ms) to seconds.
    """
    if not time_str:
        return 0.0
    time_str = time_str.strip()
    try:
        if ":" in time_str:
            parts = time_str.split(":")
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
        return float(time_str)
    except Exception:
        return 0.0


def seconds_to_time(seconds: float) -> str:
    """Format seconds into HH:MM:SS."""
    secs = int(seconds)
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    rem_secs = secs % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{rem_secs:02d}"
    return f"{minutes:02d}:{rem_secs:02d}"


def quote_arg(arg: str) -> str:
    """Quote an argument for display purposes."""
    if " " in arg or '"' in arg or ";" in arg or "[" in arg or "]" in arg:
        escaped = arg.replace('"', '\\"')
        return f'"{escaped}"'
    return arg


def build_command(
    input_file: str,
    output_file: str,
    mode: str,
    settings: Dict[str, Any],
) -> Tuple[List[str], str]:
    """
    Builds the ffmpeg argument list and display string.
    mode can be a preset key (e.g. 'convert_format', 'make_gif') or 'advanced'.
    """
    args = ["ffmpeg", "-y", "-hide_banner"]

    # Global hardware acceleration if specified in advanced mode
    hwaccel = settings.get("hwaccel", "none")
    if hwaccel and hwaccel not in ("none", "cpu", "auto_detect"):
        args.extend(["-hwaccel", hwaccel])

    # Preset Modes
    if mode == "convert_format":
        stream_copy = settings.get("stream_copy", True)
        args.extend(["-i", input_file])
        if stream_copy:
            args.extend(["-c", "copy"])
        else:
            vcodec = settings.get("video_codec", "libx264")
            acodec = settings.get("audio_codec", "aac")
            args.extend(["-c:v", vcodec, "-c:a", acodec])

    elif mode == "make_gif":
        start_time = settings.get("start_time", "").strip()
        end_time = settings.get("end_time", "").strip()
        fps = int(settings.get("fps", 15))
        scale_width = int(settings.get("scale_width", 480))
        loop = int(settings.get("loop", 0))

        if start_time:
            args.extend(["-ss", start_time])
        if end_time:
            args.extend(["-to", end_time])

        args.extend(["-i", input_file])
        filter_str = build_gif_filter(fps=fps, scale_width=scale_width)
        args.extend(["-filter_complex", filter_str, "-loop", str(loop)])

    elif mode == "extract_audio":
        acodec = settings.get("audio_codec", "libmp3lame")
        bitrate = settings.get("bitrate", "192k")
        normalize = settings.get("normalize", False)

        args.extend(["-i", input_file, "-vn"])
        if acodec:
            args.extend(["-c:a", acodec])
        if bitrate and acodec not in ("flac", "pcm_s16le"):
            args.extend(["-b:a", bitrate])
        if normalize:
            args.extend(["-af", "loudnorm"])

    elif mode == "trim_cut":
        start_time = settings.get("start_time", "00:00:00").strip()
        end_time = settings.get("end_time", "").strip()
        stream_copy = settings.get("stream_copy", True)

        if stream_copy:
            if start_time:
                args.extend(["-ss", start_time])
            if end_time:
                args.extend(["-to", end_time])
            args.extend(["-i", input_file, "-c", "copy"])
        else:
            args.extend(["-i", input_file])
            if start_time:
                args.extend(["-ss", start_time])
            if end_time:
                args.extend(["-to", end_time])
            args.extend(["-c:v", "libx264", "-crf", "20", "-c:a", "aac"])

    elif mode == "compress":
        resolution = settings.get("resolution", "720p")
        crf = str(settings.get("crf", 26))
        preset = settings.get("preset", "medium")
        audio_bitrate = settings.get("audio_bitrate", "128k")

        args.extend(["-i", input_file])
        scale_map = {
            "4K": "scale='min(3840,iw)':-2",
            "1080p": "scale='min(1920,iw)':-2",
            "720p": "scale='min(1280,iw)':-2",
            "480p": "scale='min(854,iw)':-2",
        }
        if resolution in scale_map:
            args.extend(["-vf", scale_map[resolution]])

        args.extend([
            "-c:v", "libx264",
            "-crf", crf,
            "-preset", preset,
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            "-pix_fmt", "yuv420p",
        ])

    elif mode == "change_speed":
        speed = float(settings.get("speed", 2.0))
        args.extend(["-i", input_file])
        pts_mult = 1.0 / speed if speed > 0 else 1.0
        vf = f"setpts={pts_mult:.4f}*PTS"
        af = build_atempo_filter(speed)
        args.extend(["-vf", vf, "-af", af])

    elif mode == "mute_video":
        args.extend(["-i", input_file, "-c:v", "copy", "-an"])

    elif mode == "advanced":
        start_time = settings.get("start_time", "").strip()
        end_time = settings.get("end_time", "").strip()
        if start_time:
            args.extend(["-ss", start_time])
        if end_time:
            args.extend(["-to", end_time])

        args.extend(["-i", input_file])

        # Video Codec
        vcodec = settings.get("video_codec", "auto")
        if vcodec != "auto":
            args.extend(["-c:v", vcodec])

        # Rate control
        if vcodec != "copy":
            rate_mode = settings.get("rate_mode", "crf")
            if rate_mode == "crf":
                crf = settings.get("crf")
                if crf is not None:
                    # NVENC uses -cq instead of -crf
                    if "nvenc" in vcodec:
                        args.extend(["-cq", str(crf)])
                    else:
                        args.extend(["-crf", str(crf)])
            elif rate_mode == "bitrate":
                vbitrate = settings.get("video_bitrate", "").strip()
                if vbitrate:
                    args.extend(["-b:v", vbitrate])

            # Preset
            preset = settings.get("preset", "none")
            if preset and preset != "none":
                args.extend(["-preset", preset])

            # Pixel format
            pix_fmt = settings.get("pix_fmt", "none")
            if pix_fmt and pix_fmt != "none":
                args.extend(["-pix_fmt", pix_fmt])

        # Video Filters (-vf)
        vf_filters = []
        resolution = settings.get("resolution", "original")
        if resolution != "original":
            if resolution == "4K":
                vf_filters.append("scale='min(3840,iw)':-2")
            elif resolution == "1080p":
                vf_filters.append("scale='min(1920,iw)':-2")
            elif resolution == "720p":
                vf_filters.append("scale='min(1280,iw)':-2")
            elif resolution == "480p":
                vf_filters.append("scale='min(854,iw)':-2")
            elif ":" in resolution or "x" in resolution:
                clean_res = resolution.replace("x", ":")
                vf_filters.append(f"scale={clean_res}")

        fps = settings.get("fps", "original")
        if fps and fps != "original":
            vf_filters.append(f"fps={fps}")

        rotate = settings.get("rotate", "none")
        if rotate == "90_cw":
            vf_filters.append("transpose=1")
        elif rotate == "180":
            vf_filters.append("transpose=1,transpose=1")
        elif rotate == "90_ccw":
            vf_filters.append("transpose=2")

        flip = settings.get("flip", "none")
        if flip == "horizontal":
            vf_filters.append("hflip")
        elif flip == "vertical":
            vf_filters.append("vflip")

        if settings.get("deinterlace", False):
            vf_filters.append("yadif")

        custom_vf = settings.get("custom_vf", "").strip()
        if custom_vf:
            vf_filters.append(custom_vf)

        if vf_filters and vcodec != "copy":
            args.extend(["-vf", ",".join(vf_filters)])

        # Audio Codec
        acodec = settings.get("audio_codec", "auto")
        if acodec == "none":
            args.append("-an")
        else:
            if acodec != "auto":
                args.extend(["-c:a", acodec])

            if acodec != "copy":
                abitrate = settings.get("audio_bitrate", "none")
                if abitrate and abitrate != "none":
                    args.extend(["-b:a", abitrate])

                channels = settings.get("channels", "none")
                if channels and channels != "none":
                    ch_map = {"Stereo": "2", "Mono": "1", "5.1 Surround": "6"}
                    args.extend(["-ac", ch_map.get(channels, channels)])

                af_filters = []
                if settings.get("normalize", False):
                    af_filters.append("loudnorm")

                custom_af = settings.get("custom_af", "").strip()
                if custom_af:
                    af_filters.append(custom_af)

                if af_filters:
                    args.extend(["-af", ",".join(af_filters)])

        # Custom arbitrary arguments
        extra_args = settings.get("extra_args", "").strip()
        if extra_args:
            for part in shlex.split(extra_args):
                args.append(part)

    else:
        # Fallback
        args.extend(["-i", input_file, output_file])
        cmd_str = " ".join(quote_arg(a) for a in args)
        return args, cmd_str

    args.append(output_file)
    cmd_str = " ".join(quote_arg(a) for a in args)
    return args, cmd_str


class FFmpegRunner:
    """
    Manages non-blocking FFmpeg execution with stdout/stderr real-time parsing,
    progress tracking, and cancellation support.
    """

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False
        self.is_cancelled = False
        self.total_duration = 0.0

        # Regex patterns for parsing stderr
        self.re_time = re.compile(r"time=\s*(\d{2}:\d{2}:\d{2}\.\d+|\d+\.\d+)")
        self.re_fps = re.compile(r"fps=\s*([\d.]+)")
        self.re_speed = re.compile(r"speed=\s*([\d.]+)x")
        self.re_frame = re.compile(r"frame=\s*(\d+)")
        self.re_size = re.compile(r"size=\s*(\d+\w+)")
        self.re_bitrate = re.compile(r"bitrate=\s*([\d.]+kbits/s)")

    def start(
        self,
        command: List[str],
        total_duration: float = 0.0,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        on_finish: Optional[Callable[[bool, int, str], None]] = None,
    ):
        """
        Start FFmpeg command in a background thread.
        """
        if self.is_running:
            return

        self.total_duration = total_duration
        self.is_cancelled = False
        self.is_running = True

        self.thread = threading.Thread(
            target=self._run_process,
            args=(command, on_progress, on_log, on_finish),
            daemon=True,
        )
        self.thread.start()

    def _run_process(
        self,
        command: List[str],
        on_progress: Optional[Callable[[Dict[str, Any]], None]],
        on_log: Optional[Callable[[str], None]],
        on_finish: Optional[Callable[[bool, int, str], None]],
    ):
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        last_progress_update = 0.0
        return_code = -1
        error_lines = []

        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=startupinfo,
                bufsize=1,
            )

            # FFmpeg writes progress information to stderr
            while True:
                line = self.process.stderr.readline()
                if not line:
                    break

                clean_line = line.strip()
                if on_log and clean_line:
                    on_log(clean_line)

                # Collect error messages if any
                if "error" in clean_line.lower() or "invalid" in clean_line.lower():
                    error_lines.append(clean_line)

                # Parse progress
                now = time.time()
                if on_progress and (now - last_progress_update >= 0.1):
                    progress_data = self._parse_progress_line(clean_line)
                    if progress_data:
                        on_progress(progress_data)
                        last_progress_update = now

            self.process.wait()
            return_code = self.process.returncode

        except Exception as e:
            return_code = -99
            error_lines.append(str(e))
        finally:
            if self.process:
                if self.process.stdout:
                    try:
                        self.process.stdout.close()
                    except Exception:
                        pass
                if self.process.stderr:
                    try:
                        self.process.stderr.close()
                    except Exception:
                        pass
            self.is_running = False

            # Final 100% progress if success
            if not self.is_cancelled and return_code == 0 and on_progress:
                on_progress({
                    "percentage": 100.0,
                    "time": seconds_to_time(self.total_duration),
                    "fps": "",
                    "speed": "1.0x",
                    "frame": "",
                    "size": "",
                })

            if on_finish:
                err_msg = "\n".join(error_lines[-5:]) if error_lines else ""
                success = (return_code == 0 and not self.is_cancelled)
                on_finish(success, return_code, err_msg)

    def _parse_progress_line(self, line: str) -> Optional[Dict[str, Any]]:
        m_time = self.re_time.search(line)
        if not m_time:
            return None

        current_time_str = m_time.group(1)
        current_seconds = time_to_seconds(current_time_str)

        percentage = 0.0
        if self.total_duration > 0:
            percentage = min(99.9, max(0.0, (current_seconds / self.total_duration) * 100.0))

        fps_val = ""
        m_fps = self.re_fps.search(line)
        if m_fps:
            fps_val = m_fps.group(1)

        speed_val = ""
        m_speed = self.re_speed.search(line)
        if m_speed:
            speed_val = m_speed.group(1) + "x"

        frame_val = ""
        m_frame = self.re_frame.search(line)
        if m_frame:
            frame_val = m_frame.group(1)

        size_val = ""
        m_size = self.re_size.search(line)
        if m_size:
            size_val = m_size.group(1)

        return {
            "percentage": percentage,
            "time": current_time_str,
            "seconds": current_seconds,
            "fps": fps_val,
            "speed": speed_val,
            "frame": frame_val,
            "size": size_val,
        }

    def cancel(self):
        """Terminate the active FFmpeg process."""
        self.is_cancelled = True
        if self.process and self.is_running:
            try:
                self.process.terminate()
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
