"""
FFmpeg Studio Pro - Main CustomTkinter Application
A complete, high-performance GUI for FFmpeg with quick presets and full advanced controls.
"""

import os
import queue
import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Dict, Optional, Tuple

import customtkinter as ctk
from PIL import Image

from core.ffmpeg_engine import (
    FFmpegRunner,
    build_command,
    seconds_to_time,
    time_to_seconds,
)
from core.media_probe import MediaInfo, generate_thumbnail, probe_media_file
from core.presets import PRESETS


class FFmpegApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        # Window Setup
        self.title("⚡ FFmpeg Studio Pro")
        self.geometry("1060x920")
        self.minsize(920, 750)

        # Theme defaults
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Thread-safe event queue
        self.event_queue = queue.Queue()

        # State Variables
        self.input_file_path = tk.StringVar()
        self.output_dir_path = tk.StringVar(value=os.path.abspath(os.path.join(os.getcwd(), "outputs")))
        self.output_file_name = tk.StringVar(value="")
        self.current_media_info: Optional[MediaInfo] = None
        self.runner = FFmpegRunner()
        self.start_process_time = 0.0
        self.thumb_image: Optional[ctk.CTkImage] = None
        self.pending_output_file = ""

        # Mode State
        self.selected_preset_key = tk.StringVar(value="convert_format")

        # Ensure default output directory exists
        os.makedirs(self.output_dir_path.get(), exist_ok=True)

        # Build UI
        self._build_ui()

        # Update initial command preview
        self.update_command_preview()

        # Start periodic queue processor
        self._process_events()

    def _process_events(self):
        """Process messages from background threads safely on the main thread."""
        try:
            while not self.event_queue.empty():
                evt_type, data = self.event_queue.get_nowait()
                if evt_type == "media_info":
                    info, thumb_path = data
                    self._apply_media_info(info, thumb_path)
                elif evt_type == "progress":
                    self._on_progress_update(data)
                elif evt_type == "log":
                    self._on_log_line(data)
                elif evt_type == "finish":
                    success, return_code, error_msg, output_file = data
                    self._on_finished(success, return_code, error_msg, output_file)
        except Exception:
            pass
        finally:
            self.after(40, self._process_events)

    def _build_ui(self):
        # Configure grid
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 1. Header
        self._build_header()

        # 2. File Selection (Input & Output)
        self._build_file_section()

        # 3. Main Center Tabs (Quick Presets vs Advanced Studio)
        self._build_tabs_section()

        # 4. Live Command Preview
        self._build_command_preview_section()

        # 5. Execution & Telemetry Section
        self._build_execution_section()

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray85", "gray17"))
        header_frame.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=14, pady=10, sticky="w")

        title_lbl = ctk.CTkLabel(
            title_box,
            text="⚡ FFmpeg Studio Pro",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title_lbl.pack(side="left", padx=(0, 10))

        subtitle_lbl = ctk.CTkLabel(
            title_box,
            text="• 1-Click Fast Presets & Full-Control Media Studio",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        subtitle_lbl.pack(side="left")

        # Theme Selector
        theme_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        theme_box.grid(row=0, column=1, padx=14, pady=10, sticky="e")

        theme_switch = ctk.CTkOptionMenu(
            theme_box,
            values=["Dark", "Light", "System"],
            command=self._change_theme,
            width=90,
            height=28,
        )
        theme_switch.set("Dark")
        theme_switch.pack(side="right")

        ctk.CTkLabel(theme_box, text="Theme:", text_color="gray").pack(side="right", padx=(0, 6))

    def _change_theme(self, mode: str):
        ctk.set_appearance_mode(mode.lower())

    def _build_file_section(self):
        card = ctk.CTkFrame(self, corner_radius=10)
        card.grid(row=1, column=0, padx=16, pady=6, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        # --- Input File Row ---
        ctk.CTkLabel(card, text="Input File:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=(14, 8), pady=(12, 4), sticky="w"
        )

        self.input_entry = ctk.CTkEntry(
            card,
            textvariable=self.input_file_path,
            placeholder_text="Select or drop a video, audio, or image file...",
            height=32,
        )
        self.input_entry.grid(row=0, column=1, padx=6, pady=(12, 4), sticky="ew")
        self.input_entry.bind("<KeyRelease>", lambda e: self._on_input_path_changed())

        browse_input_btn = ctk.CTkButton(
            card,
            text="📁 Browse File",
            width=110,
            height=32,
            command=self._browse_input_file,
        )
        browse_input_btn.grid(row=0, column=2, padx=(6, 14), pady=(12, 4))

        # --- Media Info Display Card ---
        self.media_info_frame = ctk.CTkFrame(card, fg_color=("gray90", "gray14"), corner_radius=8)
        self.media_info_frame.grid(row=1, column=0, columnspan=3, padx=14, pady=(4, 8), sticky="ew")
        self.media_info_frame.grid_columnconfigure(1, weight=1)

        self.thumb_label = ctk.CTkLabel(
            self.media_info_frame,
            text="🎞️\nNo Preview",
            width=100,
            height=65,
            fg_color=("gray80", "gray20"),
            corner_radius=6,
        )
        self.thumb_label.grid(row=0, column=0, rowspan=2, padx=8, pady=8, sticky="w")

        self.media_summary_label = ctk.CTkLabel(
            self.media_info_frame,
            text="No input file selected. Browse or enter a path above to inspect details.",
            font=ctk.CTkFont(size=13),
            anchor="w",
            justify="left",
        )
        self.media_summary_label.grid(row=0, column=1, padx=8, pady=(8, 2), sticky="w")

        self.media_detail_label = ctk.CTkLabel(
            self.media_info_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
            justify="left",
        )
        self.media_detail_label.grid(row=1, column=1, padx=8, pady=(0, 8), sticky="w")

        # --- Output Folder & Name Row ---
        ctk.CTkLabel(card, text="Output Folder:", font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=(14, 8), pady=4, sticky="w"
        )

        out_box = ctk.CTkFrame(card, fg_color="transparent")
        out_box.grid(row=2, column=1, padx=6, pady=4, sticky="ew")
        out_box.grid_columnconfigure(0, weight=1)

        self.output_entry = ctk.CTkEntry(out_box, textvariable=self.output_dir_path, height=32)
        self.output_entry.grid(row=0, column=0, sticky="ew")
        self.output_entry.bind("<KeyRelease>", lambda e: self.update_command_preview())

        browse_out_btn = ctk.CTkButton(
            card,
            text="📁 Browse Folder",
            width=110,
            height=32,
            fg_color=("gray60", "gray30"),
            command=self._browse_output_dir,
        )
        browse_out_btn.grid(row=2, column=2, padx=(6, 14), pady=4)

        # Output file name row
        ctk.CTkLabel(card, text="Output Name:", font=ctk.CTkFont(weight="bold")).grid(
            row=3, column=0, padx=(14, 8), pady=(4, 12), sticky="w"
        )

        name_box = ctk.CTkFrame(card, fg_color="transparent")
        name_box.grid(row=3, column=1, padx=6, pady=(4, 12), sticky="ew")
        name_box.grid_columnconfigure(0, weight=1)

        self.filename_entry = ctk.CTkEntry(
            name_box,
            textvariable=self.output_file_name,
            placeholder_text="e.g. video_converted.mkv",
            height=32,
        )
        self.filename_entry.grid(row=0, column=0, sticky="ew")
        self.filename_entry.bind("<KeyRelease>", lambda e: self.update_command_preview())

        open_folder_btn = ctk.CTkButton(
            card,
            text="📂 Open Folder",
            width=110,
            height=32,
            fg_color="#2b7a4b",
            hover_color="#1e5c36",
            command=self._open_output_folder,
        )
        open_folder_btn.grid(row=3, column=2, padx=(6, 14), pady=(4, 12))

    def _build_tabs_section(self):
        self.tabs = ctk.CTkTabview(self, corner_radius=10)
        self.tabs.grid(row=2, column=0, padx=16, pady=6, sticky="nsew")

        self.tab_presets = self.tabs.add("🚀 Quick Presets (1-Click)")
        self.tab_advanced = self.tabs.add("⚙️ Advanced Studio (Full Control)")

        self._build_presets_tab()
        self._build_advanced_tab()

        self.tabs.set("🚀 Quick Presets (1-Click)")
        # Bind tab change
        self.tabs._segmented_button.configure(command=lambda _: self.update_command_preview())

    # ------------------ PRESETS TAB ------------------
    def _build_presets_tab(self):
        tab = self.tab_presets
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Preset selector segmented buttons
        preset_bar = ctk.CTkFrame(tab, fg_color="transparent")
        preset_bar.grid(row=0, column=0, padx=8, pady=(4, 8), sticky="ew")

        preset_options = [
            ("🔄 Convert Format", "convert_format"),
            ("🎨 Make GIF", "make_gif"),
            ("🎵 Extract Audio", "extract_audio"),
            ("✂️ Trim / Cut", "trim_cut"),
            ("🗜️ Compress", "compress"),
            ("⏩ Speed", "change_speed"),
            ("🔇 Mute", "mute_video"),
        ]

        self.preset_seg = ctk.CTkSegmentedButton(
            preset_bar,
            values=[opt[0] for opt in preset_options],
            command=self._on_preset_selected,
            height=34,
        )
        self.preset_seg.pack(fill="x", expand=True)
        self.preset_map = {opt[0]: opt[1] for opt in preset_options}
        self.preset_seg.set("🔄 Convert Format")

        # Container for preset options
        self.preset_options_frame = ctk.CTkFrame(tab, corner_radius=8, fg_color=("gray90", "gray14"))
        self.preset_options_frame.grid(row=1, column=0, padx=8, pady=4, sticky="nsew")
        self.preset_options_frame.grid_columnconfigure(1, weight=1)

        # Variables for preset controls
        self.target_format_var = tk.StringVar(value="mkv")
        self.stream_copy_var = tk.BooleanVar(value=True)
        self.gif_fps_var = tk.IntVar(value=15)
        self.gif_width_var = tk.IntVar(value=480)
        self.gif_start_var = tk.StringVar(value="")
        self.gif_end_var = tk.StringVar(value="")
        self.audio_fmt_var = tk.StringVar(value="mp3")
        self.audio_bitrate_var = tk.StringVar(value="192k")
        self.audio_norm_var = tk.BooleanVar(value=False)
        self.trim_start_var = tk.StringVar(value="00:00:00")
        self.trim_end_var = tk.StringVar(value="00:00:10")
        self.trim_copy_var = tk.BooleanVar(value=True)
        self.compress_res_var = tk.StringVar(value="720p")
        self.compress_crf_var = tk.IntVar(value=26)
        self.speed_var = tk.DoubleVar(value=2.0)

        self._render_current_preset_view()

    def _on_preset_selected(self, display_name: str):
        key = self.preset_map.get(display_name, "convert_format")
        self.selected_preset_key.set(key)
        self._render_current_preset_view()
        self._update_output_filename()
        self.update_command_preview()

    def _render_current_preset_view(self):
        # Clear existing widgets in preset_options_frame
        for widget in self.preset_options_frame.winfo_children():
            widget.destroy()

        mode = self.selected_preset_key.get()

        if mode == "convert_format":
            ctk.CTkLabel(
                self.preset_options_frame,
                text="Target Container:",
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=0, column=0, padx=16, pady=14, sticky="w")

            fmt_menu = ctk.CTkOptionMenu(
                self.preset_options_frame,
                variable=self.target_format_var,
                values=["mkv", "mp4", "webm", "mov", "avi", "flv", "ts"],
                command=lambda _: (self._update_output_filename(), self.update_command_preview()),
                width=140,
            )
            fmt_menu.grid(row=0, column=1, padx=16, pady=14, sticky="w")

            switch = ctk.CTkSwitch(
                self.preset_options_frame,
                text="⚡ Instant Stream Copy (Lossless, no re-encoding)",
                variable=self.stream_copy_var,
                command=self.update_command_preview,
            )
            switch.grid(row=1, column=0, columnspan=2, padx=16, pady=8, sticky="w")

            tip = ctk.CTkLabel(
                self.preset_options_frame,
                text="Tip: Stream copy remuxes video/audio streams instantly in seconds with zero quality loss.",
                text_color="gray",
                font=ctk.CTkFont(size=12),
            )
            tip.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 14), sticky="w")

        elif mode == "make_gif":
            ctk.CTkLabel(
                self.preset_options_frame,
                text="Frame Rate (FPS):",
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=0, column=0, padx=16, pady=8, sticky="w")

            fps_box = ctk.CTkFrame(self.preset_options_frame, fg_color="transparent")
            fps_box.grid(row=0, column=1, padx=16, pady=8, sticky="ew")
            fps_lbl = ctk.CTkLabel(fps_box, text=f"{self.gif_fps_var.get()} fps", width=60)
            fps_lbl.pack(side="right")
            fps_slider = ctk.CTkSlider(
                fps_box,
                from_=5,
                to=30,
                number_of_steps=25,
                variable=self.gif_fps_var,
                command=lambda val: (fps_lbl.configure(text=f"{int(val)} fps"), self.update_command_preview()),
            )
            fps_slider.pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(
                self.preset_options_frame,
                text="Max Width (Scale):",
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=1, column=0, padx=16, pady=8, sticky="w")

            w_box = ctk.CTkFrame(self.preset_options_frame, fg_color="transparent")
            w_box.grid(row=1, column=1, padx=16, pady=8, sticky="ew")
            w_lbl = ctk.CTkLabel(w_box, text=f"{self.gif_width_var.get()} px", width=60)
            w_lbl.pack(side="right")
            w_slider = ctk.CTkSlider(
                w_box,
                from_=240,
                to=960,
                number_of_steps=24,
                variable=self.gif_width_var,
                command=lambda val: (w_lbl.configure(text=f"{int(val)} px"), self.update_command_preview()),
            )
            w_slider.pack(side="left", fill="x", expand=True)

            # Start and End Times
            ctk.CTkLabel(
                self.preset_options_frame,
                text="Time Range (Optional):",
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=2, column=0, padx=16, pady=8, sticky="w")

            time_box = ctk.CTkFrame(self.preset_options_frame, fg_color="transparent")
            time_box.grid(row=2, column=1, padx=16, pady=8, sticky="w")

            ctk.CTkLabel(time_box, text="Start:").pack(side="left", padx=(0, 4))
            s_entry = ctk.CTkEntry(time_box, textvariable=self.gif_start_var, width=80, placeholder_text="00:00:00")
            s_entry.pack(side="left", padx=(0, 16))
            s_entry.bind("<KeyRelease>", lambda e: self.update_command_preview())

            ctk.CTkLabel(time_box, text="End:").pack(side="left", padx=(0, 4))
            e_entry = ctk.CTkEntry(time_box, textvariable=self.gif_end_var, width=80, placeholder_text="00:00:03")
            e_entry.pack(side="left")
            e_entry.bind("<KeyRelease>", lambda e: self.update_command_preview())

            badge = ctk.CTkLabel(
                self.preset_options_frame,
                text="✨ 2-Pass Palette Generation enabled (eliminates grain and color banding)",
                text_color="#4ecdc4",
                font=ctk.CTkFont(size=12, weight="bold"),
            )
            badge.grid(row=3, column=0, columnspan=2, padx=16, pady=(4, 12), sticky="w")

        elif mode == "extract_audio":
            ctk.CTkLabel(
                self.preset_options_frame,
                text="Audio Format:",
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=0, column=0, padx=16, pady=10, sticky="w")

            afmt_menu = ctk.CTkOptionMenu(
                self.preset_options_frame,
                variable=self.audio_fmt_var,
                values=["mp3", "aac", "wav", "flac", "opus", "ogg", "m4a"],
                command=lambda _: (self._update_output_filename(), self.update_command_preview()),
                width=140,
            )
            afmt_menu.grid(row=0, column=1, padx=16, pady=10, sticky="w")

            ctk.CTkLabel(
                self.preset_options_frame,
                text="Bitrate:",
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=1, column=0, padx=16, pady=10, sticky="w")

            abit_menu = ctk.CTkOptionMenu(
                self.preset_options_frame,
                variable=self.audio_bitrate_var,
                values=["128k", "192k", "256k", "320k"],
                command=lambda _: self.update_command_preview(),
                width=140,
            )
            abit_menu.grid(row=1, column=1, padx=16, pady=10, sticky="w")

            norm_sw = ctk.CTkSwitch(
                self.preset_options_frame,
                text="Normalize Audio Volume (EBU R128 standard)",
                variable=self.audio_norm_var,
                command=self.update_command_preview,
            )
            norm_sw.grid(row=2, column=0, columnspan=2, padx=16, pady=10, sticky="w")

        elif mode == "trim_cut":
            ctk.CTkLabel(
                self.preset_options_frame,
                text="Start Time:",
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=0, column=0, padx=16, pady=10, sticky="w")

            tstart_entry = ctk.CTkEntry(
                self.preset_options_frame,
                textvariable=self.trim_start_var,
                width=140,
                placeholder_text="00:00:00",
            )
            tstart_entry.grid(row=0, column=1, padx=16, pady=10, sticky="w")
            tstart_entry.bind("<KeyRelease>", lambda e: self.update_command_preview())

            ctk.CTkLabel(
                self.preset_options_frame,
                text="End Time:",
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=1, column=0, padx=16, pady=10, sticky="w")

            tend_entry = ctk.CTkEntry(
                self.preset_options_frame,
                textvariable=self.trim_end_var,
                width=140,
                placeholder_text="00:00:10",
            )
            tend_entry.grid(row=1, column=1, padx=16, pady=10, sticky="w")
            tend_entry.bind("<KeyRelease>", lambda e: self.update_command_preview())

            trim_sw = ctk.CTkSwitch(
                self.preset_options_frame,
                text="⚡ Fast Keyframe Cut (Stream copy, instant)",
                variable=self.trim_copy_var,
                command=self.update_command_preview,
            )
            trim_sw.grid(row=2, column=0, columnspan=2, padx=16, pady=10, sticky="w")

        elif mode == "compress":
            ctk.CTkLabel(
                self.preset_options_frame,
                text="Target Resolution:",
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=0, column=0, padx=16, pady=10, sticky="w")

            cres_menu = ctk.CTkOptionMenu(
                self.preset_options_frame,
                variable=self.compress_res_var,
                values=["4K", "1080p", "720p", "480p"],
                command=lambda _: self.update_command_preview(),
                width=140,
            )
            cres_menu.grid(row=0, column=1, padx=16, pady=10, sticky="w")

            ctk.CTkLabel(
                self.preset_options_frame,
                text="Quality (CRF):",
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=1, column=0, padx=16, pady=10, sticky="w")

            crf_box = ctk.CTkFrame(self.preset_options_frame, fg_color="transparent")
            crf_box.grid(row=1, column=1, padx=16, pady=10, sticky="ew")
            crf_lbl = ctk.CTkLabel(crf_box, text=f"{self.compress_crf_var.get()}", width=40)
            crf_lbl.pack(side="right")
            crf_slider = ctk.CTkSlider(
                crf_box,
                from_=18,
                to=35,
                number_of_steps=17,
                variable=self.compress_crf_var,
                command=lambda val: (crf_lbl.configure(text=f"{int(val)}"), self.update_command_preview()),
            )
            crf_slider.pack(side="left", fill="x", expand=True)

            tip = ctk.CTkLabel(
                self.preset_options_frame,
                text="Lower CRF = Higher Quality | Higher CRF = Smaller File Size (23 is default, 28 is high compression).",
                text_color="gray",
                font=ctk.CTkFont(size=12),
            )
            tip.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="w")

        elif mode == "change_speed":
            ctk.CTkLabel(
                self.preset_options_frame,
                text="Speed Multiplier:",
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=0, column=0, padx=16, pady=12, sticky="w")

            speeds = ["0.25x", "0.5x", "0.75x", "1.25x", "1.5x", "2.0x", "4.0x"]
            speed_seg = ctk.CTkSegmentedButton(
                self.preset_options_frame,
                values=speeds,
                command=self._on_speed_selected,
            )
            speed_seg.grid(row=0, column=1, padx=16, pady=12, sticky="ew")
            speed_seg.set(f"{self.speed_var.get()}x")

            tip = ctk.CTkLabel(
                self.preset_options_frame,
                text="Video frames (setpts) and audio tempo (atempo) are adjusted simultaneously to prevent pitch shift.",
                text_color="gray",
                font=ctk.CTkFont(size=12),
            )
            tip.grid(row=1, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="w")

        elif mode == "mute_video":
            msg = ctk.CTkLabel(
                self.preset_options_frame,
                text="🔇 Completely removes audio track with instant stream copy (-c:v copy -an).\nNo video re-encoding or quality loss.",
                font=ctk.CTkFont(size=13),
                justify="left",
            )
            msg.grid(row=0, column=0, padx=16, pady=24, sticky="w")

    def _on_speed_selected(self, val_str: str):
        try:
            val = float(val_str.replace("x", ""))
            self.speed_var.set(val)
            self.update_command_preview()
        except Exception:
            pass

    # ------------------ ADVANCED STUDIO TAB ------------------
    def _build_advanced_tab(self):
        tab = self.tab_advanced
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=1)

        # Advanced Settings Variables
        self.adv_vcodec_var = tk.StringVar(value="auto")
        self.adv_hwaccel_var = tk.StringVar(value="none")
        self.adv_rate_mode_var = tk.StringVar(value="crf")
        self.adv_crf_var = tk.IntVar(value=23)
        self.adv_vbitrate_var = tk.StringVar(value="4000k")
        self.adv_preset_var = tk.StringVar(value="medium")
        self.adv_pixfmt_var = tk.StringVar(value="yuv420p")

        self.adv_acodec_var = tk.StringVar(value="auto")
        self.adv_abitrate_var = tk.StringVar(value="192k")
        self.adv_channels_var = tk.StringVar(value="Stereo")
        self.adv_anorm_var = tk.BooleanVar(value=False)

        self.adv_res_var = tk.StringVar(value="original")
        self.adv_fps_var = tk.StringVar(value="original")
        self.adv_rotate_var = tk.StringVar(value="none")
        self.adv_flip_var = tk.StringVar(value="none")
        self.adv_deinterlace_var = tk.BooleanVar(value=False)
        self.adv_extra_args_var = tk.StringVar(value="")

        # --- Left Column: Video Controls ---
        left_card = ctk.CTkFrame(tab, corner_radius=8, fg_color=("gray90", "gray14"))
        left_card.grid(row=0, column=0, padx=(8, 4), pady=4, sticky="nsew")
        left_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            left_card,
            text="🎞️ Video Encoding",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="w")

        # Video Codec
        ctk.CTkLabel(left_card, text="Codec:").grid(row=1, column=0, padx=12, pady=4, sticky="w")
        vcodec_menu = ctk.CTkOptionMenu(
            left_card,
            variable=self.adv_vcodec_var,
            values=[
                "auto",
                "libx264",
                "libx265",
                "libvpx-vp9",
                "libsvtav1",
                "h264_nvenc",
                "hevc_nvenc",
                "av1_nvenc",
                "h264_qsv",
                "hevc_qsv",
                "h264_amf",
                "hevc_amf",
                "prores",
                "copy",
            ],
            command=lambda _: self.update_command_preview(),
            height=28,
        )
        vcodec_menu.grid(row=1, column=1, padx=12, pady=4, sticky="ew")

        # Hardware Acceleration
        ctk.CTkLabel(left_card, text="HW Accel:").grid(row=2, column=0, padx=12, pady=4, sticky="w")
        hw_menu = ctk.CTkOptionMenu(
            left_card,
            variable=self.adv_hwaccel_var,
            values=["none", "cuda", "qsv", "d3d11va", "auto"],
            command=lambda _: self.update_command_preview(),
            height=28,
        )
        hw_menu.grid(row=2, column=1, padx=12, pady=4, sticky="ew")

        # Rate Control
        ctk.CTkLabel(left_card, text="Rate Control:").grid(row=3, column=0, padx=12, pady=4, sticky="w")
        rc_seg = ctk.CTkSegmentedButton(
            left_card,
            values=["CRF", "Bitrate"],
            variable=self.adv_rate_mode_var,
            command=lambda _: self.update_command_preview(),
            height=26,
        )
        rc_seg.grid(row=3, column=1, padx=12, pady=4, sticky="ew")
        rc_seg.set("CRF")

        # CRF Slider
        ctk.CTkLabel(left_card, text="CRF:").grid(row=4, column=0, padx=12, pady=4, sticky="w")
        crf_box = ctk.CTkFrame(left_card, fg_color="transparent")
        crf_box.grid(row=4, column=1, padx=12, pady=4, sticky="ew")
        self.adv_crf_lbl = ctk.CTkLabel(crf_box, text=f"{self.adv_crf_var.get()}", width=30)
        self.adv_crf_lbl.pack(side="right")
        adv_crf_slider = ctk.CTkSlider(
            crf_box,
            from_=0,
            to=51,
            number_of_steps=51,
            variable=self.adv_crf_var,
            command=lambda val: (self.adv_crf_lbl.configure(text=f"{int(val)}"), self.update_command_preview()),
        )
        adv_crf_slider.pack(side="left", fill="x", expand=True)

        # Preset
        ctk.CTkLabel(left_card, text="Preset:").grid(row=5, column=0, padx=12, pady=4, sticky="w")
        preset_menu = ctk.CTkOptionMenu(
            left_card,
            variable=self.adv_preset_var,
            values=["none", "ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
            command=lambda _: self.update_command_preview(),
            height=28,
        )
        preset_menu.grid(row=5, column=1, padx=12, pady=4, sticky="ew")

        # Pixel Format
        ctk.CTkLabel(left_card, text="Pixel Format:").grid(row=6, column=0, padx=12, pady=(4, 10), sticky="w")
        pix_menu = ctk.CTkOptionMenu(
            left_card,
            variable=self.adv_pixfmt_var,
            values=["yuv420p", "yuv420p10le", "yuv444p", "none"],
            command=lambda _: self.update_command_preview(),
            height=28,
        )
        pix_menu.grid(row=6, column=1, padx=12, pady=(4, 10), sticky="ew")

        # --- Right Column: Audio & Filters ---
        right_card = ctk.CTkFrame(tab, corner_radius=8, fg_color=("gray90", "gray14"))
        right_card.grid(row=0, column=1, padx=(4, 8), pady=4, sticky="nsew")
        right_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            right_card,
            text="🔊 Audio & Filters",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="w")

        # Audio Codec
        ctk.CTkLabel(right_card, text="Audio Codec:").grid(row=1, column=0, padx=12, pady=4, sticky="w")
        acodec_menu = ctk.CTkOptionMenu(
            right_card,
            variable=self.adv_acodec_var,
            values=["auto", "aac", "libmp3lame", "libopus", "flac", "copy", "none"],
            command=lambda _: self.update_command_preview(),
            height=28,
        )
        acodec_menu.grid(row=1, column=1, padx=12, pady=4, sticky="ew")

        # Audio Bitrate
        ctk.CTkLabel(right_card, text="Audio Bitrate:").grid(row=2, column=0, padx=12, pady=4, sticky="w")
        abit_menu = ctk.CTkOptionMenu(
            right_card,
            variable=self.adv_abitrate_var,
            values=["none", "96k", "128k", "192k", "256k", "320k"],
            command=lambda _: self.update_command_preview(),
            height=28,
        )
        abit_menu.grid(row=2, column=1, padx=12, pady=4, sticky="ew")

        # Channels
        ctk.CTkLabel(right_card, text="Channels:").grid(row=3, column=0, padx=12, pady=4, sticky="w")
        ch_menu = ctk.CTkOptionMenu(
            right_card,
            variable=self.adv_channels_var,
            values=["Stereo", "Mono", "5.1 Surround", "none"],
            command=lambda _: self.update_command_preview(),
            height=28,
        )
        ch_menu.grid(row=3, column=1, padx=12, pady=4, sticky="ew")

        # Resolution Scaling
        ctk.CTkLabel(right_card, text="Resolution:").grid(row=4, column=0, padx=12, pady=4, sticky="w")
        res_menu = ctk.CTkOptionMenu(
            right_card,
            variable=self.adv_res_var,
            values=["original", "4K", "1080p", "720p", "480p"],
            command=lambda _: self.update_command_preview(),
            height=28,
        )
        res_menu.grid(row=4, column=1, padx=12, pady=4, sticky="ew")

        # Frame Rate (FPS)
        ctk.CTkLabel(right_card, text="FPS:").grid(row=5, column=0, padx=12, pady=4, sticky="w")
        fps_menu = ctk.CTkOptionMenu(
            right_card,
            variable=self.adv_fps_var,
            values=["original", "24", "30", "60", "120"],
            command=lambda _: self.update_command_preview(),
            height=28,
        )
        fps_menu.grid(row=5, column=1, padx=12, pady=4, sticky="ew")

        # Normalization
        norm_chk = ctk.CTkCheckBox(
            right_card,
            text="Normalize Audio (loudnorm)",
            variable=self.adv_anorm_var,
            command=self.update_command_preview,
        )
        norm_chk.grid(row=6, column=0, columnspan=2, padx=12, pady=(4, 10), sticky="w")

        # --- Extra Arguments Bar at Bottom of Tab ---
        extra_frame = ctk.CTkFrame(tab, fg_color="transparent")
        extra_frame.grid(row=1, column=0, columnspan=2, padx=8, pady=(4, 8), sticky="ew")
        extra_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(extra_frame, text="Custom Extra Flags:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=(4, 8), pady=4, sticky="w"
        )
        extra_entry = ctk.CTkEntry(
            extra_frame,
            textvariable=self.adv_extra_args_var,
            placeholder_text="e.g. -tune film -movflags +faststart or any custom FFmpeg parameters...",
            height=30,
        )
        extra_entry.grid(row=0, column=1, sticky="ew")
        extra_entry.bind("<KeyRelease>", lambda e: self.update_command_preview())

    # ------------------ COMMAND PREVIEW SECTION ------------------
    def _build_command_preview_section(self):
        card = ctk.CTkFrame(self, corner_radius=10)
        card.grid(row=3, column=0, padx=16, pady=4, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        header_box = ctk.CTkFrame(card, fg_color="transparent")
        header_box.grid(row=0, column=0, columnspan=2, padx=12, pady=(8, 4), sticky="ew")
        header_box.grid_columnconfigure(0, weight=1)

        lbl = ctk.CTkLabel(
            header_box,
            text="⚡ Live Command Preview",
            font=ctk.CTkFont(weight="bold"),
        )
        lbl.grid(row=0, column=0, sticky="w")

        copy_btn = ctk.CTkButton(
            header_box,
            text="📋 Copy Command",
            width=120,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color=("gray60", "gray30"),
            command=self._copy_command_to_clipboard,
        )
        copy_btn.grid(row=0, column=1, sticky="e")

        self.cmd_textbox = ctk.CTkTextbox(
            card,
            height=58,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="char",
            fg_color=("gray95", "gray12"),
        )
        self.cmd_textbox.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 10), sticky="ew")

    def _copy_command_to_clipboard(self):
        cmd = self.cmd_textbox.get("1.0", "end-1c")
        if cmd.strip():
            self.clipboard_clear()
            self.clipboard_append(cmd.strip())
            messagebox.showinfo("Copied", "FFmpeg command copied to clipboard!")

    # ------------------ EXECUTION SECTION ------------------
    def _build_execution_section(self):
        card = ctk.CTkFrame(self, corner_radius=10)
        card.grid(row=4, column=0, padx=16, pady=(4, 12), sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        # Start / Cancel Button
        self.action_btn = ctk.CTkButton(
            card,
            text="🚀 Start Processing",
            height=40,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#1f77b4",
            hover_color="#14598a",
            command=self._toggle_processing,
        )
        self.action_btn.grid(row=0, column=0, padx=(12, 12), pady=10)

        # Progress bar & Status
        prog_box = ctk.CTkFrame(card, fg_color="transparent")
        prog_box.grid(row=0, column=1, padx=(0, 12), pady=10, sticky="ew")
        prog_box.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(prog_box, height=14)
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(2, 4))
        self.progress_bar.set(0.0)

        self.status_lbl = ctk.CTkLabel(
            prog_box,
            text="Ready. Choose a file and click Start Processing.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            anchor="w",
        )
        self.status_lbl.grid(row=1, column=0, sticky="w")

        # Collapsible log view button
        self.show_logs_btn = ctk.CTkButton(
            card,
            text="📜 Logs",
            width=70,
            height=40,
            fg_color=("gray60", "gray30"),
            command=self._toggle_logs_view,
        )
        self.show_logs_btn.grid(row=0, column=2, padx=(0, 12), pady=10)

        # Logs Console
        self.log_frame = ctk.CTkFrame(card, fg_color=("gray95", "gray12"), corner_radius=6)
        self.log_frame.grid(row=1, column=0, columnspan=3, padx=12, pady=(0, 10), sticky="ew")
        self.log_frame.grid_columnconfigure(0, weight=1)

        self.log_textbox = ctk.CTkTextbox(
            self.log_frame,
            height=110,
            font=ctk.CTkFont(family="Consolas", size=10),
            wrap="char",
        )
        self.log_textbox.grid(row=0, column=0, padx=6, pady=6, sticky="ew")

        # Logs control buttons
        log_ctrls = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        log_ctrls.grid(row=1, column=0, padx=6, pady=(0, 6), sticky="e")

        clear_btn = ctk.CTkButton(
            log_ctrls,
            text="Clear Logs",
            width=80,
            height=24,
            font=ctk.CTkFont(size=10),
            command=lambda: self.log_textbox.delete("1.0", "end"),
        )
        clear_btn.pack(side="right")

    def _toggle_logs_view(self):
        if self.log_frame.winfo_viewable():
            self.log_frame.grid_remove()
            self.show_logs_btn.configure(text="📜 Logs")
        else:
            self.log_frame.grid()
            self.show_logs_btn.configure(text="🔽 Hide")

    # ------------------ EVENT HANDLERS & LOGIC ------------------
    def _browse_input_file(self):
        f = filedialog.askopenfilename(
            title="Select Media File",
            filetypes=[
                ("All Media Files", "*.mp4;*.mkv;*.avi;*.mov;*.webm;*.flv;*.mp3;*.wav;*.flac;*.gif;*.png;*.jpg"),
                ("Video Files", "*.mp4;*.mkv;*.avi;*.mov;*.webm;*.flv;*.ts"),
                ("Audio Files", "*.mp3;*.wav;*.flac;*.aac;*.ogg;*.opus;*.m4a"),
                ("All Files", "*.*"),
            ],
        )
        if f:
            self.input_file_path.set(f)
            self._on_input_path_changed()

    def _browse_output_dir(self):
        d = filedialog.askdirectory(title="Select Output Folder", initialdir=self.output_dir_path.get())
        if d:
            self.output_dir_path.set(d)
            self.update_command_preview()

    def _open_output_folder(self):
        out_dir = self.output_dir_path.get()
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        try:
            os.startfile(out_dir)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder: {e}")

    def _on_input_path_changed(self):
        path = self.input_file_path.get().strip('"').strip()
        if os.path.isfile(path):
            self._load_file_metadata(path)
            self._update_output_filename()
        else:
            self.current_media_info = None
            self.media_summary_label.configure(text="File does not exist or invalid path.")
            self.media_detail_label.configure(text="")
            self.thumb_label.configure(image=None, text="🎞️\nNo Preview")
        self.update_command_preview()

    def _load_file_metadata(self, file_path: str):
        # Run probe in background to avoid freezing UI
        def _worker():
            info = probe_media_file(file_path)
            thumb_path = generate_thumbnail(file_path, timestamp=1.0)
            self.event_queue.put(("media_info", (info, thumb_path)))

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_media_info(self, info: Optional[MediaInfo], thumb_path: Optional[str]):
        self.current_media_info = info
        if info:
            self.media_summary_label.configure(
                text=f"📁 {os.path.basename(info.file_path)} ({info.size_formatted})"
            )
            self.media_detail_label.configure(text=info.summary)

            # Auto set trim end time if empty or default
            if info.duration > 0:
                self.trim_end_var.set(seconds_to_time(info.duration))
                if not self.gif_end_var.get():
                    self.gif_end_var.set(seconds_to_time(min(info.duration, 4.0)))

            # Thumbnail
            if thumb_path and os.path.isfile(thumb_path):
                try:
                    pil_img = Image.open(thumb_path)
                    # Maintain aspect ratio to fit 100x65
                    pil_img.thumbnail((100, 65))
                    self.thumb_image = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
                    self.thumb_label.configure(image=self.thumb_image, text="")
                except Exception:
                    self.thumb_label.configure(image=None, text="🎞️\nPreview")
            else:
                self.thumb_label.configure(image=None, text="🎞️\nPreview")
        else:
            self.media_summary_label.configure(text="Unable to probe media details.")
            self.media_detail_label.configure(text="")
            self.thumb_label.configure(image=None, text="🎞️\nNo Preview")

        self.update_command_preview()

    def _update_output_filename(self):
        in_path = self.input_file_path.get().strip('"').strip()
        if not in_path:
            return

        base_name, _ = os.path.splitext(os.path.basename(in_path))
        active_tab = self.tabs.get()

        if "Quick Presets" in active_tab:
            mode = self.selected_preset_key.get()
            if mode == "convert_format":
                ext = f".{self.target_format_var.get().lower()}"
                self.output_file_name.set(f"{base_name}_converted{ext}")
            elif mode == "make_gif":
                self.output_file_name.set(f"{base_name}.gif")
            elif mode == "extract_audio":
                ext = f".{self.audio_fmt_var.get().lower()}"
                self.output_file_name.set(f"{base_name}_audio{ext}")
            elif mode == "trim_cut":
                self.output_file_name.set(f"{base_name}_trimmed.mp4")
            elif mode == "compress":
                self.output_file_name.set(f"{base_name}_compressed.mp4")
            elif mode == "change_speed":
                speed = self.speed_var.get()
                self.output_file_name.set(f"{base_name}_{speed}x.mp4")
            elif mode == "mute_video":
                self.output_file_name.set(f"{base_name}_muted.mp4")
        else:
            # Advanced mode
            vcodec = self.adv_vcodec_var.get()
            acodec = self.adv_acodec_var.get()
            if acodec != "none" and vcodec == "none":
                ext = ".mp3"
            elif "webm" in vcodec or "vp9" in vcodec:
                ext = ".webm"
            elif "mkv" in vcodec:
                ext = ".mkv"
            else:
                ext = ".mp4"
            self.output_file_name.set(f"{base_name}_studio{ext}")

    def _get_current_settings(self) -> Tuple[str, Dict[str, Any]]:
        active_tab = self.tabs.get()

        if "Quick Presets" in active_tab:
            mode = self.selected_preset_key.get()
            if mode == "convert_format":
                settings = {
                    "stream_copy": self.stream_copy_var.get(),
                    "video_codec": "libx264",
                    "audio_codec": "aac",
                }
            elif mode == "make_gif":
                settings = {
                    "fps": self.gif_fps_var.get(),
                    "scale_width": self.gif_width_var.get(),
                    "start_time": self.gif_start_var.get(),
                    "end_time": self.gif_end_var.get(),
                    "loop": 0,
                }
            elif mode == "extract_audio":
                fmt = self.audio_fmt_var.get()
                codec_map = {
                    "mp3": "libmp3lame",
                    "aac": "aac",
                    "flac": "flac",
                    "wav": "pcm_s16le",
                    "opus": "libopus",
                    "ogg": "libvorbis",
                    "m4a": "aac",
                }
                settings = {
                    "audio_codec": codec_map.get(fmt, "libmp3lame"),
                    "bitrate": self.audio_bitrate_var.get(),
                    "normalize": self.audio_norm_var.get(),
                }
            elif mode == "trim_cut":
                settings = {
                    "start_time": self.trim_start_var.get(),
                    "end_time": self.trim_end_var.get(),
                    "stream_copy": self.trim_copy_var.get(),
                }
            elif mode == "compress":
                settings = {
                    "resolution": self.compress_res_var.get(),
                    "crf": self.compress_crf_var.get(),
                    "preset": "medium",
                    "audio_bitrate": "128k",
                }
            elif mode == "change_speed":
                settings = {"speed": self.speed_var.get()}
            elif mode == "mute_video":
                settings = {}
            else:
                settings = {}
            return mode, settings
        else:
            # Advanced mode
            mode = "advanced"
            settings = {
                "hwaccel": self.adv_hwaccel_var.get(),
                "video_codec": self.adv_vcodec_var.get(),
                "rate_mode": self.adv_rate_mode_var.get().lower(),
                "crf": self.adv_crf_var.get(),
                "video_bitrate": self.adv_vbitrate_var.get(),
                "preset": self.adv_preset_var.get(),
                "pix_fmt": self.adv_pixfmt_var.get(),
                "audio_codec": self.adv_acodec_var.get(),
                "audio_bitrate": self.adv_abitrate_var.get(),
                "channels": self.adv_channels_var.get(),
                "normalize": self.adv_anorm_var.get(),
                "resolution": self.adv_res_var.get(),
                "fps": self.adv_fps_var.get(),
                "rotate": self.adv_rotate_var.get(),
                "flip": self.adv_flip_var.get(),
                "deinterlace": self.adv_deinterlace_var.get(),
                "extra_args": self.adv_extra_args_var.get(),
            }
            return mode, settings

    def update_command_preview(self):
        in_file = self.input_file_path.get().strip('"').strip() or "input.mp4"
        out_dir = self.output_dir_path.get().strip('"').strip() or "outputs"
        out_name = self.output_file_name.get().strip() or "output.mp4"
        out_file = os.path.join(out_dir, out_name)

        mode, settings = self._get_current_settings()
        _, cmd_str = build_command(in_file, out_file, mode, settings)

        self.cmd_textbox.delete("1.0", "end")
        self.cmd_textbox.insert("1.0", cmd_str)

    # ------------------ EXECUTION ENGINE BINDINGS ------------------
    def _toggle_processing(self):
        if self.runner.is_running:
            # Cancel
            self.action_btn.configure(text="Cancelling...", state="disabled")
            self.runner.cancel()
        else:
            # Start
            self._start_execution()

    def _start_execution(self):
        in_file = self.input_file_path.get().strip('"').strip()
        if not in_file or not os.path.isfile(in_file):
            messagebox.showwarning("Missing Input", "Please select a valid input media file first.")
            return

        out_dir = self.output_dir_path.get().strip('"').strip()
        out_name = self.output_file_name.get().strip()
        if not out_name:
            self._update_output_filename()
            out_name = self.output_file_name.get().strip() or "output_processed.mp4"

        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, out_name)

        mode, settings = self._get_current_settings()
        args, _ = build_command(in_file, out_file, mode, settings)

        # Duration calculation for progress bar
        total_duration = 0.0
        if self.current_media_info and self.current_media_info.duration > 0:
            total_duration = self.current_media_info.duration

            # Adjust if start and end times were specified in trim/gif
            s_time = settings.get("start_time", "")
            e_time = settings.get("end_time", "")
            if s_time or e_time:
                s_sec = time_to_seconds(s_time)
                e_sec = time_to_seconds(e_time) if e_time else total_duration
                if e_sec > s_sec:
                    total_duration = e_sec - s_sec

        # Reset UI for running
        self.action_btn.configure(
            text="🛑 Cancel Processing",
            fg_color="#d62728",
            hover_color="#aa1f20",
            state="normal",
        )
        self.progress_bar.set(0.0)
        self.status_lbl.configure(text="Starting FFmpeg process...", text_color="#1f77b4")
        self.log_textbox.insert("end", f"\n=== [START] {time.strftime('%H:%M:%S')} ===\n")
        self.start_process_time = time.time()

        # Start runner
        self.runner.start(
            command=args,
            total_duration=total_duration,
            on_progress=lambda p: self.event_queue.put(("progress", p)),
            on_log=lambda l: self.event_queue.put(("log", l)),
            on_finish=lambda s, c, m: self.event_queue.put(("finish", (s, c, m, out_file))),
        )

    def _on_progress_update(self, p: Dict[str, Any]):
        pct = p.get("percentage", 0.0)
        self.progress_bar.set(pct / 100.0)

        parts = [f"Progress: {pct:.1f}%"]
        if p.get("time"):
            total_str = (
                f" / {seconds_to_time(self.runner.total_duration)}"
                if self.runner.total_duration > 0
                else ""
            )
            parts.append(f"Time: {p['time']}{total_str}")
        if p.get("speed"):
            parts.append(f"Speed: {p['speed']}")
        if p.get("fps"):
            parts.append(f"FPS: {p['fps']}")
        if p.get("size"):
            parts.append(f"Size: {p['size']}")

        self.status_lbl.configure(text=" | ".join(parts), text_color="#1f77b4")

    def _on_log_line(self, line: str):
        self.log_textbox.insert("end", line + "\n")
        self.log_textbox.see("end")

    def _on_finished(self, success: bool, return_code: int, error_msg: str, output_file: str):
        elapsed = time.time() - self.start_process_time
        self.action_btn.configure(
            text="🚀 Start Processing",
            fg_color="#1f77b4",
            hover_color="#14598a",
            state="normal",
        )

        if success and os.path.isfile(output_file):
            size_mb = os.path.getsize(output_file) / (1024 * 1024)
            self.progress_bar.set(1.0)
            self.status_lbl.configure(
                text=f"✅ Finished in {elapsed:.2f}s! Saved: {os.path.basename(output_file)} ({size_mb:.2f} MB)",
                text_color="#2ca02c",
            )
            self.log_textbox.insert("end", f"\n=== [FINISHED SUCCESS in {elapsed:.2f}s] ===\nSaved to: {output_file}\n")
        elif self.runner.is_cancelled:
            self.status_lbl.configure(text="🛑 Process was cancelled.", text_color="#d62728")
            self.log_textbox.insert("end", "\n=== [CANCELLED BY USER] ===\n")
        else:
            self.status_lbl.configure(
                text=f"❌ Error (Exit code {return_code}). Check log console below.",
                text_color="#d62728",
            )
            self.log_textbox.insert("end", f"\n=== [FAILED with exit code {return_code}] ===\n{error_msg}\n")
            if not self.log_frame.winfo_viewable():
                self._toggle_logs_view()


def main():
    app = FFmpegApp()
    app.mainloop()


if __name__ == "__main__":
    main()
