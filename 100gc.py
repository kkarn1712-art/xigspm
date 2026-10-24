import asyncio
import random
import uuid
import os
import json
import threading
import logging
import re
from flask import Flask, jsonify, Response, request
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, RateLimitError, ChallengeRequired, TwoFactorRequired

logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Configuration Directories
UPLOAD_FOLDER = "uploads"
MESSAGES_FOLDER = os.path.join(UPLOAD_FOLDER, "messages")
TITLES_FOLDER = os.path.join(UPLOAD_FOLDER, "titles")

os.makedirs(MESSAGES_FOLDER, exist_ok=True)
os.makedirs(TITLES_FOLDER, exist_ok=True)

USERNAME = "xyz.enters30"
PASSWORD = "ankushgodhu"
SESSION_FILE = f"session_{USERNAME}.json"

MSG_DELAY = 30
GROUP_DELAY = 4
ERROR_COOLDOWN = 3

DOC_ID = "29088580780787855"
IG_APP_ID = "936619743392459"

USERS = [USERNAME]
logs_ui = {USERNAME: []}

def log_line(text):
    if USERNAME not in logs_ui:
        logs_ui[USERNAME] = []
    logs_ui[USERNAME].append(text)
    if len(logs_ui[USERNAME]) > 200:
        logs_ui[USERNAME].pop(0)
    print(text)

def load_all_messages():
    """Load messages from all uploaded txt files in uploads/messages/"""
    messages = []
    files = [os.path.join(MESSAGES_FOLDER, f) for f in os.listdir(MESSAGES_FOLDER) if f.endswith('.txt')]
    if not files and os.path.exists("text.txt"):
        files.append("text.txt")
    
    for filepath in files:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                cleaned = line.strip()
                if cleaned:
                    messages.append(cleaned)
    return messages if messages else ["Default Spam Message"]

def load_all_titles():
    """Load NC titles supporting comma-separated strings with quotes: "Title 1", "Title 2" """
    titles = []
    files = [os.path.join(TITLES_FOLDER, f) for f in os.listdir(TITLES_FOLDER) if f.endswith('.txt')]
    if not files and os.path.exists("nc.txt"):
        files.append("nc.txt")

    for filepath in files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            raw_titles = re.findall(r'"([^"]*)"', content)
            if not raw_titles:
                raw_titles = [x.strip() for x in content.split(",") if x.strip()]
            if not raw_titles:
                raw_titles = [x.strip() for x in content.splitlines() if x.strip()]
            titles.extend(raw_titles)
    return titles if titles else ["ABHIxPRATIK"]

GREEN = "\033[92m"
RESET = "\033[0m"

cl = Client()
login_lock = asyncio.Lock()

app = Flask(__name__)

@app.route('/status')
def status():
    return jsonify({user: logs_ui.get(user, []) for user in USERS})

@app.route('/logs')
def logs_route():
    output = []
    header_text = "✦  ABHIxPRATIK  ✦"
    output.append(header_text)
    output.append("=" * len(header_text))
    output.append("")
    for user in USERS:
        output.append(f"[ {user} ]")
        output.append("-" * (len(user) + 4))
        for line in logs_ui.get(user, []):
            output.append(line)
        output.append("")
    return Response("\n".join(output), mimetype="text/plain")

