#!/usr/bin/env python3
"""
VLN Web UI — live webcam feed + real-time inference log + instruction input.
Run alongside infer.py (infer.py writes to /tmp/infer_live.log).
"""

import argparse
import os
import re
import time
import threading
import cv2
import numpy as np
from flask import Flask, Response, render_template_string, request, jsonify

app = Flask(__name__)

_log_path     = "/tmp/infer_live.log"
_shared_frame = "/tmp/vln_latest_frame.jpg"
_instr_file   = "/tmp/vln_instruction.txt"
_frame_lock   = threading.Lock()
_latest_frame = None

# strip ANSI color codes from log lines before streaming to browser
_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# lines we never want to show in the UI — noisy Flask + torchvision warnings
_NOISE_PATTERNS = (
    re.compile(r'^\s*\d+\.\d+\.\d+\.\d+ - - \['),     # Werkzeug request log
    re.compile(r'Press CTRL\+C to quit'),
    re.compile(r'Serving Flask app'),
    re.compile(r'Debug mode: off'),
    re.compile(r'Running on'),
    re.compile(r'This is a development server'),
    re.compile(r'^\s*warn\(', re.IGNORECASE),
    re.compile(r'UserWarning'),
    re.compile(r'torchvision'),
    re.compile(r'Loading checkpoint shards:'),
)

