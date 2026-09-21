#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Health check server + background worker launcher for Render.
Render free tier requires a web service binding to $PORT.
"""
import os
import sys
import json
import time
import threading
import subprocess
from datetime import datetime

try:
    from flask import Flask, jsonify, render_template_string
except ImportError:
    print("Installing flask...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
    from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# ==================== GLOBAL STATE ====================
START_TIME = time.time()
WORKER_PROCESS = None
WORKER_THREAD = None
WORKER_LOG = []
LOG_LOCK = threading.Lock()
MAX_LOG_LINES = 200


def log_line(line: str):
    """Append a line to the in-memory log buffer."""
    with LOG_LOCK:
        WORKER_LOG.append(f"[{datetime.now().strftime('%H:%M:%S')}] {line}")
        if len(WORKER_LOG) > MAX_LOG_LINES:
            WORKER_LOG.pop(0)


def run_worker():
    """Run RegFF_OB55.py as a subprocess and stream output to log buffer."""
    global WORKER_PROCESS
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "RegFF_OB55.py")
    log_line(f"🚀 Starting worker: {script_path}")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    try:
        WORKER_PROCESS = subprocess.Popen(
            [sys.executable, "-u", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            bufsize=1,
            universal_newlines=True,
        )
        for line in WORKER_PROCESS.stdout:
            line = line.rstrip()
            if line:
                log_line(line)
        WORKER_PROCESS.wait()
        log_line(f"⚠️ Worker exited with code {WORKER_PROCESS.returncode}")
    except Exception as e:
        log_line(f"❌ Worker exception: {e}")


def start_worker():
    """Start worker in a daemon thread (only once)."""
    global WORKER_THREAD
    if WORKER_THREAD is None or not WORKER_THREAD.is_alive():
        WORKER_THREAD = threading.Thread(target=run_worker, daemon=True)
        WORKER_THREAD.start()
        log_line("✅ Worker thread started")
    else:
        log_line("ℹ️ Worker already running")


# ==================== HTML INDEX ====================
INDEX_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RegFF OB55 - Control Panel</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', Roboto, sans-serif;
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    color: #e0e0e0;
    min-height: 100vh;
    padding: 20px;
  }
  .container { max-width: 1100px; margin: 0 auto; }
  header {
    text-align: center;
    padding: 30px 20px;
    background: rgba(255,255,255,0.05);
    border-radius: 16px;
    margin-bottom: 20px;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,0.1);
  }
  h1 {
    font-size: 2.2rem;
    background: linear-gradient(90deg, #00d4ff, #7b2ff7, #ff2e63);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
  }
  .subtitle { color: #a0a0a0; font-size: 0.95rem; }
  .status-badge {
    display: inline-block;
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 0.85rem;
    margin-top: 12px;
    font-weight: 600;
  }
  .status-online { background: #10b98122; color: #10b981; border: 1px solid #10b98144; }
  .status-offline { background: #ef444422; color: #ef4444; border: 1px solid #ef444444; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
    margin-bottom: 20px;
  }
  .card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 14px;
    padding: 20px;
    backdrop-filter: blur(10px);
    transition: transform 0.2s;
  }
  .card:hover { transform: translateY(-3px); }
  .card h3 {
    font-size: 0.85rem;
    color: #a0a0a0;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 10px;
  }
  .card .value {
    font-size: 1.8rem;
    font-weight: 700;
    color: #00d4ff;
    word-break: break-all;
  }
  .card .value.small { font-size: 1rem; color: #e0e0e0; }
  .log-box {
    background: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 12px;
    padding: 16px;
    height: 400px;
    overflow-y: auto;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 0.8rem;
    line-height: 1.5;
    color: #00ff88;
    white-space: pre-wrap;
    word-break: break-all;
  }
  .log-box::-webkit-scrollbar { width: 8px; }
  .log-box::-webkit-scrollbar-track { background: #1a1a1a; }
  .log-box::-webkit-scrollbar-thumb { background: #333; border-radius: 4px; }
  .btn-row { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
  .btn {
    padding: 10px 20px;
    border: none;
    border-radius: 10px;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    text-decoration: none;
    display: inline-block;
  }
  .btn-primary { background: linear-gradient(90deg, #00d4ff, #7b2ff7); color: white; }
  .btn-primary:hover { opacity: 0.85; transform: translateY(-2px); }
  .btn-danger { background: #ef4444; color: white; }
  .btn-danger:hover { background: #dc2626; }
  .btn-secondary { background: rgba(255,255,255,0.1); color: #e0e0e0; }
  .btn-secondary:hover { background: rgba(255,255,255,0.2); }
  footer {
    text-align: center;
    padding: 20px;
    color: #666;
    font-size: 0.8rem;
    margin-top: 20px;
  }
  .pulse {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #10b981;
    margin-right: 6px;
    animation: pulse 1.5s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>⚡ RegFF OB55 Control Panel</h1>
    <p class="subtitle">Free Fire Guest Account Generator</p>
    <div class="status-badge status-online">
      <span class="pulse"></span>Server Online
    </div>
  </header>

  <div class="grid">
    <div class="card">
      <h3>⏱️ Uptime</h3>
      <div class="value" id="uptime">--</div>
    </div>
    <div class="card">
      <h3>🔄 Worker Status</h3>
      <div class="value small" id="worker-status">Loading...</div>
    </div>
    <div class="card">
      <h3>🌍 Region</h3>
      <div class="value">{{ region }}</div>
    </div>
    <div class="card">
      <h3>🎯 Target Count</h3>
      <div class="value">{{ account_count }}</div>
    </div>
  </div>

  <div class="btn-row">
    <button class="btn btn-primary" onclick="startWorker()">▶️ Start Worker</button>
    <button class="btn btn-danger" onclick="stopWorker()">⏹️ Stop Worker</button>
    <button class="btn btn-secondary" onclick="location.reload()">🔄 Refresh</button>
    <a class="btn btn-secondary" href="/api/status" target="_blank">📊 API Status</a>
    <a class="btn btn-secondary" href="/api/logs" target="_blank">📜 API Logs</a>
  </div>

  <div class="card">
    <h3>📜 Live Logs</h3>
    <div class="log-box" id="logs">Loading logs...</div>
  </div>

  <footer>
    RegFF OB55 &copy; 2024 - Deployed on Render
  </footer>
</div>

<script>
async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const data = await r.json();
    document.getElementById('uptime').textContent = data.uptime_human;
    document.getElementById('worker-status').textContent = data.worker_running ? '🟢 Running' : '🔴 Stopped';
  } catch (e) {
    document.getElementById('uptime').textContent = 'Error';
  }
}

async function fetchLogs() {
  try {
    const r = await fetch('/api/logs');
    const data = await r.json();
    const box = document.getElementById('logs');
    box.textContent = data.logs.join('\\n') || 'No logs yet...';
    box.scrollTop = box.scrollHeight;
  } catch (e) {
    document.getElementById('logs').textContent = 'Error loading logs';
  }
}

async function startWorker() {
  await fetch('/api/start', { method: 'POST' });
  setTimeout(fetchStatus, 500);
}

async function stopWorker() {
  await fetch('/api/stop', { method: 'POST' });
  setTimeout(fetchStatus, 500);
}

fetchStatus();
fetchLogs();
setInterval(fetchStatus, 3000);
setInterval(fetchLogs, 2000);
</script>
</body>
</html>
"""


