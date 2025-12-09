# services/telegram-low/main.py
"""
Telegram Bot 1: Stage 0, Stage 1, Fingerprints
High volume, can be rate limited without affecting critical messages.
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
    format_tweet_collected,
    format_project_triaged,
    format_tweet_rejected,
    format_fingerprint
)

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6388')
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
GROUP_ID = os.environ.get('TELEGRAM_GROUP_ID', '-1003466463312')

TOPIC_STAGE_0 = int(os.environ.get('TOPIC_STAGE_0', '10'))
TOPIC_STAGE_1 = int(os.environ.get('TOPIC_STAGE_1', '3'))
TOPIC_FINGERPRINTS = int(os.environ.get('TOPIC_FINGERPRINTS', '12'))

CHANNELS = ['tweets:collected', 'projects:triaged', 'triage:rejected', 'fingerprint:new']
MAX_QUEUE = 100
RATE_LIMIT_DELAY = 1.0


class TelegramLow:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        self.pubsub = self.redis.pubsub()
        self.api_url = f"https://api.telegram.org/bot{BOT_TOKEN}"
        self.last_send_time = 0
        self.rate_limit_until = 0
        self.queue = deque(maxlen=MAX_QUEUE)
        self.stats = {'received': 0, 'sent': 0, 'dropped': 0}
        
    def log(self, msg: str):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [TG-LOW] {msg}", flush=True)
    
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
                    old_len = len(self.queue)
                    self.queue.append((channel, data))
                    self.stats['received'] += 1
                    if old_len == MAX_QUEUE:
                        self.stats['dropped'] += 1
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
                self.log(f"[RATE_LIMIT] {retry_after}s")
                return False
            if response.status_code == 400:
                del payload["parse_mode"]
                r2 = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=15)
                return r2.status_code == 200
        except Exception as e:
            self.log(f"[ERROR] {str(e)[:50]}")
        return False
    
    def format_message(self, channel: str, data: Dict) -> Tuple[int, str, List]:
        topic_id, message, buttons = None, None, []
        try:
            if channel == 'tweets:collected':
                topic_id = TOPIC_STAGE_0
                message, buttons = format_tweet_collected(data)
            elif channel == 'projects:triaged':
                topic_id = TOPIC_STAGE_1
                message, buttons = format_project_triaged(data)
            elif channel == 'triage:rejected':
                topic_id = TOPIC_STAGE_1
                message, buttons = format_tweet_rejected(data)
            elif channel == 'fingerprint:new':
                topic_id = TOPIC_FINGERPRINTS
                message, buttons = format_fingerprint(data)
        except Exception as e:
            self.log(f"[ERROR] Format: {str(e)[:40]}")
        return topic_id, message, buttons
    
    def process_one(self):
        if not self.queue:
            return
        channel, data = self.queue.popleft()
        topic_id, message, buttons = self.format_message(channel, data)
        if topic_id and message:
            if self.send_message(topic_id, message, buttons):
                self.stats['sent'] += 1
            elif time.time() < self.rate_limit_until:
                self.queue.appendleft((channel, data))
    
    def run(self):
        self.log("="*50)
        self.log("TELEGRAM LOW (Stage 0, 1, FP) STARTED")
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
                if time.time() - last_status > 60:
                    self.log(f"[STATUS] queue={len(self.queue)} | sent={self.stats['sent']}/{self.stats['received']} | dropped={self.stats['dropped']}")
                    last_status = time.time()
                time.sleep(0.05)
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.log(f"[ERROR] {str(e)[:80]}")
                time.sleep(1)


if __name__ == "__main__":
    bot = TelegramLow()
    bot.run()