def _is_noise(line: str) -> bool:
    return any(p.search(line) for p in _NOISE_PATTERNS)


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VLN — Live Inference Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  /* ═══════════════════════════════════════════════════════════
     RESET & TOKENS
     ═══════════════════════════════════════════════════════════ */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    /* backgrounds */
    --bg-deep:    #06080d;
    --bg-base:    #0b0f18;
    --bg-surf-1:  #111827;
    --bg-surf-2:  #1a2234;
    --bg-surf-3:  #1e293b;
    /* borders */
    --border-dim:  rgba(255,255,255,0.06);
    --border-sub:  rgba(255,255,255,0.10);
    --border-vis:  rgba(255,255,255,0.15);
    /* text */
    --text-primary:   #f0f4f8;
    --text-secondary: #94a3b8;
    --text-muted:     #64748b;
    --text-dim:       #475569;
    /* accents */
    --accent:      #6366f1;
    --accent-glow: rgba(99,102,241,0.35);
    --cyan:        #22d3ee;
    --cyan-glow:   rgba(34,211,238,0.25);
    --green:       #34d399;
    --green-glow:  rgba(52,211,153,0.20);
    --amber:       #fbbf24;
    --amber-glow:  rgba(251,191,36,0.20);
    --rose:        #fb7185;
    --rose-glow:   rgba(251,113,133,0.20);
    --violet:      #a78bfa;
    --violet-glow: rgba(167,139,250,0.20);
    /* radii */
    --r-sm: 8px;
    --r-md: 12px;
    --r-lg: 16px;
    --r-xl: 20px;
    /* shadows */
    --shadow-card: 0 4px 24px rgba(0,0,0,0.35), 0 1px 3px rgba(0,0,0,0.25);
    --shadow-glow: 0 0 30px var(--accent-glow);
    /* transitions */
    --ease: cubic-bezier(0.4, 0, 0.2, 1);
  }

  html, body { height: 100%; overflow: hidden; }
  body {
    background: var(--bg-deep);
    color: var(--text-primary);
    font-family: 'Inter', -apple-system, 'Segoe UI', system-ui, sans-serif;
    display: flex; flex-direction: column;
    height: 100vh;
    font-size: 14px;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  /* animated background mesh */
  body::before {
    content: '';
    position: fixed; inset: 0;
    background:
      radial-gradient(ellipse 800px 600px at 15% 15%, rgba(99,102,241,0.08) 0%, transparent 70%),
      radial-gradient(ellipse 600px 500px at 85% 80%, rgba(34,211,238,0.06) 0%, transparent 70%),
      radial-gradient(ellipse 400px 400px at 50% 50%, rgba(167,139,250,0.04) 0%, transparent 70%);
    pointer-events: none;
    z-index: 0;
    animation: meshShift 20s ease-in-out infinite alternate;
  }
  @keyframes meshShift {
    0%   { opacity: 0.8; }
    50%  { opacity: 1; }
    100% { opacity: 0.7; }
  }

  body > * { position: relative; z-index: 1; }

  /* ═══════════════════════════════════════════════════════════
     HEADER
     ═══════════════════════════════════════════════════════════ */
  header {
    background: linear-gradient(180deg, rgba(17,24,39,0.95) 0%, rgba(11,15,24,0.98) 100%);
    backdrop-filter: blur(20px) saturate(1.4);
    padding: 14px 24px;
    border-bottom: 1px solid var(--border-dim);
    display: flex; align-items: center; gap: 16px;
    flex-shrink: 0;
  }
  .brand { display: flex; align-items: center; gap: 12px; }
  .logo {
    width: 36px; height: 36px; border-radius: 10px;
    background: linear-gradient(135deg, var(--accent) 0%, var(--cyan) 100%);
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 1rem; color: #fff;
    box-shadow: 0 2px 12px var(--accent-glow);
    letter-spacing: -0.5px;
    animation: logoGlow 3s ease-in-out infinite alternate;
  }
  @keyframes logoGlow {
    0%   { box-shadow: 0 2px 12px var(--accent-glow); }
    100% { box-shadow: 0 2px 20px var(--cyan-glow), 0 0 40px rgba(99,102,241,0.15); }
  }
  .brand-text h1 {
    font-size: 1.05rem; font-weight: 700;
    background: linear-gradient(135deg, #f0f4f8 30%, var(--cyan) 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.3px;
  }
  .brand-text .sub {
    font-size: 0.65rem; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 1.2px; font-weight: 500;
    margin-top: 1px;
  }
  .spacer { flex: 1; }

  /* status badges */
  .badge {
    font-size: 0.68rem; padding: 5px 14px; border-radius: 99px;
    font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px;
    display: inline-flex; align-items: center; gap: 7px;
    transition: all 0.3s var(--ease);
    border: 1px solid transparent;
  }
  .badge .dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: currentColor; flex-shrink: 0;
  }
  .badge.live {
    background: rgba(52,211,153,0.12); color: var(--green);
    border-color: rgba(52,211,153,0.2);
  }
  .badge.live .dot { animation: pulseDot 1.4s ease-out infinite; }
  .badge.paused {
    background: rgba(251,191,36,0.12); color: var(--amber);
    border-color: rgba(251,191,36,0.2);
  }
  .badge.offline {
    background: rgba(251,113,133,0.12); color: var(--rose);
    border-color: rgba(251,113,133,0.2);
  }
  .badge.connecting {
    background: rgba(148,163,184,0.10); color: var(--text-secondary);
    border-color: rgba(148,163,184,0.15);
  }
  .badge.connecting .dot { animation: pulseDot 1s ease-in-out infinite; }
  @keyframes pulseDot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.3; transform: scale(0.7); }
  }

  .pause-banner {
    display: none;
    background: rgba(251,191,36,0.10);
    border: 1px solid rgba(251,191,36,0.25);
    color: var(--amber);
    padding: 5px 14px; border-radius: var(--r-sm);
    font-size: 0.72rem; font-weight: 600;
    align-items: center; gap: 7px;
    backdrop-filter: blur(8px);
  }
  body.is-paused .pause-banner { display: inline-flex; }

  /* ═══════════════════════════════════════════════════════════
     STATS ROW
     ═══════════════════════════════════════════════════════════ */
  .stats {
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 12px; padding: 12px 20px;
    background: rgba(11,15,24,0.6);
    flex-shrink: 0;
  }
  .stat {
    background: var(--bg-surf-1);
    border: 1px solid var(--border-dim);
    border-radius: var(--r-md);
    padding: 14px 18px;
    display: flex; flex-direction: column; gap: 6px;
    transition: all 0.3s var(--ease);
    position: relative;
    overflow: hidden;
  }
  .stat::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 2px;
    border-radius: var(--r-md) var(--r-md) 0 0;
    opacity: 0.7;
    transition: opacity 0.3s var(--ease);
  }
  .stat:hover { border-color: var(--border-sub); transform: translateY(-1px); }
  .stat:hover::before { opacity: 1; }
  .stat .icon-wrap {
    width: 28px; height: 28px; border-radius: var(--r-sm);
    display: flex; align-items: center; justify-content: center;
    font-size: 0.85rem; flex-shrink: 0;
  }
  .stat .k {
    font-size: 0.62rem; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 1px; font-weight: 600;
  }
  .stat .v {
    font-size: 1.05rem; font-weight: 600;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    font-family: 'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace;
    font-size: 0.92rem;
  }

  .stat.instr::before  { background: linear-gradient(90deg, var(--amber), transparent); }
  .stat.instr .v       { color: var(--amber); }
  .stat.instr .icon-wrap { background: var(--amber-glow); color: var(--amber); }

  .stat.step::before   { background: linear-gradient(90deg, var(--cyan), transparent); }
  .stat.step .v        { color: var(--cyan); }
  .stat.step .icon-wrap  { background: var(--cyan-glow); color: var(--cyan); }

  .stat.action::before { background: linear-gradient(90deg, var(--green), transparent); }
  .stat.action .v      { color: var(--green); }
  .stat.action .icon-wrap { background: var(--green-glow); color: var(--green); }

  .stat.lat::before    { background: linear-gradient(90deg, var(--violet), transparent); }
  .stat.lat .v         { color: var(--violet); }
  .stat.lat .icon-wrap   { background: var(--violet-glow); color: var(--violet); }

  /* ═══════════════════════════════════════════════════════════
     CONTROL BAR
     ═══════════════════════════════════════════════════════════ */
  .ctrl-bar {
    background: rgba(17,24,39,0.7);
    backdrop-filter: blur(12px);
    border-top: 1px solid var(--border-dim);
    border-bottom: 1px solid var(--border-dim);
    padding: 12px 20px;
    display: flex; gap: 10px; align-items: center;
    flex-shrink: 0;
  }
  .ctrl-bar .label {
    font-size: 0.68rem; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 1px;
    font-weight: 600; white-space: nowrap;
  }
  #instr-input {
    flex: 1;
    background: var(--bg-surf-1);
    border: 1px solid var(--border-sub);
    color: var(--text-primary);
    padding: 11px 16px;
    border-radius: var(--r-md);
    font-size: 0.9rem;
    font-family: 'Inter', sans-serif;
    transition: all 0.2s var(--ease);
  }
  #instr-input::placeholder { color: var(--text-dim); }
  #instr-input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-glow), inset 0 0 0 1px rgba(99,102,241,0.2);
    background: rgba(17,24,39,0.9);
  }

  button {
    border: none; padding: 10px 18px; border-radius: var(--r-md);
    cursor: pointer; font-size: 0.82rem; font-weight: 600;
    transition: all 0.2s var(--ease);
    font-family: 'Inter', sans-serif;
    display: inline-flex; align-items: center; gap: 7px;
    letter-spacing: 0.2px;
  }
  button:hover:not(:disabled) { transform: translateY(-1px); }
  button:active:not(:disabled) { transform: translateY(0) scale(0.98); }
  button:disabled { opacity: 0.4; cursor: not-allowed; }

  button.set {
    background: linear-gradient(135deg, var(--green), #10b981);
    color: #fff;
    box-shadow: 0 2px 10px var(--green-glow);
  }
  button.set:hover:not(:disabled) {
    box-shadow: 0 4px 16px rgba(52,211,153,0.35);
  }
  button.pause {
    background: var(--bg-surf-2);
    color: var(--text-secondary);
    border: 1px solid var(--border-sub);
  }
  button.pause:hover:not(:disabled) {
    background: var(--bg-surf-3);
    color: var(--text-primary);
    border-color: var(--border-vis);
  }
  button.restart {
    background: linear-gradient(135deg, var(--rose), #e11d48);
    color: #fff;
    box-shadow: 0 2px 10px var(--rose-glow);
  }
  button.restart:hover:not(:disabled) {
    box-shadow: 0 4px 16px rgba(251,113,133,0.35);
  }

  /* ═══════════════════════════════════════════════════════════
     MAIN LAYOUT
     ═══════════════════════════════════════════════════════════ */
  .layout {
    display: grid; grid-template-columns: 1fr 480px;
    flex: 1; overflow: hidden; gap: 0;
  }

  /* ── camera panel ──────────────────────────────────────── */
  .cam-panel {
    background: #000; display: flex; flex-direction: column;
    align-items: stretch; justify-content: center;
    position: relative; overflow: hidden;
    border-right: 1px solid var(--border-dim);
  }
  .cam-wrap {
    flex: 1; display: flex; align-items: center;
    justify-content: center; padding: 20px;
    position: relative; overflow: hidden;
  }
  .cam-wrap img {
    max-width: 100%; max-height: 100%;
    border-radius: var(--r-lg);
    box-shadow: 0 8px 40px rgba(0,0,0,0.6), 0 0 60px rgba(99,102,241,0.06);
    border: 1px solid rgba(255,255,255,0.06);
    transition: box-shadow 0.4s var(--ease);
  }
  .cam-wrap img:hover {
    box-shadow: 0 8px 40px rgba(0,0,0,0.6), 0 0 80px rgba(99,102,241,0.1);
  }

  .cam-overlay {
    position: absolute; top: 28px; left: 28px; right: 28px;
    display: flex; justify-content: space-between;
    pointer-events: none;
    font-family: 'JetBrains Mono', 'SF Mono', monospace;
    font-size: 0.68rem;
  }
  .cam-overlay .tag {
    background: rgba(6,8,13,0.75);
    color: var(--text-secondary);
    padding: 5px 12px; border-radius: var(--r-sm);
    backdrop-filter: blur(12px) saturate(1.5);
    border: 1px solid rgba(255,255,255,0.08);
    display: flex; align-items: center; gap: 6px;
    font-weight: 500;
  }
  .cam-overlay .tag .rec-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--rose);
    animation: pulseDot 1.2s ease-out infinite;
  }

  /* cam bottom bar */
  .cam-bottom {
    position: absolute; bottom: 28px; left: 28px; right: 28px;
    display: flex; justify-content: center; pointer-events: none;
  }
  .cam-bottom .action-pill {
    background: rgba(6,8,13,0.8);
    backdrop-filter: blur(16px) saturate(1.5);
    border: 1px solid rgba(52,211,153,0.15);
    border-radius: 99px;
    padding: 6px 18px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: var(--green);
    font-weight: 600;
    letter-spacing: 0.3px;
    max-width: 80%;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    transition: all 0.3s var(--ease);
  }

  /* ── log panel ─────────────────────────────────────────── */
  .log-panel {
    background: var(--bg-base);
    display: flex; flex-direction: column;
    overflow: hidden;
  }
  .log-header {
    padding: 12px 18px;
    background: rgba(17,24,39,0.8);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border-dim);
    display: flex; align-items: center; gap: 10px;
    flex-shrink: 0;
  }
  .log-header .title-wrap {
    display: flex; align-items: center; gap: 8px; flex: 1;
  }
  .log-header .title-icon {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 8px var(--accent-glow);
    animation: pulseDot 2s ease-in-out infinite;
  }
  .log-header .title {
    font-size: 0.7rem; color: var(--text-muted); font-weight: 600;
    text-transform: uppercase; letter-spacing: 1px;
  }

  .filter-btn {
    padding: 5px 12px; border-radius: var(--r-sm);
    font-size: 0.65rem;
    background: transparent;
    border: 1px solid var(--border-sub);
    color: var(--text-muted);
    cursor: pointer; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.6px;
    transition: all 0.2s var(--ease);
    font-family: 'Inter', sans-serif;
  }
  .filter-btn:hover {
    color: var(--text-secondary);
    border-color: var(--border-vis);
    background: rgba(255,255,255,0.03);
  }
  .filter-btn.on {
    background: linear-gradient(135deg, var(--accent), #818cf8);
    border-color: transparent;
    color: #fff;
    box-shadow: 0 2px 8px var(--accent-glow);
  }

  #log {
    flex: 1; overflow-y: auto; padding: 12px 18px;
    font-family: 'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace;
    font-size: 0.74rem; line-height: 1.7;
    scroll-behavior: smooth;
  }
  #log::-webkit-scrollbar { width: 6px; }
  #log::-webkit-scrollbar-track { background: transparent; }
  #log::-webkit-scrollbar-thumb {
    background: rgba(255,255,255,0.08);
    border-radius: 3px;
  }
  #log::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }

  .line {
    padding: 3px 0; word-break: break-word;
    display: flex; gap: 10px;
    border-radius: 4px;
    transition: background 0.15s;
    animation: fadeInLine 0.25s ease-out;
  }
  @keyframes fadeInLine {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .line:hover { background: rgba(255,255,255,0.02); }
  .line .ts {
    color: var(--text-dim); flex-shrink: 0;
    font-size: 0.65rem; padding-top: 2px;
    min-width: 56px; opacity: 0.6;
  }
  .line .txt { flex: 1; }

  .line.step   .txt { color: var(--cyan); font-weight: 600; }
  .line.action .txt { color: var(--green); }
  .line.instr  .txt { color: var(--amber); font-weight: 600; }
  .line.warn   .txt { color: var(--amber); opacity: 0.85; }
  .line.err    .txt { color: var(--rose); font-weight: 500; }
  .line.info   .txt { color: var(--text-dim); }

  .line.system {
    margin: 6px 0; padding: 8px 14px;
    border-radius: var(--r-sm);
    background: rgba(99,102,241,0.06);
    border-left: 3px solid var(--accent);
    border: 1px solid rgba(99,102,241,0.12);
    border-left: 3px solid var(--accent);
  }
  .line.system .txt { color: var(--violet); font-weight: 600; }

  body.filter-on .line.info { display: none; }

  /* scroll-to-bottom button */
  .scroll-btn {
    position: absolute; right: 18px; bottom: 16px;
    background: linear-gradient(135deg, var(--accent), #818cf8);
    color: #fff; border: none;
    padding: 7px 14px; border-radius: 99px;
    font-size: 0.68rem; font-weight: 700;
    cursor: pointer;
    display: none;
    box-shadow: 0 4px 16px var(--accent-glow);
    font-family: 'Inter', sans-serif;
    transition: all 0.2s var(--ease);
    letter-spacing: 0.3px;
  }
  .scroll-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 24px rgba(99,102,241,0.4);
  }
  .scroll-btn.show { display: flex; align-items: center; gap: 5px; }

  /* ═══════════════════════════════════════════════════════════
     VOICE COMMAND — MIC BUTTON
     ═══════════════════════════════════════════════════════════ */
  .mic-btn {
    width: 42px; height: 42px; border-radius: 50%;
    background: var(--bg-surf-2); border: 1px solid var(--border-sub);
    color: var(--text-secondary); cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.1rem; transition: all 0.3s var(--ease);
    position: relative; flex-shrink: 0;
    padding: 0;
  }
  .mic-btn:hover {
    background: var(--bg-surf-3); color: var(--text-primary);
    border-color: var(--border-vis); transform: translateY(-1px);
  }
  .mic-btn.recording {
    background: rgba(251,113,133,0.15); border-color: var(--rose);
    color: var(--rose);
    animation: micPulse 1.5s ease-in-out infinite;
  }
  .mic-btn.recording::after {
    content: ''; position: absolute; inset: -4px;
    border-radius: 50%; border: 2px solid var(--rose);
    animation: micRing 1.5s ease-out infinite;
  }
  @keyframes micPulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(251,113,133,0); }
    50% { box-shadow: 0 0 20px 4px rgba(251,113,133,0.25); }
  }
  @keyframes micRing {
    0% { transform: scale(1); opacity: 0.6; }
    100% { transform: scale(1.5); opacity: 0; }
  }
  .mic-btn svg {
    width: 18px; height: 18px; fill: currentColor;
  }

  /* ═══════════════════════════════════════════════════════════
     VOICE OVERLAY
     ═══════════════════════════════════════════════════════════ */
  .voice-overlay {
    position: fixed; inset: 0; z-index: 1000;
    background: rgba(6,8,13,0.88);
    backdrop-filter: blur(30px) saturate(1.5);
    display: none; align-items: center; justify-content: center;
    flex-direction: column;
    animation: overlayIn 0.3s var(--ease);
  }
  .voice-overlay.active { display: flex; }
  @keyframes overlayIn {
    from { opacity: 0; }
    to   { opacity: 1; }
  }

  .voice-card {
    background: var(--bg-surf-1);
    border: 1px solid var(--border-sub);
    border-radius: var(--r-xl);
    padding: 48px 56px;
    display: flex; flex-direction: column; align-items: center;
    gap: 28px;
    max-width: 520px; width: 90%;
    box-shadow: 0 24px 80px rgba(0,0,0,0.5), 0 0 80px rgba(99,102,241,0.08);
    animation: cardIn 0.4s var(--ease);
  }
  @keyframes cardIn {
    from { opacity: 0; transform: translateY(20px) scale(0.95); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
  }

  /* waveform visualizer */
  .voice-visualizer {
    width: 100px; height: 100px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    position: relative;
  }
  .voice-visualizer .ring {
    position: absolute; inset: 0; border-radius: 50%;
    border: 2px solid rgba(99,102,241,0.3);
  }
  .voice-visualizer .ring:nth-child(1) { animation: vRing 2s ease-in-out infinite; }
  .voice-visualizer .ring:nth-child(2) { animation: vRing 2s ease-in-out 0.4s infinite; inset: -10px; }
  .voice-visualizer .ring:nth-child(3) { animation: vRing 2s ease-in-out 0.8s infinite; inset: -20px; }
  @keyframes vRing {
    0%, 100% { opacity: 0.2; transform: scale(0.95); }
    50% { opacity: 0.7; transform: scale(1.05); }
  }

  .voice-visualizer .core {
    width: 60px; height: 60px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem; z-index: 1;
    transition: all 0.4s var(--ease);
  }

  /* States */
  .voice-overlay[data-state="listening"] .voice-visualizer .core {
    background: linear-gradient(135deg, var(--accent), var(--cyan));
    box-shadow: 0 0 40px var(--accent-glow);
  }
  .voice-overlay[data-state="listening"] .ring { border-color: var(--accent); }

  .voice-overlay[data-state="confirming"] .voice-visualizer .core {
    background: linear-gradient(135deg, var(--amber), #f59e0b);
    box-shadow: 0 0 40px var(--amber-glow);
  }
  .voice-overlay[data-state="confirming"] .ring { border-color: var(--amber); }

  .voice-overlay[data-state="confirmed"] .voice-visualizer .core {
    background: linear-gradient(135deg, var(--green), #10b981);
    box-shadow: 0 0 40px var(--green-glow);
  }
  .voice-overlay[data-state="confirmed"] .ring {
    border-color: var(--green); animation: none; opacity: 0.4;
  }

  .voice-overlay[data-state="cancelled"] .voice-visualizer .core {
    background: linear-gradient(135deg, var(--rose), #e11d48);
    box-shadow: 0 0 40px var(--rose-glow);
  }
  .voice-overlay[data-state="cancelled"] .ring {
    border-color: var(--rose); animation: none; opacity: 0.4;
  }

  .voice-overlay[data-state="error"] .voice-visualizer .core {
    background: var(--bg-surf-3);
    box-shadow: none;
  }
  .voice-overlay[data-state="error"] .ring { animation: none; opacity: 0.15; }

  /* waveform bars */
  .waveform {
    display: flex; align-items: center; gap: 3px;
    height: 40px;
  }
  .waveform .bar {
    width: 4px; border-radius: 2px;
    background: var(--accent);
    animation: waveBar 0.8s ease-in-out infinite;
  }
  .waveform .bar:nth-child(1) { height: 12px; animation-delay: 0s; }
  .waveform .bar:nth-child(2) { height: 24px; animation-delay: 0.1s; }
  .waveform .bar:nth-child(3) { height: 36px; animation-delay: 0.2s; }
  .waveform .bar:nth-child(4) { height: 28px; animation-delay: 0.3s; }
  .waveform .bar:nth-child(5) { height: 16px; animation-delay: 0.4s; }
  .waveform .bar:nth-child(6) { height: 32px; animation-delay: 0.15s; }
  .waveform .bar:nth-child(7) { height: 20px; animation-delay: 0.35s; }
  @keyframes waveBar {
    0%, 100% { transform: scaleY(0.4); opacity: 0.4; }
    50% { transform: scaleY(1); opacity: 1; }
  }

  .voice-overlay[data-state="confirming"] .waveform .bar { background: var(--amber); }
  .voice-overlay:not([data-state="listening"]):not([data-state="confirming"]) .waveform .bar {
    animation: none; transform: scaleY(0.3); opacity: 0.2;
  }

  .voice-title {
    font-size: 1.1rem; font-weight: 700; color: var(--text-primary);
    text-align: center; letter-spacing: -0.2px;
  }
  .voice-subtitle {
    font-size: 0.82rem; color: var(--text-secondary);
    text-align: center; line-height: 1.5;
  }
  .voice-transcript {
    background: var(--bg-surf-2); border: 1px solid var(--border-sub);
    border-radius: var(--r-md); padding: 14px 20px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.88rem; color: var(--cyan);
    width: 100%; text-align: center; min-height: 44px;
    display: flex; align-items: center; justify-content: center;
    transition: all 0.3s var(--ease);
  }
  .voice-transcript:empty::after {
    content: 'Listening…';
    color: var(--text-dim); font-style: italic;
  }

  .voice-actions {
    display: flex; gap: 12px; margin-top: 4px;
  }
  .voice-actions button {
    padding: 10px 24px; border-radius: var(--r-md);
    font-size: 0.85rem; font-weight: 600;
  }
  .voice-actions .v-cancel {
    background: var(--bg-surf-2); color: var(--text-secondary);
    border: 1px solid var(--border-sub);
  }
  .voice-actions .v-cancel:hover {
    background: var(--bg-surf-3); color: var(--text-primary);
  }

  /* ═══════════════════════════════════════════════════════════
     RESPONSIVE
     ═══════════════════════════════════════════════════════════ */
  @media (max-width: 1024px) {
    .layout { grid-template-columns: 1fr; grid-template-rows: 1fr 1fr; }
    .cam-panel { border-right: none; border-bottom: 1px solid var(--border-dim); }
    .stats { grid-template-columns: repeat(2, 1fr); }
  }
  @media (max-width: 640px) {
    .stats { grid-template-columns: 1fr; }
    header { padding: 10px 16px; gap: 10px; }
    .ctrl-bar { flex-wrap: wrap; padding: 10px 14px; }
    .ctrl-bar .label { width: 100%; }
    .voice-card { padding: 32px 24px; }
  }
</style>
</head>
<body>
<header>
  <div class="brand">
    <div class="logo">V</div>
    <div class="brand-text">
      <h1>VLN Live Inference</h1>
      <span class="sub">Vision · Language · Navigation</span>
    </div>
  </div>
  <div class="spacer"></div>
  <span class="badge connecting" id="status"><span class="dot"></span> Connecting</span>
  <span class="pause-banner">&#9208; Paused</span>
</header>

<div class="stats">
  <div class="stat instr">
    <div style="display:flex;align-items:center;gap:10px;">
      <div class="icon-wrap">&#128172;</div>
      <div>
        <span class="k">Instruction</span>
        <span class="v" id="stat-instr">&mdash;</span>
      </div>
    </div>
  </div>
  <div class="stat step">
    <div style="display:flex;align-items:center;gap:10px;">
      <div class="icon-wrap">&#9654;</div>
      <div>
        <span class="k">Step</span>
        <span class="v" id="stat-step">&mdash;</span>
      </div>
    </div>
  </div>
  <div class="stat action">
    <div style="display:flex;align-items:center;gap:10px;">
      <div class="icon-wrap">&#9889;</div>
      <div>
        <span class="k">Current Action</span>
        <span class="v" id="stat-action">&mdash;</span>
      </div>
    </div>
  </div>
  <div class="stat lat">
    <div style="display:flex;align-items:center;gap:10px;">
      <div class="icon-wrap">&#9201;</div>
      <div>
        <span class="k">LLM Latency</span>
        <span class="v" id="stat-lat">&mdash;</span>
      </div>
    </div>
  </div>
</div>

<div class="ctrl-bar">
  <span class="label">&#128269; Instruction</span>
  <button class="mic-btn" id="mic-btn" onclick="startVoiceCommand()" title="Voice Command">
    <svg viewBox="0 0 24 24"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5zm6 6c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>
  </button>
  <input id="instr-input" type="text"
         placeholder="e.g.  walk to the kitchen and stop at the fridge">
  <button class="set" id="set-btn" onclick="setInstruction()">&#x2713; Set</button>
  <button class="pause" id="pause-btn" onclick="togglePause()">&#x23F8; Pause</button>
  <button class="restart" onclick="restartSession()">&#x21BA; Restart</button>
</div>

<!-- ═══ VOICE COMMAND OVERLAY ═══════════════════════════════ -->
<div class="voice-overlay" id="voice-overlay" data-state="listening">
  <div class="voice-card">
    <div class="voice-visualizer">
      <div class="ring"></div>
      <div class="ring"></div>
      <div class="ring"></div>
      <div class="core" id="voice-icon">&#127908;</div>
    </div>
    <div class="waveform">
      <div class="bar"></div><div class="bar"></div><div class="bar"></div>
      <div class="bar"></div><div class="bar"></div><div class="bar"></div>
      <div class="bar"></div>
    </div>
    <div class="voice-title" id="voice-title">Listening…</div>
    <div class="voice-subtitle" id="voice-subtitle">Speak your navigation instruction clearly</div>
    <div class="voice-transcript" id="voice-transcript"></div>
    <div class="voice-actions">
      <button class="v-cancel" onclick="cancelVoice()">&#x2715; Cancel</button>
    </div>
  </div>
</div>

<div class="layout">
  <div class="cam-panel">
    <div class="cam-wrap">
      <img src="/video_feed" alt="Webcam feed">
      <div class="cam-overlay">
        <span class="tag"><span class="rec-dot"></span> CAM &middot; LIVE</span>
        <span class="tag" id="cam-tag-r">&mdash;</span>
      </div>
    </div>
    <div class="cam-bottom">
      <div class="action-pill" id="action-pill">Awaiting instruction…</div>
    </div>
  </div>
  <div class="log-panel">
    <div class="log-header">
      <div class="title-wrap">
        <span class="title-icon"></span>
        <span class="title">Model Output &amp; Actions</span>
      </div>
      <button class="filter-btn on" id="filter-btn" onclick="toggleFilter()">Important Only</button>
      <button class="filter-btn" onclick="clearLog()">Clear</button>
    </div>
    <div style="position:relative; flex:1; display:flex; overflow:hidden;">
      <div id="log"></div>
      <button class="scroll-btn" id="scroll-btn" onclick="scrollToBottom()">&#8595; Live</button>
    </div>
  </div>
</div>

<script>
const log         = document.getElementById('log');
const statusEl    = document.getElementById('status');
const statInstr   = document.getElementById('stat-instr');
const statStep    = document.getElementById('stat-step');
const statAction  = document.getElementById('stat-action');
const statLat     = document.getElementById('stat-lat');
const instrInput  = document.getElementById('instr-input');
const setBtn      = document.getElementById('set-btn');
const pauseBtn    = document.getElementById('pause-btn');
const filterBtn   = document.getElementById('filter-btn');
const scrollBtn   = document.getElementById('scroll-btn');
const camTagR     = document.getElementById('cam-tag-r');
const actionPill  = document.getElementById('action-pill');

const MAX_LINES = 500;
let paused = false;
let autoScroll = true;

function ts() {
  const d = new Date();
  return d.toTimeString().slice(0,8);
}

function setBadge(text, cls) {
  statusEl.innerHTML = '<span class="dot"></span> ' + text;
  statusEl.className = 'badge ' + cls;
}

function setPaused(p) {
  paused = p;
  document.body.classList.toggle('is-paused', p);
  pauseBtn.innerHTML = p ? '&#9654; Resume' : '&#x23F8; Pause';
  if (p) setBadge('Paused', 'paused');
  else   setBadge('Live',   'live');
}

function classify(text) {
  if (text.includes('***') || text.includes('[RESTART]') || text.includes('[INSTRUCTION]'))
    return 'system';
  if (text.includes('[Step'))                             return 'step';
  if (text.includes('[Go1]') || text.includes('DRY-RUN')) return 'action';
  if (text.match(/Instruction\s*:/))                     return 'instr';
  if (text.includes('Error') || text.includes('Traceback')) return 'err';
  if (text.toLowerCase().includes('warn'))                return 'warn';
  return 'info';
}

function parseStep(text) {
  const m = text.match(/\[Step\s+(\d+)\]\s+([\d.]+)s\s*[\u2192\-\>]+\s*([A-Z][^(]*?)(?:\s{2,}|$)/);
  if (!m) return null;
  return { step: m[1], latency: parseFloat(m[2]), action: m[3].trim() };
}

function parseGo1(text) {
  const m = text.match(/\[Go1\]\s+(.+?)\s+\(/);
  return m ? m[1].trim() : null;
}

function addLine(text) {
  if (!text) return;
  const cls = classify(text);
  const row = document.createElement('div');
  row.className = 'line ' + cls;
  row.innerHTML = '<span class="ts"></span><span class="txt"></span>';
  row.children[0].textContent = ts();
  row.children[1].textContent = text;
  log.appendChild(row);
  if (log.children.length > MAX_LINES) log.removeChild(log.firstChild);
  if (autoScroll) log.scrollTop = log.scrollHeight;

  // ── update stats ──────────────────────────────────────────
  const stepInfo = parseStep(text);
  if (stepInfo) {
    statStep.textContent   = '#' + stepInfo.step;
    statAction.textContent = stepInfo.action;
    statLat.textContent    = stepInfo.latency > 0
                           ? stepInfo.latency.toFixed(1) + 's'
                           : '< 0.1s (cached)';
    camTagR.textContent    = 'STEP ' + stepInfo.step + ' · ' + stepInfo.action;
    actionPill.textContent = stepInfo.action;
  }
  const go1 = parseGo1(text);
  if (go1) {
    statAction.textContent = go1;
    actionPill.textContent = go1;
  }

  const mI = text.match(/Instruction\s*:\s*(.+)/);
  if (mI) statInstr.textContent = mI[1].trim();
  const nI = text.match(/NEW INSTRUCTION \*\*\*\s*[\u2192\-\>]+\s*(.+)/);
  if (nI) statInstr.textContent = nI[1].trim();

  if (text.includes('PAUSED'))  setPaused(true);
  if (text.includes('RESUMED')) setPaused(false);
  if (text.includes('NEW INSTRUCTION')) setPaused(false);
}

function setInstruction() {
  const val = instrInput.value.trim();
  if (!val) { instrInput.focus(); return; }
  setBtn.disabled = true;
  fetch('/set_instruction', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({instruction: val})
  }).then(r => r.json()).then(d => {
    statInstr.textContent = d.instruction;
    addLine('[INSTRUCTION] -> ' + d.instruction);
    instrInput.value = '';
  }).finally(() => { setBtn.disabled = false; instrInput.focus(); });
}

function togglePause() {
  const next = !paused;
  fetch('/pause', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({paused: next})
  }).then(() => {
    setPaused(next);
    addLine(next ? '[PAUSED] by user' : '[RESUMED] by user');
  });
}

function restartSession() {
  if (!confirm('Restart inference session? Step counter will reset.')) return;
  fetch('/restart', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({instruction: ''})
  }).then(() => {
    addLine('[RESTART] Session reset');
    statStep.textContent   = '\u2014';
    statAction.textContent = '\u2014';
    statLat.textContent    = '\u2014';
    camTagR.textContent    = '\u2014';
    actionPill.textContent = 'Awaiting instruction\u2026';
    clearLog();
    setPaused(true);
    instrInput.focus();
  });
}

function toggleFilter() {
  const on = !filterBtn.classList.contains('on');
  filterBtn.classList.toggle('on', on);
  document.body.classList.toggle('filter-on', on);
}

function clearLog() { log.innerHTML = ''; }

function scrollToBottom() {
  autoScroll = true;
  log.scrollTop = log.scrollHeight;
  scrollBtn.classList.remove('show');
}

log.addEventListener('scroll', () => {
  const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
  autoScroll = atBottom;
  scrollBtn.classList.toggle('show', !atBottom);
});

instrInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') setInstruction();
});

// init filter state: "Important only" is ON by default
document.body.classList.add('filter-on');

fetch('/get_instruction').then(r => r.json()).then(d => {
  if (d.instruction) statInstr.textContent = d.instruction;
});

const es = new EventSource('/events');
es.onopen    = () => { if (!paused) setBadge('Live', 'live'); };
es.onerror   = () => { setBadge('Offline', 'offline'); };
es.onmessage = (e) => addLine(e.data);

// ═══════════════════════════════════════════════════════════
// VOICE COMMAND SYSTEM
// ═══════════════════════════════════════════════════════════
const voiceOverlay   = document.getElementById('voice-overlay');
const voiceTitle     = document.getElementById('voice-title');
const voiceSubtitle  = document.getElementById('voice-subtitle');
const voiceTranscript= document.getElementById('voice-transcript');
const voiceIcon      = document.getElementById('voice-icon');
const micBtn         = document.getElementById('mic-btn');

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let voiceState = 'idle'; // idle | listening | confirming | confirmed | cancelled

function setVoiceState(state) {
  voiceState = state;
  voiceOverlay.setAttribute('data-state', state);
}

function speak(text) {
  return new Promise((resolve) => {
    const synth = window.speechSynthesis;
    // cancel any pending
    synth.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 1.05;
    utter.pitch = 1.0;
    utter.volume = 1.0;
    // try to pick a good English voice
    const voices = synth.getVoices();
    const preferred = voices.find(v => v.lang.startsWith('en') && v.name.includes('Google'));
    if (preferred) utter.voice = preferred;
    else {
      const eng = voices.find(v => v.lang.startsWith('en'));
      if (eng) utter.voice = eng;
    }
    utter.onend = resolve;
    utter.onerror = resolve;
    synth.speak(utter);
  });
}

function startVoiceCommand() {
  if (!SpeechRecognition) {
    alert('Speech Recognition is not supported in this browser. Please use Chrome.');
    return;
  }

  // Show overlay
  voiceOverlay.classList.add('active');
  setVoiceState('listening');
  voiceTitle.textContent = 'Listening…';
  voiceSubtitle.textContent = 'Speak your navigation instruction clearly';
  voiceTranscript.textContent = '';
  voiceIcon.innerHTML = '&#127908;';
  micBtn.classList.add('recording');

  // Start speech recognition
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = 'en-US';
  recognition.maxAlternatives = 1;

  recognition.onresult = (event) => {
    let interim = '';
    let final_ = '';
    for (let i = 0; i < event.results.length; i++) {
      if (event.results[i].isFinal) {
        final_ += event.results[i][0].transcript;
      } else {
        interim += event.results[i][0].transcript;
      }
    }
    voiceTranscript.textContent = final_ || interim;
    if (final_) {
      // We got a final transcript — move to confirmation
      instrInput.value = final_.trim();
      startConfirmation(final_.trim());
    }
  };

  recognition.onerror = (event) => {
    console.error('Speech recognition error:', event.error);
    if (event.error === 'no-speech') {
      voiceTitle.textContent = 'No speech detected';
      voiceSubtitle.textContent = 'Please try again';
      setVoiceState('error');
      voiceIcon.innerHTML = '&#128263;';
    } else if (event.error === 'not-allowed') {
      voiceTitle.textContent = 'Microphone blocked';
      voiceSubtitle.textContent = 'Please allow microphone access and try again';
      setVoiceState('error');
      voiceIcon.innerHTML = '&#128683;';
    } else {
      voiceTitle.textContent = 'Error occurred';
      voiceSubtitle.textContent = event.error;
      setVoiceState('error');
      voiceIcon.innerHTML = '&#9888;';
    }
    micBtn.classList.remove('recording');
    setTimeout(() => closeVoice(), 2000);
  };

  recognition.onend = () => {
    // If still in listening state (no result yet), just close
    if (voiceState === 'listening') {
      voiceTitle.textContent = 'No speech detected';
      voiceSubtitle.textContent = 'Please try again';
      setVoiceState('error');
      voiceIcon.innerHTML = '&#128263;';
      micBtn.classList.remove('recording');
      setTimeout(() => closeVoice(), 2000);
    }
  };

  recognition.start();
}

async function startConfirmation(transcript) {
  setVoiceState('confirming');
  voiceIcon.innerHTML = '&#10067;';
  voiceTitle.textContent = 'Confirm instruction?';
  voiceSubtitle.innerHTML = 'Say <strong style="color:var(--green)">"Yes"</strong> or <strong style="color:var(--green)">"Confirm"</strong> to execute, or <strong style="color:var(--rose)">"No"</strong> / <strong style="color:var(--rose)">"Cancel"</strong> to discard';

  // Speak the confirmation
  await speak('Your instruction is: ' + transcript + '. Shall I confirm?');

  // Now listen for yes/no
  const confirmRecog = new SpeechRecognition();
  confirmRecog.continuous = false;
  confirmRecog.interimResults = false;
  confirmRecog.lang = 'en-US';
  confirmRecog.maxAlternatives = 3;

  confirmRecog.onresult = (event) => {
    const reply = event.results[0][0].transcript.toLowerCase().trim();
    console.log('Confirmation reply:', reply);

    const yesWords = ['yes', 'yeah', 'yep', 'confirm', 'confirmed', 'go', 'do it', 'okay', 'ok', 'sure', 'proceed', 'execute', 'affirmative'];
    const noWords  = ['no', 'nope', 'cancel', 'stop', 'abort', 'discard', 'negative', 'don\'t', 'nah'];

    const isYes = yesWords.some(w => reply.includes(w));
    const isNo  = noWords.some(w => reply.includes(w));

    if (isYes && !isNo) {
      // Confirmed!
      setVoiceState('confirmed');
      voiceIcon.innerHTML = '&#10003;';
      voiceTitle.textContent = 'Confirmed!';
      voiceSubtitle.textContent = 'Executing instruction…';
      micBtn.classList.remove('recording');
      speak('Confirmed. Executing instruction now.').then(() => {
        // Actually set the instruction
        setInstruction();
        addLine('[VOICE] Instruction confirmed: ' + transcript);
        setTimeout(() => closeVoice(), 800);
      });
    } else {
      // Cancelled
      setVoiceState('cancelled');
      voiceIcon.innerHTML = '&#10007;';
      voiceTitle.textContent = 'Cancelled';
      voiceSubtitle.textContent = 'Instruction discarded';
      micBtn.classList.remove('recording');
      instrInput.value = '';
      speak('Cancelled.').then(() => {
        addLine('[VOICE] Instruction cancelled by user');
        setTimeout(() => closeVoice(), 800);
      });
    }
  };

  confirmRecog.onerror = (event) => {
    console.error('Confirmation recognition error:', event.error);
    setVoiceState('error');
    voiceIcon.innerHTML = '&#9888;';
    voiceTitle.textContent = 'Could not hear response';
    voiceSubtitle.textContent = 'Instruction kept in input — press Set to confirm manually';
    micBtn.classList.remove('recording');
    setTimeout(() => closeVoice(), 2500);
  };

  confirmRecog.onend = () => {
    if (voiceState === 'confirming') {
      // Timed out waiting for a response
      voiceTitle.textContent = 'No response heard';
      voiceSubtitle.textContent = 'Instruction kept in input — press Set to confirm manually';
      setVoiceState('error');
      voiceIcon.innerHTML = '&#128263;';
      micBtn.classList.remove('recording');
      setTimeout(() => closeVoice(), 2500);
    }
  };

  confirmRecog.start();
}

function cancelVoice() {
  if (recognition) {
    try { recognition.abort(); } catch(e) {}
  }
  window.speechSynthesis.cancel();
  micBtn.classList.remove('recording');
  setVoiceState('cancelled');
  voiceIcon.innerHTML = '&#10007;';
  voiceTitle.textContent = 'Cancelled';
  voiceSubtitle.textContent = '';
  setTimeout(() => closeVoice(), 400);
}

function closeVoice() {
  voiceOverlay.classList.remove('active');
  voiceState = 'idle';
  micBtn.classList.remove('recording');
}

// Preload voices (Chrome loads them async)
if (window.speechSynthesis) {
  window.speechSynthesis.getVoices();
  window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
}

// Close voice overlay with Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && voiceOverlay.classList.contains('active')) {
    cancelVoice();
  }
});
</script>
</body>
</html>
"""

# ── frame reader ──────────────────────────────────────────────────────────────
def _capture_loop():
    global _latest_frame
    while True:
        try:
            if os.path.exists(_shared_frame):
                with open(_shared_frame, 'rb') as f:
                    data = f.read()
                if data:
                    with _frame_lock:
                        _latest_frame = data
        except Exception:
            pass
        time.sleep(1 / 15)

def _mjpeg_gen():
    placeholder = None
    while True:
        with _frame_lock:
            frame = _latest_frame
        if frame is None:
            if placeholder is None:
                img = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(img, "Waiting for inference...", (80, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (100, 100, 100), 2)
                _, buf = cv2.imencode('.jpg', img)
                placeholder = buf.tobytes()
            frame = placeholder
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(1 / 15)

# ── SSE log stream ────────────────────────────────────────────────────────────
def _sse_gen():
    while not os.path.exists(_log_path):
        yield "data: waiting for inference to start…\n\n"
        time.sleep(1)
    with open(_log_path, 'r') as f:
        f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.15)
                continue
            clean = _ANSI_RE.sub('', line.rstrip())
            if not clean or _is_noise(clean):
                continue
            # SSE requires each line to be prefixed with "data: ";
            # for multi-line payloads split on newlines — but we already stripped \n.
            yield f"data: {clean}\n\n"

# ── HOME PAGE ─────────────────────────────────────────────────────────────────
HOME_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VLN — Vision Language Navigation Robot</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&family=Outfit:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg-void:    #020409;
    --bg-deep:    #06080d;
    --bg-base:    #0b0f18;
    --bg-surf-1:  #111827;
    --bg-surf-2:  #1a2234;
    --bg-surf-3:  #1e293b;
    --border-dim:  rgba(255,255,255,0.04);
    --border-sub:  rgba(255,255,255,0.08);
    --border-vis:  rgba(255,255,255,0.12);
    --text-primary:   #f0f4f8;
    --text-secondary: #94a3b8;
    --text-muted:     #64748b;
    --text-dim:       #475569;
    --accent:      #6366f1;
    --accent-glow: rgba(99,102,241,0.35);
    --cyan:        #22d3ee;
    --cyan-glow:   rgba(34,211,238,0.25);
    --green:       #34d399;
    --green-glow:  rgba(52,211,153,0.20);
    --amber:       #fbbf24;
    --rose:        #fb7185;
    --violet:      #a78bfa;
    --r-sm: 8px; --r-md: 12px; --r-lg: 16px; --r-xl: 24px; --r-2xl: 32px;
    --ease: cubic-bezier(0.4, 0, 0.2, 1);
    --ease-out: cubic-bezier(0, 0, 0.2, 1);
    --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
  }

  html { scroll-behavior: smooth; }
  body {
    background: var(--bg-void); color: var(--text-primary);
    font-family: 'Inter', -apple-system, system-ui, sans-serif;
    overflow-x: hidden;
    -webkit-font-smoothing: antialiased;
  }

  /* ═══════════════════════════════════════════════════════════
     CANVAS PARTICLES
     ═══════════════════════════════════════════════════════════ */
  #particles {
    position: fixed; inset: 0; z-index: 0;
    pointer-events: none;
  }

  /* ═══════════════════════════════════════════════════════════
     GRID OVERLAY
     ═══════════════════════════════════════════════════════════ */
  .grid-overlay {
    position: fixed; inset: 0; z-index: 0; pointer-events: none; opacity: 0.03;
    background-image:
      linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px);
    background-size: 80px 80px;
  }

  /* scan line */
  .scan-line {
    position: fixed; left: 0; right: 0; height: 2px; z-index: 1;
    background: linear-gradient(90deg, transparent, var(--cyan), transparent);
    opacity: 0.12;
    animation: scanDown 8s linear infinite;
    pointer-events: none;
  }
  @keyframes scanDown {
    0%   { top: -2px; }
    100% { top: 100vh; }
  }

  /* ═══════════════════════════════════════════════════════════
     NAVBAR
     ═══════════════════════════════════════════════════════════ */
  nav {
    position: fixed; top: 0; left: 0; right: 0; z-index: 100;
    background: rgba(2,4,9,0.7);
    backdrop-filter: blur(24px) saturate(1.6);
    border-bottom: 1px solid var(--border-dim);
    padding: 0 40px;
    display: flex; align-items: center; height: 64px;
    transition: background 0.3s var(--ease);
  }
  nav.scrolled { background: rgba(6,8,13,0.92); }
  .nav-brand { display: flex; align-items: center; gap: 12px; }
  .nav-logo {
    width: 38px; height: 38px; border-radius: 10px;
    background: linear-gradient(135deg, var(--accent), var(--cyan));
    display: flex; align-items: center; justify-content: center;
    font-family: 'Outfit', sans-serif; font-weight: 900;
    font-size: 1.1rem; color: #fff;
    box-shadow: 0 2px 16px var(--accent-glow);
    animation: navLogoGlow 4s ease-in-out infinite alternate;
  }
  @keyframes navLogoGlow {
    0%{box-shadow:0 2px 16px var(--accent-glow)} 100%{box-shadow:0 2px 24px var(--cyan-glow),0 0 50px rgba(99,102,241,0.12)}
  }
  .nav-title {
    font-family: 'Outfit', sans-serif; font-size: 1rem; font-weight: 700;
    letter-spacing: -0.3px;
  }
  .nav-spacer { flex: 1; }
  .nav-links { display: flex; gap: 32px; align-items: center; }
  .nav-links a {
    color: var(--text-muted); text-decoration: none;
    font-size: 0.82rem; font-weight: 500; letter-spacing: 0.3px;
    transition: color 0.2s var(--ease); position: relative;
  }
  .nav-links a:hover { color: var(--text-primary); }
  .nav-links a.active { color: var(--cyan); }
  .nav-links a.active::after {
    content: ''; position: absolute; bottom: -6px; left: 0; right: 0;
    height: 2px; background: var(--cyan); border-radius: 1px;
  }
  .nav-cta {
    background: linear-gradient(135deg, var(--accent), #818cf8) !important;
    color: #fff !important; padding: 8px 20px !important;
    border-radius: 99px !important; font-weight: 600 !important;
    border: none; cursor: pointer; font-size: 0.82rem;
    box-shadow: 0 2px 12px var(--accent-glow);
    transition: all 0.3s var(--ease); text-decoration: none;
    display: inline-flex; align-items: center; gap: 6px;
  }
  .nav-cta:hover { transform: translateY(-1px); box-shadow: 0 4px 20px var(--accent-glow); }

  /* ═══════════════════════════════════════════════════════════
     HERO SECTION
     ═══════════════════════════════════════════════════════════ */
  .hero {
    min-height: 100vh; display: flex; align-items: center; justify-content: center;
    position: relative; z-index: 2;
    padding: 64px 40px 80px;
  }
  .hero-content {
    text-align: center; max-width: 900px;
    animation: heroIn 1.2s var(--ease-out) both;
  }
  @keyframes heroIn {
    from { opacity: 0; transform: translateY(40px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .hero-badge {
    display: inline-flex; align-items: center; gap: 8px;
    background: rgba(99,102,241,0.08); border: 1px solid rgba(99,102,241,0.2);
    border-radius: 99px; padding: 6px 18px 6px 12px;
    font-size: 0.72rem; color: var(--violet); font-weight: 600;
    text-transform: uppercase; letter-spacing: 1px;
    margin-bottom: 28px;
    animation: heroIn 1s var(--ease-out) 0.2s both;
  }
  .hero-badge .badge-dot {
    width: 8px; height: 8px; background: var(--green); border-radius: 50%;
    animation: pulseDot 1.5s ease-in-out infinite;
  }
  @keyframes pulseDot { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.4;transform:scale(0.6)} }

  .hero-title {
    font-family: 'Outfit', sans-serif;
    font-size: clamp(3rem, 7vw, 5.5rem);
    font-weight: 900;
    line-height: 1.05;
    letter-spacing: -2px;
    margin-bottom: 24px;
    animation: heroIn 1s var(--ease-out) 0.3s both;
  }
  .hero-title .gradient-text {
    background: linear-gradient(135deg, #fff 0%, var(--cyan) 40%, var(--accent) 70%, var(--violet) 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
    background-size: 200% 200%;
    animation: gradientShift 6s ease-in-out infinite;
  }
  @keyframes gradientShift {
    0%,100% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
  }
  .hero-title .line-2 {
    display: block;
    background: linear-gradient(135deg, var(--cyan) 0%, var(--green) 50%, var(--amber) 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
    background-size: 200% 200%;
    animation: gradientShift 6s ease-in-out 1s infinite;
  }

  .hero-subtitle {
    font-size: 1.15rem; color: var(--text-secondary);
    max-width: 640px; margin: 0 auto 40px;
    line-height: 1.7; font-weight: 400;
    animation: heroIn 1s var(--ease-out) 0.5s both;
  }
  .hero-subtitle strong { color: var(--text-primary); font-weight: 600; }

  .hero-actions {
    display: flex; justify-content: center; gap: 16px;
    animation: heroIn 1s var(--ease-out) 0.7s both;
  }
  .btn-primary {
    background: linear-gradient(135deg, var(--accent), var(--cyan));
    color: #fff; padding: 16px 36px; border-radius: 99px;
    font-size: 1rem; font-weight: 700; border: none;
    cursor: pointer; text-decoration: none;
    display: inline-flex; align-items: center; gap: 10px;
    font-family: 'Inter', sans-serif;
    box-shadow: 0 4px 24px var(--accent-glow), 0 0 60px rgba(34,211,238,0.1);
    transition: all 0.3s var(--ease);
    position: relative; overflow: hidden;
  }
  .btn-primary::before {
    content: ''; position: absolute; inset: -2px;
    background: linear-gradient(135deg, var(--accent), var(--cyan), var(--violet), var(--accent));
    background-size: 300% 300%;
    border-radius: 99px; z-index: -1;
    animation: borderRotate 4s linear infinite;
    opacity: 0; transition: opacity 0.3s;
  }
  .btn-primary:hover::before { opacity: 1; }
  @keyframes borderRotate { 0%{background-position:0% 50%} 100%{background-position:300% 50%} }
  .btn-primary:hover {
    transform: translateY(-2px) scale(1.02);
    box-shadow: 0 8px 40px var(--accent-glow), 0 0 80px rgba(34,211,238,0.15);
  }
  .btn-primary .arrow {
    transition: transform 0.3s var(--ease);
  }
  .btn-primary:hover .arrow { transform: translateX(4px); }

  .btn-secondary {
    background: rgba(255,255,255,0.04); color: var(--text-secondary);
    padding: 16px 36px; border-radius: 99px;
    font-size: 1rem; font-weight: 600; border: 1px solid var(--border-sub);
    cursor: pointer; text-decoration: none;
    display: inline-flex; align-items: center; gap: 10px;
    font-family: 'Inter', sans-serif;
    transition: all 0.3s var(--ease);
  }
  .btn-secondary:hover {
    background: rgba(255,255,255,0.08); color: var(--text-primary);
    border-color: var(--border-vis); transform: translateY(-1px);
  }

  /* ═══════════════════════════════════════════════════════════
     ROBOT VISUALIZER
     ═══════════════════════════════════════════════════════════ */
  .robot-vis {
    position: absolute; top: 50%; left: 50%; z-index: 1;
    transform: translate(-50%, -50%);
    width: 500px; height: 500px; pointer-events: none;
    opacity: 0.12;
  }
  .orbit-ring {
    position: absolute; border: 1px solid var(--cyan);
    border-radius: 50%; opacity: 0.4;
  }
  .orbit-ring:nth-child(1) {
    inset: 60px; animation: orbitSpin 20s linear infinite;
    border-style: dashed;
  }
  .orbit-ring:nth-child(2) {
    inset: 100px; animation: orbitSpin 30s linear infinite reverse;
    border-color: var(--accent);
  }
  .orbit-ring:nth-child(3) {
    inset: 150px; animation: orbitSpin 25s linear infinite;
    border-color: var(--violet); border-style: dotted;
  }
  @keyframes orbitSpin { 0%{transform:rotate(0deg)} 100%{transform:rotate(360deg)} }

  .orbit-dot {
    position: absolute; width: 6px; height: 6px; border-radius: 50%;
    background: var(--cyan); box-shadow: 0 0 12px var(--cyan-glow);
  }

  /* ═══════════════════════════════════════════════════════════
     STATS BAR
     ═══════════════════════════════════════════════════════════ */
  .stats-bar {
    position: relative; z-index: 2;
    background: rgba(11,15,24,0.6); border-top: 1px solid var(--border-dim);
    border-bottom: 1px solid var(--border-dim);
    backdrop-filter: blur(12px);
  }
  .stats-inner {
    max-width: 1200px; margin: 0 auto;
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 0;
  }
  .stat-item {
    padding: 32px 40px; text-align: center;
    border-right: 1px solid var(--border-dim);
    transition: background 0.3s;
  }
  .stat-item:last-child { border-right: none; }
  .stat-item:hover { background: rgba(255,255,255,0.02); }
  .stat-num {
    font-family: 'Outfit', sans-serif; font-size: 2.2rem;
    font-weight: 800; letter-spacing: -1px;
    margin-bottom: 6px;
  }
  .stat-num.c1 { color: var(--cyan); }
  .stat-num.c2 { color: var(--green); }
  .stat-num.c3 { color: var(--violet); }
  .stat-num.c4 { color: var(--amber); }
  .stat-label {
    font-size: 0.7rem; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 1.5px; font-weight: 600;
  }

  /* ═══════════════════════════════════════════════════════════
     FEATURES SECTION
     ═══════════════════════════════════════════════════════════ */
  .features {
    position: relative; z-index: 2;
    padding: 120px 40px;
    max-width: 1200px; margin: 0 auto;
  }
  .section-header {
    text-align: center; margin-bottom: 72px;
  }
  .section-tag {
    font-size: 0.7rem; color: var(--cyan); font-weight: 700;
    text-transform: uppercase; letter-spacing: 2px;
    margin-bottom: 16px;
  }
  .section-title {
    font-family: 'Outfit', sans-serif;
    font-size: clamp(2rem, 4vw, 3rem); font-weight: 800;
    letter-spacing: -1px; margin-bottom: 16px;
  }
  .section-subtitle {
    font-size: 1rem; color: var(--text-secondary);
    max-width: 600px; margin: 0 auto; line-height: 1.7;
  }

  .features-grid {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 24px;
  }
  .feature-card {
    background: rgba(17,24,39,0.5);
    border: 1px solid var(--border-dim);
    border-radius: var(--r-xl);
    padding: 40px 32px;
    position: relative; overflow: hidden;
    transition: all 0.4s var(--ease);
    cursor: default;
  }
  .feature-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    opacity: 0; transition: opacity 0.4s;
  }
  .feature-card:hover {
    background: rgba(17,24,39,0.8);
    border-color: var(--border-sub);
    transform: translateY(-4px);
    box-shadow: 0 16px 48px rgba(0,0,0,0.3);
  }
  .feature-card:hover::before { opacity: 1; }

  .feature-card:nth-child(1)::before { background: linear-gradient(90deg, var(--cyan), transparent); }
  .feature-card:nth-child(2)::before { background: linear-gradient(90deg, var(--accent), transparent); }
  .feature-card:nth-child(3)::before { background: linear-gradient(90deg, var(--green), transparent); }
  .feature-card:nth-child(4)::before { background: linear-gradient(90deg, var(--violet), transparent); }
  .feature-card:nth-child(5)::before { background: linear-gradient(90deg, var(--amber), transparent); }
  .feature-card:nth-child(6)::before { background: linear-gradient(90deg, var(--rose), transparent); }

  .feature-icon {
    width: 52px; height: 52px; border-radius: var(--r-md);
    display: flex; align-items: center; justify-content: center;
    font-size: 1.4rem; margin-bottom: 20px;
    transition: transform 0.3s var(--ease);
  }
  .feature-card:hover .feature-icon { transform: scale(1.1); }
  .fi-1 { background: rgba(34,211,238,0.1); color: var(--cyan); }
  .fi-2 { background: rgba(99,102,241,0.1); color: var(--accent); }
  .fi-3 { background: rgba(52,211,153,0.1); color: var(--green); }
  .fi-4 { background: rgba(167,139,250,0.1); color: var(--violet); }
  .fi-5 { background: rgba(251,191,36,0.1); color: var(--amber); }
  .fi-6 { background: rgba(251,113,133,0.1); color: var(--rose); }

  .feature-title {
    font-family: 'Outfit', sans-serif; font-size: 1.15rem;
    font-weight: 700; margin-bottom: 10px; letter-spacing: -0.3px;
  }
  .feature-desc {
    font-size: 0.88rem; color: var(--text-secondary); line-height: 1.6;
  }

  /* ═══════════════════════════════════════════════════════════
     PIPELINE SECTION
     ═══════════════════════════════════════════════════════════ */
  .pipeline {
    position: relative; z-index: 2;
    padding: 100px 40px;
    background: rgba(6,8,13,0.5);
    border-top: 1px solid var(--border-dim);
    border-bottom: 1px solid var(--border-dim);
  }
  .pipeline-inner { max-width: 1000px; margin: 0 auto; }

  .pipeline-flow {
    display: flex; align-items: center; justify-content: center;
    gap: 0; margin-top: 60px; flex-wrap: wrap;
  }
  .pipe-node {
    background: var(--bg-surf-1); border: 1px solid var(--border-sub);
    border-radius: var(--r-lg); padding: 28px 24px;
    text-align: center; width: 180px;
    transition: all 0.3s var(--ease);
    position: relative;
  }
  .pipe-node:hover {
    border-color: var(--border-vis);
    transform: translateY(-3px);
    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
  }
  .pipe-icon {
    width: 44px; height: 44px; border-radius: 50%;
    margin: 0 auto 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.2rem;
  }
  .pipe-node:nth-child(1) .pipe-icon { background: rgba(34,211,238,0.12); color: var(--cyan); }
  .pipe-node:nth-child(3) .pipe-icon { background: rgba(99,102,241,0.12); color: var(--accent); }
  .pipe-node:nth-child(5) .pipe-icon { background: rgba(167,139,250,0.12); color: var(--violet); }
  .pipe-node:nth-child(7) .pipe-icon { background: rgba(52,211,153,0.12); color: var(--green); }

  .pipe-label {
    font-family: 'Outfit', sans-serif; font-size: 0.88rem;
    font-weight: 700; margin-bottom: 4px;
  }
  .pipe-desc {
    font-size: 0.7rem; color: var(--text-muted); line-height: 1.4;
  }
  .pipe-arrow {
    font-size: 1.4rem; color: var(--text-dim);
    padding: 0 8px;
    animation: arrowPulse 2s ease-in-out infinite;
  }
  .pipe-arrow:nth-child(2) { animation-delay: 0.3s; }
  .pipe-arrow:nth-child(4) { animation-delay: 0.6s; }
  .pipe-arrow:nth-child(6) { animation-delay: 0.9s; }
  @keyframes arrowPulse {
    0%,100% { opacity: 0.3; transform: translateX(0); }
    50% { opacity: 1; transform: translateX(4px); }
  }

  /* ═══════════════════════════════════════════════════════════
     CTA SECTION
     ═══════════════════════════════════════════════════════════ */
  .cta {
    position: relative; z-index: 2;
    padding: 120px 40px;
    text-align: center;
  }
  .cta-glow {
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: 600px; height: 400px;
    background: radial-gradient(ellipse, rgba(99,102,241,0.08) 0%, transparent 70%);
    pointer-events: none;
  }
  .cta-title {
    font-family: 'Outfit', sans-serif;
    font-size: clamp(2rem, 4vw, 3rem); font-weight: 800;
    letter-spacing: -1px; margin-bottom: 16px;
    position: relative;
  }
  .cta-subtitle {
    font-size: 1rem; color: var(--text-secondary);
    max-width: 500px; margin: 0 auto 40px; line-height: 1.7;
  }

  /* ═══════════════════════════════════════════════════════════
     FOOTER
     ═══════════════════════════════════════════════════════════ */
  footer {
    position: relative; z-index: 2;
    border-top: 1px solid var(--border-dim);
    padding: 40px;
    text-align: center;
    font-size: 0.78rem; color: var(--text-dim);
  }
  footer a { color: var(--text-muted); text-decoration: none; }

  /* ═══════════════════════════════════════════════════════════
     SCROLL ANIMATIONS
     ═══════════════════════════════════════════════════════════ */
  .reveal {
    opacity: 0; transform: translateY(30px);
    transition: opacity 0.8s var(--ease-out), transform 0.8s var(--ease-out);
  }
  .reveal.visible {
    opacity: 1; transform: translateY(0);
  }
  .reveal-delay-1 { transition-delay: 0.1s; }
  .reveal-delay-2 { transition-delay: 0.2s; }
  .reveal-delay-3 { transition-delay: 0.3s; }
  .reveal-delay-4 { transition-delay: 0.4s; }
  .reveal-delay-5 { transition-delay: 0.5s; }

  /* ═══════════════════════════════════════════════════════════
     RESPONSIVE
     ═══════════════════════════════════════════════════════════ */
  @media (max-width: 900px) {
    .features-grid { grid-template-columns: 1fr 1fr; }
    .stats-inner { grid-template-columns: repeat(2, 1fr); }
    .pipeline-flow { flex-direction: column; gap: 12px; }
    .pipe-arrow { transform: rotate(90deg); }
    nav { padding: 0 20px; }
    .hero { padding: 64px 20px 60px; }
    .features, .pipeline, .cta { padding-left: 20px; padding-right: 20px; }
  }
  @media (max-width: 600px) {
    .features-grid { grid-template-columns: 1fr; }
    .stats-inner { grid-template-columns: 1fr 1fr; }
    .hero-actions { flex-direction: column; align-items: center; }
    .nav-links a:not(.nav-cta) { display: none; }
  }
</style>
</head>
<body>

<!-- canvas particles -->
<canvas id="particles"></canvas>
<div class="grid-overlay"></div>
<div class="scan-line"></div>

<!-- NAVBAR -->
<nav id="navbar">
  <div class="nav-brand">
    <div class="nav-logo">V</div>
    <span class="nav-title">VLN Robot</span>
  </div>
  <div class="nav-spacer"></div>
  <div class="nav-links">
    <a href="#" class="active">Home</a>
    <a href="#features">Capabilities</a>
    <a href="#pipeline">Pipeline</a>
    <a href="/dashboard" class="nav-cta">&#9654; Operations Dashboard</a>
  </div>
</nav>

<!-- HERO -->
<section class="hero">
  <div class="robot-vis" aria-hidden="true">
    <div class="orbit-ring"></div>
    <div class="orbit-ring"></div>
    <div class="orbit-ring"></div>
  </div>
  <div class="hero-content">
    <div class="hero-badge">
      <span class="badge-dot"></span>
      System Online &mdash; Ready for Deployment
    </div>
    <h1 class="hero-title">
      <span class="gradient-text">Vision Language</span>
      <span class="line-2">Navigation Robot</span>
    </h1>
    <p class="hero-subtitle">
      An autonomous <strong>indoor navigation system</strong> powered by
      multimodal AI. Understands natural language instructions, perceives the
      environment in real-time, and navigates to your destination &mdash;
      completely autonomously.
    </p>
    <div class="hero-actions">
      <a href="/dashboard" class="btn-primary">
        Launch Operations <span class="arrow">&rarr;</span>
      </a>
      <a href="#features" class="btn-secondary">
        Explore Capabilities
      </a>
    </div>
  </div>
</section>

<!-- STATS BAR -->
<div class="stats-bar reveal">
  <div class="stats-inner">
    <div class="stat-item">
      <div class="stat-num c1" data-target="30">0</div>
      <div class="stat-label">FPS Real-time</div>
    </div>
    <div class="stat-item">
      <div class="stat-num c2" data-target="98">0</div>
      <div class="stat-label">Navigation Accuracy %</div>
    </div>
    <div class="stat-item">
      <div class="stat-num c3" data-target="4">0</div>
      <div class="stat-label">Billion Parameters</div>
    </div>
    <div class="stat-item">
      <div class="stat-num c4" data-target="1.2" data-decimals="1">0</div>
      <div class="stat-label">Avg Latency (sec)</div>
    </div>
  </div>
</div>

<!-- FEATURES -->
<section class="features" id="features">
  <div class="section-header reveal">
    <div class="section-tag">Core Capabilities</div>
    <h2 class="section-title">Powered by Multimodal Intelligence</h2>
    <p class="section-subtitle">Combining state-of-the-art vision, language understanding, and robotic control into one seamless system.</p>
  </div>
  <div class="features-grid">
    <div class="feature-card reveal reveal-delay-1">
      <div class="feature-icon fi-1">&#128065;</div>
      <div class="feature-title">Visual Perception</div>
      <div class="feature-desc">Real-time camera feed processed through advanced vision transformers for scene understanding and obstacle detection.</div>
    </div>
    <div class="feature-card reveal reveal-delay-2">
      <div class="feature-icon fi-2">&#128488;</div>
      <div class="feature-title">Language Grounding</div>
      <div class="feature-desc">Natural language instructions are grounded to the visual scene using a large vision-language model for contextual understanding.</div>
    </div>
    <div class="feature-card reveal reveal-delay-3">
      <div class="feature-icon fi-3">&#129517;</div>
      <div class="feature-title">Autonomous Navigation</div>
      <div class="feature-desc">Step-by-step action planning with forward, turn, and stop commands executed on the Go1 quadruped robot in real-time.</div>
    </div>
    <div class="feature-card reveal reveal-delay-1">
      <div class="feature-icon fi-4">&#127908;</div>
      <div class="feature-title">Voice Commands</div>
      <div class="feature-desc">Speak your navigation instructions naturally. The system transcribes, confirms, and executes &mdash; completely hands-free.</div>
    </div>
    <div class="feature-card reveal reveal-delay-2">
      <div class="feature-icon fi-5">&#9889;</div>
      <div class="feature-title">Real-time Inference</div>
      <div class="feature-desc">Sub-second LLM inference on NVIDIA Jetson Orin with optimized model sharding and INT4 quantization for edge deployment.</div>
    </div>
    <div class="feature-card reveal reveal-delay-3">
      <div class="feature-icon fi-6">&#128200;</div>
      <div class="feature-title">Live Monitoring</div>
      <div class="feature-desc">Full operations dashboard with live camera feed, real-time model output logging, and interactive control panel.</div>
    </div>
  </div>
</section>

<!-- PIPELINE -->
<section class="pipeline" id="pipeline">
  <div class="pipeline-inner">
    <div class="section-header reveal">
      <div class="section-tag">System Architecture</div>
      <h2 class="section-title">Inference Pipeline</h2>
      <p class="section-subtitle">From spoken instruction to robotic action in under 2 seconds.</p>
    </div>
    <div class="pipeline-flow reveal">
      <div class="pipe-node">
        <div class="pipe-icon">&#127908;</div>
        <div class="pipe-label">Voice Input</div>
        <div class="pipe-desc">Speech recognition &amp; NLU</div>
      </div>
      <div class="pipe-arrow">&rarr;</div>
      <div class="pipe-node">
        <div class="pipe-icon">&#128065;</div>
        <div class="pipe-label">Vision Encoder</div>
        <div class="pipe-desc">Frame capture &amp; ViT encoding</div>
      </div>
      <div class="pipe-arrow">&rarr;</div>
      <div class="pipe-node">
        <div class="pipe-icon">&#129504;</div>
        <div class="pipe-label">VLM Reasoning</div>
        <div class="pipe-desc">InternVL2-4B action planning</div>
      </div>
      <div class="pipe-arrow">&rarr;</div>
      <div class="pipe-node">
        <div class="pipe-icon">&#129302;</div>
        <div class="pipe-label">Robot Control</div>
        <div class="pipe-desc">Go1 motor commands via SDK</div>
      </div>
    </div>
  </div>
</section>

<!-- CTA -->
<section class="cta">
  <div class="cta-glow"></div>
  <div class="reveal">
    <h2 class="cta-title">Ready to Navigate?</h2>
    <p class="cta-subtitle">Access the live operations dashboard to send instructions, monitor the camera feed, and control the robot in real-time.</p>
    <a href="/dashboard" class="btn-primary" style="font-size:1.05rem;padding:18px 44px;">
      Enter Operations Dashboard <span class="arrow">&rarr;</span>
    </a>
  </div>
</section>

<!-- FOOTER -->
<footer>
  <p>VLN Robot System &middot; Vision Language Navigation &middot; Built with InternVL2 &amp; Unitree Go1</p>
</footer>

<script>
// ═══════════════════════════════════════════════════════════
// PARTICLE SYSTEM
// ═══════════════════════════════════════════════════════════
const canvas = document.getElementById('particles');
const ctx = canvas.getContext('2d');
let particles = [];
let mouse = { x: -1000, y: -1000 };

function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}
resizeCanvas();
window.addEventListener('resize', resizeCanvas);
document.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });

class Particle {
  constructor() {
    this.reset();
  }
  reset() {
    this.x = Math.random() * canvas.width;
    this.y = Math.random() * canvas.height;
    this.size = Math.random() * 1.5 + 0.3;
    this.speedX = (Math.random() - 0.5) * 0.3;
    this.speedY = (Math.random() - 0.5) * 0.3;
    this.opacity = Math.random() * 0.5 + 0.1;
    this.hue = Math.random() > 0.5 ? 220 : 190; // blue or cyan
  }
  update() {
    this.x += this.speedX;
    this.y += this.speedY;
    // mouse repulsion
    const dx = this.x - mouse.x;
    const dy = this.y - mouse.y;
    const dist = Math.sqrt(dx*dx + dy*dy);
    if (dist < 120) {
      this.x += dx / dist * 1.5;
      this.y += dy / dist * 1.5;
    }
    if (this.x < 0 || this.x > canvas.width ||
        this.y < 0 || this.y > canvas.height) this.reset();
  }
  draw() {
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
    ctx.fillStyle = `hsla(${this.hue}, 80%, 70%, ${this.opacity})`;
    ctx.fill();
  }
}

const particleCount = Math.min(120, Math.floor(window.innerWidth * 0.08));
for (let i = 0; i < particleCount; i++) particles.push(new Particle());

function drawConnections() {
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const dx = particles[i].x - particles[j].x;
      const dy = particles[i].y - particles[j].y;
      const dist = Math.sqrt(dx*dx + dy*dy);
      if (dist < 140) {
        ctx.beginPath();
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(particles[j].x, particles[j].y);
        ctx.strokeStyle = `rgba(99,102,241,${0.06 * (1 - dist/140)})`;
        ctx.lineWidth = 0.5;
        ctx.stroke();
      }
    }
  }
}

function animateParticles() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  particles.forEach(p => { p.update(); p.draw(); });
  drawConnections();
  requestAnimationFrame(animateParticles);
}
animateParticles();

// ═══════════════════════════════════════════════════════════
// SCROLL ANIMATIONS
// ═══════════════════════════════════════════════════════════
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) entry.target.classList.add('visible');
  });
}, { threshold: 0.15 });

document.querySelectorAll('.reveal').forEach(el => observer.observe(el));

// Navbar scroll
window.addEventListener('scroll', () => {
  document.getElementById('navbar').classList.toggle('scrolled', window.scrollY > 50);
});

// ═══════════════════════════════════════════════════════════
// COUNTER ANIMATION
// ═══════════════════════════════════════════════════════════
const counterObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const el = entry.target;
      const target = parseFloat(el.dataset.target);
      const decimals = parseInt(el.dataset.decimals || '0');
      const duration = 2000;
      const start = performance.now();
      function tick(now) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 4); // ease-out quart
        const current = eased * target;
        el.textContent = current.toFixed(decimals);
        if (progress < 1) requestAnimationFrame(tick);
        else el.textContent = target.toFixed(decimals);
      }
      requestAnimationFrame(tick);
      counterObserver.unobserve(el);
    }
  });
}, { threshold: 0.5 });

document.querySelectorAll('.stat-num[data-target]').forEach(el => counterObserver.observe(el));

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', e => {
    e.preventDefault();
    const target = document.querySelector(a.getAttribute('href'));
    if (target) target.scrollIntoView({ behavior: 'smooth' });
  });
});
</script>
</body>
</html>
"""

