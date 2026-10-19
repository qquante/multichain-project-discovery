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

# Add shared modules to path
sys.path.insert(0, '/app/shared')
sys.path.insert(0, '/app')

from agent.chain_utils import get_chain_group, get_chain_emoji

# Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6388')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Simplified channel routing:
# - NEW PROJECT (confirmed) -> ALL channel
# - UPDATE (monitored) -> dedicated UPDATES channel
CHAT_ID_ALL = os.getenv('TELEGRAM_CHAT_ID_ALL')  # NEW PROJECTS go here
CHAT_ID_UPDATES = '-1003541521775'  # ALL UPDATES go here

# Legacy CHAIN_CHAT_IDS kept for compatibility but not used for routing anymore
CHAIN_CHAT_IDS = {
    'solana': os.getenv('TELEGRAM_CHAT_ID_SOLANA'),
    'base': os.getenv('TELEGRAM_CHAT_ID_BASE'),
    'ethereum': os.getenv('TELEGRAM_CHAT_ID_ETHEREUM'),
    'bsc': os.getenv('TELEGRAM_CHAT_ID_BSC'),
    'megaeth': os.getenv('TELEGRAM_CHAT_ID_MEGAETH'),
    'monad': os.getenv('TELEGRAM_CHAT_ID_MONAD'),
    'other': os.getenv('TELEGRAM_CHAT_ID_OTHER'),
    'unknown': os.getenv('TELEGRAM_CHAT_ID_UNKNOWN'),
    'all': os.getenv('TELEGRAM_CHAT_ID_ALL'),
}

# Rate limiting
RATE_LIMIT_SECONDS = 1.0
MAX_QUEUE_SIZE = 500

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


def get_chat_id_for_chain(chain: str) -> str:
    """Get Telegram chat ID for a chain."""
    group = get_chain_group(chain)
    return CHAIN_CHAT_IDS.get(group)


def format_chain_emoji(chain: str) -> str:
    """Get emoji for chain - uses shared chain_utils."""
    return get_chain_emoji(chain)


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


def format_discovery_source(data: dict) -> str:
    """Format discovery source badge."""
    source = data.get('discovery_source', 'collector')
    keyword = data.get('discovery_keyword', '')
    
    if source == 'alphagate':
        return "🎯 ALPHAGATE"
    elif source == 'alpha_followers':
        return "👤 ALPHA FOLLOWERS"
    elif keyword:
        return "🔍 COLLECTOR"
    else:
        return "🔍 COLLECTOR"


def format_discovery_from(data: dict) -> str:
    """Format the FROM line based on discovery source."""
    source = data.get('discovery_source', 'collector')
    keyword = data.get('discovery_keyword', '')
    
    if source == 'alphagate':
        return keyword or 'AlphaGate Discovery'
    elif source == 'alpha_followers':
        # keyword contains the seed handle like @mikedemarais
        return f"ALPHA {keyword}" if keyword else "Alpha Followers"
    elif keyword:
        return f"Keyword [{keyword}]"
    else:
        return "Keyword Tracker"


def format_launch_info(data: dict) -> str:
    """Format launch date/time info with days remaining."""
    launch_date = data.get('launch_date', '') or ''
    launch_time = data.get('launch_time', '') or ''
    launch_urgency = data.get('launch_urgency', '') or 'unknown'
    launch_platform = data.get('launch_platform', '') or ''
    
    if not launch_date or launch_date == 'TBA':
        return f"TBA ({launch_urgency})"
    
    # Calculate days remaining
    try:
        launch_dt = datetime.strptime(launch_date, '%Y-%m-%d')
        days_until = (launch_dt - datetime.now()).days
        
        if days_until <= 0:
            days_str = "TODAY!"
        elif days_until == 1:
            days_str = "1 day"
        else:
            days_str = f"{days_until} days"
        
        # Format date nicely
        date_nice = launch_dt.strftime("%b %d, %Y")
        
        result = f"{date_nice} ({days_str})"
        if launch_time:
            result = f"{date_nice} {launch_time} ({days_str})"
        if launch_platform:
            result += f" on {launch_platform}"
        
        return result
    except:
        return f"{launch_date} ({launch_urgency})"


def format_token_info(data: dict) -> str:
    """Format token name and ticker (with possibilities if no confirmed ticker)."""
    name = data.get('project_name', '') or 'Unknown'
    ticker = data.get('project_ticker', '') or ''
    
    # If we have a confirmed ticker, show: Name $TICKER (both bold)
    if ticker:
        # Ensure ticker has $ prefix
        ticker_formatted = ticker if ticker.startswith('$') else f"${ticker}"
        return f"<b>{name}</b> <b>{ticker_formatted}</b>"
    
    # Try to get ticker possibilities
    ticker_possibilities = data.get('ticker_possibilities', [])
    if ticker_possibilities:
        # Parse if string
        if isinstance(ticker_possibilities, str):
            try:
                import json
                ticker_possibilities = json.loads(ticker_possibilities)
            except:
                ticker_possibilities = []
        
        # Extract tickers
        possible_tickers = []
        for tp in ticker_possibilities[:3]:  # Max 3 possibilities
            if isinstance(tp, dict):
                t = tp.get('ticker', '')
                if t:
                    possible_tickers.append(t)
            elif isinstance(tp, str):
                possible_tickers.append(tp)
        
        if possible_tickers:
            return f"<b>{name}</b> (Possible: {', '.join(possible_tickers)})"
    
    return f"<b>{name}</b>"


