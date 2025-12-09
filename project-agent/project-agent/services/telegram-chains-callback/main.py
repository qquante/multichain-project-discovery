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
    has_user_favorited,
    remove_project_favorite,
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


def send_message(chat_id: int, text: str, reply_to: int = None, max_retries: int = 3):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    
    for attempt in range(max_retries):
        try:
            requests.post(f"{API_URL}/sendMessage", json=payload, timeout=10)
            return
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt < max_retries - 1:
                time.sleep((attempt + 1) * 2)
                continue
            log(f"Send failed after {max_retries} retries")


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


def build_likes_line(favorites: List[Dict]) -> str:
    """Build the likes line from all favorites."""
    if not favorites:
        return ""
    usernames = [f.get('username', '').lstrip('@') for f in favorites if f.get('username')]
    if not usernames:
        return ""
    # Format: ❤️ Liked by @user1, @user2, @user3
    formatted = ", ".join([f"@{u}" for u in usernames])
    return f"❤️ Liked by {formatted}"


def update_likes_in_text(text: str, favorites: List[Dict]) -> str:
    """Update or remove the likes line in the message text."""
    # Remove existing likes line(s)
    lines = text.split('\n')
    new_lines = [ln for ln in lines if not ln.strip().startswith('❤️ Liked by')]
    
    # Remove trailing empty lines
    while new_lines and not new_lines[-1].strip():
        new_lines.pop()
    
    # Add new likes line if there are favorites
    likes_line = build_likes_line(favorites)
    if likes_line:
        new_lines.append('')  # Empty line for spacing
        new_lines.append(likes_line)
    
    return '\n'.join(new_lines)


def handle_favorite(cb: Dict[str, Any], handle: str):
    user = cb.get("from", {})
    username = user.get("username") or user.get("first_name") or "user"
    user_id = str(user.get("id"))
    chat_id = cb["message"]["chat"]["id"]
    message = cb["message"]
    
    # Toggle: if already liked, remove; otherwise add
    if has_user_favorited(handle, user_id):
        # REMOVE like
        remove_project_favorite(handle, user_id)
        action_text = "Like removido!"
        log(f"[UNLIKE] @{handle} by {username}")
    else:
        # ADD like
        add_project_favorite(handle, user_id, username=f"@{username}", chat_id=str(chat_id))
        action_text = "Favoritado!"
        log(f"[LIKE] @{handle} by {username}")
    
    # Get all current favorites for this project and update message
    all_favorites = get_project_favorites(handle)
    text = message.get("text", "")
    new_text = update_likes_in_text(text, all_favorites)
    
    # Only edit if text changed
    if new_text != text:
        edit_message(chat_id, message["message_id"], new_text, message.get("reply_markup"))
    
    requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": cb["id"], "text": action_text}, timeout=5)


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
    consecutive_errors = 0
    while True:
        try:
            resp = requests.get(f"{API_URL}/getUpdates", params={"offset": offset + 1, "timeout": 30}, timeout=40)
            if resp.status_code != 200:
                consecutive_errors += 1
                wait_time = min(consecutive_errors * 5, 60)  # Max 60s backoff
                log(f"HTTP {resp.status_code}, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            consecutive_errors = 0  # Reset on success
            updates = resp.json().get("result", [])
            for upd in updates:
                offset = max(offset, upd.get("update_id", 0))
                if "callback_query" in upd:
                    handle_callback(upd["callback_query"])
                elif "message" in upd:
                    handle_command(upd["message"])
            save_offset(offset)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            consecutive_errors += 1
            wait_time = min(consecutive_errors * 5, 60)  # Max 60s backoff
            log(f"Connection error, retry in {wait_time}s: {str(e)[:50]}")
            time.sleep(wait_time)
        except Exception as e:
            log(f"Error polling: {str(e)[:100]}")
            time.sleep(5)


if __name__ == "__main__":
    poll()

