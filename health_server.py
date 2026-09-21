#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Health check server + Control Panel cho Render.
UI tiếng Việt, realtime logs qua SSE.
"""
import os
import sys
import json
import time
import threading
import subprocess
from datetime import datetime, timedelta
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


def log_line(line: str):
    """Thêm log vào buffer + broadcast SSE."""
    ts = datetime.now().strftime("%H:%M:%S")
    entry = {"time": ts, "msg": line}
    with LOG_LOCK:
        LOG_BUFFER.append(entry)
    # Broadcast to SSE subscribers
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
    """Parse log để cập nhật stats."""
    with STATS_LOCK:
        if "✅" in line and "UID=" in line:
            STATS["success"] += 1
            try:
                uid_part = line.split("UID=")[1].split("|")[0].strip()
                STATS["last_uid"] = uid_part
                if "ID=" in line:
                    STATS["last_account_id"] = line.split("ID=")[1].split("|")[0].strip()
                if "|" in line:
                    name_part = line.split("|")[-1].strip()
                    STATS["last_name"] = name_part[:40]
            except Exception:
                pass
        if "❌" in line:
            STATS["fail"] += 1
        if "💎" in line:
            STATS["rare"] += 1
        if "💑" in line:
            STATS["couple"] += 1


def run_worker():
    """Chạy RegFF_OB55.py và stream log."""
    global WORKER_PROCESS
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "RegFF_OB55.py")
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


# ==================== HTML ====================
HTML = r"""
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>⚡ RegFF OB55 — Bảng điều khiển</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-0: #0a0e1a;
    --bg-1: #111827;
    --bg-2: #1a2233;
    --border: rgba(255,255,255,0.08);
    --border-hover: rgba(255,255,255,0.15);
    --text: #e6edf7;
    --text-dim: #8b95a8;
    --accent: #00d9ff;
    --accent-2: #7c3aed;
    --success: #10b981;
    --danger: #ef4444;
    --warning: #f59e0b;
    --rare: #fbbf24;
    --couple: #ec4899;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: 'Be Vietnam Pro', -apple-system, sans-serif;
    background: var(--bg-0);
    color: var(--text);
    min-height: 100vh;
    overflow-x: hidden;
    position: relative;
  }
  /* Animated background */
  body::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background:
      radial-gradient(circle at 15% 20%, rgba(0, 217, 255, 0.08) 0%, transparent 40%),
      radial-gradient(circle at 85% 80%, rgba(124, 58, 237, 0.08) 0%, transparent 40%),
      radial-gradient(circle at 50% 50%, rgba(236, 72, 153, 0.04) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
  }
  .container {
    position: relative;
    z-index: 1;
    max-width: 1280px;
    margin: 0 auto;
    padding: 24px;
  }

  /* ===== HEADER ===== */
  .header {
    background: linear-gradient(135deg, rgba(26, 34, 51, 0.9), rgba(17, 24, 39, 0.9));
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 28px 32px;
    margin-bottom: 20px;
    backdrop-filter: blur(20px);
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 20px;
    position: relative;
    overflow: hidden;
  }
  .header::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--accent), var(--accent-2), var(--couple), var(--accent));
    background-size: 300% 100%;
    animation: shimmer 4s linear infinite;
  }
  @keyframes shimmer {
    0% { background-position: 0% 50%; }
    100% { background-position: 300% 50%; }
  }
  .header-left h1 {
    font-size: 1.9rem;
    font-weight: 800;
    letter-spacing: -0.5px;
    background: linear-gradient(135deg, #fff 0%, var(--accent) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .header-left p {
    color: var(--text-dim);
    font-size: 0.9rem;
    margin-top: 6px;
    font-weight: 500;
  }
  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 18px;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
    background: rgba(16, 185, 129, 0.1);
    color: var(--success);
    border: 1px solid rgba(16, 185, 129, 0.25);
  }
  .status-pill.offline {
    background: rgba(239, 68, 68, 0.1);
    color: var(--danger);
    border-color: rgba(239, 68, 68, 0.25);
  }
  .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: currentColor;
    animation: pulse 1.5s ease-in-out infinite;
    box-shadow: 0 0 8px currentColor;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.85); }
  }

  /* ===== STATS GRID ===== */
  .stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 20px;
  }
  .stat-card {
    background: linear-gradient(135deg, var(--bg-2) 0%, var(--bg-1) 100%);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 20px;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
  }
  .stat-card:hover {
    transform: translateY(-4px);
    border-color: var(--border-hover);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
  }
  .stat-card::after {
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 100px; height: 100px;
    background: radial-gradient(circle, var(--accent) 0%, transparent 70%);
    opacity: 0.08;
    border-radius: 50%;
    transform: translate(30%, -30%);
  }
  .stat-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 1.2px;
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 10px;
  }
  .stat-value {
    font-size: 1.9rem;
    font-weight: 800;
    color: var(--text);
    letter-spacing: -0.5px;
    font-family: 'JetBrains Mono', monospace;
  }
  .stat-value.cyan { color: var(--accent); }
  .stat-value.green { color: var(--success); }
  .stat-value.red { color: var(--danger); }
  .stat-value.gold { color: var(--rare); }
  .stat-value.pink { color: var(--couple); }
  .stat-sub {
    font-size: 0.75rem;
    color: var(--text-dim);
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
    margin-bottom: 20px;
    flex-wrap: wrap;
  }
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 12px 22px;
    border: 1px solid var(--border);
    border-radius: 12px;
    font-family: inherit;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    text-decoration: none;
    color: var(--text);
    background: var(--bg-2);
    user-select: none;
  }
  .btn:hover {
    transform: translateY(-2px);
    border-color: var(--border-hover);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3);
  }
  .btn:active { transform: translateY(0); }
  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
  }
  .btn-primary {
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    border: none;
    color: white;
  }
  .btn-success {
    background: linear-gradient(135deg, #10b981, #059669);
    border: none;
    color: white;
  }
  .btn-danger {
    background: linear-gradient(135deg, #ef4444, #dc2626);
    border: none;
    color: white;
  }
  .btn-ghost { background: var(--bg-2); }

  /* ===== LOG PANEL ===== */
  .log-panel {
    background: linear-gradient(180deg, var(--bg-1) 0%, #0d1117 100%);
    border: 1px solid var(--border);
    border-radius: 16px;
    overflow: hidden;
  }
  .log-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
    background: rgba(0, 0, 0, 0.3);
  }
  .log-title {
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .log-actions { display: flex; gap: 8px; }
  .log-actions .btn {
    padding: 6px 12px;
    font-size: 0.75rem;
    border-radius: 8px;
  }
  .log-body {
    height: 480px;
    overflow-y: auto;
    padding: 16px 20px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    line-height: 1.7;
    scroll-behavior: smooth;
  }
  .log-body::-webkit-scrollbar { width: 8px; }
  .log-body::-webkit-scrollbar-track { background: transparent; }
  .log-body::-webkit-scrollbar-thumb {
    background: rgba(255,255,255,0.15);
    border-radius: 4px;
  }
  .log-body::-webkit-scrollbar-thumb:hover {
    background: rgba(255,255,255,0.25);
  }
  .log-line {
    display: flex;
    gap: 12px;
    padding: 3px 0;
    border-radius: 6px;
    transition: background 0.15s;
    word-break: break-all;
  }
  .log-line:hover { background: rgba(255,255,255,0.03); }
  .log-time {
    color: var(--text-dim);
    flex-shrink: 0;
    font-size: 0.75rem;
    padding-top: 2px;
  }
  .log-msg { color: #a8b3c4; flex: 1; }
  .log-line.ok .log-msg { color: var(--success); }
  .log-line.err .log-msg { color: var(--danger); }
  .log-line.rare .log-msg { color: var(--rare); font-weight: 600; }
  .log-line.couple .log-msg { color: var(--couple); font-weight: 600; }
  .log-line.info .log-msg { color: var(--accent); }
  .log-line.warn .log-msg { color: var(--warning); }

  /* ===== PROGRESS BAR ===== */
  .progress-wrap {
    margin-top: 20px;
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 20px;
  }
  .progress-info {
    display: flex;
    justify-content: space-between;
    font-size: 0.85rem;
    margin-bottom: 10px;
    font-weight: 600;
  }
  .progress-bar {
    height: 10px;
    background: rgba(255,255,255,0.05);
    border-radius: 5px;
    overflow: hidden;
    position: relative;
  }
  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--accent-2));
    border-radius: 5px;
    transition: width 0.5s ease;
    position: relative;
    box-shadow: 0 0 20px rgba(0, 217, 255, 0.5);
  }
  .progress-fill::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
    animation: shine 2s infinite;
  }
  @keyframes shine {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(100%); }
  }

  /* ===== EMPTY ===== */
  .empty {
    color: var(--text-dim);
    text-align: center;
    padding: 60px 20px;
    font-style: italic;
  }

  /* ===== FOOTER ===== */
  .footer {
    text-align: center;
    padding: 24px;
    color: var(--text-dim);
    font-size: 0.8rem;
    margin-top: 20px;
  }
  .footer a { color: var(--accent); text-decoration: none; }

  /* ===== RESPONSIVE ===== */
  @media (max-width: 640px) {
    .container { padding: 16px; }
    .header { padding: 20px; }
    .header-left h1 { font-size: 1.4rem; }
    .stat-value { font-size: 1.5rem; }
    .log-body { height: 380px; }
    .btn { padding: 10px 16px; font-size: 0.85rem; }
  }

  /* ===== TOAST ===== */
  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 20px;
    color: var(--text);
    font-size: 0.9rem;
    font-weight: 500;
    box-shadow: 0 10px 40px rgba(0,0,0,0.5);
    transform: translateY(100px);
    opacity: 0;
    transition: all 0.3s;
    z-index: 9999;
  }
  .toast.show { transform: translateY(0); opacity: 1; }
  .toast.success { border-color: var(--success); }
  .toast.error { border-color: var(--danger); }
