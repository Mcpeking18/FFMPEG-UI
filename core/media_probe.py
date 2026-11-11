"""
Media probe module using ffprobe to extract stream, format, and metadata information.
"""

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class StreamInfo:
    index: int
    codec_type: str  # 'video', 'audio', 'subtitle'
    codec_name: str
    codec_long_name: str = ""
    # Video specific
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    pix_fmt: Optional[str] = None
    bitrate: Optional[int] = None
    # Audio specific
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    channel_layout: Optional[str] = None


@dataclass
class MediaInfo:
    file_path: str
    format_name: str = ""
    format_long_name: str = ""
    duration: float = 0.0  # In seconds
    size_bytes: int = 0
    bitrate: int = 0
    streams: List[StreamInfo] = field(default_factory=list)

    @property
    def video_stream(self) -> Optional[StreamInfo]:
        for s in self.streams:
            if s.codec_type == "video" and s.codec_name not in ("mjpeg", "png"):
                return s
        for s in self.streams:
            if s.codec_type == "video":
                return s
        return None

    @property
    def audio_stream(self) -> Optional[StreamInfo]:
        for s in self.streams:
            if s.codec_type == "audio":
                return s
        return None

    @property
    def duration_formatted(self) -> str:
        seconds = int(self.duration)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        ms = int((self.duration - seconds) * 100)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}.{ms:02d}"

    @property
    def size_formatted(self) -> str:
        size = self.size_bytes
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0 or unit == "GB":
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{self.size_bytes} B"

    @property
    def resolution_str(self) -> str:
        v = self.video_stream
        if v and v.width and v.height:
            return f"{v.width}x{v.height}"
        return "N/A"

    @property
    def summary(self) -> str:
        parts = []
        if self.duration > 0:
            parts.append(f"Duration: {self.duration_formatted}")
        if self.size_bytes > 0:
            parts.append(f"Size: {self.size_formatted}")
        v = self.video_stream
        if v:
            v_desc = f"Video: {v.codec_name.upper()}"
            if v.width and v.height:
                v_desc += f" ({v.width}x{v.height}"
                if v.fps:
                    v_desc += f" @ {v.fps:.2f}fps"
                v_desc += ")"
            parts.append(v_desc)
        a = self.audio_stream
        if a:
            a_desc = f"Audio: {a.codec_name.upper()}"
            if a.sample_rate:
                a_desc += f" ({a.sample_rate}Hz"
                if a.channels:
                    a_desc += f", {a.channels}ch"
                a_desc += ")"
            parts.append(a_desc)
        return " | ".join(parts) if parts else "No media streams found."


def probe_media_file(file_path: str) -> Optional[MediaInfo]:
    """
    Run ffprobe to get comprehensive metadata on a media file.
    Returns MediaInfo dataclass or None if file cannot be probed.
    """
    if not os.path.isfile(file_path):
        return None

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path,
    ]

    try:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            startupinfo=startupinfo,
            timeout=15,
        )
        if res.returncode != 0 or not res.stdout:
            return None

        data = json.loads(res.stdout)
        format_data = data.get("format", {})
        streams_data = data.get("streams", [])

        duration = float(format_data.get("duration", 0.0) or 0.0)
        size_bytes = int(format_data.get("size", 0) or os.path.getsize(file_path))
        bitrate = int(format_data.get("bit_rate", 0) or 0)

        streams: List[StreamInfo] = []
        for s in streams_data:
            codec_type = s.get("codec_type", "unknown")
            codec_name = s.get("codec_name", "")
            codec_long_name = s.get("codec_long_name", "")

            # Frame rate parsing
            fps = None
            avg_frame_rate = s.get("avg_frame_rate", "")
            if avg_frame_rate and "/" in avg_frame_rate:
                try:
                    num, den = avg_frame_rate.split("/")
                    if float(den) > 0:
                        fps = float(num) / float(den)
                except Exception:
                    pass

            width = s.get("width")
            height = s.get("height")
            pix_fmt = s.get("pix_fmt")
            s_bitrate = int(s.get("bit_rate", 0) or 0)

            sample_rate = int(s.get("sample_rate", 0) or 0) if s.get("sample_rate") else None
            channels = s.get("channels")
            channel_layout = s.get("channel_layout")

            streams.append(
                StreamInfo(
                    index=int(s.get("index", len(streams))),
                    codec_type=codec_type,
                    codec_name=codec_name,
                    codec_long_name=codec_long_name,
                    width=width,
                    height=height,
                    fps=fps,
                    pix_fmt=pix_fmt,
                    bitrate=s_bitrate if s_bitrate > 0 else None,
                    sample_rate=sample_rate,
                    channels=channels,
                    channel_layout=channel_layout,
                )
            )

        return MediaInfo(
            file_path=file_path,
            format_name=format_data.get("format_name", ""),
            format_long_name=format_data.get("format_long_name", ""),
            duration=duration,
            size_bytes=size_bytes,
            bitrate=bitrate,
            streams=streams,
        )

    except Exception:
        return None


def generate_thumbnail(file_path: str, timestamp: float = 1.0, max_size: int = 180) -> Optional[str]:
    """
    Extract a single frame thumbnail using ffmpeg and return the temporary image path.
    """
    if not os.path.isfile(file_path):
        return None

    temp_thumb = os.path.join(tempfile.gettempdir(), f"ffmpeg_thumb_{os.getpid()}_{abs(hash(file_path))}.jpg")

    # If timestamp is beyond duration, ffmpeg might fail, but -ss before -i seeks quickly
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(max(0.1, timestamp)),
        "-i", file_path,
        "-vframes", "1",
        "-vf", f"scale='min({max_size},iw)':-1",
        "-q:v", "3",
        temp_thumb,
    ]

    try:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
            timeout=10,
        )
        if res.returncode == 0 and os.path.isfile(temp_thumb) and os.path.getsize(temp_thumb) > 0:
            return temp_thumb
    except Exception:
        pass

    return None
