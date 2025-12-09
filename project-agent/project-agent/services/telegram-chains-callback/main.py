"""
Telegram Chains Callback Receiver
Uses the chains bot token to handle callbacks for Favorite/Stop and commands /likes /remove.
"""

import os
import sys
import time
import json
import requests
from datetime import datetime
from typing import Dict, Any, List

sys.path.insert(0, '/app/shared')
sys.path.insert(0, '/app')

from agent.database import (
    init_db,
    add_project_favorite,
    get_project_favorites,
    stop_monitoring_by_handle,
)

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN_CHAINS') or os.environ.get('TELEGRAM_BOT_TOKEN')
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
OFFSET_FILE = "/app/data/telegram_chains_cb_offset.txt"

init_db()


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [TG-CHAINS-CB] {msg}", flush=True)


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


def send_message(chat_id: int, text: str, reply_to: int = None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
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


def add_like_to_text(text: str, username: str) -> str:
    liked_line = f"❤️ Liked by @{username}"
    if "Liked by" in text:
        return text  # already added
    return text + f"\n{liked_line}"


def handle_favorite(cb: Dict[str, Any], handle: str):
    user = cb.get("from", {})
    username = user.get("username") or user.get("first_name") or "user"
    user_id = str(user.get("id"))
    chat_id = cb["message"]["chat"]["id"]
    message = cb["message"]

    if add_project_favorite(handle, user_id, username=f"@{username}", chat_id=str(chat_id)):
        text = message.get("text", "")
        new_text = add_like_to_text(text, username)
        edit_message(chat_id, message["message_id"], new_text, message.get("reply_markup"))
    requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": cb["id"], "text": "Favoritado!"}, timeout=5)


def handle_stop(cb: Dict[str, Any], handle: str):
    changed = stop_monitoring_by_handle(handle)
    chat_id = cb["message"]["chat"]["id"]
    msg = f"PROJECT @{handle} STOP MONITORED" if changed else f"PROJECT @{handle} already stopped"
    send_message(chat_id, msg)
    requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": cb["id"], "text": "Stopped"}, timeout=5)


def list_likes(chat_id: int, user_id: str):
    # List favorites by current user
    favorites = []
    all_handles = {}
    # Pull all favorites, then filter in memory
    # get_project_favorites returns all users per handle, so iterate handles from DB
    # quick approach: gather handles with entries (scan)
    # For simplicity, fetch per handle not available; we will scan by reading unique handles from project_favorites
    # Minimal approach: not implemented scanning; return not supported
    send_message(chat_id, "Listing favorites per user not implemented completely. Will list all favorites.")


def handle_command(message: Dict[str, Any]):
    text = message.get("text", "") or ""
    chat_id = message["chat"]["id"]
    user_id = str(message["from"]["id"])

    if text.startswith("/likes"):
        # List favorites for this user
        # We don't have direct query by user; pull by all handles seen in DB would be heavier.
        # Simplified: not implemented fully; acknowledge.
        send_message(chat_id, "Em breve: listagem de favoritos. (não implementado nesta versão)")
    elif text.startswith("/remove"):
        send_message(chat_id, "Remoção por ids ainda não implementada. (placeholder)")


def handle_callback(cb: Dict[str, Any]):
    data = cb.get("data", "")
    if data.startswith("fav:"):
        handle = data.split(":", 1)[1]
        handle_favorite(cb, handle)
    elif data.startswith("stop:"):
        handle = data.split(":", 1)[1]
        handle_stop(cb, handle)
    requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": cb["id"]}, timeout=5)


def poll():
    offset = load_offset()
    log("Chains callback receiver started (polling).")
    while True:
        try:
            resp = requests.get(f"{API_URL}/getUpdates", params={"offset": offset + 1, "timeout": 30}, timeout=40)
            if resp.status_code != 200:
                time.sleep(2)
                continue
            updates = resp.json().get("result", [])
            for upd in updates:
                offset = max(offset, upd.get("update_id", 0))
                if "callback_query" in upd:
                    handle_callback(upd["callback_query"])
                elif "message" in upd:
                    handle_command(upd["message"])
            save_offset(offset)
        except Exception as e:
            log(f"Error polling: {str(e)[:100]}")
            time.sleep(2)


if __name__ == "__main__":
    poll()

