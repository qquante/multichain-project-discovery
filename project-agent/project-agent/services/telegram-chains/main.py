# services/telegram-chains/main.py
"""
Telegram Chains Service
Sends project confirmations to chain-specific Telegram groups.
One bot, multiple groups (by chain).
"""

import os
import sys
import json
import time
import asyncio
import threading
from collections import deque
from datetime import datetime

import redis.asyncio as redis
import requests

# Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Chat IDs for each chain (to be filled in .env) - 9 channels
CHAIN_CHAT_IDS = {
    'solana': os.getenv('TELEGRAM_CHAT_ID_SOLANA'),
    'base': os.getenv('TELEGRAM_CHAT_ID_BASE'),
    'ethereum': os.getenv('TELEGRAM_CHAT_ID_ETHEREUM'),
    'bsc': os.getenv('TELEGRAM_CHAT_ID_BSC'),
    'megaeth': os.getenv('TELEGRAM_CHAT_ID_MEGAETH'),
    'monad': os.getenv('TELEGRAM_CHAT_ID_MONAD'),
    'other': os.getenv('TELEGRAM_CHAT_ID_OTHER'),
    'unknown': os.getenv('TELEGRAM_CHAT_ID_UNKNOWN'),
    'all': os.getenv('TELEGRAM_CHAT_ID_ALL'),  # All chains combined
}

# Chains that map to 'megaeth' group (excluding monad which has its own)
MEGAETH_CHAINS = ['megaeth', 'berachain', 'abstract', 'movement']

# Rate limiting
RATE_LIMIT_SECONDS = 1.0
MAX_QUEUE_SIZE = 500  # Per chain

# Subscribe to chain-specific channels (8 chains)
CHANNELS = [
    'projects:confirmed:solana',
    'projects:confirmed:base',
    'projects:confirmed:ethereum',
    'projects:confirmed:bsc',
    'projects:confirmed:megaeth',
    'projects:confirmed:monad',
    'projects:confirmed:other',
    'projects:confirmed:unknown',
    'projects:monitored:solana',
    'projects:monitored:base',
    'projects:monitored:ethereum',
    'projects:monitored:bsc',
    'projects:monitored:megaeth',
    'projects:monitored:monad',
    'projects:monitored:other',
    'projects:monitored:unknown',
]


def log(msg: str):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [TG-CHAINS] {msg}", flush=True)


def get_chain_from_channel(channel: str) -> str:
    """Extract chain name from channel."""
    # projects:confirmed:solana -> solana
    parts = channel.split(':')
    if len(parts) >= 3:
        return parts[2]
    return 'unknown'


def get_chain_group(chain: str) -> str:
    """Map chain to group key (8 groups)."""
    chain_lower = chain.lower() if chain else 'unknown'
    
    if chain_lower in ['sol', 'solana']:
        return 'solana'
    elif chain_lower in ['base']:
        return 'base'
    elif chain_lower in ['eth', 'ethereum']:
        return 'ethereum'
    elif chain_lower in ['bsc', 'bnb', 'binance']:
        return 'bsc'
    elif chain_lower in ['monad']:
        return 'monad'
    elif chain_lower in MEGAETH_CHAINS:
        return 'megaeth'
    elif chain_lower in ['unknown', '']:
        return 'unknown'
    else:
        return 'other'


def get_chat_id_for_chain(chain: str) -> str:
    """Get Telegram chat ID for a chain."""
    group = get_chain_group(chain)
    return CHAIN_CHAT_IDS.get(group)


def format_chain_emoji(chain: str) -> str:
    """Get emoji for chain."""
    emojis = {
        'solana': '🟢',
        'base': '🔵',
        'ethereum': '🟣',
        'bsc': '🟡',
        'bnb': '🟡',
        'megaeth': '⚡',
        'monad': '🟪',
        'berachain': '🐻',
        'other': '🔶',
        'unknown': '❓'
    }
    return emojis.get(chain.lower(), '🔷')