</style>
</head>
<body>
<div class="container">

  <!-- HEADER -->
  <div class="header">
    <div class="header-left">
      <h1>⚡ RegFF OB55</h1>
      <p>Trình tạo tài khoản khách Free Fire · Bảng điều khiển</p>
    </div>
    <div id="status-pill" class="status-pill">
      <span class="dot"></span>
      <span id="status-text">Đang tải...</span>
    </div>
  </div>

  <!-- STATS -->
  <div class="stats">
    <div class="stat-card">
      <div class="stat-label">⏱️ Thời gian hoạt động</div>
      <div class="stat-value cyan" id="uptime">--</div>
      <div class="stat-sub" id="started-at">Bắt đầu: --</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">✅ Thành công</div>
      <div class="stat-value green" id="stat-success">0</div>
      <div class="stat-sub" id="stat-last-uid">Chưa có</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">❌ Thất bại</div>
      <div class="stat-value red" id="stat-fail">0</div>
      <div class="stat-sub">Tổng số lỗi</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">💎 Tài khoản hiếm</div>
      <div class="stat-value gold" id="stat-rare">0</div>
      <div class="stat-sub">Rarity cao</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">💑 Cặp đôi</div>
      <div class="stat-value pink" id="stat-couple">0</div>
      <div class="stat-sub">ID tuần tự / đối xứng</div>
    </div>
  </div>

  <!-- CONTROLS -->
  <div class="controls">
    <button class="btn btn-success" id="btn-start" onclick="startWorker()">
      ▶️ Bắt đầu
    </button>
    <button class="btn btn-danger" id="btn-stop" onclick="stopWorker()">
      ⏹️ Dừng
    </button>
    <button class="btn btn-primary" onclick="clearLogs()">
      🗑️ Xóa log
    </button>
    <a class="btn btn-ghost" href="/api/status" target="_blank">
      📊 API Trạng thái
    </a>
    <a class="btn btn-ghost" href="/api/logs" target="_blank">
      📜 API Logs
    </a>
  </div>

  <!-- PROGRESS -->
  <div class="progress-wrap">
    <div class="progress-info">
      <span>📈 Tiến độ tạo tài khoản</span>
      <span id="progress-text">0 / 0</span>
    </div>
    <div class="progress-bar">
      <div class="progress-fill" id="progress-fill" style="width: 0%"></div>
    </div>
  </div>

  <!-- LOGS -->
  <div class="log-panel" style="margin-top: 20px;">
    <div class="log-header">
      <div class="log-title">
        <span>📜 Nhật ký trực tiếp</span>
        <span id="log-count" style="color: var(--text-dim); font-weight: 400; font-size: 0.75rem;">(0)</span>
      </div>
      <div class="log-actions">
        <button class="btn btn-ghost" onclick="toggleAutoScroll()" id="btn-autoscroll">
          ⏸️ Tạm dừng tự cuộn
        </button>
      </div>
    </div>
    <div class="log-body" id="log-body">
      <div class="empty">Chưa có nhật ký nào... Nhấn "Bắt đầu" để chạy worker.</div>
    </div>
  </div>

  <div class="footer">
    RegFF OB55 · Chạy trên <a href="https://render.com" target="_blank">Render</a> · {{ year }}
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
// ==================== STATE ====================
let autoScroll = true;
let logCount = 0;
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
  if (h > 0) return `${h}g ${m}p ${s}s`;
  if (m > 0) return `${m}p ${s}s`;
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
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

