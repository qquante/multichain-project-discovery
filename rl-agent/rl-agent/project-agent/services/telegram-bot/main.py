"""
Telegram Bot Receiver
Handles /add flow, favorite, and stop track callbacks.
"""

import os
import sys
import time
import json
import requests
from datetime import datetime
from typing import Dict, Any

sys.path.insert(0, '/app/shared')
sys.path.insert(0, '/app')

from agent.database import (
    init_db,
    add_project_favorite,
    get_project_favorites,
    stop_monitoring_by_handle,
    upsert_add_request,
    get_add_request,
    clear_add_request,
    save_triage_result,
)

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
OFFSET_FILE = "/app/data/telegram_bot_offset.txt"

MONITOR_LEVELS = ["critical", "high", "medium", "low"]

# Ensure DB is initialized
init_db()


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [TG-BOT] {msg}", flush=True)


def load_offset() -> int:
    try:
        with open(OFFSET_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def save_offset(offset: int):
    try:
        with open(OFFSET_FILE, "w") as f:
            f.write(str(offset))
    except Exception:
        pass


def send_message(chat_id: int, text: str, reply_to: int = None, reply_markup: Dict = None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{API_URL}/sendMessage", json=payload, timeout=10)


def edit_message(chat_id: int, message_id: int, text: str, reply_markup: Dict = None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{API_URL}/editMessageText", json=payload, timeout=10)


def build_level_keyboard():
    return {
        "inline_keyboard": [
            [{"text": lvl.title(), "callback_data": f"level:{lvl}"} for lvl in MONITOR_LEVELS]
        ]
    }


def build_add_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "📎 Twitter", "callback_data": "add:twitter"},
                {"text": "📝 Resumo", "callback_data": "add:summary"},
                {"text": "🛰️ Nível", "callback_data": "add:level"},
            ]
        ]
    }


def handle_favorite(callback, handle: str):
    user = callback.get("from", {})
    username = user.get("username") or user.get("first_name") or "user"
    user_id = str(user.get("id"))
    chat_id = callback["message"]["chat"]["id"]
    message = callback["message"]
    if add_project_favorite(handle, user_id, username=f"@{username}", chat_id=str(chat_id)):
        # Build liked line
        text = message.get("text", "")
        # Append liked info to the Key Followers line if not present
        liked_line = f"⭐️ Liked by @{username}"
        if "Liked by" in text:
            # Already present; do not duplicate
            pass
        else:
            lines = text.split("\n")
            for i, ln in enumerate(lines):
                if "Key Followers:" in ln:
                    lines[i] = ln + f" | {liked_line}"
                    break
            text = "\n".join(lines)
            edit_message(chat_id, message["message_id"], text, message.get("reply_markup"))
    # Answer callback
    requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": callback["id"], "text": "Favoritado!"}, timeout=5)


def handle_stop(callback, handle: str):
    changed = stop_monitoring_by_handle(handle)
    chat_id = callback["message"]["chat"]["id"]
    msg = f"PROJECT @{handle} STOP MONITORED" if changed else f"PROJECT @{handle} already stopped"
    send_message(chat_id, msg)
    requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": callback["id"], "text": "Stopped"}, timeout=5)


def start_add(chat_id: int, user_id: str):
    upsert_add_request(str(chat_id), user_id, "twitter")
    send_message(chat_id, "Envie o Twitter do projeto (ex: @project).", reply_markup=build_add_keyboard())


def process_level_choice(chat_id: int, user_id: str, level: str):
    state = get_add_request(str(chat_id), user_id) or {}
    if state.get("step") not in ["level", "summary_done"]:
        return
    upsert_add_request(str(chat_id), user_id, "done", state.get("twitter_handle"), state.get("summary"), level)
    # Create triage stub
    handle = (state.get("twitter_handle") or "").lstrip("@")
    summary = state.get("summary") or ""
    triage_result = {
        "project": {},
        "launch": {},
        "signals": {},
        "mentions": {},
        "source": {
            "twitter_handle": f"@{handle}",
            "tweet_id": None,
            "tweet_date": None,
            "tweet_text_preview": f"Manual add: {summary[:200]}",
            "discovery_source": "manual_add",
            "discovery_keyword": f"@{handle}",
        }
    }
    saved = save_triage_result(triage_result)
    clear_add_request(str(chat_id), user_id)
    send_message(chat_id, f"Projeto @{handle} adicionado para triagem (nivel={level}).")


def handle_message(msg: Dict[str, Any]):
    chat_id = msg["chat"]["id"]
    user_id = str(msg["from"]["id"])
    text = msg.get("text", "")
    if text.startswith("/add"):
        start_add(chat_id, user_id)
        return
    # If awaiting fields
    state = get_add_request(str(chat_id), user_id)
    if not state:
        return
    step = state.get("step")
    if step == "twitter":
        upsert_add_request(str(chat_id), user_id, "summary", twitter_handle=text.strip().lstrip("@"))
        send_message(chat_id, "Envie o resumo/porquê.")
    elif step == "summary":
        upsert_add_request(str(chat_id), user_id, "level", state.get("twitter_handle"), summary=text.strip())
        send_message(chat_id, "Escolha o nível de monitoramento:", reply_markup=build_level_keyboard())


def handle_callback(cb: Dict[str, Any]):
    data = cb.get("data", "")
    if data.startswith("fav:"):
        handle = data.split(":", 1)[1]
        handle_favorite(cb, handle)
    elif data.startswith("stop:"):
        handle = data.split(":", 1)[1]
        handle_stop(cb, handle)
    elif data.startswith("level:"):
        level = data.split(":", 1)[1]
        chat_id = cb["message"]["chat"]["id"]
        user_id = str(cb["from"]["id"])
        process_level_choice(chat_id, user_id, level)
    elif data.startswith("add:"):
        # If user taps one of the add buttons, remind the current step
        chat_id = cb["message"]["chat"]["id"]
        user_id = str(cb["from"]["id"])
        state = get_add_request(str(chat_id), user_id)
        if not state:
            start_add(chat_id, user_id)
        else:
            step = state.get("step")
            if step == "twitter":
                send_message(chat_id, "Envie o Twitter do projeto (ex: @project).")
            elif step == "summary":
                send_message(chat_id, "Envie o resumo/porquê.")
            elif step == "level":
                send_message(chat_id, "Escolha o nível de monitoramento:", reply_markup=build_level_keyboard())
    requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": cb["id"]}, timeout=5)


def poll():
    offset = load_offset()
    log("Bot receiver started (polling).")
    while True:
        try:
            resp = requests.get(f"{API_URL}/getUpdates", params={"offset": offset + 1, "timeout": 30}, timeout=40)
            if resp.status_code != 200:
                time.sleep(2)
                continue
            updates = resp.json().get("result", [])
            for upd in updates:
                offset = max(offset, upd.get("update_id", 0))
                if "message" in upd:
                    handle_message(upd["message"])
                if "callback_query" in upd:
                    handle_callback(upd["callback_query"])
            save_offset(offset)
        except Exception as e:
            log(f"Error polling: {str(e)[:100]}")
            time.sleep(2)


if __name__ == "__main__":
    poll()