def format_account_date(created_at: str) -> str:
    """Format account creation date as exact date (e.g., 'Feb 15, 2024')."""
    if not created_at:
        return "?"
    try:
        created_dt = None
        
        # Try various date formats
        for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S']:
            try:
                created_dt = datetime.strptime(created_at[:19], fmt[:19])
                break
            except:
                continue
        
        if not created_dt:
            # Try Twitter format: "Sat Nov 23 00:00:00 +0000 2024"
            parts = created_at.split()
            if len(parts) >= 6:
                month_map = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
                month = month_map.get(parts[1], 1)
                day = int(parts[2])
                year = int(parts[5])
                created_dt = datetime(year, month, day)
        
        if created_dt:
            # Format as "Feb 15, 2024"
            return created_dt.strftime("%b %d, %Y")
        return "?"
    except:
        return "?"


def format_message(data: dict, channel: str) -> str:
    """Format message for chain-specific group."""
    msg_type = 'confirmed' if 'confirmed' in channel else 'monitored'
    handle = data.get('twitter_handle', '').lstrip('@')
    name = data.get('project_name', '') or 'Unknown'
    ticker = data.get('project_ticker', '') or ''
    chain = data.get('chain', '') or data.get('project_chain', '') or 'unknown'
    chain_emoji = format_chain_emoji(chain)
    
    # Account creation date
    account_created = data.get('account_created_at', '') or data.get('created_at', '')
    account_date = format_account_date(account_created)
    
    if msg_type == 'confirmed':
        # Confirmed project
        project_type = data.get('project_type', '') or 'token'
        followers = data.get('followers', 0)
        bio = data.get('bio', '')[:200] if data.get('bio') else ''
        
        # Launch info
        launch_urgency = data.get('launch_urgency', '') or 'unknown'
        launch_date = data.get('launch_date', '') or 'TBA'
        launch_platform = data.get('launch_platform', '') or ''
        
        # AlphaGate
        key_followers = data.get('key_followers_count', 0)
        alpha_hunters = data.get('alpha_hunters_count', 0)
        best_wr = data.get('best_hunter_winrate', 0)
        
        # Build launch line
        launch_parts = [launch_urgency, launch_date]
        if launch_platform:
            launch_parts.append(launch_platform)
        launch_line = ' | '.join(launch_parts)
        
        message = f"""{chain_emoji} <b>NEW PROJECT</b> | {chain.upper()}
━━━━━━━━━━━━━━━━━━
👤 <a href="https://x.com/{handle}">@{handle}</a> | 📛 {name}{f' | {ticker}' if ticker else ''}
📊 {project_type} | 👥 {followers:,} | 📅 {account_date}
🚀 LAUNCH | {launch_line}

📋 {bio}

🔑 KF: {key_followers} | 🎯 Hunters: {alpha_hunters}{f' | WR: {best_wr:.1f}%' if best_wr else ''}"""
    
    else:
        # Monitored update
        status = data.get('status', '') or data.get('monitoring_status', '')
        changes = data.get('changes', []) or []
        changes_str = ', '.join(changes) if changes else 'routine check'
        
        ca_detected = data.get('ca_detected', False) or data.get('ca_mentioned', False)
        ca_address = data.get('ca_address', '')
        
        launch_urgency = data.get('launch_urgency', '') or 'unknown'
        
        message = f"""{chain_emoji} <b>UPDATE</b> | {chain.upper()}
━━━━━━━━━━━━━━━━━━
👤 <a href="https://x.com/{handle}">@{handle}</a> | 📛 {name}
📊 {status} | ⏰ {launch_urgency}

📋 {changes_str}"""
        
        if ca_detected and ca_address:
            message += f"\n\n🚀 <b>CA:</b> <code>{ca_address}</code>"
    
    return message


