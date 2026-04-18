#!/usr/bin/env python3
"""
Entry point for running the VLN Web UI as a module.

Usage:
    python3 -m vln_web --port 5001
"""

import argparse
import threading

from vln_web.app import create_app
from vln_web.config import DEFAULT_PORT, DEFAULT_CAMERA_INDEX
from vln_web.services.frame_capture import FrameCapture
from vln_web.routes.pages import set_frame_capture


def main():
    parser = argparse.ArgumentParser(
        description="VLN Web UI — Voice-enabled dashboard for robot navigation"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to run the web server on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=DEFAULT_CAMERA_INDEX,
        help=f"Camera index (default: {DEFAULT_CAMERA_INDEX})",
    )
    parser.add_argument(
        "--log",
        default="/tmp/infer_live.log",
        help="Path to inference log file (default: /tmp/infer_live.log)",
    )
    args = parser.parse_args()

    # Create Flask app
    app = create_app()

    # Start frame capture thread
    frame_capture = FrameCapture()
    set_frame_capture(frame_capture)
    capture_thread = threading.Thread(target=frame_capture._capture_loop, daemon=True)
    capture_thread.start()

    # Print startup info
    print("=" * 60)
    print("VLN Web UI — Voice-Enabled Robot Navigation Dashboard")
    print("=" * 60)
    print(f"  Port        : {args.port}")
    print(f"  Camera      : {args.camera}")
    print(f"  Log file    : {args.log}")
    print(f"  Access at   : http://<robot-ip>:{args.port}")
    print("=" * 60)
    print()

    # Run Flask app
    app.run(host="0.0.0.0", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
