#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Health server + Gaming LED Control Panel cho Render.
Giao diện Gaming LED RGB 7.0 + bảng tài khoản realtime.
"""
import os
import sys
import json
import time
import threading
import subprocess
from datetime import datetime
from collections import deque

try:
    from flask import Flask, jsonify, render_template_string, Response, request
except ImportError:
    print("Installing flask...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
    from flask import Flask, jsonify, render_template_string, Response, request

app = Flask(__name__)

# ==================== STATE ====================
START_TIME = time.time()
WORKER_PROCESS = None
WORKER_THREAD = None
LOG_BUFFER = deque(maxlen=500)
LOG_LOCK = threading.Lock()
LOG_SUBSCRIBERS = []
SUB_LOCK = threading.Lock()
STATS = {
    "success": 0, "fail": 0, "rare": 0, "couple": 0,
    "last_uid": "", "last_name": "", "last_account_id": "",
}
STATS_LOCK = threading.Lock()

# Đường dẫn file accounts
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(CURRENT_DIR, "DATA_ACCOUNTS", "ACCOUNTS", "accounts-VN.json")
ACCOUNTS_LOCK = threading.Lock()


# ==================== HELPERS ====================
def log_line(line: str):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = {"time": ts, "msg": line}
    with LOG_LOCK:
        LOG_BUFFER.append(entry)
    with SUB_LOCK:
        dead = []
        for q in LOG_SUBSCRIBERS:
            try:
                q.append(entry)
            except Exception:
                dead.append(q)
        for q in dead:
            LOG_SUBSCRIBERS.remove(q)


def update_stats_from_log(line: str):
    with STATS_LOCK:
        if "✅" in line and "UID=" in line:
            STATS["success"] += 1
            try:
                if "UID=" in line:
                    STATS["last_uid"] = line.split("UID=")[1].split("|")[0].strip()
                if "ID=" in line:
                    STATS["last_account_id"] = line.split("ID=")[1].split("|")[0].strip()
                if "|" in line:
                    STATS["last_name"] = line.split("|")[-1].strip()[:40]
            except Exception:
                pass
        if "❌" in line:
            STATS["fail"] += 1
        if "💎" in line:
            STATS["rare"] += 1
        if "💑" in line:
            STATS["couple"] += 1


def load_accounts() -> list:
    """Load danh sách tài khoản từ file JSON."""
    with ACCOUNTS_LOCK:
        if not os.path.exists(ACCOUNTS_FILE):
            return []
        try:
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []


def run_worker():
    global WORKER_PROCESS
    script = os.path.join(CURRENT_DIR, "RegFF_OB55.py")
    log_line(f"🚀 Khởi động worker: {script}")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    try:
        WORKER_PROCESS = subprocess.Popen(
            [sys.executable, "-u", script],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, bufsize=1, universal_newlines=True,
        )
        for line in WORKER_PROCESS.stdout:
            line = line.rstrip()
            if line:
                log_line(line)
                update_stats_from_log(line)
        WORKER_PROCESS.wait()
        log_line(f"⚠️ Worker kết thúc (exit code {WORKER_PROCESS.returncode})")
    except Exception as e:
        log_line(f"❌ Lỗi worker: {e}")


def start_worker():
    global WORKER_THREAD
    if WORKER_THREAD is None or not WORKER_THREAD.is_alive():
        WORKER_THREAD = threading.Thread(target=run_worker, daemon=True)
        WORKER_THREAD.start()
        log_line("✅ Đã khởi động worker")
    else:
        log_line("ℹ️ Worker đang chạy rồi")


# ==================== HTML — GAMING LED 7.0 ====================
HTML = r"""
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>⚡ RegFF OB55 — GAMING LED 7.0</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&family=Rajdhani:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --neon-cyan: #00f0ff;
    --neon-magenta: #ff00e5;
    --neon-purple: #8b00ff;
    --neon-green: #00ff88;
    --neon-pink: #ff2e63;
    --neon-yellow: #ffea00;
    --neon-orange: #ff6b00;
    --bg-dark: #05060f;
    --bg-panel: #0a0e1a;
    --bg-card: #10162a;
    --border-neon: rgba(0, 240, 255, 0.3);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: 'Rajdhani', -apple-system, sans-serif;
    background: var(--bg-dark);
    color: #e0e8ff;
    min-height: 100vh;
    overflow-x: hidden;
    position: relative;
  }

  /* ===== LED BACKGROUND GRID ===== */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(0,240,255,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,0,229,0.03) 1px, transparent 1px);
    background-size: 50px 50px;
    pointer-events: none;
    z-index: 0;
    animation: gridMove 20s linear infinite;
  }
  @keyframes gridMove {
    0% { background-position: 0 0, 0 0; }
    100% { background-position: 50px 50px, 50px 50px; }
  }

  /* ===== LED GLOW ORBS ===== */
  body::after {
    content: '';
    position: fixed;
    inset: 0;
    background:
      radial-gradient(circle at 20% 30%, rgba(0,240,255,0.15) 0%, transparent 40%),
      radial-gradient(circle at 80% 70%, rgba(255,0,229,0.15) 0%, transparent 40%),
      radial-gradient(circle at 50% 50%, rgba(139,0,255,0.08) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
    animation: orbsPulse 6s ease-in-out infinite;
  }
  @keyframes orbsPulse {
    0%, 100% { opacity: 0.8; }
    50% { opacity: 1; }
  }

  .container {
    position: relative;
    z-index: 1;
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px;
  }

  /* ===== HEADER ===== */
  .header {
    background: linear-gradient(135deg, rgba(10,14,26,0.95), rgba(16,22,42,0.95));
    border: 2px solid transparent;
    background-clip: padding-box;
    border-radius: 20px;
    padding: 24px 32px;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 20px;
  }
  .header::before {
    content: '';
    position: absolute;
    inset: -2px;
    border-radius: 20px;
    padding: 2px;
    background: linear-gradient(90deg, var(--neon-cyan), var(--neon-magenta), var(--neon-purple), var(--neon-cyan));
    background-size: 300% 100%;
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    animation: borderFlow 3s linear infinite;
    z-index: -1;
  }
  @keyframes borderFlow {
    0% { background-position: 0% 50%; }
    100% { background-position: 300% 50%; }
  }
  .header-left h1 {
    font-family: 'Orbitron', sans-serif;
    font-size: 2rem;
    font-weight: 900;
    letter-spacing: 2px;
    background: linear-gradient(90deg, var(--neon-cyan), var(--neon-magenta));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    text-shadow: 0 0 30px rgba(0, 240, 255, 0.5);
    animation: titleGlow 3s ease-in-out infinite;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  @keyframes titleGlow {
    0%, 100% { filter: drop-shadow(0 0 10px rgba(0,240,255,0.5)); }
    50% { filter: drop-shadow(0 0 25px rgba(255,0,229,0.7)); }
  }
  .header-left p {
    color: #8b95a8;
    font-size: 0.9rem;
    margin-top: 6px;
    font-weight: 500;
    letter-spacing: 1px;
    text-transform: uppercase;
  }
  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 10px 22px;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 700;
    background: rgba(0, 255, 136, 0.08);
    color: var(--neon-green);
    border: 1.5px solid rgba(0, 255, 136, 0.4);
    box-shadow: 0 0 20px rgba(0, 255, 136, 0.3), inset 0 0 10px rgba(0, 255, 136, 0.1);
    text-transform: uppercase;
    letter-spacing: 1px;
    font-family: 'Orbitron', sans-serif;
  }
  .status-pill.offline {
    background: rgba(255, 46, 99, 0.08);
    color: var(--neon-pink);
    border-color: rgba(255, 46, 99, 0.4);
    box-shadow: 0 0 20px rgba(255, 46, 99, 0.3), inset 0 0 10px rgba(255, 46, 99, 0.1);
  }
  .dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 10px currentColor, 0 0 20px currentColor;
    animation: dotPulse 1.2s ease-in-out infinite;
  }
  @keyframes dotPulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.7); }
  }

  /* ===== STATS GRID ===== */
  .stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
    margin-bottom: 24px;
  }
  .stat-card {
    background: linear-gradient(135deg, var(--bg-card) 0%, var(--bg-panel) 100%);
    border: 1.5px solid rgba(0, 240, 255, 0.15);
    border-radius: 16px;
    padding: 18px;
    transition: all 0.3s;
    position: relative;
    overflow: hidden;
  }
  .stat-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--neon-cyan), transparent);
    opacity: 0;
    transition: opacity 0.3s;
  }
  .stat-card:hover {
    transform: translateY(-4px);
    border-color: var(--neon-cyan);
    box-shadow: 0 0 30px rgba(0, 240, 255, 0.3), inset 0 0 20px rgba(0, 240, 255, 0.05);
  }
  .stat-card:hover::before { opacity: 1; }
  .stat-card.magenta:hover {
    border-color: var(--neon-magenta);
    box-shadow: 0 0 30px rgba(255, 0, 229, 0.3), inset 0 0 20px rgba(255, 0, 229, 0.05);
  }
  .stat-card.green:hover {
    border-color: var(--neon-green);
    box-shadow: 0 0 30px rgba(0, 255, 136, 0.3), inset 0 0 20px rgba(0, 255, 136, 0.05);
  }
  .stat-card.yellow:hover {
    border-color: var(--neon-yellow);
    box-shadow: 0 0 30px rgba(255, 234, 0, 0.3);
  }
  .stat-card.pink:hover {
    border-color: var(--neon-pink);
    box-shadow: 0 0 30px rgba(255, 46, 99, 0.3);
  }
  .stat-label {
    font-size: 0.7rem;
    font-weight: 700;
    color: #8b95a8;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 10px;
    font-family: 'Orbitron', sans-serif;
  }
  .stat-value {
    font-size: 1.9rem;
    font-weight: 900;
    color: var(--neon-cyan);
    letter-spacing: 1px;
    font-family: 'Orbitron', sans-serif;
    text-shadow: 0 0 15px currentColor;
  }
  .stat-value.green { color: var(--neon-green); text-shadow: 0 0 15px var(--neon-green); }
  .stat-value.red { color: var(--neon-pink); text-shadow: 0 0 15px var(--neon-pink); }
  .stat-value.gold { color: var(--neon-yellow); text-shadow: 0 0 15px var(--neon-yellow); }
  .stat-value.pink { color: var(--neon-magenta); text-shadow: 0 0 15px var(--neon-magenta); }
  .stat-sub {
    font-size: 0.72rem;
    color: #8b95a8;
    margin-top: 6px;
    font-family: 'JetBrains Mono', monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* ===== CONTROLS ===== */
  .controls {
    display: flex;
    gap: 12px;
    margin-bottom: 24px;
    flex-wrap: wrap;
  }
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 12px 22px;
    border: 1.5px solid rgba(0, 240, 255, 0.3);
    border-radius: 12px;
    font-family: 'Orbitron', sans-serif;
    font-size: 0.78rem;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.3s;
    text-decoration: none;
    color: var(--neon-cyan);
    background: rgba(0, 240, 255, 0.05);
    user-select: none;
    text-transform: uppercase;
    letter-spacing: 1px;
    position: relative;
    overflow: hidden;
  }
  .btn::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, transparent, rgba(0, 240, 255, 0.2), transparent);
    transform: translateX(-100%);
    transition: transform 0.5s;
  }
  .btn:hover::before { transform: translateX(100%); }
  .btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 0 25px rgba(0, 240, 255, 0.5), inset 0 0 15px rgba(0, 240, 255, 0.1);
    border-color: var(--neon-cyan);
  }
  .btn:active { transform: translateY(0); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
  .btn-primary {
    background: linear-gradient(135deg, var(--neon-cyan), var(--neon-purple));
    color: #fff;
    border: none;
    box-shadow: 0 0 20px rgba(0, 240, 255, 0.5);
  }
  .btn-primary:hover {
    box-shadow: 0 0 35px rgba(0, 240, 255, 0.7), 0 0 60px rgba(139, 0, 255, 0.4);
  }
  .btn-success {
    background: linear-gradient(135deg, var(--neon-green), #00a855);
    color: #fff;
    border: none;
    box-shadow: 0 0 20px rgba(0, 255, 136, 0.5);
  }
  .btn-success:hover {
    box-shadow: 0 0 35px rgba(0, 255, 136, 0.7);
  }
  .btn-danger {
    background: linear-gradient(135deg, var(--neon-pink), #a30028);
    color: #fff;
    border: none;
    box-shadow: 0 0 20px rgba(255, 46, 99, 0.5);
  }
  .btn-danger:hover {
    box-shadow: 0 0 35px rgba(255, 46, 99, 0.7);
  }
  .btn-magenta {
    background: linear-gradient(135deg, var(--neon-magenta), var(--neon-purple));
    color: #fff;
    border: none;
    box-shadow: 0 0 20px rgba(255, 0, 229, 0.5);
  }

  /* ===== ACCOUNT TABLE ===== */
  .panel {
    background: linear-gradient(180deg, var(--bg-panel) 0%, #070a14 100%);
    border: 1.5px solid rgba(0, 240, 255, 0.2);
    border-radius: 16px;
    overflow: hidden;
    margin-bottom: 24px;
    box-shadow: 0 0 40px rgba(0, 240, 255, 0.1), inset 0 0 60px rgba(0, 240, 255, 0.02);
    position: relative;
  }
  .panel::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--neon-cyan), var(--neon-magenta), var(--neon-cyan));
    background-size: 200% 100%;
    animation: borderFlow 3s linear infinite;
  }
  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid rgba(0, 240, 255, 0.1);
    background: rgba(0, 240, 255, 0.03);
    flex-wrap: wrap;
    gap: 12px;
  }
  .panel-title {
    font-family: 'Orbitron', sans-serif;
    font-size: 1rem;
    font-weight: 700;
    color: var(--neon-cyan);
    text-transform: uppercase;
    letter-spacing: 2px;
    display: flex;
    align-items: center;
    gap: 10px;
    text-shadow: 0 0 15px rgba(0, 240, 255, 0.6);
  }
  .panel-title .count {
    color: var(--neon-magenta);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
    text-shadow: 0 0 10px var(--neon-magenta);
  }
  .panel-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .panel-actions .btn {
    padding: 8px 14px;
    font-size: 0.7rem;
  }
  .table-wrap {
    max-height: 500px;
    overflow-y: auto;
    overflow-x: auto;
  }
  .table-wrap::-webkit-scrollbar { width: 10px; height: 10px; }
  .table-wrap::-webkit-scrollbar-track { background: rgba(0, 240, 255, 0.05); }
  .table-wrap::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, var(--neon-cyan), var(--neon-magenta));
    border-radius: 5px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    min-width: 700px;
  }
  th, td {
    padding: 12px 14px;
    text-align: left;
    border-bottom: 1px solid rgba(0, 240, 255, 0.08);
    font-size: 0.85rem;
  }
  th {
    background: rgba(0, 240, 255, 0.05);
    color: var(--neon-cyan);
    font-family: 'Orbitron', sans-serif;
    font-weight: 700;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    position: sticky;
    top: 0;
    z-index: 2;
    text-shadow: 0 0 10px rgba(0, 240, 255, 0.6);
  }
  tbody tr {
    transition: all 0.2s;
  }
  tbody tr:hover {
    background: rgba(0, 240, 255, 0.05);
    box-shadow: inset 0 0 20px rgba(0, 240, 255, 0.1);
  }
  .idx {
    color: #8b95a8;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
  }
  .uid-cell {
    color: var(--neon-cyan);
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    text-shadow: 0 0 8px rgba(0, 240, 255, 0.5);
  }
  .pass-cell {
    color: var(--neon-yellow);
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    text-shadow: 0 0 8px rgba(255, 234, 0, 0.4);
  }
  .name-cell {
    color: var(--neon-magenta);
    font-weight: 600;
    text-shadow: 0 0 8px rgba(255, 0, 229, 0.4);
  }
  .id-cell {
    color: var(--neon-green);
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    text-shadow: 0 0 8px rgba(0, 255, 136, 0.4);
  }
  .copy-btn {
    background: transparent;
    border: 1px solid rgba(0, 240, 255, 0.3);
    color: var(--neon-cyan);
    padding: 3px 8px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.7rem;
    margin-left: 6px;
    transition: all 0.2s;
  }
  .copy-btn:hover {
    background: rgba(0, 240, 255, 0.15);
    box-shadow: 0 0 15px rgba(0, 240, 255, 0.4);
    border-color: var(--neon-cyan);
  }
  .copy-btn.copied {
    background: rgba(0, 255, 136, 0.2);
    color: var(--neon-green);
    border-color: var(--neon-green);
  }
  .empty {
    color: #8b95a8;
    text-align: center;
    padding: 60px 20px;
    font-style: italic;
    font-family: 'Rajdhani', sans-serif;
    font-size: 1rem;
  }

  /* ===== PROGRESS ===== */
  .progress-wrap {
    background: linear-gradient(180deg, var(--bg-card) 0%, var(--bg-panel) 100%);
    border: 1.5px solid rgba(0, 240, 255, 0.2);
    border-radius: 16px;
    padding: 18px 22px;
    margin-bottom: 24px;
    box-shadow: 0 0 30px rgba(0, 240, 255, 0.1);
  }
  .progress-info {
    display: flex;
    justify-content: space-between;
    font-family: 'Orbitron', sans-serif;
    font-size: 0.85rem;
    margin-bottom: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--neon-cyan);
  }
  .progress-bar {
    height: 14px;
    background: rgba(0, 240, 255, 0.08);
    border-radius: 7px;
    overflow: hidden;
    position: relative;
    border: 1px solid rgba(0, 240, 255, 0.2);
  }
  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--neon-cyan), var(--neon-magenta), var(--neon-purple), var(--neon-cyan));
    background-size: 300% 100%;
    border-radius: 7px;
    transition: width 0.5s ease;
    animation: progressFlow 3s linear infinite;
    box-shadow: 0 0 20px rgba(0, 240, 255, 0.8), inset 0 0 10px rgba(255,255,255,0.3);
  }
  @keyframes progressFlow {
    0% { background-position: 0% 50%; }
    100% { background-position: 300% 50%; }
  }

  /* ===== LOG PANEL ===== */
  .log-body {
    height: 400px;
    overflow-y: auto;
    padding: 14px 20px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    line-height: 1.7;
    scroll-behavior: smooth;
  }
  .log-body::-webkit-scrollbar { width: 8px; }
  .log-body::-webkit-scrollbar-track { background: transparent; }
  .log-body::-webkit-scrollbar-thumb {
    background: rgba(0, 240, 255, 0.3);
    border-radius: 4px;
  }
  .log-line {
    display: flex;
    gap: 12px;
    padding: 3px 0;
    border-radius: 6px;
    transition: background 0.15s;
    word-break: break-all;
  }
  .log-line:hover { background: rgba(0, 240, 255, 0.05); }
  .log-time {
    color: #5a6580;
    flex-shrink: 0;
    font-size: 0.75rem;
    padding-top: 2px;
  }
  .log-msg { color: #b8c4dc; flex: 1; }
  .log-line.ok .log-msg { color: var(--neon-green); text-shadow: 0 0 8px rgba(0,255,136,0.5); }
  .log-line.err .log-msg { color: var(--neon-pink); text-shadow: 0 0 8px rgba(255,46,99,0.5); }
  .log-line.rare .log-msg { color: var(--neon-yellow); font-weight: 600; text-shadow: 0 0 10px var(--neon-yellow); }
  .log-line.couple .log-msg { color: var(--neon-magenta); font-weight: 600; text-shadow: 0 0 10px var(--neon-magenta); }
  .log-line.info .log-msg { color: var(--neon-cyan); }
  .log-line.warn .log-msg { color: var(--neon-orange); }

  /* ===== FOOTER ===== */
  .footer {
    text-align: center;
    padding: 24px;
    color: #5a6580;
    font-size: 0.8rem;
    font-family: 'Orbitron', sans-serif;
    letter-spacing: 2px;
    text-transform: uppercase;
  }
  .footer a {
    color: var(--neon-cyan);
    text-decoration: none;
    text-shadow: 0 0 10px var(--neon-cyan);
  }

  /* ===== TOAST ===== */
  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: var(--bg-card);
    border: 1.5px solid var(--neon-cyan);
    border-radius: 12px;
    padding: 14px 20px;
    color: var(--neon-cyan);
    font-family: 'Orbitron', sans-serif;
    font-size: 0.82rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    box-shadow: 0 0 30px rgba(0, 240, 255, 0.5);
    transform: translateY(100px);
    opacity: 0;
    transition: all 0.3s;
    z-index: 9999;
  }
  .toast.show { transform: translateY(0); opacity: 1; }
  .toast.error {
    border-color: var(--neon-pink);
    color: var(--neon-pink);
    box-shadow: 0 0 30px rgba(255, 46, 99, 0.5);
  }
  .toast.success {
    border-color: var(--neon-green);
    color: var(--neon-green);
    box-shadow: 0 0 30px rgba(0, 255, 136, 0.5);
  }

  /* ===== RESPONSIVE ===== */
  @media (max-width: 768px) {
    .container { padding: 12px; }
    .header { padding: 18px; }
    .header-left h1 { font-size: 1.3rem; letter-spacing: 1px; }
    .stat-value { font-size: 1.4rem; }
    .log-body { height: 320px; font-size: 0.75rem; }
    .btn { padding: 10px 14px; font-size: 0.7rem; }
    th, td { padding: 8px 10px; font-size: 0.75rem; }
    .hide-mobile { display: none; }
  }

  /* ===== SCANLINE EFFECT ===== */
  .scanlines {
    position: fixed;
    inset: 0;
    background: repeating-linear-gradient(
      0deg,
      rgba(0, 0, 0, 0.15) 0px,
      rgba(0, 0, 0, 0.15) 1px,
      transparent 1px,
      transparent 3px
    );
    pointer-events: none;
    z-index: 9998;
    opacity: 0.4;
  }
