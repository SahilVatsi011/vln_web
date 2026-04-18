"""
REST API routes for controlling the inference session.

Handles:
    POST /set_instruction  → Write a new navigation instruction
    GET  /get_instruction  → Read the current instruction
    POST /pause            → Pause or resume inference
    POST /restart          → Restart the inference session
"""

import os

from flask import Blueprint, request, jsonify

from vln_web.config import (
    INSTRUCTION_FILE,
    PAUSE_FLAG_FILE,
    RESTART_FLAG_FILE,
)

api_blueprint = Blueprint("api", __name__)


def _write_file(path: str, content: str) -> None:
    """Write content to a file, creating it if needed."""
    with open(path, "w") as file:
        file.write(content)


def _read_file(path: str) -> str:
    """Read and return stripped file content, or empty string."""
    if not os.path.exists(path):
        return ""
    with open(path, "r") as file:
        return file.read().strip()


def _remove_file(path: str) -> None:
    """Remove a file if it exists, silently ignore if not."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


# ── Instruction ───────────────────────────────────────────────

@api_blueprint.route("/set_instruction", methods=["POST"])
def set_instruction():
    """Set a new navigation instruction and resume inference."""
    data = request.get_json() or {}
    instruction = data.get("instruction", "").strip()

    if instruction:
        _write_file(INSTRUCTION_FILE, instruction)
        # Setting a new instruction always resumes inference
        _remove_file(PAUSE_FLAG_FILE)

    return jsonify(instruction=instruction)


@api_blueprint.route("/get_instruction")
def get_instruction():
    """Return the current navigation instruction."""
    instruction = _read_file(INSTRUCTION_FILE)
    return jsonify(instruction=instruction)


# ── Session control ───────────────────────────────────────────

@api_blueprint.route("/pause", methods=["POST"])
def pause():
    """Pause or resume the inference session."""
    data = request.get_json() or {}
    is_paused = bool(data.get("paused", True))

    if is_paused:
        _write_file(PAUSE_FLAG_FILE, "")
    else:
        _remove_file(PAUSE_FLAG_FILE)

    return jsonify(paused=is_paused)


@api_blueprint.route("/restart", methods=["POST"])
def restart():
    """Restart the inference session with an optional instruction."""
    data = request.get_json() or {}
    instruction = data.get("instruction", "").strip()

    _write_file(RESTART_FLAG_FILE, instruction)

    if instruction:
        _write_file(INSTRUCTION_FILE, instruction)

    return jsonify(instruction=instruction)
