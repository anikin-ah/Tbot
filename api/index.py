import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID_1 = int(os.environ["CHANNEL_ID_1"])
CHANNEL_ID_2 = int(os.environ["CHANNEL_ID_2"])

BOT_USERNAME = "smartanikin_bot"            # ← replace, without @
CHANNEL_1_LINK = "https://t.me/aakashio"  # ← replace
CHANNEL_2_LINK = "https://t.me/+Auw6rKRx3Q1lZmE1"  # ← replace
CHANNEL_1_NAME = "The Legend of Hei 1 & 2"
CHANNEL_2_NAME = "Anime"

BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Each file has a name, file_id, and an emoji icon
FILE_INDEX = {
    "wallpaper": {
        "label": "🖼 Wallpaper (@wallandiadesk)",
        "file_id": "BQACAgUAAyEFAAThvr8XAAMUae80odT4KXW_OImhRMsHwteK0U8AAj0hAALOnHlXjqQUCa-SuPE7BA"
    },
    "hei1": {
        "label": "🎬 The Legend of Hei (ENG)",
        "file_id": "BQACAgUAAyEFAAThvr8XAAMVae9z3sQ3l65QsNFQaxI8ZRfQBikAAi4bAAJZXQABVeRKzDZn-DjVOwQ"
    },
    "hei2": {
        "label": "🎬 The Legend of Hei 2",
        "file_id": "BQACAgUAAyEFAAThvr8XAAMWae9z3uLu4p_GkzGMgI65tcvL7Z4AApkcAALSjdBWPYB_jbO8zDg7BA"
    },
    "demonslayer": {
        "label": "⚔️ Demon Slayer — Infinity Castle",
        "file_id": "BQACAgUAAyEFAAThvr8XAAMXae90At3iRcrujkcyFaPTdMIOPx0AArUVAAKBtJFV9YH_ATbu0JY7BA"
    },
    "nezha2": {
        "label": "🐉 Ne Zha 2 (2025)",
        "file_id": "BAACAgQAAyEFAAThvr8XAAMYae90AqK4rkwIeHq9iNx5ItyfEFwAAgosAAJ-S2FQ9D12m24upo87BA"
    },
    "rezearc": {
        "label": "💥 Reze Arc",
        "file_id": "BQACAgUAAyEFAAThvr8XAAMZae90ApJeOchui0MHMwE1dqH6SPcAArcVAAKBtJFV_tkYjPzwuIk7BA"
    }
}

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
    for key, info in FILE_INDEX.items():
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

    if not chat_id or not text or not user_id:
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
        info = FILE_INDEX.get(keyword)
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

# ── Callback handler ──────────────────────────────────────────────────────────

def handle_callback(callback_query):
    query_id = callback_query["id"]
    user_id = callback_query["from"]["id"]
    chat_id = callback_query["message"]["chat"]["id"]
    data = callback_query.get("data", "")

    # File button tapped
    if data.startswith("get:"):
        key = data[4:]
        info = FILE_INDEX.get(key)

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