</style>
</head>
<body>
<div class="scanlines"></div>

<div class="container">

  <!-- HEADER -->
  <div class="header">
    <div class="header-left">
      <h1>⚡ RegFF OB55</h1>
      <p>Gaming LED Control Panel · v7.0</p>
    </div>
    <div id="status-pill" class="status-pill">
      <span class="dot"></span>
      <span id="status-text">Đang tải...</span>
    </div>
  </div>

  <!-- STATS -->
  <div class="stats">
    <div class="stat-card">
      <div class="stat-label">⏱️ Uptime</div>
      <div class="stat-value" id="uptime">--</div>
    </div>
    <div class="stat-card green">
      <div class="stat-label">✅ Thành công</div>
      <div class="stat-value green" id="stat-success">0</div>
    </div>
    <div class="stat-card pink">
      <div class="stat-label">❌ Thất bại</div>
      <div class="stat-value red" id="stat-fail">0</div>
    </div>
    <div class="stat-card yellow">
      <div class="stat-label">💎 Hiếm</div>
      <div class="stat-value gold" id="stat-rare">0</div>
    </div>
    <div class="stat-card magenta">
      <div class="stat-label">💑 Cặp đôi</div>
      <div class="stat-value pink" id="stat-couple">0</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">📋 Tài khoản</div>
      <div class="stat-value" id="stat-total-accounts">0</div>
    </div>
  </div>

  <!-- CONTROLS -->
  <div class="controls">
    <button class="btn btn-success" id="btn-start" onclick="startWorker()">▶️ Bắt đầu</button>
    <button class="btn btn-danger" id="btn-stop" onclick="stopWorker()">⏹️ Dừng</button>
    <button class="btn btn-magenta" onclick="refreshAccounts()">🔄 Làm mới</button>
    <a class="btn" href="/accounts/download">📥 Tải TXT</a>
    <a class="btn" href="/accounts/export">📤 Export UID|PASS</a>
    <a class="btn" href="/api/status" target="_blank">📊 API</a>
  </div>

  <!-- PROGRESS -->
  <div class="progress-wrap">
    <div class="progress-info">
      <span>📈 Tiến độ</span>
      <span id="progress-text">0 / 0</span>
    </div>
    <div class="progress-bar">
      <div class="progress-fill" id="progress-fill" style="width: 0%"></div>
    </div>
  </div>

  <!-- ACCOUNT TABLE -->
  <div class="panel">
    <div class="panel-header">
      <div class="panel-title">
        <span>🎮 Danh sách tài khoản</span>
        <span class="count" id="accounts-count">(0)</span>
      </div>
      <div class="panel-actions">
        <button class="btn" onclick="refreshAccounts()">🔄 Refresh</button>
        <a class="btn" href="/accounts/export" target="_blank">📤 Export</a>
      </div>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th style="width:50px">#</th>
            <th>UID</th>
            <th>PASSWORD</th>
            <th class="hide-mobile">NAME</th>
            <th class="hide-mobile">ACCOUNT ID</th>
            <th style="width:80px">Copy</th>
          </tr>
        </thead>
        <tbody id="accounts-tbody">
          <tr><td colspan="6" class="empty">📭 Chưa có tài khoản nào</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- LOGS -->
  <div class="panel">
    <div class="panel-header">
      <div class="panel-title">
        <span>📜 Nhật ký trực tiếp</span>
        <span class="count" id="log-count">(0)</span>
      </div>
      <div class="panel-actions">
        <button class="btn" onclick="toggleAutoScroll()" id="btn-autoscroll">⏸️ Pause</button>
        <button class="btn" onclick="clearLogs()">🗑️ Clear</button>
      </div>
    </div>
    <div class="log-body" id="log-body">
      <div class="empty">Chưa có nhật ký nào...</div>
    </div>
  </div>

  <div class="footer">
    RegFF OB55 · <a href="https://render.com" target="_blank">Render</a> · 2026
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
// ==================== STATE ====================
let autoScroll = true;
let logCount = 0;
let lastAccountCount = 0;
const MAX_LOGS = 500;

