"""
Server-Sent Events log stream with ANSI stripping and noise filtering.

Tails the inference log file and yields clean, categorised lines
as SSE events for the browser dashboard.
"""

import os
import re
import time
from typing import Generator

from vln_web.config import LOG_PATH, SSE_POLL_INTERVAL

# Regex to strip ANSI escape codes from terminal output
_ANSI_PATTERN = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
)

# Lines matching any of these patterns are suppressed in the UI
_NOISE_PATTERNS = (
    re.compile(r"^\s*\d+\.\d+\.\d+\.\d+ - - \["),   # Werkzeug request log
    re.compile(r"Press CTRL\+C to quit"),
    re.compile(r"Serving Flask app"),
    re.compile(r"Debug mode: off"),
    re.compile(r"Running on"),
    re.compile(r"This is a development server"),
    re.compile(r"^\s*warn\(", re.IGNORECASE),
    re.compile(r"UserWarning"),
    re.compile(r"torchvision"),
    re.compile(r"Loading checkpoint shards:"),
)


def _strip_ansi(text: str) -> str:
    """Remove ANSI color/escape codes from a string."""
    return _ANSI_PATTERN.sub("", text)


def _is_noise(line: str) -> bool:
    """Return True if the line matches a known noise pattern."""
    return any(pattern.search(line) for pattern in _NOISE_PATTERNS)


def generate_sse(log_path: str = LOG_PATH) -> Generator[str, None, None]:
    """Tail the inference log and yield SSE-formatted lines.

    Blocks until the log file appears, then streams new lines
    with ANSI codes stripped and noise lines filtered out.

    Args:
        log_path: Absolute path to the inference log file.

    Yields:
        SSE data strings (``data: <text>\\n\\n``).
    """
    # Wait for the log file to be created by the inference process
    while not os.path.exists(log_path):
        yield "data: waiting for inference to start…\n\n"
        time.sleep(1)

    with open(log_path, "r") as log_file:
        # Jump to end of file — only stream new content
        log_file.seek(0, 2)

        while True:
            line = log_file.readline()

            if not line:
                time.sleep(SSE_POLL_INTERVAL)
                continue

            clean = _strip_ansi(line.rstrip())

            if not clean or _is_noise(clean):
                continue

            yield f"data: {clean}\n\n"
