import os
import requests
from flask import Flask, request, jsonify

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db

app = Flask(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID_1 = int(os.environ["CHANNEL_ID_1"])
CHANNEL_ID_2 = int(os.environ["CHANNEL_ID_2"])
ADMIN_ID = int(os.environ["ADMIN_ID"])  # your Telegram user id — for /addfile & /delfile

BOT_USERNAME = "smartanikin_bot"            # ← replace, without @
CHANNEL_1_LINK = "https://t.me/aakashio"  # ← replace
CHANNEL_2_LINK = "https://t.me/+Auw6rKRx3Q1lZmE1"  # ← replace
CHANNEL_1_NAME = "Videoes"
CHANNEL_2_NAME = "Wallpaper"

BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# File index now lives in Turso (see db.py) instead of a hardcoded dict.
db.init_db()

# ── Telegram API helpers ──────────────────────────────────────────────────────

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    r = requests.post(f"{BASE}/sendMessage", json=payload)
    if not r.json().get("ok"):
        print(f"[ERROR] sendMessage → {r.json()}")
    return r.json().get("ok", False)

def send_document(chat_id, file_id, caption=None):
    payload = {"chat_id": chat_id, "document": file_id}
    if caption:
        payload["caption"] = caption
        payload["parse_mode"] = "HTML"
    r = requests.post(f"{BASE}/sendDocument", json=payload)
    if not r.json().get("ok"):
        print(f"[ERROR] sendDocument → {r.json()}")
    return r.json().get("ok", False)

def answer_callback(query_id, text=None, show_alert=False):
    requests.post(f"{BASE}/answerCallbackQuery", json={
        "callback_query_id": query_id,
        "text": text or "",
        "show_alert": show_alert
    })

def get_member_status(channel_id, user_id):
    r = requests.get(f"{BASE}/getChatMember", params={
        "chat_id": channel_id,
        "user_id": user_id
    }).json()
    print(f"[DEBUG] getChatMember → channel={channel_id} user={user_id} → {r}")
    if not r.get("ok"):
        return "left"
    return r.get("result", {}).get("status", "left")

# ── Membership helpers ────────────────────────────────────────────────────────

def check_membership(user_id):
    allowed = ("member", "administrator", "creator")
    in_ch1 = get_member_status(CHANNEL_ID_1, user_id) in allowed
    in_ch2 = get_member_status(CHANNEL_ID_2, user_id) in allowed
    return in_ch1, in_ch2

def build_join_prompt(in_ch1, in_ch2):
    missing = []
    buttons = []
    if not in_ch1:
        missing.append(f"• <b>{CHANNEL_1_NAME}</b>")
        buttons.append([{"text": f"➕ Join {CHANNEL_1_NAME}", "url": CHANNEL_1_LINK}])
    if not in_ch2:
        missing.append(f"• <b>{CHANNEL_2_NAME}</b>")
        buttons.append([{"text": f"➕ Join {CHANNEL_2_NAME}", "url": CHANNEL_2_LINK}])
    buttons.append([{
        "text": "✅ I've joined — verify me",
        "url": f"https://t.me/{BOT_USERNAME}?start=verify"
    }])
    text = (
        "⛔ <b>Access denied.</b>\n\n"
        "You need to join the following channel(s) first:\n"
        + "\n".join(missing) +
        "\n\n<b>Steps:</b>\n"
        "1️⃣ Click the join button(s) above\n"
        "2️⃣ Tap <b>Verify me</b>\n"
        "3️⃣ Press <b>Start</b> in the bot\n"
        "4️⃣ You'll get access automatically ✅"
    )
    return text, {"inline_keyboard": buttons}

# ── File list as inline buttons ───────────────────────────────────────────────

def build_file_list_buttons():
    """Each file gets its own button row. Tapping sends the file."""
    buttons = []
    for key, info in db.list_files().items():
        buttons.append([{
            "text": info["label"],
            "callback_data": f"get:{key}"
        }])
    return {
        "inline_keyboard": buttons
    }

# ── Webhook handler ───────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    # ── Callback from inline buttons ──
    if "callback_query" in data:
        handle_callback(data["callback_query"])
        return jsonify(ok=True)

    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    username = message.get("from", {}).get("first_name", "there")
    text = (message.get("text") or "").strip()

    if not chat_id or not user_id:
        return jsonify(ok=True)

    # ── Admin file-management commands (work even without a text command,
    #    since /addfile is typically sent as a reply to a document) ──
    if user_id == ADMIN_ID and text.lower().startswith(("/addfile", "/delfile", "/files")):
        handle_admin_command(message, chat_id, text)
        return jsonify(ok=True)

    if not text:
        return jsonify(ok=True)

    text_lower = text.lower()

    # /start
    if text_lower == "/start" or text_lower.startswith("/start "):
        param = text.split(" ")[1] if " " in text else ""
        in_ch1, in_ch2 = check_membership(user_id)
        if in_ch1 and in_ch2:
            send_message(chat_id,
                f"👋 Welcome, <b>{username}</b>!\n\n"
                "Tap a file below to receive it in your DM.",
                reply_markup=build_file_list_buttons()
            )
        else:
            if param == "verify":
                prompt, markup = build_join_prompt(in_ch1, in_ch2)
                send_message(chat_id,
                    "⚠️ <b>Still not verified.</b>\n\n"
                    "Make sure you joined the channel(s), then tap verify again.",
                    reply_markup=markup
                )
            else:
                prompt, markup = build_join_prompt(in_ch1, in_ch2)
                send_message(chat_id, prompt, reply_markup=markup)
        return jsonify(ok=True)

    # Check membership for all other commands
    in_ch1, in_ch2 = check_membership(user_id)
    if not (in_ch1 and in_ch2):
        prompt, markup = build_join_prompt(in_ch1, in_ch2)
        send_message(chat_id, prompt, reply_markup=markup)
        return jsonify(ok=True)

    # /list — show file buttons
    if text_lower == "/list":
        send_message(chat_id,
            "📂 <b>Available files</b> — tap one to receive it:",
            reply_markup=build_file_list_buttons()
        )

    # /get <key> — still supported as text command too
    elif text_lower.startswith("/get "):
        keyword = text[5:].strip().lower()
        info = db.get_file(keyword)
        if not info:
            send_message(chat_id,
                f"❌ No file found for '<code>{keyword}</code>'.\n\n"
                "Use /list to browse available files."
            )
        else:
            send_message(chat_id, f"📤 Sending <b>{info['label']}</b>...")
            send_document(chat_id, info["file_id"], caption=f"<b>{info['label']}</b>")

    else:
        send_message(chat_id,
            "🤖 <b>Commands:</b>\n"
            "/list — browse all files\n"
            "/get &lt;name&gt; — receive a specific file"
        )

    return jsonify(ok=True)

# ── Admin: manage the file index without touching code ───────────────────────

def handle_admin_command(message, chat_id, text):
    """
    /addfile <key> | <label>   — send as a REPLY to a document message;
                                  the file_id is pulled from the replied-to document.
    /delfile <key>             — remove an entry.
    /files                     — list raw entries (key, label, file_id) for debugging.
    """
    text_lower = text.lower()

    if text_lower.startswith("/addfile"):
        reply = message.get("reply_to_message", {})
        document = reply.get("document")
        if not document:
            send_message(chat_id,
                "⚠️ Send <code>/addfile key | Label text</code> as a <b>reply</b> "
                "to the document you want to register."
            )
            return

        payload = text.split(" ", 1)[1].strip() if " " in text else ""
        if "|" not in payload:
            send_message(chat_id, "⚠️ Format: <code>/addfile key | Label text</code>")
            return

        key, label = (part.strip() for part in payload.split("|", 1))
        key = key.lower()
        if not key or not label:
            send_message(chat_id, "⚠️ Both key and label are required.")
            return

        db.add_file(key, label, document["file_id"])
        send_message(chat_id, f"✅ Saved <b>{key}</b> → {label}")

    elif text_lower.startswith("/delfile"):
        parts = text.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            send_message(chat_id, "⚠️ Format: <code>/delfile key</code>")
            return
        key = parts[1].strip().lower()
        if db.remove_file(key):
            send_message(chat_id, f"🗑 Removed <b>{key}</b>.")
        else:
            send_message(chat_id, f"❌ No entry found for '<code>{key}</code>'.")

    elif text_lower.startswith("/files"):
        files = db.list_files()
        if not files:
            send_message(chat_id, "No files stored yet.")
            return
        lines = [
            f"• <code>{key}</code> — {info['label']}\n  <code>{info['file_id']}</code>"
            for key, info in files.items()
        ]
        send_message(chat_id, "📋 <b>Stored files:</b>\n\n" + "\n\n".join(lines))

# ── Callback handler ──────────────────────────────────────────────────────────

def handle_callback(callback_query):
    print(f"[DEBUG] Callback received: {callback_query}")
    query_id = callback_query["id"]
    user_id = callback_query["from"]["id"]
    chat_id = callback_query["message"]["chat"]["id"]
    data = callback_query.get("data", "")

    # File button tapped
    if data.startswith("get:"):
        key = data[4:]
        info = db.get_file(key)

        if not info:
            answer_callback(query_id, "File not found.", show_alert=True)
            return

        # Re-check membership before sending
        in_ch1, in_ch2 = check_membership(user_id)
        if not (in_ch1 and in_ch2):
            answer_callback(query_id, "⛔ Access denied. Join both channels first.", show_alert=True)
            return

        answer_callback(query_id, f"Sending {info['label']}...")
        success = send_document(chat_id, info["file_id"],
                                caption=f"<b>{info['label']}</b>")
        if not success:
            send_message(chat_id, "⚠️ Failed to send file. Please try again.")