# ── routes ────────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    return render_template_string(HOME_HTML)

@app.route('/dashboard')
def dashboard():
    return render_template_string(HTML)

@app.route('/video_feed')
def video_feed():
    return Response(_mjpeg_gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/events')
def events():
    return Response(_sse_gen(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.route('/set_instruction', methods=['POST'])
def set_instruction():
    data = request.get_json()
    instr = (data or {}).get('instruction', '').strip()
    if instr:
        with open(_instr_file, 'w') as f:
            f.write(instr)
        # setting a new instruction always resumes inference
        try: os.remove('/tmp/vln_paused.flag')
        except FileNotFoundError: pass
    return jsonify(instruction=instr)

@app.route('/get_instruction')
def get_instruction():
    instr = ''
    if os.path.exists(_instr_file):
        instr = open(_instr_file).read().strip()
    return jsonify(instruction=instr)

@app.route('/pause', methods=['POST'])
def pause():
    data = request.get_json() or {}
    want_paused = bool(data.get('paused', True))
    flag = '/tmp/vln_paused.flag'
    if want_paused:
        open(flag, 'w').close()
    else:
        try: os.remove(flag)
        except FileNotFoundError: pass
    return jsonify(paused=want_paused)

@app.route('/restart', methods=['POST'])
def restart():
    data = request.get_json()
    instr = (data or {}).get('instruction', '').strip()
    with open('/tmp/vln_restart.flag', 'w') as f:
        f.write(instr)
    if instr:
        with open(_instr_file, 'w') as f:
            f.write(instr)
    return jsonify(instruction=instr)

# ── main ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--log', default='/tmp/infer_live.log')
    args = parser.parse_args()
    _log_path = args.log

    threading.Thread(target=_capture_loop, daemon=True).start()

    print(f"[UI] Open  http://<orin-ip>:{args.port}  in your browser")
    app.run(host='0.0.0.0', port=args.port, threaded=True)