@app.route("/", methods=['GET', 'POST'])
def dashboard_handler():
    global USERNAME, PASSWORD, SESSION_FILE
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        # 1. HANDLE LOGIN VIA CREDENTIALS
        if action == 'login_creds':
            USERNAME = request.form.get('username', '').strip()
            PASSWORD = request.form.get('password', '').strip()
            otp = request.form.get('otp', '').strip()
            SESSION_FILE = f"session_{USERNAME}.json"
            if USERNAME not in USERS:
                USERS.append(USERNAME)
                logs_ui[USERNAME] = []
            try:
                setup_mobile_fingerprint()
                if otp:
                    cl.login(USERNAME, PASSWORD, verification_code=otp)
                else:
                    cl.login(USERNAME, PASSWORD)
                cl.dump_settings(SESSION_FILE)
                log_line(f"🔑 WEB LOGIN SUCCESSFUL - {USERNAME}")
            except TwoFactorRequired:
                log_line(f"⚠️ 2FA Required for {USERNAME}. Submit OTP code.")
            except ChallengeRequired:
                log_line(f"⚠️ Challenge Required for {USERNAME}. Submit Email/SMS code.")
            except Exception as e:
                log_line(f"❌ Login Failed: {str(e)}")

        # 2. HANDLE LOGIN VIA SESSION JSON
        elif action == 'login_session':
            session_data = request.form.get('session_data', '').strip()
            u_name = request.form.get('session_user', 'session_user').strip()
            USERNAME = u_name
            SESSION_FILE = f"session_{USERNAME}.json"
            if USERNAME not in USERS:
                USERS.append(USERNAME)
                logs_ui[USERNAME] = []
            try:
                session_json = json.loads(session_data)
                cl.set_settings(session_json)
                cl.dump_settings(SESSION_FILE)
                log_line(f"⏳ SESSION LOADED VIA WEB - {USERNAME}")
            except Exception as e:
                log_line(f"❌ Session Error: {str(e)}")

        # 3. HANDLE FILE UPLOADS
        elif action == 'upload_files':
            file_type = request.form.get('file_type')
            uploaded_files = request.files.getlist('files')
            target_dir = MESSAGES_FOLDER if file_type == 'message' else TITLES_FOLDER
            count = 0
            for file in uploaded_files:
                if file and file.filename.endswith('.txt'):
                    file.save(os.path.join(target_dir, file.filename))
                    count += 1
            log_line(f"📁 Successfully uploaded {count} {file_type} file(s)!")

    # Build dynamic logs
    logs_html = ""
    for user in USERS:
        logs_html += f'<div class="panel-title">User: {user}</div>'
        for line in logs_ui.get(user, []):
            logs_html += f'<div class="log-line">{line}</div>'

    return f"""
    <html>
    <head>
        <title>ABHIxPRATIK - All-in-One Control Panel</title>
        <meta http-equiv="refresh" content="3">
        <style>
            body {{ background-color: #0d1117; font-family: monospace; margin: 0; padding: 15px; color: #00ff88; }}
            .header {{ text-align: center; font-size: 24px; font-weight: bold; margin-bottom: 15px; border: 2px solid #00ff88; padding: 10px; }}
            .grid {{ display: flex; flex-wrap: wrap; gap: 15px; align-items: flex-start; }}
            .card {{ border: 2px solid #00ff88; background-color: #111827; padding: 15px; flex: 1; min-width: 320px; box-sizing: border-box; }}
            .card h3 {{ margin-top: 0; border-bottom: 1px solid #00ff88; padding-bottom: 5px; font-size: 15px; }}
            input, select, textarea {{ width: 100%; padding: 8px; margin: 6px 0; background: #0d1117; border: 1px solid #00ff88; color: #00ff88; box-sizing: border-box; }}
            button {{ background: #00ff88; color: #0d1117; border: none; padding: 10px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 5px; }}
            .log-panel {{ border: 2px solid #00ff88; background-color: #111827; padding: 15px; flex: 2; min-width: 350px; height: 62vh; overflow-y: auto; box-sizing: border-box; }}
            .panel-title {{ font-weight: bold; margin-bottom: 10px; border-bottom: 1px solid #00ff88; padding-bottom: 5px; }}
            .log-line {{ margin-bottom: 5px; white-space: pre-wrap; font-size: 13px; }}
        </style>
    </head>
    <body>
        <div class="header">✦ ABHIxPRATIK ALL-IN-ONE CONTROL PANEL ✦</div>
        
        <div class="grid">
            <!-- LEFT COLUMN: CONTROLS (LOGIN & UPLOADS) -->
            <div style="flex: 1; min-width: 320px; display: flex; flex-direction: column; gap: 15px;">
                
                <!-- 1. IDP LOGIN -->
                <div class="card">
                    <h3>🔑 Login via ID / Pass / OTP</h3>
                    <form method="POST">
                        <input type="hidden" name="action" value="login_creds">
                        <input type="text" name="username" placeholder="Username" required>
                        <input type="password" name="password" placeholder="Password" required>
                        <input type="text" name="otp" placeholder="2FA / OTP Code (if prompted)">
                        <button type="submit">LOGIN ACCOUNT</button>
                    </form>
                </div>

                <!-- 2. SESSION LOGIN -->
                <div class="card">
                    <h3>⏳ Login via Session JSON</h3>
                    <form method="POST">
                        <input type="hidden" name="action" value="login_session">
                        <input type="text" name="session_user" placeholder="Account Username" required>
                        <textarea name="session_data" rows="3" placeholder='Paste Session JSON payload...' required></textarea>
                        <button type="submit">LOAD SESSION</button>
                    </form>
                </div>

                <!-- 3. FILE UPLOADS -->
                <div class="card">
                    <h3>📁 Upload TXT Files (Spam & NC Titles)</h3>
                    <form method="POST" enctype="multipart/form-data">
                        <input type="hidden" name="action" value="upload_files">
                        <select name="file_type">
                            <option value="message">Spam Message TXT (Multiple)</option>
                            <option value="title">NC Group Title TXT (Quotes/Commas)</option>
                        </select>
                        <input type="file" name="files" accept=".txt" multiple required>
                        <button type="submit">UPLOAD FILES</button>
                    </form>
                </div>

            </div>

            <!-- RIGHT COLUMN: LIVE EXECUTION CONSOLE -->
            <div class="log-panel" id="logPanel">
                <div class="panel-title">📡 Live Execution Console</div>
                {logs_html}
            </div>
        </div>

        <script>
        function autoScroll() {{
            var p = document.getElementById('logPanel');
            p.scrollTop = p.scrollHeight;
        }}
        window.onload = autoScroll;
        </script>
    </body>
    </html>
    """

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def setup_mobile_fingerprint():
    cl.set_user_agent(
        "Instagram 312.0.0.22.114 Android "
        "(33/13; 420dpi; 1080x2400; OnePlus; "
        "GM1913; OnePlus7Pro; qcom; en_US)"
    )
    cl.set_locale("en_US")
    cl.set_country_code(1)
    cl.set_timezone_offset(-18000)

    uuids = {
        "phone_id": str(uuid.uuid4()),
        "uuid": str(uuid.uuid4()),
        "client_session_id": str(uuid.uuid4()),
        "advertising_id": str(uuid.uuid4()),
        "device_id": "android-" + uuid.uuid4().hex[:16]
    }
    cl.set_uuids(uuids)
    cl.private.headers.update({
        "X-IG-App-ID": IG_APP_ID,
        "X-IG-Device-ID": uuids["uuid"],
        "X-IG-Android-ID": uuids["device_id"],
        "X-IG-Timezone-Offset": "-18000",
        "Accept-Language": "en-US",
        "Connection": "keep-alive"
    })