def create_buttons(handle: str) -> list:
    """Create inline keyboard buttons for the message."""
    handle = handle.lstrip('@')
    return [
        [
            {"text": "👤 Profile", "url": f"https://x.com/{handle}"},
            {"text": "🎯 Alphagate", "url": f"https://alphagate.io/project/{handle}"},
            {"text": "❤️ LIKE", "callback_data": f"fav:{handle}"},
            {"text": "🛑 Stop Track", "callback_data": f"stop:{handle}"}
        ]
    ]


def format_message(data: dict, channel: str) -> str:
    """Format message for chain-specific group - NEW LAYOUT WITH TIER AND SCORE."""
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
        # === NEW PROJECT MESSAGE ===
        project_type = data.get('project_type', '') or 'token'
        followers = data.get('followers', 0)
        bio = data.get('bio', '')[:300] if data.get('bio') else ''
        
        # Discovery source
        source_badge = format_discovery_source(data)
        
        # ML Scoring data (NEW)
        ml_score = data.get('ml_final_score', 0) or data.get('final_score', 0)
        ml_grade = data.get('ml_grade', '') or data.get('grade', '')
        tier = data.get('tier', 'C')
        tier_emoji = data.get('tier_emoji', '🟠')
        tier_label = data.get('tier_label', 'Baixa Confiança')
        
        # Signals (NEW)
        positive_signals = data.get('ml_positive_signals', []) or data.get('positive_signals', [])
        red_flags = data.get('ml_red_flags', []) or data.get('red_flags', [])
        
        # AlphaGate stats
        key_followers = data.get('key_followers_count', 0)
        alpha_hunters = data.get('alpha_hunters_count', 0)
        best_wr = data.get('best_hunter_winrate', 0)
        
        # Token info
        token_info = format_token_info(data)
        
        # Launch info
        launch_info = format_launch_info(data)
        
        # Blue verified badge
        is_verified = data.get('is_blue_verified', False)
        verified_badge = " ✅" if is_verified else ""
        
        # Build KF stats line
        kf_stats = f"KF: {key_followers} | H: {alpha_hunters}"
        if best_wr:
            kf_stats += f" | WR: {best_wr:.1f}%"
        
        # Build signals section (NEW)
        signals_section = ""
        if positive_signals:
            signals_list = " | ".join([s for s in positive_signals[:5]])
            signals_section = f"\n\n✅ <b>SINAIS POSITIVOS</b>\n{signals_list}"
        
        # Build warnings section (NEW)
        warnings_section = ""
        if red_flags:
            flags_list = " | ".join([f for f in red_flags[:3]])
            warnings_section = f"\n\n⚠️ <b>AVISOS</b>\n{flags_list}"
        
        # AI Summary (if available)
        ai_summary = data.get('ai_summary', '') or data.get('reasoning', '')
        ai_section = ""
        if ai_summary:
            # Clean JSON artifacts if LLM returned JSON instead of plain text
            ai_clean = ai_summary.strip()
            if ai_clean.startswith('{'):
                # Try to extract text from JSON
                try:
                    import json
                    parsed = json.loads(ai_clean)
                    # Look for common keys that contain the summary text
                    for key in ['resumo', 'summary', 'project_summary', 'projeto']:
                        if key in parsed and isinstance(parsed[key], str):
                            ai_clean = parsed[key]
                            break
                    else:
                        # Just use first string value found
                        for v in parsed.values():
                            if isinstance(v, str) and len(v) > 20:
                                ai_clean = v
                                break
                except:
                    # If JSON parse fails, just strip the braces
                    ai_clean = ai_clean.strip('{}[]"\'').strip()
            
            # Don't truncate - show full summary
            ai_section = f"\n\n💬 <i>{ai_clean}</i>"

        # Likes block (to append at bottom if provided) - extra newline for visible spacing
        liked_by = data.get('liked_by')
        liked_section = ""
        if liked_by:
            liked_section = f"\n\n\n❤️ Liked by {liked_by}"
        
        message = f"""{tier_emoji} <b>NOVO PROJETO</b> | TIER {tier} [{source_badge}]

📊 <b>Score: {ml_score}/100 ({ml_grade})</b> | {tier_label}
🌎 FROM: {format_discovery_from(data)}
{chain_emoji} CHAIN: {chain.upper()}

━━━━━━━━━━━━━━━━━━

👤 Twitter: <a href="https://x.com/{handle}">{handle}</a>{verified_badge}
🫂 Seguidores: {followers:,}
📅 Criado em: {account_date}
⭐️ Key Followers: {key_followers} ({kf_stats})

📋 Bio: {bio}

🔑 Token: {token_info}
🎒 Tipo: {project_type}

🚀 Lançamento: {launch_info}{signals_section}{warnings_section}{ai_section}{liked_section}"""
    
    else:
        # === UPDATE MESSAGE ===
        status = data.get('status', '') or data.get('monitoring_status', '')
        changes = data.get('changes', []) or []
        changes_str = ', '.join(changes) if changes else 'verificação de rotina'
        
        ca_detected = data.get('ca_detected', False) or data.get('ca_mentioned', False)
        ca_address = data.get('ca_address', '')
        
        launch_info = format_launch_info(data)
        
        # ML Score for updates too
        ml_score = data.get('ml_final_score', 0) or data.get('final_score', 0)
        tier = data.get('tier', 'C')
        tier_emoji = data.get('tier_emoji', '🟠')
        
        message = f"""{chain_emoji} <b>ATUALIZAÇÃO</b> | {chain.upper()} | TIER {tier}
━━━━━━━━━━━━━━━━━━
👤 <a href="https://x.com/{handle}">{handle}</a> | 📛 {name}
📊 Score: {ml_score}/100 | Status: {status}
🚀 Lançamento: {launch_info}

📋 {changes_str}"""
        
        if ca_detected and ca_address:
            message += f"\n\n🎉 <b>CA:</b> <code>{ca_address}</code>"
    
    return message


