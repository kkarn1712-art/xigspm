# --- eventlet MUST be monkey-patched before any other import ---
import eventlet
eventlet.monkey_patch()

import os
import io
import json
import time
import threading
import logging
from typing import List, Dict, Optional

from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit

# ---- Real automation libs ----
try:
    from instagrapi import Client as IGClient
    from instagrapi.exceptions import (
        LoginRequired, TwoFactorRequired, ChallengeRequired,
        PleaseWaitFewMinutes, ClientError,
    )
    IG_AVAILABLE = True
except Exception as _e:
    IG_AVAILABLE = False
    IG_IMPORT_ERROR = str(_e)

try:
    from playwright.sync_api import sync_playwright
    PW_AVAILABLE = True
except Exception as _e:
    PW_AVAILABLE = False
    PW_IMPORT_ERROR = str(_e)

# ---- Optional encryption of saved sessions ----
try:
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except Exception:
    CRYPTO_AVAILABLE = False

# ---------------------------------------------------------------
# Config / logging
# ---------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
SESSION_FILE = os.path.join(BASE_DIR, "sessions.json")
KEY_FILE = os.path.join(BASE_DIR, ".session.key")
os.makedirs(UPLOAD_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "panel.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("panel")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('PANEL_SECRET', os.urandom(32).hex())
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB uploads

allowed_origins = os.environ.get('PANEL_ORIGINS', '*')
socketio = SocketIO(app, cors_allowed_origins=allowed_origins, async_mode='eventlet')


# ---------------------------------------------------------------
# Message templates (UNCHANGED — same 4 sets)
# ---------------------------------------------------------------
MESSAGE_TEMPLATES = {
    "Pratik template 1": [ 
            "𝗔𝗡𝗧𝗘𝗥 𝗠𝗔𝗡𝗧𝗘𝗥 𝗦𝗛𝗘𝗧𝗔𝗡𝗜 𝗞𝗛𝗢𝗣𝗗𝗔 < {target}> 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗔 𝗕𝗛𝗢𝗦𝗗𝗔 🪼⋆｡𖦹°🫧⋆.ೃ࿔*:･",
            "𝗔𝗡𝗧𝗘𝗥 𝗠𝗔𝗡𝗧𝗘𝗥 𝗦𝗛𝗘𝗧𝗔𝗡𝗜 𝗞𝗛𝗢𝗣𝗗𝗔 < {target}> 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗔 𝗕𝗛𝗢𝗦𝗗𝗔 🪼⋆｡𖦹°🫧⋆.ೃ࿔*:･",
            "𝗔𝗡𝗧𝗘𝗥 𝗠𝗔𝗡𝗧𝗘𝗥 𝗦𝗛𝗘𝗧𝗔𝗡𝗜 𝗞𝗛𝗢𝗣𝗗𝗔 < {target}> 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗔 𝗕𝗛𝗢𝗦𝗗𝗔 🪼⋆｡𖦹°🫧⋆.ೃ࿔*:･",
            "𝗔𝗡𝗧𝗘𝗥 𝗠𝗔𝗡𝗧𝗘𝗥 𝗦𝗛𝗘𝗧𝗔𝗡𝗜 𝗞𝗛𝗢𝗣𝗗𝗔 < {target}> 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗔 𝗕𝗛𝗢𝗦𝗗𝗔 🪼⋆｡𖦹°🫧⋆.ೃ࿔*:･",
            "𝗠𝗔𝗜 𝗣𝗜𝗧𝗔 𝗛𝗨𝗡 𝗣𝗔𝗡𝗜 < {target}> 𝗞𝗜 𝗠𝗔𝗔 𝗥𝗔𝗡𝗗𝗜𝗢𝗡 𝗞𝗜 𝗥𝗔𝗡𝗜 ˖°𓇼🌊⋆🐚🫧",
            "𝗠𝗔𝗜 𝗣𝗜𝗧𝗔 𝗛𝗨𝗡 𝗣𝗔𝗡𝗜 < {target}> 𝗞𝗜 𝗠𝗔𝗔 𝗥𝗔𝗡𝗗𝗜𝗢𝗡 𝗞𝗜 𝗥𝗔𝗡𝗜 ˖°𓇼🌊⋆🐚🫧",
            "𝗠𝗔𝗜 𝗣𝗜𝗧𝗔 𝗛𝗨𝗡 𝗣𝗔𝗡𝗜 < {target}> 𝗞𝗜 𝗠𝗔𝗔 𝗥𝗔𝗡𝗗𝗜𝗢𝗡 𝗞𝗜 𝗥𝗔𝗡𝗜 ˖°𓇼🌊⋆🐚🫧",
            "𝗠𝗔𝗜 𝗣𝗜𝗧𝗔 𝗛𝗨𝗡 𝗣𝗔𝗡𝗜 < {target}> 𝗞𝗜 𝗠𝗔𝗔 𝗥𝗔𝗡𝗗𝗜𝗢𝗡 𝗞𝗜 𝗥𝗔𝗡𝗜 ˖°𓇼🌊⋆🐚🫧",
            "< {target} > ----------𝗢𝗬𝗘 𝗧𝗘𝗥𝗜 𝗥𝗔𝗡𝗗𝗜 𝗠𝗔𝗔 𝗞𝗢 𝗛𝗔𝗞𝗟𝗔 𝗞𝗘 𝗖𝗛𝗢𝗗𝗨 ‧₊˚🖇️✩ ₊˚🎧⊹♡",
            "< {target} > ----------𝗢𝗬𝗘 𝗧𝗘𝗥𝗜 𝗥𝗔𝗡𝗗𝗜 𝗠𝗔𝗔 𝗞𝗢 𝗛𝗔𝗞𝗟𝗔 𝗞𝗘 𝗖𝗛𝗢𝗗𝗨 ‧₊˚🖇️✩ ₊˚🎧⊹♡",
            "< {target} > ----------𝗢𝗬𝗘 𝗧𝗘𝗥𝗜 𝗥𝗔𝗡𝗗𝗜 𝗠𝗔𝗔 𝗞𝗢 𝗛𝗔𝗞𝗟𝗔 𝗞𝗘 𝗖𝗛𝗢𝗗𝗨 ‧₊˚🖇️✩ ₊˚🎧⊹♡",
            "< {target} > ----------𝗢𝗬𝗘 𝗧𝗘𝗥𝗜 𝗥𝗔𝗡𝗗𝗜 𝗠𝗔𝗔 𝗞𝗢 𝗛𝗔𝗞𝗟𝗔 𝗞𝗘 𝗖𝗛𝗢𝗗𝗨 ‧₊˚🖇️✩ ₊˚🎧⊹♡",
            "< {target} > -----------  𝗢𝗬𝗘 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗜 𝗖𝗛𝗨𝗧 𝗣𝗘 𝗠𝗢𝗢𝗧 𝗗𝗨𝗡𝗚𝗔 🫧𓇼𓏲*ੈ✩₊˚🎐",
            "< {target} > -----------  𝗢𝗬𝗘 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗜 𝗖𝗛𝗨𝗧 𝗣𝗘 𝗠𝗢𝗢𝗧 𝗗𝗨𝗡𝗚𝗔 🫧𓇼𓏲*ੈ✩₊˚🎐",
            "< {target} > -----------  𝗢𝗬𝗘 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗜 𝗖𝗛𝗨𝗧 𝗣𝗘 𝗠𝗢𝗢𝗧 𝗗𝗨𝗡𝗚𝗔 🫧𓇼𓏲*ੈ✩₊˚🎐",
            "< {target} > -----------  𝗢𝗬𝗘 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗜 𝗖𝗛𝗨𝗧 𝗣𝗘 𝗠𝗢𝗢𝗧 𝗗𝗨𝗡𝗚𝗔 🫧𓇼𓏲*ੈ✩₊˚🎐",
            "𝗔𝗖𝗛𝗔 𝗦𝗨𝗡 𝗧𝗢 < {target}> 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗢 𝗕𝗛𝗔𝗚𝗔 𝗕𝗛𝗔𝗚𝗔 𝗖𝗛𝗢𝗗𝗨 ‧₊˚ ☁️⋅♡🪐༘⋆",
            "𝗔𝗖𝗛𝗔 𝗦𝗨𝗡 𝗧𝗢 < {target}> 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗢 𝗕𝗛𝗔𝗚𝗔 𝗕𝗛𝗔𝗚𝗔 𝗖𝗛𝗢𝗗𝗨 ‧₊˚ ☁️⋅♡🪐༘⋆",
            "𝗔𝗖𝗛𝗔 𝗦𝗨𝗡 𝗧𝗢 < {target}> 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗢 𝗕𝗛𝗔𝗚𝗔 𝗕𝗛𝗔𝗚𝗔 𝗖𝗛𝗢𝗗𝗨 ‧₊˚ ☁️⋅♡🪐༘⋆",
            "𝗔𝗖𝗛𝗔 𝗦𝗨𝗡 𝗧𝗢 < {target}> 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗢 𝗕𝗛𝗔𝗚𝗔 𝗕𝗛𝗔𝗚𝗔 𝗖𝗛𝗢𝗗𝗨 ‧₊˚ ☁️⋅♡🪐༘⋆",
            "< {target} > ---------- 𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗡 𝗞𝗜 𝗧𝗔𝗡𝗚 𝗨𝗧𝗛𝗔 𝗞𝗘 𝗜𝗗𝗛𝗘𝗥 𝗨𝗗𝗛𝗘𝗥 𝗖𝗛𝗢𝗗𝗨𝗡𝗚𝗔 ༘⋆🌷🫧💭₊˚ෆ",
            "< {target} > ---------- 𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗡 𝗞𝗜 𝗧𝗔𝗡𝗚 𝗨𝗧𝗛𝗔 𝗞𝗘 𝗜𝗗𝗛𝗘𝗥 𝗨𝗗𝗛𝗘𝗥 𝗖𝗛𝗢𝗗𝗨𝗡𝗚𝗔 ༘⋆🌷🫧💭₊˚ෆ",
            "< {target} > ---------- 𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗡 𝗞𝗜 𝗧𝗔𝗡𝗚 𝗨𝗧𝗛𝗔 𝗞𝗘 𝗜𝗗𝗛𝗘𝗥 𝗨𝗗𝗛𝗘𝗥 𝗖𝗛𝗢𝗗𝗨𝗡𝗚𝗔 ༘⋆🌷🫧💭₊˚ෆ",
            "< {target} > ---------- 𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗡 𝗞𝗜 𝗧𝗔𝗡𝗚 𝗨𝗧𝗛𝗔 𝗞𝗘 𝗜𝗗𝗛𝗘𝗥 𝗨𝗗𝗛𝗘𝗥 𝗖𝗛𝗢𝗗𝗨𝗡𝗚𝗔 ༘⋆🌷🫧💭₊˚ෆ",
            "< {target} > ----------𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗡 𝗞𝗢 𝗨𝗟𝗧𝗔 𝗞𝗥𝗞𝗘 𝗖𝗢𝗗 𝗗𝗨𝗡𝗚𝗔 𝗛𝗘𝗛𝗘 ✩°𓏲⋆🌿. ⋆⸜ 🍵✮˚",
            "< {target} > ----------𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗡 𝗞𝗢 𝗨𝗟𝗧𝗔 𝗞𝗥𝗞𝗘 𝗖𝗢𝗗 𝗗𝗨𝗡𝗚𝗔 𝗛𝗘𝗛𝗘 ✩°𓏲⋆🌿. ⋆⸜ 🍵✮˚",
            "< {target} > ----------𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗡 𝗞𝗢 𝗨𝗟𝗧𝗔 𝗞𝗥𝗞𝗘 𝗖𝗢𝗗 𝗗𝗨𝗡𝗚𝗔 𝗛𝗘𝗛𝗘 ✩°𓏲⋆🌿. ⋆⸜ 🍵✮˚",
            "< {target} > ----------𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗡 𝗞𝗢 𝗨𝗟𝗧𝗔 𝗞𝗥𝗞𝗘 𝗖𝗢𝗗 𝗗𝗨𝗡𝗚𝗔 𝗛𝗘𝗛𝗘 ✩°𓏲⋆🌿. ⋆⸜ 🍵✮˚",
            "< {target} > -----𝗞𝗨𝗧𝗧𝗜𝗬𝗔 𝗕𝗔𝗡𝗔 𝗞𝗜 𝗖𝗢𝗗𝗨 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗢 🧉❀🐚🐉︎ ࿔*:･ﾟ☾",
            "< {target} > -----𝗞𝗨𝗧𝗧𝗜𝗬𝗔 𝗕𝗔𝗡𝗔 𝗞𝗜 𝗖𝗢𝗗𝗨 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗢 🧉❀🐚🐉︎ ࿔*:･ﾟ☾",
            "< {target} > -----𝗞𝗨𝗧𝗧𝗜𝗬𝗔 𝗕𝗔𝗡𝗔 𝗞𝗜 𝗖𝗢𝗗𝗨 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗢 🧉❀🐚🐉︎ ࿔*:･ﾟ☾",
            "< {target} > -----𝗞𝗨𝗧𝗧𝗜𝗬𝗔 𝗕𝗔𝗡𝗔 𝗞𝗜 𝗖𝗢𝗗𝗨 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗢 🧉❀🐚🐉︎ ࿔*:･ﾟ☾",
            ],
    "Pratik template 2": [
        "< {target} >    Ƭᴇʀɪ Mᴀᴀ Ƙᴀ Ɓʜᴏsᴅᴀ??\n\n< {target} >    Ƭᴇʀɪ Mᴀᴀ Ƙᴀ Ɓʜᴏsᴅᴀ??\n\n< {target} >    Ƭᴇʀɪ Mᴀᴀ Ƙᴀ Ɓʜᴏsᴅᴀ??",
        "< {target} >    Ƈʜᴏᴛᴇ  Լᴀʀᴄᴇ Mᴇʀɪ Ƭᴀᴛᴛɪ Ƙʜᴀ??\n\n< {target} >    Ƈʜᴏᴛᴇ  Լᴀʀᴄᴇ Mᴇʀɪ Ƭᴀᴛᴛɪ Ƙʜᴀ??",
        "< {target} >    Ƭᴇʀɪ Ɓʜᴇɴ Ƈʜᴏᴅ Ɗɪ Ӈᴇʜᴇ!!\n\n< {target} >    Ƭᴇʀɪ Ɓʜᴇɴ Ƈʜᴏᴅ Ɗɪ Ӈᴇʜᴇ!!",
        "< {target} >    Ƭᴇʀɪ Mᴀᴀ 25 Ƥᴀɪsᴇ Mᴇ Ɗᴇɢɪ??\n\n< {target} >    Ƭᴇʀɪ Mᴀᴀ 25 Ƥᴀɪsᴇ Mᴇ Ɗᴇɢɪ??",
        "< {target} >    Ƙɪᴛɴᱟ Ƈʜᴜᴅᴇɢᱟ Ɓʜᱟɢ  ʆᱟ Ƴᱟᱟʀ??\n\n< {target} >    Ƙɪᴛɴᱟ Ƈʜᴜᴅᴇɢᱟ Ɓʜᱟɢ  ʆᱟ Ƴᱟᱟʀ??",
        "Ƥᴀᴛʜᴀʀ Mᴀᴀʀ Ƙᴇ    < {target} >    Ƭᴇʀɪ Mᴀᴀ Ƙᴀ Ɓʜᴏsᴅᴀ Ƒᴀᴅ Ɗᴜɴɢᴀ??",
    ],
    "Pratik template 3": [
        "( {target} )-----------𝑷𝑹 𝑻𝑬𝑹𝑰 𝑴𝑨𝑨 𝑪𝑯𝑼𝑫𝑵𝑬 𝑲𝑰𝑼 𝑳𝑨𝑮 𝑮𝑨𝑰 <🙄🔥>",
        "( {target} )-----------𝑻𝑬𝑹𝑰 𝑲𝑰 𝑪𝑯𝑼𝑻 𝑻𝑶 𝑬𝑲 𝑫𝑨𝑴 𝑴𝑰𝑻𝑯𝑨𝑰 𝑱𝑨𝑰𝑺𝑰 𝑯𝑨𝑰  <✨❄️>",
        "( {target} )-----------𝑶𝑯 𝑵𝑶 𝑨𝑩𝑻𝑶 𝑨𝑷𝑲𝑰 𝑪𝑯𝑼𝑫𝑨𝑰 𝑯𝑶𝑮𝑰 <😊💔>",
        "( {target} )-----------𝑨𝑷 𝑩𝑵𝑫𝑬 𝑻𝑶 𝑨𝑪𝑯𝑬 𝑯𝑶 𝑷𝑹 𝑨𝑷 𝑹𝑨𝑵𝑫𝑰 𝑲𝑬 𝑩𝑨𝑪𝑯𝑬 𝑯𝑶 <😁❤️‍🔥>",
        "( {target} )-----------𝑵𝑰𝑪𝑯𝑬 𝑩𝑬𝑻𝑯𝑲𝑬 𝑷𝑬𝑹 𝑪𝑯𝑼 𝑴𝑬𝑹𝑬 𝑮𝑼𝑳𝑨𝑴 <😎🦶🏻>",
        "( {target} )-----------𝑺𝑯𝑼𝑻 𝑼𝑷 𝑹𝑨𝑵𝑫𝑰 𝑴𝑨𝑨𝑲𝑬 𝑩𝑨𝑪𝑯𝑬 𝑮𝑨𝑹𝑬𝑬𝑩 <😥🖕🏻>",
    ],
    "Pratik template 4": [
        "𝑨𝒏𝒕𝒔 𝑰𝒏 𝒀𝒐𝒖𝒓 𝑨𝒔𝒔🐊⋆｡𖦹°🫧⋆.ೃ࿔*:･ ⏔⏔⏔ ꒰ {target} ꒱ ⏔⏔⏔🐙⋆｡𖦹°🫧⋆.ೃ࿔*:･",
    ],
}


# ---------------------------------------------------------------
# Session storage helpers (persist sessions.json)
# ---------------------------------------------------------------
def _get_fernet():
    if not CRYPTO_AVAILABLE:
        return None
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        try:
            os.chmod(KEY_FILE, 0o600)
        except OSError:
            pass
    return Fernet(key)

def _save_sessions(data: dict):
    f = _get_fernet()
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    if f:
        raw = f.encrypt(raw)
    tmp = SESSION_FILE + ".tmp"
    with open(tmp, "wb") as fp:
        fp.write(raw)
    os.replace(tmp, SESSION_FILE)

def _load_sessions() -> dict:
    if not os.path.exists(SESSION_FILE):
        return {}
    with open(SESSION_FILE, "rb") as fp:
        raw = fp.read()
    f = _get_fernet()
    if f:
        try:
            raw = f.decrypt(raw)
        except Exception:
            log.warning("Could not decrypt sessions.json, starting empty")
            return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------
# Engine
# ---------------------------------------------------------------
class NodeExecutionEngine:
    def __init__(self):
        # node -> {status, engine, sent_count, uptime_start, client}
        self.active_nodes: Dict[str, Dict] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._pending_otp: Dict[str, Dict] = {}  # username -> {client, password}

    # ---------- logging / metrics ----------
    def log_terminal(self, node: str, message: str, level: str = "info"):
        entry = {
            "timestamp": time.strftime("%H:%M:%S"),
            "node": node,
            "message": message,
            "level": level,
        }
        log.info("[%s] %s", node, message)
        socketio.emit('terminal_log', entry)

    def update_metrics(self):
        with self._lock:
            active_count = sum(1 for d in self.active_nodes.values() if d["status"] == "LIVE")
            total_sent = sum(d["sent_count"] for d in self.active_nodes.values())
            logged = len(self.active_nodes)
        socketio.emit('metrics_update', {
            "logged_count": logged,
            "running_count": active_count,
            "total_sent": total_sent,
        })

    # ---------- auth ----------
    def _make_client(self) -> Optional["IGClient"]:
        if not IG_AVAILABLE:
            self.log_terminal("SYSTEM", f"instagrapi unavailable: {IG_IMPORT_ERROR}", "error")
            return None
        return IGClient()

    def _persist_client(self, username: str, client: "IGClient"):
        try:
            data = _load_sessions()
            data[username] = client.get_settings()
            _save_sessions(data)
        except Exception as e:
            log.warning("Could not persist session for %s: %s", username, e)

    def _restore_client(self, username: str) -> Optional["IGClient"]:
        try:
            data = _load_sessions()
            if username in data:
                cl = IGClient()
                cl.set_settings(data[username])
                return cl
        except Exception as e:
            log.warning("Restore failed for %s: %s", username, e)
        return None

    def authenticate_node(
        self,
        node_id: str,
        login_mode: str,
        session_id: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        otp_code: Optional[str] = None,
    ):
        clean_id = (username or node_id or "auth_node").strip().lstrip('@')

        # --- try restoring existing session first ---
        restored = self._restore_client(clean_id)
        if restored is not None and login_mode == "session":
            try:
                restored.get_timeline_feed()  # verify
                self._register(clean_id, restored)
                self.log_terminal(clean_id, "Restored saved session.", "success")
                return "SUCCESS"
            except Exception:
                pass  # fall through to fresh login

        if login_mode == "session":
            cl = self._make_client()
            if cl is None:
                return "ERROR"
            if not session_id:
                self.log_terminal(clean_id, "No sessionid cookie supplied.", "error")
                return "ERROR"
            try:
                cl.login_by_sessionid(session_id.strip())
                self._persist_client(clean_id, cl)
                self._register(clean_id, cl)
                self.log_terminal(clean_id, "Session ID cookie authorized.", "success")
                return "SUCCESS"
            except LoginRequired as e:
                self.log_terminal(clean_id, f"Session invalid: {e}", "error")
                return "ERROR"
            except Exception as e:
                self.log_terminal(clean_id, f"Session login failed: {e}", "error")
                return "ERROR"

        # --- IDP ---
        cl = self._make_client()
        if cl is None:
            return "ERROR"
        if not username or not password:
            self.log_terminal(clean_id, "Missing username/password.", "error")
            return "ERROR"

        if not otp_code:
            try:
                cl.login(clean_id, password)
                self._persist_client(clean_id, cl)
                self._register(clean_id, cl)
                self.log_terminal(clean_id, "IDP login successful (no 2FA).", "success")
                return "SUCCESS"
            except TwoFactorRequired:
                self._pending_otp[clean_id] = {"client": cl, "password": password}
                self.log_terminal(clean_id, "2FA code dispatched.", "warning")
                return "OTP_REQUIRED"
            except ChallengeRequired:
                self.log_terminal(clean_id, "Challenge required — approve on device & retry.", "error")
                return "ERROR"
            except PleaseWaitFewMinutes as e:
                self.log_terminal(clean_id, f"Rate-limited: {e}", "error")
                return "ERROR"
            except ClientError as e:
                self.log_terminal(clean_id, f"Login error: {e}", "error")
                return "ERROR"
            except Exception as e:
                self.log_terminal(clean_id, f"Unexpected login error: {e}", "error")
                return "ERROR"

        # OTP verification
        pending = self._pending_otp.get(clean_id)
        if not pending:
            self.log_terminal(clean_id, "No pending 2FA request — restart login.", "error")
            return "ERROR"
        try:
            pending["client"].login(clean_id, pending["password"], verification_code=otp_code.strip())
            self._persist_client(clean_id, pending["client"])
            self._register(clean_id, pending["client"])
            self._pending_otp.pop(clean_id, None)
            self.log_terminal(clean_id, f"2FA code {otp_code} verified.", "success")
            return "SUCCESS"
        except Exception as e:
            self.log_terminal(clean_id, f"OTP failed: {e}", "error")
            return "ERROR"

    def _register(self, node: str, client: "IGClient"):
        with self._lock:
            if node not in self.active_nodes:
                self.active_nodes[node] = {
                    "status": "STOP",
                    "engine": "STANDBY",
                    "sent_count": 0,
                    "uptime_start": None,
                    "client": client,
                }
            else:
                self.active_nodes[node]["client"] = client
        self.update_metrics()
        socketio.emit('refresh_nodes_list', self.get_matrix_status())

    # ---------- insta API spammer ----------
    def start_insta_api_spammer(self, selected_nodes, target_name, scope="global",
                                 thread_id=None, delay=3.5, template_name="Pratik template 1"):
        for node in selected_nodes:
            self._start_node_task(node, "Insta API Spammer", self._worker_insta_api,
                                  node, target_name, scope, thread_id, delay, template_name)

    def _resolve_thread(self, cl: "IGClient", target_name: str, thread_id: Optional[str]) -> Optional[str]:
        # 1) explicit thread_id
        if thread_id and thread_id.strip():
            return thread_id.strip()
        # 2) search thread by title
        try:
            threads = cl.direct_threads(amount=20)
            for t in threads:
                if getattr(t, "thread_title", None) and target_name.lower() in t.thread_title.lower():
                    return t.id
        except Exception:
            pass
        # 3) search user by username -> open thread
        try:
            uid = cl.user_id_from_username(target_name.lstrip('@'))
            return cl.direct_send("", [uid]).id  # first msg to open thread
        except Exception:
            return None

    def _worker_insta_api(self, node, target, scope, thread_id, delay, template_name, stop_evt):
        cl: Optional["IGClient"] = self.active_nodes.get(node, {}).get("client")
        if cl is None:
            self.log_terminal(node, "No active IG client — login first.", "error")
            return
        messages = MESSAGE_TEMPLATES.get(template_name, MESSAGE_TEMPLATES["Pratik template 1"])
        idx = 0
        resolved_tid = None
        if scope == "single":
            resolved_tid = self._resolve_thread(cl, target, thread_id)
            if not resolved_tid:
                self.log_terminal(node, f"Could not resolve thread for '{target}'.", "error")
                return
        while not stop_evt.is_set():
            raw = messages[idx % len(messages)]
            payload = raw.replace("{target}", target)
            try:
                if scope == "global":
                    tid = self._resolve_thread(cl, target, None)
                    if tid:
                        cl.direct_send(payload, thread_ids=[tid])
                    else:
                        uid = cl.user_id_from_username(target.lstrip('@'))
                        cl.direct_send(payload, [uid])
                    dest = "Global"
                else:
                    cl.direct_send(payload, thread_ids=[resolved_tid])
                    dest = f"Thread:{resolved_tid}"
                self.active_nodes[node]["sent_count"] += 1
                self.update_metrics()
                self.log_terminal(node, f"[{template_name}] Sent -> {dest} | Target: {target}", "success")
            except Exception as e:
                self.log_terminal(node, f"Send failed: {e}", "error")
            idx += 1
            stop_evt.wait(delay)

    # ---------- photo spammer ----------
    def start_photo_spammer(self, selected_nodes, filename, delay=4.0):
        for node in selected_nodes:
            self._start_node_task(node, "Photo Spammer", self._worker_photo_spammer, node, filename, delay)

    def _resolve_local_path(self, filename: str) -> Optional[str]:
        if not filename:
            return None
        p = filename if os.path.isabs(filename) else os.path.join(UPLOAD_DIR, filename)
        return p if os.path.exists(p) else None

    def _worker_photo_spammer(self, node, filename, delay, stop_evt):
        cl = self.active_nodes.get(node, {}).get("client")
        if cl is None:
            self.log_terminal(node, "No active IG client.", "error")
            return
        path = self._resolve_local_path(filename)
        if not path:
            self.log_terminal(node, f"File not found: {filename} (put it in uploads/)", "error")
            return
        while not stop_evt.is_set():
            try:
                cl.direct_send_photo(path)
                self.active_nodes[node]["sent_count"] += 1
                self.update_metrics()
                self.log_terminal(node, f"Photo sent: {os.path.basename(path)}", "success")
            except Exception as e:
                self.log_terminal(node, f"Photo send failed: {e}", "error")
            stop_evt.wait(delay)

    # ---------- GCPFP changer ----------
    def start_gcpfp_changer(self, selected_nodes, filename, delay=5.0):
        for node in selected_nodes:
            self._start_node_task(node, "GCPFP Changer", self._worker_gcpfp_changer, node, filename, delay)

    def _worker_gcpfp_changer(self, node, filename, delay, stop_evt):
        cl = self.active_nodes.get(node, {}).get("client")
        if cl is None:
            self.log_terminal(node, "No active IG client.", "error")
            return
        path = self._resolve_local_path(filename)
        if not path:
            self.log_terminal(node, "Skipped PFP change (no valid file).", "warning")
            return
        while not stop_evt.is_set():
            try:
                threads = cl.direct_threads(amount=10)
                for t in threads:
                    try:
                        cl.direct_thread_update(t.id, profile_pic=path)
                    except Exception:
                        pass
                self.active_nodes[node]["sent_count"] += 1
                self.update_metrics()
                self.log_terminal(node, f"GC PFP updated with {os.path.basename(path)} on {len(threads)} thread(s).", "success")
            except Exception as e:
                self.log_terminal(node, f"GC PFP update failed: {e}", "error")
            stop_evt.wait(delay)

    # ---------- GCNC lock ----------
    def start_gcnc_lock(self, selected_nodes, thread_id, new_title):
        for node in selected_nodes:
            self._start_node_task(node, "GCNC Protection", self._worker_gcnc_lock, node, thread_id, new_title)

    def _worker_gcnc_lock(self, node, thread_id, new_title, stop_evt):
        cl = self.active_nodes.get(node, {}).get("client")
        if cl is None:
            self.log_terminal(node, "No active IG client.", "error")
            return
        if not thread_id:
            self.log_terminal(node, "Missing thread_id.", "error")
            return
        while not stop_evt.is_set():
            try:
                cl.direct_thread_update_title(thread_id.strip(), new_title)
                self.log_terminal(node, f"Enforced GCNC Title '{new_title}' on {thread_id}", "success")
            except Exception as e:
                self.log_terminal(node, f"GCNC update failed: {e}", "error")
            stop_evt.wait(8.0)

    # ---------- GC creator ----------
    def start_gc_creator(self, selected_nodes, prefix, usernames, delay=3.0):
        for node in selected_nodes:
            self._start_node_task(node, "GC Creator Engine", self._worker_gc_creator, node, prefix, usernames, delay)

    def _worker_gc_creator(self, node, prefix, usernames, delay, stop_evt):
        cl = self.active_nodes.get(node, {}).get("client")
        if cl is None:
            self.log_terminal(node, "No active IG client.", "error")
            return
        ids: List[str] = []
        for u in usernames:
            u = u.strip().lstrip('@')
            if not u:
                continue
            try:
                ids.append(cl.user_id_from_username(u))
            except Exception as e:
                self.log_terminal(node, f"Could not resolve @{u}: {e}", "warning")
        if not ids:
            self.log_terminal(node, "No valid usernames to add.", "error")
            return
        count = 1
        while not stop_evt.is_set():
            gc_name = f"{prefix} #{count}"
            try:
                cl.direct_thread_create(ids, title=gc_name)
                self.active_nodes[node]["sent_count"] += 1
                self.update_metrics()
                self.log_terminal(node, f"Created Group '{gc_name}' with {len(ids)} member(s).", "success")
            except Exception as e:
                self.log_terminal(node, f"Group create failed: {e}", "error")
            count += 1
            stop_evt.wait(delay)

    # ---------- Playwright ----------
    def start_playwright_engine(self, selected_nodes, target_url, target_name, delay=3.5):
        for node in selected_nodes:
            self._start_node_task(node, "Playwright Mode", self._worker_playwright, node, target_url, target_name, delay)

    def _worker_playwright(self, node, target_url, target_name, delay, stop_evt):
        if not PW_AVAILABLE:
            self.log_terminal(node, f"Playwright unavailable: {PW_IMPORT_ERROR}", "error")
            return
        if not target_url:
            self.log_terminal(node, "Missing target URL.", "error")
            return
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context()
                page = ctx.new_page()
                page.goto(target_url, timeout=60000)
                while not stop_evt.is_set():
                    try:
                        page.goto(target_url, timeout=60000)
                        page.wait_for_timeout(1000)
                        self.active_nodes[node]["sent_count"] += 1
                        self.update_metrics()
                        self.log_terminal(node, f"Playwright navigated to {target_url} for '{target_name}'", "success")
                    except Exception as e:
                        self.log_terminal(node, f"Playwright cycle error: {e}", "error")
                    stop_evt.wait(delay)
                browser.close()
        except Exception as e:
            self.log_terminal(node, f"Playwright crashed: {e}", "error")

    # ---------- lifecycle ----------
    def _start_node_task(self, node, engine_name, worker_func, *args):
        self.halt_node(node)
        stop_evt = threading.Event()
        with self._lock:
            self._stop_events[node] = stop_evt
            if node not in self.active_nodes:
                self.active_nodes[node] = {
                    "status": "LIVE",
                    "engine": engine_name,
                    "sent_count": 0,
                    "uptime_start": time.time(),
                    "client": None,
                }
            else:
                self.active_nodes[node]["status"] = "LIVE"
                self.active_nodes[node]["engine"] = engine_name
                self.active_nodes[node]["uptime_start"] = time.time()
        t = threading.Thread(target=worker_func, args=(*args, stop_evt), daemon=True)
        t.start()
        self.log_terminal(node, f"Launched engine instance [{engine_name}]", "success")
        self.update_metrics()
        socketio.emit('refresh_nodes_list', self.get_matrix_status())

    def halt_node(self, node):
        evt = self._stop_events.get(node)
        if evt:
            evt.set()
        with self._lock:
            if node in self.active_nodes:
                if self.active_nodes[node]["status"] == "LIVE":
                    self.log_terminal(node, "Halted background engine process.", "error")
                self.active_nodes[node]["status"] = "STOP"
                self.active_nodes[node]["engine"] = "STANDBY"
        self.update_metrics()
        socketio.emit('refresh_nodes_list', self.get_matrix_status())

    def remove_node(self, node):
        self.halt_node(node)
        with self._lock:
            self.active_nodes.pop(node, None)
        self.log_terminal("SYSTEM", f"Node @{node} removed.", "error")
        self.update_metrics()
        socketio.emit('refresh_nodes_list', self.get_matrix_status())

    def get_matrix_status(self) -> List[Dict]:
        with self._lock:
            return [
                {
                    "node": node,
                    "engine": d["engine"],
                    "status": d["status"],
                    "total_dispatched": d["sent_count"],
                }
                for node, d in self.active_nodes.items()
            ]


engine = NodeExecutionEngine()


# ---------------------------------------------------------------
# HTML (UNCHANGED — identical to original)
# ---------------------------------------------------------------
HTML_LAYOUT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ABHIXPRATIK // @Abusivegang Suite</title>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <style>
        :root {
            --bg-base: #0a0101; --panel-bg: #150202; --card-bg: #1f0404; --border-color: #571616;
            --accent-primary: #ff1e1e; --accent-success: #ff4d4d; --accent-warning: #cc0000;
            --accent-danger: #800000; --text-main: #fce8e8; --text-muted: #b88a8a;
        }
        * { box-sizing: border-box; }
        body { background-color: var(--bg-base); color: var(--text-main); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 15px; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; background: var(--panel-bg); border: 1px solid var(--border-color); padding: 12px 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 0 15px rgba(255,30,30,0.15); }
        .header h1 { font-size: 13px; font-weight: 600; color: var(--text-main); margin: 0; letter-spacing: 0.5px; text-shadow: 0 0 5px rgba(255,0,0,0.5); }
        .nav-tabs { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; background: var(--panel-bg); padding: 8px 15px; border-radius: 8px; border: 1px solid var(--border-color); flex-wrap: wrap; gap: 8px; }
        .nav-left { display: flex; gap: 6px; flex-wrap: wrap; }
        .nav-tabs a { background: var(--card-bg); border: 1px solid var(--border-color); color: var(--text-muted); padding: 6px 12px; border-radius: 6px; text-decoration: none; font-size: 11px; font-weight: 500; transition: 0.2s; cursor: pointer; }
        .nav-tabs a:hover { color: var(--text-main); border-color: var(--accent-primary); }
        .nav-tabs a.active { background: var(--accent-primary); color: #0a0101; border-color: var(--accent-primary); font-weight: 700; }
        .btn-logout { background: var(--accent-danger) !important; color: #fff !important; border-color: var(--accent-danger) !important; }
        .stats-bar { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 15px; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; font-size: 11px; font-family: monospace; white-space: nowrap; overflow-x: auto; box-shadow: inset 0 0 10px rgba(255,0,0,0.1); }
        .stat-item { display: flex; align-items: center; gap: 6px; }
        .stat-item span { color: var(--text-muted); }
        .stat-item strong { color: var(--accent-primary); font-weight: 700; }
        .dashboard-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; }
        @media(max-width: 1100px) { .dashboard-grid { grid-template-columns: 1fr; } }
        .card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; box-shadow: 0 4px 15px rgba(255,0,0,0.08); display: flex; flex-direction: column; justify-content: space-between; position: relative; transition: border-color 0.2s; }
        .card:hover { border-color: var(--accent-primary); }
        .card-top-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
        .card-icon-box { width: 38px; height: 38px; background: #0a0101; border: 1px solid var(--border-color); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 16px; color: var(--accent-primary); }
        .badge-tag { background: rgba(255,30,30,0.1); border: 1px solid var(--accent-primary); color: var(--accent-primary); padding: 3px 8px; font-size: 8px; font-weight: 700; border-radius: 20px; text-transform: uppercase; letter-spacing: 0.5px; }
        .card-title { font-size: 14px; font-weight: 700; color: var(--text-main); margin-bottom: 4px; letter-spacing: 0.3px; }
        .card-desc { font-size: 10px; color: var(--text-muted); line-height: 1.3; margin-bottom: 12px; font-family: monospace; }
        .tags-row { display: flex; gap: 5px; margin-bottom: 12px; flex-wrap: wrap; }
        .mini-tag { background: #0a0101; border: 1px solid var(--border-color); color: var(--text-muted); padding: 2px 6px; border-radius: 4px; font-size: 9px; font-family: monospace; }
        .btn { width: 100%; padding: 10px; background: var(--accent-primary); border: none; color: #0a0101; font-weight: 700; border-radius: 6px; cursor: pointer; font-size: 11px; margin-top: 6px; transition: opacity 0.2s; text-transform: uppercase; letter-spacing: 0.5px; }
        .btn:hover { opacity: 0.85; }
        .btn-danger { background: var(--accent-danger); color: #fff; }
        .btn-success { background: var(--accent-success); color: #0a0101; }
        .view-section { display: none; }
        .view-section.active { display: block; }
        .form-group { margin-bottom: 12px; }
        label { display: block; font-size: 10px; font-weight: 500; color: var(--text-muted); margin-bottom: 4px; font-family: monospace; }
        input, select, textarea { width: 100%; padding: 9px 10px; background: #0a0101; border: 1px solid var(--border-color); color: var(--text-main); border-radius: 6px; font-size: 11px; outline: none; transition: border-color 0.2s; }
        input:focus, select:focus, textarea:focus { border-color: var(--accent-primary); box-shadow: 0 0 5px rgba(255,30,30,0.5); }
        .checkbox-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 6px; background: #0a0101; padding: 10px; border-radius: 6px; border: 1px solid var(--border-color); max-height: 130px; overflow-y: auto; }
        .checkbox-item { display: flex; align-items: center; gap: 5px; font-size: 10px; cursor: pointer; color: var(--text-main); font-family: monospace; }
        .node-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 10px; font-family: monospace; }
        .node-table th, .node-table td { border: 1px solid var(--border-color); padding: 8px; text-align: left; }
        .node-table th { background: #0a0101; color: var(--accent-primary); text-transform: uppercase; }
        .status-pill { padding: 2px 6px; border-radius: 10px; font-size: 8px; font-weight: 700; text-transform: uppercase; display: inline-block; }
        .status-live { background: rgba(255,77,77,0.2); border: 1px solid var(--accent-success); color: #ff9999; }
        .status-stop { background: rgba(128,0,0,0.3); border: 1px solid var(--accent-danger); color: #ff8080; }
        .terminal-container { grid-column: span 3; margin-top: 15px; }
        @media(max-width: 1100px) { .terminal-container { grid-column: span 1; } }
        .terminal { background: #0a0101; border: 1px solid var(--border-color); border-radius: 6px; height: 260px; overflow-y: auto; padding: 12px; font-size: 10px; font-family: monospace; display: flex; flex-direction: column-reverse; box-shadow: inset 0 0 10px rgba(255,0,0,0.1); }
        .log-line { margin-bottom: 4px; }
        .success { color: #ff6666; } .error { color: #ff1a1a; font-weight: bold; } .warning { color: #ff9933; } .info { color: #ff4d4d; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>💀 ABHIXPRATIK &mdash; @Abusivegang | Private Console: <span style="color: var(--accent-primary);">ELITE_USER</span></h1>
        <div style="font-size: 11px; color: var(--text-muted); font-family: monospace;">Uptime: <span id="uptime" style="color: var(--accent-primary); font-weight: 600;">0h 0m 0s</span></div>
    </div>
    <div class="stats-bar">
        <div class="stat-item"><span>🛡️ IDs:</span> <strong id="stat-logged-count">0</strong></div>
        <div class="stat-item"><span>⚡ Active:</span> <strong id="stat-running-count">0</strong></div>
        <div class="stat-item"><span>💬 Sent:</span> <strong id="stat-msg-sent">0</strong></div>
    </div>
    <div class="nav-tabs">
        <div class="nav-left">
            <a onclick="switchView('dashboard')" id="nav-dashboard" class="active">Control Hub</a>
            <a onclick="openEngine('nodes')" id="nav-nodes">Nodes List & Status</a>
            <a id="nav-engine-breadcrumb" style="display:none; background: var(--accent-primary); color: #0a0101; font-weight: 700;" class="active">Active Engine Console</a>
        </div>
        <div><a href="#" class="btn-logout">Exit</a></div>
    </div>
    <div id="view-dashboard" class="view-section active">
        <div class="dashboard-grid">
            <div class="card"><div><div class="card-top-header"><div class="card-icon-box">🛡️</div><div class="badge-tag">Auth Vault</div></div><div class="card-title">Managed Accounts</div><div class="card-desc">Dedicated ID login hub via Session ID or IDP credentials with OTP flow.</div><div class="tags-row"><span class="mini-tag">Session ID</span><span class="mini-tag">IDP Login</span><span class="mini-tag">OTP</span></div></div><button class="btn" onclick="openEngine('auth')">LAUNCH ENGINE &rarr;</button></div>
            <div class="card"><div><div class="card-top-header"><div class="card-icon-box">💬</div><div class="badge-tag">Insta API</div></div><div class="card-title">Insta API Spammer</div><div class="card-desc">Multi-node text broadcasting with Templates 1-4 & Global/Single GC routing.</div><div class="tags-row"><span class="mini-tag">Templates 1-4</span><span class="mini-tag">Global/Single</span></div></div><button class="btn btn-success" onclick="openEngine('insta_api')">LAUNCH ENGINE &rarr;</button></div>
            <div class="card"><div><div class="card-top-header"><div class="card-icon-box">🖼️</div><div class="badge-tag">Photo Spm</div></div><div class="card-title">Photo Spammer</div><div class="card-desc">Continuous direct photo blast in Single & Multi GC using uploaded .jpeg payloads.</div><div class="tags-row"><span class="mini-tag">.jpeg Upload</span><span class="mini-tag">Delay</span></div></div><button class="btn" onclick="openEngine('photo')">LAUNCH ENGINE &rarr;</button></div>
            <div class="card"><div><div class="card-top-header"><div class="card-icon-box">📸</div><div class="badge-tag">Gcpfp Chnge</div></div><div class="card-title">GCPFP Profile Changer</div><div class="card-desc">Change group profile picture with .jpeg file upload and custom delay intervals.</div><div class="tags-row"><span class="mini-tag">.jpeg PFP</span><span class="mini-tag">Skip Option</span></div></div><button class="btn" onclick="openEngine('gcpfp')">LAUNCH ENGINE &rarr;</button></div>
            <div class="card"><div><div class="card-top-header"><div class="card-icon-box">✏️</div><div class="badge-tag">Gcnc Chnge</div></div><div class="card-title">GCNC Name Protection</div><div class="card-desc">Secure group title lock and automated name reversion against manual overrides.</div><div class="tags-row"><span class="mini-tag">NC Lock</span><span class="mini-tag">Auto Sync</span></div></div><button class="btn" onclick="openEngine('gcnc')">LAUNCH ENGINE &rarr;</button></div>
            <div class="card"><div><div class="card-top-header"><div class="card-icon-box">➕</div><div class="badge-tag">GC Creator</div></div><div class="card-title">GC Creator Engine</div><div class="card-desc">Mass sequential group creation adding multiple comma-separated usernames with delay.</div><div class="tags-row"><span class="mini-tag">Comma Users</span><span class="mini-tag">Delay</span></div></div><button class="btn" onclick="openEngine('gc_creator')">LAUNCH ENGINE &rarr;</button></div>
            <div class="card"><div><div class="card-top-header"><div class="card-icon-box">⚡</div><div class="badge-tag">Playwright</div></div><div class="card-title">Playwright Automation</div><div class="card-desc">Select account pool quantities and launch browser automated spam routines.</div><div class="tags-row"><span class="mini-tag">Account Select</span><span class="mini-tag">URL Target</span></div></div><button class="btn" onclick="openEngine('playwright')">LAUNCH ENGINE &rarr;</button></div>
        </div>
    </div>
    <div id="view-engine" class="view-section">
        <div style="background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 20px; margin-bottom: 15px;">
            <div class="card-header" id="engine-page-title" style="margin-bottom: 15px; font-size: 13px; color: var(--accent-primary); font-family: monospace;"></div>
            <form id="engine-active-form">
                <div id="account-selector-wrapper" class="form-group" style="background: #0a0101; padding: 12px; border-radius: 6px; border: 1px solid var(--border-color); margin-bottom: 15px;">
                    <label style="color: var(--accent-primary); font-weight: 700; margin-bottom: 8px; font-size: 11px;">Select Logged-In Accounts / Nodes from Panel</label>
                    <div id="dynamic-nodes-checkboxes" class="checkbox-grid"><span style="font-size:10px; color:var(--text-muted);">No accounts logged in yet. Use Managed Accounts vault to login.</span></div>
                </div>
                <div id="engine-form-content"></div>
                <div id="execution-buttons-wrapper" style="display: flex; gap: 8px; margin-top: 15px;">
                    <button type="button" class="btn btn-success" style="flex: 2;" onclick="triggerEngineAction('start')">▶ START</button>
                    <button type="button" class="btn btn-danger" style="flex: 1;" onclick="triggerEngineAction('halt')">⏹ HALT</button>
                    <button type="button" class="btn" style="background: var(--panel-bg); color: var(--text-main); border: 1px solid var(--border-color); flex: 1;" onclick="switchView('dashboard')">BACK</button>
                </div>
            </form>
        </div>
    </div>
    <div class="card terminal-container">
        <div class="card-header" style="color: var(--accent-primary);">💀 Private Terminal Console & Telemetry (Encrypted & Isolated)</div>
        <div id="terminal" class="terminal"><div class="log-line info">[ABUSIVEGANG] Secure haunted console active. Ready for input.</div></div>
    </div>
</div>
<script>
    const socket = io();
    let currentEngine = '';
    socket.on('terminal_log', function(data) {
        const terminal = document.getElementById('terminal');
        const line = document.createElement('div');
        line.className = `log-line ${data.level}`;
        line.innerText = `[${data.timestamp}] [${data.node}] ${data.message}`;
        terminal.prepend(line);
    });
    socket.on('metrics_update', function(data) {
        document.getElementById('stat-logged-count').innerText = data.logged_count;
        document.getElementById('stat-running-count').innerText = data.running_count;
        document.getElementById('stat-msg-sent').innerText = data.total_sent;
    });
    socket.on('refresh_nodes_list', function(nodes) {
        const container = document.getElementById('dynamic-nodes-checkboxes');
        if(nodes.length === 0) { container.innerHTML = '<span style="font-size:10px; color:var(--text-muted);">No accounts logged in yet. Use Managed Accounts vault.</span>'; return; }
        let html = '';
        nodes.forEach(n => { html += `<label class="checkbox-item"><input type="checkbox" name="node_select" value="${n.node}" checked> @${n.node}</label>`; });
        container.innerHTML = html;
        window.currentNodesData = nodes;
    });
    function switchView(viewName) {
        document.getElementById('view-dashboard').classList.remove('active');
        document.getElementById('view-engine').classList.remove('active');
        document.getElementById('nav-dashboard').classList.remove('active');
        document.getElementById('nav-nodes').classList.remove('active');
        document.getElementById('nav-engine-breadcrumb').style.display = 'none';
        if(viewName === 'dashboard') { document.getElementById('view-dashboard').classList.add('active'); document.getElementById('nav-dashboard').classList.add('active'); }
        else if(viewName === 'engine') { document.getElementById('view-engine').classList.add('active'); document.getElementById('nav-engine-breadcrumb').style.display = 'inline-block'; }
        window.scrollTo(0, 0);
    }
    function openEngine(engineType) {
        currentEngine = engineType;
        let titleEl = document.getElementById('engine-page-title');
        let contentEl = document.getElementById('engine-form-content');
        let accSelectorWrapper = document.getElementById('account-selector-wrapper');
        let execButtonsWrapper = document.getElementById('execution-buttons-wrapper');
        let html = '';
        if(engineType === 'nodes') {
            titleEl.innerText = "📋 Active Logged-In Nodes List & Status Matrix";
            accSelectorWrapper.style.display = 'none';
            execButtonsWrapper.style.display = 'none';
            let rows = '';
            if(!window.currentNodesData || window.currentNodesData.length === 0) { rows = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">No active nodes found.</td></tr>'; }
            else { window.currentNodesData.forEach(n => { let pillClass = n.status === 'LIVE' ? 'status-live' : 'status-stop'; rows += `<tr><td>@${n.node}</td><td style="color:#ff6666;">${n.engine}</td><td><span class="status-pill ${pillClass}">${n.status}</span></td><td>Active</td><td>${n.total_dispatched} Total</td><td><button class="btn btn-danger" style="padding:3px 6px; font-size:9px; margin:0;" onclick="removeNode('${n.node}')">Remove</button></td></tr>`; }); }
            html = `<div style="overflow-x:auto;"><table class="node-table"><thead><tr><th>Username</th><th>Engine</th><th>Status</th><th>Uptime</th><th>Total</th><th>Action</th></tr></thead><tbody>${rows}</tbody></table></div><div style="margin-top:15px;"><button type="button" class="btn" style="background: var(--panel-bg); color: var(--text-main); border: 1px solid var(--border-color);" onclick="switchView('dashboard')">RETURN TO HUB</button></div>`;
            document.getElementById('nav-nodes').classList.add('active');
            document.getElementById('view-engine').classList.add('active');
            document.getElementById('view-dashboard').classList.remove('active');
            contentEl.innerHTML = html;
            window.scrollTo(0, 0);
            return;
        }
        if(engineType === 'auth') {
            titleEl.innerText = "🛡️ Managed Accounts & IDP Verification Vault";
            accSelectorWrapper.style.display = 'none';
            execButtonsWrapper.style.display = 'none';
            html = `<div class="form-group"><label>Login Method</label><select id="loginModeSelect" onchange="toggleLoginMode()"><option value="session">Session ID Cookie String</option><option value="idp">IDP Login (Username & Password + OTP)</option></select></div>
                <div id="sessionFieldGroup" class="form-group"><label>Instagram Username / Node Handle</label><input type="text" id="sessUser" placeholder="e.g. my_account"><label style="margin-top:6px;">Session ID Cookie String</label><input type="text" id="sessString" placeholder="Paste sessionid cookie..."><button type="button" class="btn" style="margin-top:8px;" onclick="submitAuth('session')">Authorize Session Node</button></div>
                <div id="idpFieldGroup" style="display:none;"><div class="form-group"><label>Instagram Username / Email / Phone</label><input type="text" id="idpUser" placeholder="Enter username..."></div><div class="form-group"><label>Password</label><input type="password" id="idpPass" placeholder="Enter password..."></div><div id="otpBoxContainer" class="form-group" style="display:none; background:#0a0101; padding:10px; border:1px solid var(--accent-warning); border-radius:6px; margin-top:8px;"><label style="color:var(--accent-warning);">Enter OTP / 2FA Code received</label><input type="text" id="idpOtp" placeholder="6-digit code..." style="margin-top:4px;"></div><div style="display: flex; gap: 8px; margin-top: 12px;"><button type="button" class="btn" style="flex:1;" onclick="submitAuth('idp_step1')">1. Request Code</button><button type="button" class="btn btn-success" style="flex:1;" onclick="submitAuth('idp_step2')">2. Verify & Login</button></div></div>
                <div style="margin-top:15px;"><button type="button" class="btn" style="background: var(--panel-bg); color: var(--text-main); border: 1px solid var(--border-color);" onclick="switchView('dashboard')">RETURN TO HUB</button></div>`;
        } else {
            accSelectorWrapper.style.display = 'block';
            execButtonsWrapper.style.display = 'flex';
            if(engineType === 'insta_api') {
                titleEl.innerText = "💬 Insta API Spammer (Templates 1-4 & Global/Single GC)";
                html = `<div class="form-group"><label>Select Message Template</label><select id="templateSelect"><option value="Pratik template 1">Pratik template 1</option><option value="Pratik template 2">Pratik template 2</option><option value="Pratik template 3">Pratik template 3</option><option value="Pratik template 4">Pratik template 4</option></select></div>
                    <div class="form-group"><label>Routing Scope</label><select id="apiScopeSelect" onchange="toggleApiScope()"><option value="global">Global Mode (All GCs - No Thread ID required)</option><option value="single">Isolated Single Channel (Requires Thread ID & Delay)</option></select></div>
                    <div class="form-group"><label>Primary Target Name / Identity</label><input type="text" id="targetName" placeholder="Target Name..." required></div>
                    <div id="singleGcFields" style="display:none;"><div class="form-group"><label>Target Group ID / Thread Link</label><input type="text" id="threadId" placeholder="Thread ID..."></div><div class="form-group"><label>Execution Delay (Seconds)</label><input type="number" id="apiDelay" step="any" value="3.5" min="2.0"></div></div>`;
            } else if(engineType === 'photo') {
                titleEl.innerText = "🖼️ Photo Spammer (.jpeg direct blast)";
                html = `<div class="form-group"><label>Filename / .jpeg Image Payload (must exist in uploads/)</label><input type="text" id="photoFilename" value="payload_image.jpeg" required></div><div class="form-group"><label>Delay (Seconds)</label><input type="number" id="photoDelay" step="any" value="4.0" min="2.0" required></div>`;
            } else if(engineType === 'gcpfp') {
                titleEl.innerText = "📸 GCPFP Profile Picture Changer";
                html = `<div class="form-group"><label>Filename / .jpeg Image (Leave empty to skip)</label><input type="text" id="pfpFilename" value="group_icon.jpeg"></div><div class="form-group"><label>Interval / Delay (Seconds)</label><input type="number" id="pfpDelay" value="5" min="2"></div>`;
            } else if(engineType === 'gcnc') {
                titleEl.innerText = "✏️ GCNC Group Name Protection & NC Lock";
                html = `<div class="form-group"><label>Target Group ID / Thread Link</label><input type="text" id="gcncThread" placeholder="Thread ID..." required></div><div class="form-group"><label>New Secured Group Title (GCNC)</label><input type="text" id="gcncTitle" placeholder="Enter title..." required></div>`;
            } else if(engineType === 'gc_creator') {
                titleEl.innerText = "➕ Mass GC Creator Engine";
                html = `<div class="form-group"><label>Deployment Prefix</label><input type="text" id="gcPrefix" placeholder="Raid Group..." required></div><div class="form-group"><label>Usernames to Add (Comma Separated)</label><input type="text" id="gcUsernames" placeholder="user1, user2, user3..." required></div><div class="form-group"><label>Creation Delay Interval (Seconds)</label><input type="number" id="gcDelay" step="any" value="3.0" min="1.0" required></div>`;
            } else if(engineType === 'playwright') {
                titleEl.innerText = "⚡ Playwright Automation Engine";
                html = `<div class="form-group"><label>Target Group URL / Thread Link</label><input type="text" id="pwUrl" placeholder="https://instagram.com/direct/t/..." required></div><div class="form-group"><label>Target Name Placeholder</label><input type="text" id="pwName" placeholder="Target Name" required></div><div class="form-group"><label>Execution Delay (Seconds)</label><input type="number" id="pwDelay" step="any" value="3.5" min="2.0" required></div>`;
            }
        }
        contentEl.innerHTML = html;
        switchView('engine');
    }
    function toggleLoginMode() { let mode = document.getElementById('loginModeSelect').value; if(mode === 'session') { document.getElementById('sessionFieldGroup').style.display = 'block'; document.getElementById('idpFieldGroup').style.display = 'none'; } else { document.getElementById('sessionFieldGroup').style.display = 'none'; document.getElementById('idpFieldGroup').style.display = 'block'; } }
    function toggleApiScope() { let scope = document.getElementById('apiScopeSelect').value; if(scope === 'single') { document.getElementById('singleGcFields').style.display = 'block'; } else { document.getElementById('singleGcFields').style.display = 'none'; } }
    function getSelectedNodes() { let nodes = []; document.querySelectorAll('input[name="node_select"]:checked').forEach(el => { nodes.push(el.value); }); return nodes; }
    function submitAuth(mode) {
        let payload = {};
        if(mode === 'session') { payload = { login_mode: 'session', node_id: document.getElementById('sessUser').value || 'node_user', session_id: document.getElementById('sessString').value }; }
        else if(mode === 'idp_step1' || mode === 'idp_step2') { payload = { login_mode: 'idp', username: document.getElementById('idpUser').value, password: document.getElementById('idpPass').value, otp_code: mode === 'idp_step2' ? document.getElementById('idpOtp').value : null }; if(mode === 'idp_step1') { document.getElementById('otpBoxContainer').style.display = 'block'; } }
        fetch('/api/auth_node', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) })
        .then(res => res.json()).then(data => {
            if(data.status === 'OTP_REQUIRED') { alert('2FA Code requested. Please enter OTP.'); }
            else if(data.status === 'SUCCESS') { alert('Account logged in and saved to panel matrix!'); switchView('dashboard'); }
            else { alert('Login failed. Check terminal for details.'); }
        });
    }
    function triggerEngineAction(action) {
        let nodes = getSelectedNodes();
        if(nodes.length === 0 && action === 'start') { alert('Please select at least one logged-in account node!'); return; }
        let payload = {action: action, engine: currentEngine, nodes: nodes};
        if(action === 'start') {
            if(currentEngine === 'insta_api') { payload.template_name = document.getElementById('templateSelect').value; payload.scope = document.getElementById('apiScopeSelect').value; payload.target_name = document.getElementById('targetName').value; payload.thread_id = document.getElementById('threadId') ? document.getElementById('threadId').value : null; payload.delay = document.getElementById('apiDelay') ? parseFloat(document.getElementById('apiDelay').value) : 3.5; }
            else if(currentEngine === 'photo') { payload.filename = document.getElementById('photoFilename').value; payload.delay = parseFloat(document.getElementById('photoDelay').value); }
            else if(currentEngine === 'gcpfp') { payload.filename = document.getElementById('pfpFilename').value; payload.delay = parseFloat(document.getElementById('pfpDelay').value); }
            else if(currentEngine === 'gcnc') { payload.thread_id = document.getElementById('gcncThread').value; payload.new_title = document.getElementById('gcncTitle').value; }
            else if(currentEngine === 'gc_creator') { payload.prefix = document.getElementById('gcPrefix').value; payload.usernames = document.getElementById('gcUsernames').value.split(',').map(s => s.trim()); payload.delay = parseFloat(document.getElementById('gcDelay').value); }
            else if(currentEngine === 'playwright') { payload.target_url = document.getElementById('pwUrl').value; payload.target_name = document.getElementById('pwName').value; payload.delay = parseFloat(document.getElementById('pwDelay').value); }
        }
        fetch('/api/run_engine', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) })
        .then(res => res.json()).then(data => { alert(data.message); });
    }
    function removeNode(nodeName) { fetch('/api/remove_node', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({node: nodeName}) }).then(res => res.json()).then(data => { openEngine('nodes'); }); }
    let startTime = Math.floor(Date.now() / 1000);
    function updateUptime() { let now = Math.floor(Date.now() / 1000); let diff = now - startTime; let h = Math.floor(diff / 3600); let m = Math.floor((diff % 3600) / 60); let s = diff % 60; document.getElementById('uptime').innerText = h + "h " + m + "m " + s + "s"; }
    setInterval(updateUptime, 1000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------
# Routes
# ---------------------------------------------------------------
@app.route('/')
def index():
    return render_template_string(HTML_LAYOUT)


@app.route('/api/auth_node', methods=['POST'])
def api_auth_node():
    data = request.json or {}
    try:
        status = engine.authenticate_node(
            node_id=data.get('node_id'),
            login_mode=data.get('login_mode'),
            session_id=data.get('session_id'),
            username=data.get('username'),
            password=data.get('password'),
            otp_code=data.get('otp_code'),
        )
    except Exception as e:
        log.exception("auth_node crashed")
        engine.log_terminal("SYSTEM", f"Auth error: {e}", "error")
        status = "ERROR"
    return jsonify({"status": status})


@app.route('/api/remove_node', methods=['POST'])
def api_remove_node():
    data = request.json or {}
    engine.remove_node(data.get('node'))
    return jsonify({"status": "success"})


@app.route('/api/upload', methods=['POST'])
def api_upload():
    """Optional endpoint — lets you push a real .jpeg into uploads/ without touching HTML."""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "no file field"}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({"status": "error", "message": "empty filename"}), 400
    safe = os.path.basename(f.filename)
    dest = os.path.join(UPLOAD_DIR, safe)
    f.save(dest)
    return jsonify({"status": "success", "filename": safe, "path": dest})


@app.route('/api/run_engine', methods=['POST'])
def api_run_engine():
    data = request.json or {}
    action = data.get('action')
    engine_type = data.get('engine')
    nodes = data.get('nodes', []) or []

    if action == 'halt':
        targets = nodes if nodes else list(engine.active_nodes.keys())
        for node in targets:
            engine.halt_node(node)
        return jsonify({"message": f"Halted {len(targets)} node(s)." if targets else "No nodes to halt."})

    if action == 'start':
        if not nodes:
            return jsonify({"message": "No nodes selected."})

        if engine_type == 'insta_api':
            engine.start_insta_api_spammer(
                selected_nodes=nodes,
                target_name=data.get('target_name') or '',
                scope=data.get('scope', 'global'),
                thread_id=data.get('thread_id'),
                delay=float(data.get('delay', 3.5) or 3.5),
                template_name=data.get('template_name', 'Pratik template 1'),
            )
        elif engine_type == 'photo':
            engine.start_photo_spammer(nodes, data.get('filename'), float(data.get('delay', 4.0) or 4.0))
        elif engine_type == 'gcpfp':
            engine.start_gcpfp_changer(nodes, data.get('filename'), float(data.get('delay', 5.0) or 5.0))
        elif engine_type == 'gcnc':
            engine.start_gcnc_lock(nodes, data.get('thread_id') or '', data.get('new_title') or '')
        elif engine_type == 'gc_creator':
            engine.start_gc_creator(nodes, data.get('prefix') or '',
                                    data.get('usernames') or [], float(data.get('delay', 3.0) or 3.0))
        elif engine_type == 'playwright':
            engine.start_playwright_engine(nodes, data.get('target_url') or '',
                                           data.get('target_name') or '', float(data.get('delay', 3.5) or 3.5))
        else:
            return jsonify({"message": f"Unknown engine: {engine_type}"})

        return jsonify({"message": f"Engine [{engine_type}] started on {len(nodes)} node(s)."})

    return jsonify({"message": "Unknown command"})


if __name__ == '__main__':
    host = os.environ.get('PANEL_HOST', '0.0.0.0')
    port = int(os.environ.get('PANEL_PORT', '5000'))
    debug = os.environ.get('PANEL_DEBUG', '0') == '1'
    log.info("Starting panel on %s:%s (debug=%s)", host, port, debug)
    socketio.run(app, host=host, port=port, debug=debug, use_reloader=False)
