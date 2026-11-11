@echo off
title FFmpeg Studio Pro Launcher
echo Starting FFmpeg Studio Pro...
python "%~dp0main.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred while running the application.
    pause
)
