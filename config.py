"""
Central configuration and constants for the VLN Web UI.

All magic numbers and file paths live here so the rest of the
codebase stays free of hard-coded values.
"""

# ── File paths (shared with infer.py via /tmp) ────────────────
LOG_PATH = "/tmp/infer_live.log"
SHARED_FRAME_PATH = "/tmp/vln_latest_frame.jpg"
INSTRUCTION_FILE = "/tmp/vln_instruction.txt"
PAUSE_FLAG_FILE = "/tmp/vln_paused.flag"
RESTART_FLAG_FILE = "/tmp/vln_restart.flag"

# ── Streaming settings ────────────────────────────────────────
FRAME_RATE = 15          # frames per second for video feed
SSE_POLL_INTERVAL = 0.15  # seconds between log file polls
MAX_LOG_LINES = 500       # max lines kept in frontend log

# ── Server defaults ───────────────────────────────────────────
DEFAULT_PORT = 5000
DEFAULT_CAMERA_INDEX = 0