// ==================== UTILS ====================
function toast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show ' + type;
  setTimeout(() => el.className = 'toast', 3000);
}

function fmtUptime(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function classifyLog(msg) {
  if (msg.includes('💎')) return 'rare';
  if (msg.includes('💑')) return 'couple';
  if (msg.includes('✅')) return 'ok';
  if (msg.includes('❌')) return 'err';
  if (msg.includes('⚠️')) return 'warn';
  if (msg.includes('🚀') || msg.includes('ℹ️') || msg.includes('📊')) return 'info';
  return '';
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    btn.classList.add('copied');
    const old = btn.textContent;
    btn.textContent = '✅';
    setTimeout(() => {
      btn.textContent = old;
      btn.classList.remove('copied');
    }, 800);
  });
}

// ==================== STATUS ====================
async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    document.getElementById('uptime').textContent = fmtUptime(d.uptime_seconds);
    const pill = document.getElementById('status-pill');
    const txt = document.getElementById('status-text');
    if (d.worker_running) {
      pill.classList.remove('offline');
      txt.textContent = 'WORKER ONLINE';
      document.getElementById('btn-start').disabled = true;
      document.getElementById('btn-stop').disabled = false;
    } else {
      pill.classList.add('offline');
      txt.textContent = 'WORKER OFFLINE';
      document.getElementById('btn-start').disabled = false;
      document.getElementById('btn-stop').disabled = true;
    }
    document.getElementById('stat-success').textContent = d.stats.success;
    document.getElementById('stat-fail').textContent = d.stats.fail;
    document.getElementById('stat-rare').textContent = d.stats.rare;
    document.getElementById('stat-couple').textContent = d.stats.couple;

    // Progress
    const target = d.account_count || 0;
    const done = d.stats.success || 0;
    const pct = target > 0 ? Math.min(100, (done / target) * 100) : 0;
    document.getElementById('progress-fill').style.width = pct + '%';
    document.getElementById('progress-text').textContent = `${done} / ${target}`;
  } catch (e) {
    console.error('Status error:', e);
  }
}

