# services/telegram/main.py
"""
Telegram Notifier Service - FIXED VERSION

PROBLEM: During rate limit wait, messages were lost.
FIX: Continue receiving messages while waiting for rate limit.
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
    format_mention_detected,
    format_project_discovered,
    format_project_confirmed,
    format_project_rejected_verification,
    format_project_monitored,
    format_launch_alert,
    format_project_launched,
    format_project_abandoned,
    format_project_removed,
    format_project_reactivated,
    format_fingerprint
)


# ============================================
# CONFIGURATION
# ============================================

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '[REMOVED_CREDENTIAL]')
GROUP_ID = os.environ.get('TELEGRAM_GROUP_ID', '-1003466463312')

TOPIC_STAGE_0 = int(os.environ.get('TOPIC_STAGE_0', '10'))
TOPIC_STAGE_1 = int(os.environ.get('TOPIC_STAGE_1', '3'))
TOPIC_MENTIONS = int(os.environ.get('TOPIC_MENTIONS', '637'))
TOPIC_STAGE_2 = int(os.environ.get('TOPIC_STAGE_2', '5'))
TOPIC_STAGE_3 = int(os.environ.get('TOPIC_STAGE_3', '7'))
TOPIC_FINGERPRINTS = int(os.environ.get('TOPIC_FINGERPRINTS', '12'))

# HIGH PRIORITY channels - NEVER DROP
HIGH_PRIORITY_CHANNELS = {
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
}

# LOW PRIORITY channels - CAN DROP
LOW_PRIORITY_CHANNELS = {
    'tweets:collected',
    'projects:triaged',
    'triage:rejected',
    'fingerprint:new'
}

ALL_CHANNELS = list(HIGH_PRIORITY_CHANNELS | LOW_PRIORITY_CHANNELS)

MAX_LOW_PRIORITY_QUEUE = 50
RATE_LIMIT_DELAY = 1.0  # 1 second between messages
MAX_RETRIES = 3


class TelegramNotifier:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        self.pubsub = self.redis.pubsub()
        self.api_url = f"https://api.telegram.org/bot{BOT_TOKEN}"
        self.last_send_time = 0
        self.rate_limit_until = 0  # Timestamp when rate limit ends
        
        self.high_queue = deque()
        self.low_queue = deque(maxlen=MAX_LOW_PRIORITY_QUEUE)
        
        self.stats = {
            'high_received': 0, 'high_sent': 0,
            'low_received': 0, 'low_sent': 0, 'low_dropped': 0
        }
        
    def log(self, msg: str):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [TELEGRAM] {msg}", flush=True)
    
    def drain_redis(self):
        """Drain ALL pending messages from Redis into queues."""
        count = 0
        while True:
            message = self.pubsub.get_message(timeout=0.01)
            if not message:
                break
            if message['type'] == 'message':
                self.add_to_queue(message)
                count += 1
        return count
    
    def add_to_queue(self, message):
        """Add Redis message to appropriate queue."""
        channel = message['channel']
        if isinstance(channel, bytes):
            channel = channel.decode('utf-8')
        
        try:
            data = json.loads(message['data'])
            handle = data.get('twitter_handle', data.get('author_username', '?'))
            
            if channel in HIGH_PRIORITY_CHANNELS:
                self.high_queue.append((channel, data))
                self.stats['high_received'] += 1
                self.log(f"[HIGH QUEUE] {channel} | @{handle} | queue={len(self.high_queue)}")
            else:
                old_len = len(self.low_queue)
                self.low_queue.append((channel, data))
                self.stats['low_received'] += 1
                if old_len == MAX_LOW_PRIORITY_QUEUE:
                    self.stats['low_dropped'] += 1
                    
        except json.JSONDecodeError:
            pass
    
    def can_send(self) -> bool:
        """Check if we can send (not rate limited)."""
        now = time.time()
        if now < self.rate_limit_until:
            return False
        if now - self.last_send_time < RATE_LIMIT_DELAY:
            return False
        return True
    
    def send_message(self, topic_id: int, text: str, buttons: List = None) -> bool:
        """Send message to Telegram."""
        if not text or not text.strip():
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
        
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(
                    f"{self.api_url}/sendMessage",
                    json=payload,
                    timeout=15
                )
                
                self.last_send_time = time.time()
                
                if response.status_code == 200:
                    return True
                
                if response.status_code == 429:
                    retry_after = response.json().get('parameters', {}).get('retry_after', 30)
                    self.rate_limit_until = time.time() + retry_after + 1
                    self.log(f"[RATE_LIMIT] Waiting {retry_after}s (will continue receiving)")
                    return False  # Return immediately, don't block
                
                if response.status_code == 400:
                    # Try without HTML
                    del payload["parse_mode"]
                    response2 = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=15)
                    return response2.status_code == 200
                
                self.log(f"[ERROR] {response.status_code}: {response.text[:80]}")
                return False
                
            except Exception as e:
                self.log(f"[ERROR] {str(e)[:60]}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(1)
        
        return False
    
    def format_message(self, channel: str, data: Dict) -> Tuple[int, str, List]:
        """Format message and return (topic_id, message, buttons)."""
        topic_id = None
        message = None
        buttons = []
        
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
            elif channel == 'mentions:new':
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
            elif channel == 'fingerprint:new':
                topic_id = TOPIC_FINGERPRINTS
                message, buttons = format_fingerprint(data)
        except Exception as e:
            self.log(f"[ERROR] Format {channel}: {str(e)[:40]}")
        
        return topic_id, message, buttons
    
    def process_one_message(self) -> bool:
        """Process ONE message from queues. Returns True if message was sent."""
        # HIGH PRIORITY FIRST
        if self.high_queue:
            channel, data = self.high_queue.popleft()
            handle = data.get('twitter_handle', '?')
            topic_id, message, buttons = self.format_message(channel, data)
            
            if topic_id and message:
                self.log(f"[SEND HIGH] {channel} | @{handle} | topic={topic_id}")
                if self.send_message(topic_id, message, buttons):
                    self.stats['high_sent'] += 1
                    self.log(f"[OK HIGH] @{handle} | sent={self.stats['high_sent']}")
                    return True
                else:
                    # Put back if rate limited
                    if time.time() < self.rate_limit_until:
                        self.high_queue.appendleft((channel, data))
            return False
        
        # Then LOW PRIORITY
        if self.low_queue:
            channel, data = self.low_queue.popleft()
            handle = data.get('twitter_handle', data.get('author_username', '?'))
            topic_id, message, buttons = self.format_message(channel, data)
            
            if topic_id and message:
                if self.send_message(topic_id, message, buttons):
                    self.stats['low_sent'] += 1
                    return True
                else:
                    # Put back if rate limited
                    if time.time() < self.rate_limit_until:
                        self.low_queue.appendleft((channel, data))
            return False
        
        return False
    
    def run(self):
        """Main loop - ALWAYS receive, send when possible."""
        self.log("="*50)
        self.log("TELEGRAM SERVICE STARTED - FIXED VERSION")
        self.log("="*50)
        self.log(f"Redis: {REDIS_URL}")
        self.log(f"Group: {GROUP_ID}")
        self.log(f"Topics: S0={TOPIC_STAGE_0}, S1={TOPIC_STAGE_1}, S2={TOPIC_STAGE_2}, S3={TOPIC_STAGE_3}")
        
        # Test bot
        try:
            response = requests.get(f"{self.api_url}/getMe", timeout=5)
            if response.status_code == 200:
                bot_info = response.json().get('result', {})
                self.log(f"Bot connected: @{bot_info.get('username')}")
        except Exception as e:
            self.log(f"[WARNING] Bot test failed: {e}")
        
        # Subscribe
        self.pubsub.subscribe(*ALL_CHANNELS)
        self.log(f"Subscribed to {len(ALL_CHANNELS)} channels")
        self.log(f"HIGH: {HIGH_PRIORITY_CHANNELS}")
        self.log(f"LOW: {LOW_PRIORITY_CHANNELS}")
        
        last_status = 0
        
        while True:
            try:
                # 1. ALWAYS drain Redis first (receive all pending messages)
                drained = self.drain_redis()
                
                # 2. Send ONE message if not rate limited
                if self.can_send():
                    self.process_one_message()
                
                # 3. Status every 30 seconds
                if time.time() - last_status > 30:
                    rate_wait = max(0, self.rate_limit_until - time.time())
                    self.log(f"[STATUS] HIGH: {len(self.high_queue)} queued, {self.stats['high_sent']}/{self.stats['high_received']} sent | LOW: {len(self.low_queue)} queued, {self.stats['low_sent']}/{self.stats['low_received']} sent | rate_wait={rate_wait:.0f}s")
                    last_status = time.time()
                
                time.sleep(0.05)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.log(f"[ERROR] {str(e)[:100]}")
                time.sleep(1)


if __name__ == "__main__":
    notifier = TelegramNotifier()
    notifier.run()