// ==================== STATUS POLLING ====================
async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();

    document.getElementById('uptime').textContent = fmtUptime(d.uptime_seconds);
    document.getElementById('started-at').textContent = 'Bắt đầu: ' + d.started_at;

    const pill = document.getElementById('status-pill');
    const txt = document.getElementById('status-text');
    if (d.worker_running) {
      pill.classList.remove('offline');
      txt.textContent = 'Worker đang chạy';
      document.getElementById('btn-start').disabled = true;
      document.getElementById('btn-stop').disabled = false;
    } else {
      pill.classList.add('offline');
      txt.textContent = 'Worker đã dừng';
      document.getElementById('btn-start').disabled = false;
      document.getElementById('btn-stop').disabled = true;
    }

    document.getElementById('stat-success').textContent = d.stats.success;
    document.getElementById('stat-fail').textContent = d.stats.fail;
    document.getElementById('stat-rare').textContent = d.stats.rare;
    document.getElementById('stat-couple').textContent = d.stats.couple;
    if (d.stats.last_uid) {
      document.getElementById('stat-last-uid').textContent = 'UID cuối: ' + d.stats.last_uid;
    }

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

// ==================== LIVE LOGS (SSE) ====================
let evtSource = null;
function connectSSE() {
  if (evtSource) evtSource.close();
  evtSource = new EventSource('/api/logs/stream');

  evtSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === 'snapshot') {
        // Initial snapshot
        const body = document.getElementById('log-body');
        body.innerHTML = '';
        logCount = 0;
        data.logs.forEach(addLogLine);
      } else if (data.type === 'log') {
        addLogLine(data.entry);
      }
    } catch (err) {
      console.error('SSE parse error:', err);
    }
  };

  evtSource.onerror = () => {
    console.warn('SSE disconnected, retry in 3s...');
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
  // Trim
  while (body.children.length > MAX_LOGS) {
    body.removeChild(body.firstChild);
  }
  document.getElementById('log-count').textContent = `(${logCount})`;

  if (autoScroll) {
    body.scrollTop = body.scrollHeight;
  }
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
  btn.textContent = autoScroll ? '⏸️ Tạm dừng tự cuộn' : '▶️ Bật tự cuộn';
  if (autoScroll) {
    const body = document.getElementById('log-body');
    body.scrollTop = body.scrollHeight;
  }
}