// ==================== ACCOUNTS ====================
async function refreshAccounts() {
  try {
    const r = await fetch('/api/accounts');
    const d = await r.json();
    const accounts = d.accounts || [];
    const tbody = document.getElementById('accounts-tbody');
    document.getElementById('accounts-count').textContent = `(${accounts.length})`;
    document.getElementById('stat-total-accounts').textContent = accounts.length;

    if (accounts.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">📭 Chưa có tài khoản nào</td></tr>';
      return;
    }

    // Chỉ re-render nếu số lượng thay đổi
    if (accounts.length === lastAccountCount) return;
    lastAccountCount = accounts.length;

    let html = '';
    // Hiển thị mới nhất lên đầu
    for (let i = accounts.length - 1; i >= 0; i--) {
      const a = accounts[i];
      const idx = i + 1;
      const uid = a.uid || 'N/A';
      const pwd = a.password || 'N/A';
      const name = a.name || 'N/A';
      const aid = a.account_id || 'N/A';
      html += `<tr>
        <td class="idx">${idx}</td>
        <td class="uid-cell">${escapeHtml(uid)}</td>
        <td class="pass-cell">${escapeHtml(pwd)}</td>
        <td class="hide-mobile name-cell">${escapeHtml(name)}</td>
        <td class="hide-mobile id-cell">${escapeHtml(aid)}</td>
        <td>
          <button class="copy-btn" onclick="copyText('${uid}|${pwd}', this)">📋</button>
        </td>
      </tr>`;
    }
    tbody.innerHTML = html;
  } catch (e) {
    console.error('Accounts error:', e);
  }
}

