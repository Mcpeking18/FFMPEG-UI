"""
FFmpeg Studio Pro
Entry point for launching the desktop application.
"""

import sys
import os

# Ensure current directory is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from gui.app import main

if __name__ == "__main__":
    main()
