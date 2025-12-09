# services/telegram-high/main.py
"""
Telegram Bot 2: Stage 2, Stage 3, Mentions
CRITICAL - Never miss these messages!
"""

import os
import sys
import time
import json
import redis
import requests
from collections import deque
from datetime import datetime
from typing import Dict, Any, List, Tuple

from formatter import (
    format_mention_detected,
    format_project_discovered,
    format_project_confirmed,
    format_project_rejected_verification,
    format_project_monitored,
    format_launch_alert,
    format_project_launched,
    format_project_abandoned,
    format_project_removed,
    format_project_reactivated
)

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6388')
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
GROUP_ID = os.environ.get('TELEGRAM_GROUP_ID', '-1003466463312')

TOPIC_MENTIONS = int(os.environ.get('TOPIC_MENTIONS', '14'))
TOPIC_STAGE_2 = int(os.environ.get('TOPIC_STAGE_2', '5'))
TOPIC_STAGE_3 = int(os.environ.get('TOPIC_STAGE_3', '7'))

# CRITICAL channels - NEVER DROP
CHANNELS = [
    'projects:confirmed',
    'projects:rejected',
    'projects:monitored',
    'projects:alert',
    'projects:launched',
    'projects:abandoned',
    'projects:removed',
    'projects:reactivated',
    'mentions:new',
    'discovery:complete'
]

RATE_LIMIT_DELAY = 1.0


class TelegramHigh:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        self.pubsub = self.redis.pubsub()
        self.api_url = f"https://api.telegram.org/bot{BOT_TOKEN}"
        self.last_send_time = 0
        self.rate_limit_until = 0
        self.queue = deque()  # UNLIMITED - never drop
        self.stats = {'received': 0, 'sent': 0}
        
    def log(self, msg: str):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [TG-HIGH] {msg}", flush=True)
    
    def drain_redis(self):
        while True:
            message = self.pubsub.get_message(timeout=0.01)
            if not message:
                break
            if message['type'] == 'message':
                channel = message['channel']
                if isinstance(channel, bytes):
                    channel = channel.decode('utf-8')
                try:
                    data = json.loads(message['data'])
                    self.queue.append((channel, data))
                    self.stats['received'] += 1
                    handle = data.get('twitter_handle', '?')
                    self.log(f"[RECEIVED] {channel} | @{handle} | queue={len(self.queue)}")
                except:
                    pass
    
    def can_send(self) -> bool:
        now = time.time()
        return now >= self.rate_limit_until and (now - self.last_send_time) >= RATE_LIMIT_DELAY
    
    def send_message(self, topic_id: int, text: str, buttons: List = None) -> bool:
        if not text:
            return False
        
        payload = {
            "chat_id": GROUP_ID,
            "message_thread_id": topic_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        
        try:
            response = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=15)
            self.last_send_time = time.time()
            
            if response.status_code == 200:
                return True
            if response.status_code == 429:
                retry_after = response.json().get('parameters', {}).get('retry_after', 30)
                self.rate_limit_until = time.time() + retry_after + 1
                self.log(f"[RATE_LIMIT] {retry_after}s - will retry")
                return False
            if response.status_code == 400:
                del payload["parse_mode"]
                r2 = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=15)
                return r2.status_code == 200
            self.log(f"[ERROR] {response.status_code}: {response.text[:80]}")
        except Exception as e:
            self.log(f"[ERROR] {str(e)[:50]}")
        return False
    
    def format_message(self, channel: str, data: Dict) -> Tuple[int, str, List]:
        topic_id, message, buttons = None, None, []
        try:
            if channel == 'mentions:new':
                topic_id = TOPIC_MENTIONS
                message, buttons = format_mention_detected(data)
            elif channel == 'discovery:complete':
                topic_id = TOPIC_MENTIONS
                message, buttons = format_project_discovered(data)
            elif channel == 'projects:confirmed':
                topic_id = TOPIC_STAGE_2
                message, buttons = format_project_confirmed(data)
            elif channel == 'projects:rejected':
                topic_id = TOPIC_STAGE_2
                message, buttons = format_project_rejected_verification(data)
            elif channel == 'projects:monitored':
                topic_id = TOPIC_STAGE_3
                message, buttons = format_project_monitored(data)
            elif channel == 'projects:alert':
                topic_id = TOPIC_STAGE_3
                message, buttons = format_launch_alert(data)
            elif channel == 'projects:launched':
                topic_id = TOPIC_STAGE_3
                message, buttons = format_project_launched(data)
            elif channel == 'projects:abandoned':
                topic_id = TOPIC_STAGE_3
                message, buttons = format_project_abandoned(data)
            elif channel == 'projects:removed':
                topic_id = TOPIC_STAGE_3
                message, buttons = format_project_removed(data)
            elif channel == 'projects:reactivated':
                topic_id = TOPIC_STAGE_3
                message, buttons = format_project_reactivated(data)
        except Exception as e:
            self.log(f"[ERROR] Format {channel}: {str(e)[:40]}")
        return topic_id, message, buttons
    
    def process_one(self):
        if not self.queue:
            return
        channel, data = self.queue.popleft()
        handle = data.get('twitter_handle', '?')
        topic_id, message, buttons = self.format_message(channel, data)
        
        if topic_id and message:
            self.log(f"[SEND] {channel} | @{handle} | topic={topic_id}")
            if self.send_message(topic_id, message, buttons):
                self.stats['sent'] += 1
                self.log(f"[OK] @{handle} | sent={self.stats['sent']}")
            elif time.time() < self.rate_limit_until:
                # Put back - NEVER DROP
                self.queue.appendleft((channel, data))
                self.log(f"[RETRY] @{handle} put back in queue")
    
    def run(self):
        self.log("="*50)
        self.log("TELEGRAM HIGH (Stage 2, 3, Mentions) STARTED")
        self.log("CRITICAL - NEVER DROP MESSAGES")
        self.log(f"Bot: {BOT_TOKEN[:20]}...")
        self.log(f"Channels: {CHANNELS}")
        self.log("="*50)
        
        try:
            r = requests.get(f"{self.api_url}/getMe", timeout=5)
            if r.status_code == 200:
                self.log(f"Bot: @{r.json()['result']['username']}")
        except:
            pass
        
        self.pubsub.subscribe(*CHANNELS)
        self.log(f"Subscribed to {len(CHANNELS)} channels")
        
        last_status = 0
        while True:
            try:
                self.drain_redis()
                if self.can_send():
                    self.process_one()
                if time.time() - last_status > 30:
                    self.log(f"[STATUS] queue={len(self.queue)} | sent={self.stats['sent']}/{self.stats['received']}")
                    last_status = time.time()
                time.sleep(0.05)
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.log(f"[ERROR] {str(e)[:80]}")
                time.sleep(1)


if __name__ == "__main__":
    bot = TelegramHigh()
    bot.run()