// ==================== LIVE LOGS (SSE) ====================
let evtSource = null;
function connectSSE() {
  if (evtSource) evtSource.close();
  evtSource = new EventSource('/api/logs/stream');

  evtSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === 'snapshot') {
        const body = document.getElementById('log-body');
        body.innerHTML = '';
        logCount = 0;
        data.logs.forEach(addLogLine);
      } else if (data.type === 'log') {
        addLogLine(data.entry);
        // Refresh accounts mỗi khi có log mới (throttled bởi timeout)
        if (data.entry.msg.includes('✅')) {
          clearTimeout(window._accTimeout);
          window._accTimeout = setTimeout(refreshAccounts, 1000);
        }
      }
    } catch (err) {
      console.error('SSE parse error:', err);
    }
  };

  evtSource.onerror = () => {
    evtSource.close();
    setTimeout(connectSSE, 3000);
  };
}

function addLogLine(entry) {
  const body = document.getElementById('log-body');
  const empty = body.querySelector('.empty');
  if (empty) empty.remove();

  const cls = classifyLog(entry.msg);
  const div = document.createElement('div');
  div.className = 'log-line ' + cls;
  div.innerHTML = `<span class="log-time">${escapeHtml(entry.time)}</span><span class="log-msg">${escapeHtml(entry.msg)}</span>`;
  body.appendChild(div);

  logCount++;
  while (body.children.length > MAX_LOGS) {
    body.removeChild(body.firstChild);
  }
  document.getElementById('log-count').textContent = `(${logCount})`;

  if (autoScroll) body.scrollTop = body.scrollHeight;
}