class ChainMessageSender:
    """Handles sending messages to chain-specific groups."""
    
    def __init__(self):
        self.queues = {chain: deque(maxlen=MAX_QUEUE_SIZE) for chain in CHAIN_CHAT_IDS.keys()}
        self.last_send_time = {chain: 0 for chain in CHAIN_CHAT_IDS.keys()}
        self.running = True
        self.stats = {chain: {'sent': 0, 'dropped': 0, 'errors': 0} for chain in CHAIN_CHAT_IDS.keys()}
    
    def add_message(self, chain: str, message: str, buttons: list = None):
        """Add message to chain queue AND to ALL queue."""
        chain_group = get_chain_group(chain)
        
        msg_data = {
            'message': message,
            'buttons': buttons,
            'timestamp': time.time()
        }
        
        # Add to chain-specific queue
        if len(self.queues[chain_group]) >= MAX_QUEUE_SIZE:
            self.stats[chain_group]['dropped'] += 1
        else:
            self.queues[chain_group].append(msg_data)
        
        # Also add to ALL queue (receives everything)
        if 'all' in self.queues:
            if len(self.queues['all']) >= MAX_QUEUE_SIZE:
                self.stats['all']['dropped'] += 1
            else:
                self.queues['all'].append(msg_data.copy())
        
        return True
    
    def send_message(self, chat_id: str, message: str, buttons: list = None) -> bool:
        """Send message to Telegram."""
        if not chat_id or not TELEGRAM_BOT_TOKEN:
            return False
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        if buttons:
            payload["reply_markup"] = json.dumps({"inline_keyboard": buttons})
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            log(f"[ERROR] Send failed: {str(e)[:50]}")
            return False
    
    def process_queues(self):
        """Process all chain queues."""
        while self.running:
            for chain, queue in self.queues.items():
                chat_id = CHAIN_CHAT_IDS.get(chain)
                
                if not chat_id:
                    # No chat ID configured for this chain
                    continue
                
                if not queue:
                    continue
                
                # Rate limiting per chain
                now = time.time()
                if now - self.last_send_time[chain] < RATE_LIMIT_SECONDS:
                    continue
                
                try:
                    item = queue.popleft()
                    success = self.send_message(
                        chat_id=chat_id,
                        message=item['message'],
                        buttons=item.get('buttons')
                    )
                    
                    if success:
                        self.stats[chain]['sent'] += 1
                    else:
                        self.stats[chain]['errors'] += 1
                    
                    self.last_send_time[chain] = now
                    
                except Exception as e:
                    self.stats[chain]['errors'] += 1
                    log(f"[ERROR] {chain}: {str(e)[:50]}")
            
            time.sleep(0.1)
    
    def start(self):
        """Start the sender thread."""
        thread = threading.Thread(target=self.process_queues, daemon=True)
        thread.start()
        return thread
    
    def stop(self):
        """Stop the sender."""
        self.running = False
    
    def get_stats(self) -> dict:
        """Get statistics."""
        return {
            'queues': {chain: len(q) for chain, q in self.queues.items()},
            'stats': self.stats
        }


async def main():
    log("=" * 60)
    log("Telegram Chains Service Starting")
    log(f"Redis: {REDIS_URL}")
    log(f"Channels: {CHANNELS}")
    log("=" * 60)
    
    # Log configured chains
    for chain, chat_id in CHAIN_CHAT_IDS.items():
        status = "✅" if chat_id else "❌ NOT CONFIGURED"
        log(f"  {chain}: {status}")
    
    # Initialize sender
    sender = ChainMessageSender()
    sender.start()
    
    # Connect to Redis
    redis_client = await redis.from_url(REDIS_URL)
    pubsub = redis_client.pubsub()
    
    # Subscribe to channels
    await pubsub.subscribe(*CHANNELS)
    log(f"Subscribed to {len(CHANNELS)} channels")
    
    # Process messages
    try:
        async for message in pubsub.listen():
            if message['type'] != 'message':
                continue
            
            try:
                channel = message['channel'].decode() if isinstance(message['channel'], bytes) else message['channel']
                data = json.loads(message['data'])
                
                # Get chain from channel or data
                chain = get_chain_from_channel(channel)
                if not chain or chain == 'unknown':
                    chain = data.get('chain', '') or data.get('project_chain', '') or 'unknown'
                
                # Format message
                formatted = format_message(data, channel)
                
                # Add to queue
                sender.add_message(chain, formatted)
                
                log(f"[QUEUED] {channel} | @{data.get('twitter_handle', '?')} | chain={chain}")
                
            except json.JSONDecodeError:
                log(f"[ERROR] Invalid JSON")
            except Exception as e:
                log(f"[ERROR] {str(e)[:50]}")
    
    except asyncio.CancelledError:
        log("Shutting down...")
    finally:
        sender.stop()
        await pubsub.unsubscribe(*CHANNELS)
        await redis_client.aclose()


if __name__ == '__main__':
    asyncio.run(main())