class ChainMessageSender:
    """Handles sending messages - simplified routing."""
    
    def __init__(self):
        # Simplified: only 2 queues - 'confirmed' (NEW PROJECT) and 'monitored' (UPDATE)
        self.queues = {
            'confirmed': deque(maxlen=MAX_QUEUE_SIZE),
            'monitored': deque(maxlen=MAX_QUEUE_SIZE)
        }
        self.last_send_time = {'confirmed': 0, 'monitored': 0}
        self.running = True
        self.stats = {
            'confirmed': {'sent': 0, 'dropped': 0, 'errors': 0},
            'monitored': {'sent': 0, 'dropped': 0, 'errors': 0}
        }
    
    def add_message(self, msg_type: str, message: str, buttons: list = None):
        """Add message to appropriate queue based on type.
        
        Args:
            msg_type: 'confirmed' (NEW PROJECT -> ALL) or 'monitored' (UPDATE -> UPDATES channel)
        """
        msg_data = {
            'message': message,
            'buttons': buttons,
            'timestamp': time.time()
        }
        
        queue_key = 'confirmed' if msg_type == 'confirmed' else 'monitored'
        
        if len(self.queues[queue_key]) >= MAX_QUEUE_SIZE:
            self.stats[queue_key]['dropped'] += 1
        else:
            self.queues[queue_key].append(msg_data)
        
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
        """Process queues - send confirmed to ALL, monitored to UPDATES."""
        while self.running:
            for queue_type, queue in self.queues.items():
                # Determine chat ID based on queue type
                if queue_type == 'confirmed':
                    chat_id = CHAT_ID_ALL  # NEW PROJECT -> ALL
                else:
                    chat_id = CHAT_ID_UPDATES  # UPDATE -> dedicated channel
                
                if not chat_id:
                    continue
                
                if not queue:
                    continue
                
                # Rate limiting
                now = time.time()
                if now - self.last_send_time[queue_type] < RATE_LIMIT_SECONDS:
                    continue
                
                try:
                    item = queue.popleft()
                    success = self.send_message(
                        chat_id=chat_id,
                        message=item['message'],
                        buttons=item.get('buttons')
                    )
                    
                    if success:
                        self.stats[queue_type]['sent'] += 1
                    else:
                        self.stats[queue_type]['errors'] += 1
                    
                    self.last_send_time[queue_type] = now
                    
                except Exception as e:
                    self.stats[queue_type]['errors'] += 1
                    log(f"[ERROR] {queue_type}: {str(e)[:50]}")
            
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
                
                # Determine message type from channel
                msg_type = 'confirmed' if 'confirmed' in channel else 'monitored'
                
                # Format message
                formatted = format_message(data, channel)
                
                # Create buttons
                handle = data.get('twitter_handle', '').lstrip('@')
                buttons = create_buttons(handle) if handle else None
                
                # Add to appropriate queue
                sender.add_message(msg_type, formatted, buttons)
                
                destination = 'ALL' if msg_type == 'confirmed' else 'UPDATES'
                log(f"[QUEUED] {channel} | @{data.get('twitter_handle', '?')} -> {destination}")
                
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