// ==================== ACTIONS ====================
async function startWorker() {
  try {
    const r = await fetch('/api/start', { method: 'POST' });
    const d = await r.json();
    toast(d.message || 'Đã khởi động', d.ok ? 'success' : 'error');
    setTimeout(fetchStatus, 500);
  } catch (e) {
    toast('Lỗi kết nối', 'error');
  }
}

async function stopWorker() {
  try {
    const r = await fetch('/api/stop', { method: 'POST' });
    const d = await r.json();
    toast(d.message || 'Đã dừng', d.ok ? 'success' : 'error');
    setTimeout(fetchStatus, 500);
  } catch (e) {
    toast('Lỗi kết nối', 'error');
  }
}

function clearLogs() {
  document.getElementById('log-body').innerHTML = '<div class="empty">Đã xóa nhật ký.</div>';
  logCount = 0;
  document.getElementById('log-count').textContent = '(0)';
  toast('Đã xóa nhật ký', 'success');
}

function toggleAutoScroll() {
  autoScroll = !autoScroll;
  const btn = document.getElementById('btn-autoscroll');
  btn.textContent = autoScroll ? '⏸️ Pause' : '▶️ Resume';
  if (autoScroll) {
    const body = document.getElementById('log-body');
    body.scrollTop = body.scrollHeight;
  }
}

