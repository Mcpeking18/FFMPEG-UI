# ⚡ FFmpeg Studio Pro

A modern, high-performance desktop GUI for FFmpeg built with Python and CustomTkinter. Designed to make everyday media tasks instantaneous with one-click presets while providing a full-featured "Advanced Studio" mode for granular control over every FFmpeg parameter.

---

## 🌟 Key Features

### 🚀 1-Click Quick Presets
- **🔄 Convert Container / Format**: Convert between `MP4`, `MKV`, `WEBM`, `AVI`, `MOV`, `FLV`, and `TS`. Features **Instant Stream Copy** (`-c copy`) for near-instant container remuxing with zero quality loss.
- **🎨 High-Quality GIF Generator**: Generates vivid, artifact-free GIFs using **2-Pass Palette Generation** (`palettegen` + `paletteuse`) with adjustable frame rates (5–30 FPS), width scaling (240–960px), and optional start/end trim timestamps.
- **🎵 Extract Audio Track**: Rip audio to `MP3`, `AAC`, `WAV`, `FLAC`, `OPUS`, `OGG`, or `M4A` with custom bitrates and optional EBU R128 volume normalization (`loudnorm`).
- **✂️ Trim & Cut**: Slice video clips with start/end timestamps using instant keyframe copy or frame-accurate re-encoding.
- **🗜️ Compress & Resize**: Compress videos with target resolution presets (`4K`, `1080p`, `720p`, `480p`) and CRF sliders.
- **⏩ Change Speed**: Speed up or slow down videos (0.25x to 4.0x) with automatic audio tempo (`atempo`) synchronization to prevent pitch shifts.
- **🔇 Mute Video**: Strip audio tracks completely using instant stream copy (`-c:v copy -an`).

### ⚙️ Advanced Studio Mode ("Every Control in FFmpeg")
- **Video Encoders**: `libx264` (H.264), `libx265` (HEVC), `libvpx-vp9` (VP9), `libsvtav1` (AV1), `prores`, and stream `copy`.
- **Hardware Acceleration**: NVIDIA NVENC (`h264_nvenc`, `hevc_nvenc`, `av1_nvenc`), Intel QSV (`h264_qsv`, `hevc_qsv`), AMD AMF (`h264_amf`, `hevc_amf`), and CPU.
- **Rate Control**: Interactive **CRF slider** (0–51) or custom **Video Bitrate** (e.g. `4000k`, `2M`).
- **Encoding Presets**: `ultrafast`, `superfast`, `veryfast`, `faster`, `fast`, `medium`, `slow`, `veryslow`.
- **Pixel Formats**: `yuv420p` (maximum compatibility), `yuv420p10le` (10-bit HDR), `yuv444p`.
- **Audio Options**: `AAC`, `libmp3lame` (MP3), `libopus`, `flac` (lossless), `copy`, or mute (`-an`), with bitrate and channel (`Stereo`, `Mono`, `5.1`) selectors.
- **Video Filters**: Scaling, FPS alteration, 90°/180° rotation, horizontal/vertical flipping, and deinterlacing (`yadif`).
- **Custom Extra Flags**: Text input to supply arbitrary FFmpeg parameters (e.g. `-tune film`, `-movflags +faststart`, or complex filtergraphs).

### 🖥️ Workspace-Centric & Live Transparency
- **Default Output Directory**: Automatically saves processed files to `./outputs` in the project directory.
- **📂 Open Folder Button**: One-click opening of the output directory in Windows Explorer.
- **⚡ Live Command Preview**: Shows the exact `ffmpeg -i ...` command updating in real time as you adjust controls, with a 1-click **📋 Copy Command** button.
- **📊 Real-Time Progress & Telemetry**: Non-blocking background worker with progress bar, percentage, current time, processing speed multiplier (e.g. `4.2x`), and FPS.
- **📜 Live Log Console**: Collapsible real-time console streaming raw FFmpeg output.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+
- FFmpeg and FFprobe installed and available in system `PATH`
- `customtkinter` and `pillow` (already installed):
  ```bash
  pip install -r requirements.txt
  ```

### 2. Launch the App
Double-click `run.bat` or run in terminal:
```bash
python main.py
```

---

## 📁 Project Structure

```
FFMPEG UI/
├── core/
│   ├── ffmpeg_engine.py    # Command builder, regex progress parser & async process runner
│   ├── media_probe.py      # ffprobe metadata analyzer & thumbnail extractor
│   └── presets.py          # Quick presets & filter complex generators (GIF, atempo, etc.)
├── gui/
│   └── app.py              # CustomTkinter GUI layout, tabs, widgets & event handlers
├── tests/
│   └── test_engine.py      # Automated unit tests for command generation & parsing
├── outputs/                # Default destination folder for all processed files
├── main.py                 # Application launcher
├── run.bat                 # 1-Click Windows batch launcher
├── requirements.txt        # Python dependencies
└── README.md               # Documentation
```
