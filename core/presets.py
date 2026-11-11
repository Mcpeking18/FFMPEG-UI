"""
Predefined operational presets for common and high-value FFmpeg tasks.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class PresetConfig:
    name: str
    description: str
    output_extension: str
    # Builder function or predefined parameters
    mode: str  # 'format_convert', 'make_gif', 'extract_audio', 'trim_cut', 'compress', 'change_speed', 'mute_video'
    default_params: Dict[str, Any] = field(default_factory=dict)


PRESETS: Dict[str, PresetConfig] = {
    "convert_format": PresetConfig(
        name="Convert Container / Format",
        description="Convert container format (e.g., MP4 to MKV, MOV to MP4). Supports instant stream copy without re-encoding.",
        output_extension=".mkv",
        mode="format_convert",
        default_params={
            "target_format": "mkv",
            "stream_copy": True,
            "video_codec": "libx264",
            "audio_codec": "aac",
        },
    ),
    "make_gif": PresetConfig(
        name="Make High-Quality GIF",
        description="Create smooth, optimized GIFs with two-pass palette generation for vivid colors and no color banding.",
        output_extension=".gif",
        mode="make_gif",
        default_params={
            "fps": 15,
            "scale_width": 480,
            "start_time": "",
            "end_time": "",
            "loop": 0,  # 0 = infinite loop
        },
    ),
    "extract_audio": PresetConfig(
        name="Extract Audio Track",
        description="Rip audio from video and save to MP3, AAC, WAV, FLAC, or OPUS.",
        output_extension=".mp3",
        mode="extract_audio",
        default_params={
            "target_format": "mp3",
            "audio_codec": "libmp3lame",
            "bitrate": "192k",
            "normalize": False,
        },
    ),
    "trim_cut": PresetConfig(
        name="Trim & Cut Video",
        description="Cut a portion of video using start and end timestamps. Choose fast copy or frame-accurate cut.",
        output_extension=".mp4",
        mode="trim_cut",
        default_params={
            "start_time": "00:00:00",
            "end_time": "00:00:10",
            "stream_copy": True,
        },
    ),
    "compress": PresetConfig(
        name="Compress & Resize Video",
        description="Downscale resolution and reduce file size with optimal CRF rate control.",
        output_extension=".mp4",
        mode="compress",
        default_params={
            "resolution": "720p",
            "crf": 26,
            "preset": "medium",
            "audio_bitrate": "128k",
        },
    ),
    "change_speed": PresetConfig(
        name="Change Playback Speed",
        description="Speed up (2x, 4x) or slow down (0.5x, 0.25x) video and audio synchronously.",
        output_extension=".mp4",
        mode="change_speed",
        default_params={
            "speed": 2.0,
        },
    ),
    "mute_video": PresetConfig(
        name="Mute Video (Remove Audio)",
        description="Strip audio track completely using instant stream copy.",
        output_extension=".mp4",
        mode="mute_video",
        default_params={},
    ),
}


def build_gif_filter(fps: int = 15, scale_width: int = 480) -> str:
    """
    Builds FFmpeg filter complex for 2-pass palette generation.
    Returns the filter string.
    """
    if scale_width > 0:
        scale_str = f"scale={scale_width}:-1:flags=lanczos,"
    else:
        scale_str = ""

    return (
        f"[0:v] fps={fps},{scale_str}split [a][b]; "
        f"[a] palettegen=stats_mode=diff [p]; "
        f"[b][p] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
    )


def build_atempo_filter(speed: float) -> str:
    """
    FFmpeg atempo filter only supports values between 0.5 and 2.0.
    Chains multiple atempo filters for speeds outside this range.
    """
    if speed <= 0:
        return "atempo=1.0"

    filters = []
    remaining = speed

    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0

    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5

    filters.append(f"atempo={remaining:.3f}")
    return ",".join(filters)