# ==================== ROUTES ====================
@app.route("/")
def index():
    return render_template_string(
        INDEX_HTML,
        region=os.environ.get("REGION", "VN"),
        account_count=os.environ.get("ACCOUNT_COUNT", "100"),
    )


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime_seconds": int(time.time() - START_TIME),
    })


@app.route("/api/status")
def api_status():
    worker_running = WORKER_PROCESS is not None and WORKER_PROCESS.poll() is None
    uptime = int(time.time() - START_TIME)
    hours, rem = divmod(uptime, 3600)
    minutes, seconds = divmod(rem, 60)
    return jsonify({
        "status": "online",
        "uptime_seconds": uptime,
        "uptime_human": f"{hours}h {minutes}m {seconds}s",
        "worker_running": worker_running,
        "worker_pid": WORKER_PROCESS.pid if WORKER_PROCESS else None,
        "worker_exit_code": WORKER_PROCESS.returncode if WORKER_PROCESS else None,
        "region": os.environ.get("REGION", "VN"),
        "account_count": os.environ.get("ACCOUNT_COUNT", "100"),
        "thread_count": os.environ.get("THREAD_COUNT", "3"),
        "log_lines": len(WORKER_LOG),
    })


@app.route("/api/logs")
def api_logs():
    with LOG_LOCK:
        logs = list(WORKER_LOG)
    return jsonify({"count": len(logs), "logs": logs})


@app.route("/api/start", methods=["POST"])
def api_start():
    start_worker()
    return jsonify({"ok": True, "message": "Worker started"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    global WORKER_PROCESS
    if WORKER_PROCESS and WORKER_PROCESS.poll() is None:
        WORKER_PROCESS.terminate()
        try:
            WORKER_PROCESS.wait(timeout=5)
        except subprocess.TimeoutExpired:
            WORKER_PROCESS.kill()
        log_line("⏹️ Worker stopped by user")
        return jsonify({"ok": True, "message": "Worker stopped"})
    return jsonify({"ok": False, "message": "Worker not running"})


# ==================== STARTUP ====================
def auto_start():
    """Auto-start worker if AUTO_START env is true."""
    if os.environ.get("AUTO_START", "true").lower() == "true":
        time.sleep(2)  # wait for server to bind
        start_worker()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    log_line(f"🌐 Starting health server on port {port}")

    # Auto-start worker in background
    threading.Thread(target=auto_start, daemon=True).start()

    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