// ==================== INIT ====================
fetchStatus();
connectSSE();
setInterval(fetchStatus, 3000);
</script>
</body>
</html>
"""


# ==================== ROUTES ====================
@app.route("/")
def index():
    return render_template_string(HTML, year=datetime.now().year)


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "uptime": int(time.time() - START_TIME)})


@app.route("/api/status")
def api_status():
    running = WORKER_PROCESS is not None and WORKER_PROCESS.poll() is None
    uptime = int(time.time() - START_TIME)
    with STATS_LOCK:
        stats = dict(STATS)
    started = datetime.fromtimestamp(START_TIME).strftime("%H:%M:%S %d/%m/%Y")
    return jsonify({
        "status": "online",
        "uptime_seconds": uptime,
        "started_at": started,
        "worker_running": running,
        "worker_pid": WORKER_PROCESS.pid if WORKER_PROCESS else None,
        "region": os.environ.get("REGION", "VN"),
        "account_count": int(os.environ.get("ACCOUNT_COUNT", "100")),
        "thread_count": int(os.environ.get("THREAD_COUNT", "3")),
        "stats": stats,
        "log_count": len(LOG_BUFFER),
    })


@app.route("/api/logs")
def api_logs():
    with LOG_LOCK:
        logs = [f"[{e['time']}] {e['msg']}" for e in LOG_BUFFER]
    return jsonify({"count": len(logs), "logs": logs})


@app.route("/api/logs/stream")
def api_logs_stream():
    """SSE endpoint - stream logs realtime."""
    def gen():
        # Initial snapshot
        with LOG_LOCK:
            snapshot = list(LOG_BUFFER)
        yield f"data: {json.dumps({'type': 'snapshot', 'logs': snapshot})}\n\n"

        # Subscribe to new logs
        q = deque(maxlen=100)
        with SUB_LOCK:
            LOG_SUBSCRIBERS.append(q)

        try:
            last_heartbeat = time.time()
            while True:
                if q:
                    entry = q.popleft()
                    yield f"data: {json.dumps({'type': 'log', 'entry': entry})}\n\n"
                else:
                    time.sleep(0.3)
                    # Heartbeat every 15s
                    if time.time() - last_heartbeat > 15:
                        yield ": heartbeat\n\n"
                        last_heartbeat = time.time()
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
