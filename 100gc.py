import asyncio
import random
import uuid
import os
import json
import threading
import logging
import re
from flask import Flask, jsonify, Response, request, render_template_string
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
            # Extract quotes or comma separated titles
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

@app.route('/')
def home():
    return "alive"

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

@app.route("/dashboard")
def dashboard():
    html = """
    <html>
    <head>
        <title>ABHIxPRATIK</title>
        <meta http-equiv="refresh" content="2">
        <style>
            body { background-color: #0d1117; font-family: monospace; margin: 0; padding: 20px; color: #00ff88; }
            .header { text-align: center; font-size: 28px; font-weight: bold; margin-bottom: 20px; border: 2px solid #00ff88; padding: 10px; }
            .nav { text-align: center; margin-bottom: 20px; }
            .nav a { color: #00ff88; margin: 0 15px; text-decoration: none; border: 1px solid #00ff88; padding: 5px 15px; }
            .container { display: flex; flex-direction: row; gap: 20px; align-items: flex-start; }
            .panel { flex: 1; min-width: 300px; border: 2px solid #00ff88; background-color: #111827; padding: 15px; height: 70vh; overflow-y: auto; }
            .panel-title { font-weight: bold; margin-bottom: 10px; border-bottom: 1px solid #00ff88; padding-bottom: 5px; }
            .log-line { margin-bottom: 6px; white-space: pre-wrap; }
        </style>
    </head>
    <body>
        <div class="header">✦ ABHIxPRATIK ✦</div>
        <div class="nav">
            <a href="/login-panel">🔑 LOGIN PANEL</a>
            <a href="/upload-panel">📁 FILE UPLOAD PANEL</a>
        </div>
        <div class="container">
    """
    for user in USERS:
        html += f'<div class="panel"><div class="panel-title">{user}</div>'
        for line in logs_ui.get(user, []):
            html += f'<div class="log-line">{line}</div>'
        html += "</div>"
    html += """
        </div>
        <script>
        function scrollPanels() {
            document.querySelectorAll('.panel').forEach(function(panel) {
                panel.scrollTop = panel.scrollHeight;
            });
        }
        window.onload = scrollPanels;
        setInterval(scrollPanels, 1500);
        </script>
    </body>
    </html>
    """
    return html

@app.route('/login-panel', methods=['GET', 'POST'])
def login_panel():
    msg = ""
    if request.method == 'POST':
        login_type = request.form.get('login_type')
        global USERNAME, PASSWORD, SESSION_FILE

        if login_type == 'credentials':
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
                msg = "Login successful! Check dashboard for details."
            except TwoFactorRequired:
                msg = "2FA Required! Please submit form again with 2FA OTP code."
            except ChallengeRequired:
                msg = "Challenge Required by Instagram! Submit OTP code received on Email/SMS."
            except Exception as e:
                msg = f"Login Failed: {str(e)}"

        elif login_type == 'session':
            session_data = request.form.get('session_data', '').strip()
            u_name = request.form.get('session_user', 'session_user').strip()
            USERNAME = u_name
            SESSION_FILE = f"session_{USERNAME}.json"
            
            try:
                session_json = json.loads(session_data)
                cl.set_settings(session_json)
                cl.dump_settings(SESSION_FILE)
                log_line(f"⏳ SESSION LOADED VIA WEB - {USERNAME}")
                msg = "Session settings successfully loaded!"
            except Exception as e:
                msg = f"Invalid Session JSON: {str(e)}"

    return f"""
    <html>
    <head>
        <title>ABHIxPRATIK - Login</title>
        <style>
            body {{ background-color: #0d1117; font-family: monospace; padding: 30px; color: #00ff88; }}
            .box {{ border: 2px solid #00ff88; padding: 20px; max-width: 500px; margin: 0 auto 30px auto; background: #111827; }}
            input, select, textarea {{ width: 100%; padding: 10px; margin: 10px 0; background: #0d1117; border: 1px solid #00ff88; color: #00ff88; box-sizing: border-box; }}
            button {{ background: #00ff88; color: #0d1117; border: none; padding: 10px 20px; font-weight: bold; cursor: pointer; width: 100%; }}
            .msg {{ color: #ff0055; margin-bottom: 15px; font-weight: bold; text-align: center; }}
            a {{ color: #00ff88; text-decoration: none; display: block; text-align: center; margin-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="msg">{msg}</div>
        
        <!-- OPTION 1: CREDENTIALS / OTP -->
        <div class="box">
            <h3>Option 1: Login via ID / Pass / OTP</h3>
            <form method="POST">
                <input type="hidden" name="login_type" value="credentials">
                <input type="text" name="username" placeholder="Username" required>
                <input type="password" name="password" placeholder="Password" required>
                <input type="text" name="otp" placeholder="2FA / OTP Code (Optional)">
                <button type="submit">LOGIN VIA ID</button>
            </form>
        </div>

        <!-- OPTION 2: SESSION -->
        <div class="box">
            <h3>Option 2: Login via Session JSON</h3>
            <form method="POST">
                <input type="hidden" name="login_type" value="session">
                <input type="text" name="session_user" placeholder="Account Username identifier" required>
                <textarea name="session_data" rows="5" placeholder='Paste Session JSON payload here...' required></textarea>
                <button type="submit">LOAD SESSION</button>
            </form>
        </div>

        <a href="/dashboard">← Back to Dashboard</a>
    </body>
    </html>
    """

@app.route('/upload-panel', methods=['GET', 'POST'])
def upload_panel():
    msg = ""
    if request.method == 'POST':
        file_type = request.form.get('file_type')
        uploaded_files = request.files.getlist('files')

        target_dir = MESSAGES_FOLDER if file_type == 'message' else TITLES_FOLDER
        
        count = 0
        for file in uploaded_files:
            if file and file.filename.endswith('.txt'):
                file.save(os.path.join(target_dir, file.filename))
                count += 1
        
        msg = f"Successfully uploaded {count} file(s)!"

    return f"""
    <html>
    <head>
        <title>ABHIxPRATIK - File Upload</title>
        <style>
            body {{ background-color: #0d1117; font-family: monospace; padding: 30px; color: #00ff88; }}
            .box {{ border: 2px solid #00ff88; padding: 20px; max-width: 500px; margin: 0 auto; background: #111827; }}
            select, input {{ width: 100%; padding: 10px; margin: 10px 0; background: #0d1117; border: 1px solid #00ff88; color: #00ff88; box-sizing: border-box; }}
            button {{ background: #00ff88; color: #0d1117; border: none; padding: 10px 20px; font-weight: bold; cursor: pointer; width: 100%; }}
            .msg {{ color: #00ff88; margin-bottom: 15px; font-weight: bold; text-align: center; }}
            a {{ color: #00ff88; text-decoration: none; display: block; text-align: center; margin-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="box">
            <h3>📁 Upload TXT Files</h3>
            <div class="msg">{msg}</div>
            <form method="POST" enctype="multipart/form-data">
                <label>Target File Type:</label>
                <select name="file_type">
                    <option value="message">Spam Message TXT (Multiple Supported)</option>
                    <option value="title">NC Group Title TXT (Comma/Quotes Supported)</option>
                </select>
                
                <input type="file" name="files" accept=".txt" multiple required>
                <button type="submit">UPLOAD FILES</button>
            </form>
        </div>
        <a href="/dashboard">← Back to Dashboard</a>
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