async def login():
    async with login_lock:
        if os.path.exists(SESSION_FILE):
            try:
                cl.load_settings(SESSION_FILE)
                cl.login(USERNAME, PASSWORD)
                cl.get_timeline_feed()
                log_line(f"⏳SESSION LOGIN - {GREEN}{USERNAME}{RESET}")
                return
            except Exception:
                pass
        try:
            cl.login(USERNAME, PASSWORD)
            cl.dump_settings(SESSION_FILE)
            log_line(f"⏳FRESH LOGIN - {GREEN}{USERNAME}{RESET}")
        except Exception as e:
            log_line(f"❌ LOGIN ERROR: {str(e)}")

def fetch_group_threads():
    try:
        threads = cl.direct_threads(amount=100)
    except Exception:
        return []
    group_ids = []
    for t in threads:
        try:
            if getattr(t, "is_group", False) and len(t.users) >= 2:
                group_ids.append(t.id)
        except Exception:
            continue
    log_line(f"🕸️ GCS - {GREEN}{len(group_ids)}{RESET}")
    return group_ids

async def api_call(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)

def graphql_rename(thread_id, title):
    csrf = cl.private.cookies.get("csrftoken", "")
    cl.private.headers.update({
        "X-CSRFToken": csrf,
        "Referer": f"https://www.instagram.com/direct/t/{thread_id}/"
    })
    payload = {
        "doc_id": DOC_ID,
        "variables": json.dumps({
            "thread_fbid": str(thread_id),
            "new_title": title
        })
    }
    r = cl.private.post(
        "https://www.instagram.com/api/graphql/",
        data=payload,
        timeout=10
    )
    return r.status_code == 200

def rename_thread(thread_id, title):
    try:
        cl.private_request(
            f"direct_v2/threads/{thread_id}/update_title/",
            data={"title": title}
        )
        return True
    except RateLimitError:
        return graphql_rename(thread_id, title)
    except Exception as e:
        if "rate" in str(e).lower():
            return graphql_rename(thread_id, title)
        return False

async def process_groups(group_ids):
    messages = load_all_messages()
    titles = load_all_titles()
    
    total = len(group_ids)
    for i, gid in enumerate(group_ids, start=1):
        try:
            msg = random.choice(messages)
            await api_call(cl.direct_send, msg, thread_ids=[gid])
            log_line(f"📨 - {i}/{total}")
            await asyncio.sleep(MSG_DELAY)
            
            title = random.choice(titles)
            success = await api_call(rename_thread, gid, title)
            if success:
                log_line(f"💠 - {title}")
            await asyncio.sleep(GROUP_DELAY)
        except LoginRequired:
            await login()
        except Exception:
            await asyncio.sleep(ERROR_COOLDOWN)

async def main():
    setup_mobile_fingerprint()
    await login()
    round_num = 1
    while True:
        groups = fetch_group_threads()
        if groups:
            await process_groups(groups)
        round_num += 1
        log_line(f"\n🥤- ROUND {round_num} (120s wait)\n")
        await asyncio.sleep(120)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    asyncio.run(main())