// ==================== INIT ====================
fetchStatus();
refreshAccounts();
connectSSE();
setInterval(fetchStatus, 3000);
setInterval(refreshAccounts, 5000);
</script>
</body>
</html>
"""


# ==================== ROUTES ====================
@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "uptime": int(time.time() - START_TIME)})


@app.route("/api/status")
def api_status():
    running = WORKER_PROCESS is not None and WORKER_PROCESS.poll() is None
    uptime = int(time.time() - START_TIME)
    with STATS_LOCK:
        stats = dict(STATS)
    return jsonify({
        "status": "online",
        "uptime_seconds": uptime,
        "worker_running": running,
        "worker_pid": WORKER_PROCESS.pid if WORKER_PROCESS else None,
        "region": os.environ.get("REGION", "VN"),
        "account_count": int(os.environ.get("ACCOUNT_COUNT", "100")),
        "thread_count": int(os.environ.get("THREAD_COUNT", "3")),
        "stats": stats,
    })


@app.route("/api/accounts")
def api_accounts():
    accounts = load_accounts()
    return jsonify({"count": len(accounts), "accounts": accounts})


@app.route("/api/logs")
def api_logs():
    with LOG_LOCK:
        logs = [f"[{e['time']}] {e['msg']}" for e in LOG_BUFFER]
    return jsonify({"count": len(logs), "logs": logs})


@app.route("/api/logs/stream")
def api_logs_stream():
    def gen():
        with LOG_LOCK:
            snapshot = list(LOG_BUFFER)
        yield f"data: {json.dumps({'type': 'snapshot', 'logs': snapshot})}\n\n"
        q = deque(maxlen=100)
        with SUB_LOCK:
            LOG_SUBSCRIBERS.append(q)
        try:
            last_hb = time.time()
            while True:
                if q:
                    entry = q.popleft()
                    yield f"data: {json.dumps({'type': 'log', 'entry': entry})}\n\n"
                else:
                    time.sleep(0.3)
                    if time.time() - last_hb > 15:
                        yield ": heartbeat\n\n"
                        last_hb = time.time()
        except GeneratorExit:
            pass
        finally:
            with SUB_LOCK:
                if q in LOG_SUBSCRIBERS:
                    LOG_SUBSCRIBERS.remove(q)
    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/start", methods=["POST"])
def api_start():
    start_worker()
    return jsonify({"ok": True, "message": "Đã khởi động worker"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    global WORKER_PROCESS
    if WORKER_PROCESS and WORKER_PROCESS.poll() is None:
        WORKER_PROCESS.terminate()
        try:
            WORKER_PROCESS.wait(timeout=5)
        except subprocess.TimeoutExpired:
            WORKER_PROCESS.kill()
        log_line("⏹️ Worker đã dừng theo yêu cầu")
        return jsonify({"ok": True, "message": "Đã dừng worker"})
    return jsonify({"ok": False, "message": "Worker chưa chạy"})


@app.route("/accounts/download")
def accounts_download():
    accounts = load_accounts()
    lines = [
        "=" * 70,
        f"  DANH SÁCH TÀI KHOẢN - VN ({len(accounts)} acc)",
        f"  Xuất lúc: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        "",
    ]
    for i, a in enumerate(accounts, 1):
        lines.append(f"#{i}")
        lines.append(f"  UID       : {a.get('uid', '')}")
        lines.append(f"  Password  : {a.get('password', '')}")
        lines.append(f"  Name      : {a.get('name', '')}")
        lines.append(f"  AccountID : {a.get('account_id', '')}")
        lines.append("")
    return Response(
        "\n".join(lines), mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=accounts-VN.txt"}
    )


@app.route("/accounts/export")
def accounts_export():
    accounts = load_accounts()
    lines = [f"{a.get('uid')}|{a.get('password')}" for a in accounts]
    return Response(
        "\n".join(lines), mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=input.txt"}
    )


@app.route("/api/accounts/list")
def api_accounts_list():
    """Alias cho /api/accounts."""
    return api_accounts()


# ==================== STARTUP ====================
def auto_start():
    if os.environ.get("AUTO_START", "true").lower() == "true":
        time.sleep(2)
        start_worker()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    log_line(f"🌐 Health server khởi động tại cổng {port}")
    threading.Thread(target=auto_start, daemon=True).start()
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
