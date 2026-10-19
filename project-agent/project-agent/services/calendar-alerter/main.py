# services/calendar-alerter/main.py
"""
Calendar Alerter Service
Checks calendar and sends alerts for upcoming launches.
Groups alerts by chain, shows time remaining.
"""

import os
import sys
import json
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any

import redis.asyncio as redis
import requests

# Add parent for imports
sys.path.insert(0, '/app')

from agent.database import (
    init_db,
    get_calendar_today,
    get_calendar_upcoming,
    get_calendar_by_urgency,
    get_calendar_pending_alerts,
    mark_calendar_alert_sent,
    get_calendar_stats,
    get_all_favorited_handles,
    get_favorites_with_chain
)

# Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6388')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_ALERT_CHAT_ID = os.getenv('TELEGRAM_ALERT_CHAT_ID')  # Main alerts channel

CHECK_INTERVAL_MINUTES = int(os.getenv('ALERT_CHECK_INTERVAL', '60'))  # Check every hour

# Rate limiting
RATE_LIMIT_SECONDS = 2.0


def log(msg: str):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [ALERTER] {msg}", flush=True)


def get_chain_emoji(chain: str) -> str:
    """Get emoji for chain (8 chains)."""
    emojis = {
        'solana': '🟣',
        'base': '🔵',
        'ethereum': '🔷',
        'bsc': '🔶',
        'bnb': '🔶',
        'megaeth': '⚡',
        'monad': '🟪',
        'berachain': '🐻',
        'other': '⚪',
        'unknown': '❓'
    }
    return emojis.get(chain.lower() if chain else 'unknown', '🔷')


def calculate_time_remaining(launch_date: str, launch_time: str = None) -> str:
    """Calculate human-readable time remaining."""
    if not launch_date:
        return "TBA"
    
    try:
        if launch_time:
            # Has specific time
            dt_str = f"{launch_date} {launch_time}"
            try:
                launch_dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M UTC')
            except:
                launch_dt = datetime.strptime(launch_date, '%Y-%m-%d')
        else:
            launch_dt = datetime.strptime(launch_date, '%Y-%m-%d')
        
        now = datetime.now()
        diff = launch_dt - now
        
        if diff.total_seconds() < 0:
            return "NOW/PAST"
        
        days = diff.days
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60
        
        if days > 0:
            return f"{days}d {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    
    except ValueError:
        return "TBA"


def group_by_chain(projects: List[Dict]) -> Dict[str, List[Dict]]:
    """Group projects by chain."""
    grouped = {}
    for p in projects:
        chain = (p.get('chain') or 'unknown').lower()
        if chain not in grouped:
            grouped[chain] = []
        grouped[chain].append(p)
    return grouped


def format_launch_time(launch_time: str) -> str:
    """Format launch time for display (already in UTC)."""
    if not launch_time:
        return "TBA"
    # Remove "UTC" if already in string, then add it back formatted
    time_clean = launch_time.replace(' UTC', '').replace('UTC', '').strip()
    return f"{time_clean} UTC"


def get_possible_tickers(project: Dict) -> str:
    """Get possible tickers if no confirmed ticker."""
    # Check for ticker_possibilities in the data
    possibilities = project.get('ticker_possibilities', [])
    if isinstance(possibilities, str):
        try:
            import json
            possibilities = json.loads(possibilities)
        except:
            possibilities = []
    
    if possibilities:
        # Format: $X, $Y, $Z
        tickers = [p.get('ticker', '') if isinstance(p, dict) else str(p) for p in possibilities[:3]]
        tickers = [t for t in tickers if t]  # Filter empty
        if tickers:
            return ", ".join(tickers)
    
    # Infer from project name if no possibilities
    name = project.get('project_name', '')
    if name:
        # Generate common ticker patterns
        name_clean = name.replace(' ', '').upper()
        suggestions = []
        
        # Full name short version (first 4-5 chars)
        if len(name_clean) >= 3:
            suggestions.append(f"${name_clean[:4]}")
        
        # Initials
        words = name.split()
        if len(words) >= 2:
            initials = ''.join(w[0].upper() for w in words if w)
            if len(initials) >= 2:
                suggestions.append(f"${initials}")
        
        # First 3 letters
        if len(name_clean) >= 3:
            suggestions.append(f"${name_clean[:3]}")
        
        return ", ".join(suggestions[:3]) if suggestions else None
    
    return None


def format_alert_message(alert_type: str, projects: List[Dict], favorites_handles: List[str] = None) -> str:
    """Format alert message with time remaining, grouped by chain.
    Shows FAVORITES section first if any favorited projects are launching.
    """
    
    if not projects:
        return None
    
    favorites_handles = favorites_handles or []
    favorites_set = set(h.lower().lstrip('@') for h in favorites_handles)
    
    # Header based on alert type
    if alert_type == 'imminent':
        header = "🚨 LAUNCHING NOW / IMMINENT"
    elif alert_type == 'today':
        header = "📅 LAUNCHING TODAY"
    elif alert_type == '24h':
        header = "⏰ LAUNCHING IN 24 HOURS"
    elif alert_type == '7d':
        header = "📆 LAUNCHING IN 7 DAYS"
    else:
        header = "🚀 LAUNCH ALERT"
    
    # Separate favorites from regular projects
    favorites_projects = []
    regular_projects = []
    
    for p in projects:
        handle = (p.get('twitter_handle') or '').lower().lstrip('@')
        if handle in favorites_set:
            favorites_projects.append(p)
        else:
            regular_projects.append(p)
    
    # Group regular by chain
    grouped = group_by_chain(regular_projects)
    
    # Build message
    lines = [
        f"<b>{header}</b> ({len(projects)} projects)",
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    ]
    
    # FAVORITES section first (if any) - simple format without bullets/links
    if favorites_projects:
        # Show count only if more than 1
        if len(favorites_projects) > 1:
            lines.append(f"\n❤️ <b>FAVORITES</b> ({len(favorites_projects)})")
        else:
            lines.append(f"\n❤️ <b>FAVORITES</b>")
        for p in favorites_projects:
            handle = p.get('twitter_handle', '').lstrip('@')
            chain = (p.get('chain') or 'unknown').upper()
            # Simple format: @handle - CHAIN (no bullets, no links, no extra info)
            lines.append(f"@{handle} - {chain}")
    
    # Chain sections
    for chain in sorted(grouped.keys()):
        chain_projects = grouped[chain]
        emoji = get_chain_emoji(chain)
        
        lines.append(f"\n{emoji} <b>{chain.upper()}</b> ({len(chain_projects)})")
        
        for p in chain_projects:
            handle = p.get('twitter_handle', '').lstrip('@')
            name = p.get('project_name', '') or ''
            ticker = p.get('project_ticker', '')
            launch_time = format_launch_time(p.get('launch_time'))
            time_remaining = calculate_time_remaining(
                p.get('launch_date'),
                p.get('launch_time')
            )
            platform = p.get('launch_platform', '')
            launch_date = p.get('launch_date', '')
            
            # Line 1: Handle + Name + Ticker
            line1 = f"• <a href=\"https://x.com/{handle}\">@{handle}</a>"
            if name:
                line1 += f" | {name}"
            if ticker:
                line1 += f" | {ticker}"
            lines.append(line1)
            
            # Line 2: Date (if >24h) + Time + Remaining + Platform
            if alert_type in ['7d', '24h'] and launch_date:
                # Show date for future launches
                try:
                    from datetime import datetime
                    dt = datetime.strptime(launch_date, '%Y-%m-%d')
                    date_str = dt.strftime('%b %d')  # "Dec 14"
                    line2 = f"  📅 {date_str} | 🕐 {launch_time} | ⏰ {time_remaining}"
                except:
                    line2 = f"  🕐 {launch_time} | ⏰ {time_remaining}"
            else:
                line2 = f"  🕐 {launch_time} | ⏰ {time_remaining}"
            
            if platform:
                line2 += f" | {platform}"
            lines.append(line2)
            
            # Line 3: Possible tickers (only if no confirmed ticker)
            if not ticker:
                possible = get_possible_tickers(p)
                if possible:
                    lines.append(f"  💭 Possible: {possible}")
    
    return "\n".join(lines)


def send_telegram_alert(message: str) -> bool:
    """Send alert to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ALERT_CHAT_ID:
        log("[WARN] Telegram not configured")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": TELEGRAM_ALERT_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        log(f"[ERROR] Send failed: {str(e)[:50]}")
        return False


async def publish_to_redis(redis_client, alert_type: str, projects: List[Dict]):
    """Publish alert to Redis for other services."""
    try:
        data = {
            'alert_type': alert_type,
            'projects_count': len(projects),
            'projects': [
                {
                    'twitter_handle': p.get('twitter_handle'),
                    'project_name': p.get('project_name'),
                    'chain': p.get('chain'),
                    'launch_date': p.get('launch_date'),
                    'launch_time': p.get('launch_time')
                }
                for p in projects
            ],
            'timestamp': datetime.now().isoformat()
        }
        
        await redis_client.publish(f'calendar:alert:{alert_type}', json.dumps(data))
        
    except Exception as e:
        log(f"[ERROR] Redis publish: {str(e)[:50]}")


async def check_and_send_alerts(redis_client):
    """Check calendar and send alerts."""
    log("Checking for alerts...")
    
    alerts_sent = 0
    
    # Get all favorited handles (used to highlight in alerts)
    favorited_handles = get_all_favorited_handles()
    if favorited_handles:
        log(f"[FAVORITES] {len(favorited_handles)} handles favorited")
    
    # 1. Check imminent launches
    imminent = get_calendar_pending_alerts('imminent')
    if imminent:
        log(f"[IMMINENT] {len(imminent)} projects")
        message = format_alert_message('imminent', imminent, favorited_handles)
        if message and send_telegram_alert(message):
            for p in imminent:
                mark_calendar_alert_sent(p['id'], 'imminent')
            alerts_sent += 1
            await publish_to_redis(redis_client, 'imminent', imminent)
        time.sleep(RATE_LIMIT_SECONDS)
    
    # 2. Check today's launches
    today = get_calendar_pending_alerts('today')
    if today:
        log(f"[TODAY] {len(today)} projects")
        message = format_alert_message('today', today, favorited_handles)
        if message and send_telegram_alert(message):
            for p in today:
                mark_calendar_alert_sent(p['id'], 'today')
            alerts_sent += 1
            await publish_to_redis(redis_client, 'today', today)
        time.sleep(RATE_LIMIT_SECONDS)
    
    # 3. Check 24h launches
    tomorrow = get_calendar_pending_alerts('24h')
    if tomorrow:
        log(f"[24H] {len(tomorrow)} projects")
        message = format_alert_message('24h', tomorrow, favorited_handles)
        if message and send_telegram_alert(message):
            for p in tomorrow:
                mark_calendar_alert_sent(p['id'], '24h')
            alerts_sent += 1
            await publish_to_redis(redis_client, '24h', tomorrow)
        time.sleep(RATE_LIMIT_SECONDS)
    
    # 4. Check 7d launches (weekly digest)
    week = get_calendar_pending_alerts('7d')
    if week:
        log(f"[7D] {len(week)} projects")
        message = format_alert_message('7d', week, favorited_handles)
        if message and send_telegram_alert(message):
            for p in week:
                mark_calendar_alert_sent(p['id'], '7d')
            alerts_sent += 1
            await publish_to_redis(redis_client, '7d', week)
    
    return alerts_sent


async def main():
    log("=" * 60)
    log("Calendar Alerter Service Starting")
    log(f"Redis: {REDIS_URL}")
    log(f"Check interval: {CHECK_INTERVAL_MINUTES} minutes")
    log(f"Alert chat: {TELEGRAM_ALERT_CHAT_ID or 'NOT CONFIGURED'}")
    log("=" * 60)
    
    # Initialize database
    init_db()
    
    # Connect to Redis
    redis_client = await redis.from_url(REDIS_URL)
    
    # Initial stats
    stats = get_calendar_stats()
    log(f"Calendar stats: {stats}")
    
    # Main loop
    while True:
        try:
            alerts_sent = await check_and_send_alerts(redis_client)
            
            if alerts_sent > 0:
                log(f"[DONE] Sent {alerts_sent} alert batches")
            else:
                log("[DONE] No alerts to send")
            
            # Update stats
            stats = get_calendar_stats()
            log(f"[STATS] today={stats.get('launching_today', 0)} | week={stats.get('launching_this_week', 0)} | total={stats.get('total', 0)}")
            
        except Exception as e:
            log(f"[ERROR] {str(e)}")
        
        # Wait for next check
        log(f"Next check in {CHECK_INTERVAL_MINUTES} minutes...")
        await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)


if __name__ == '__main__':
    asyncio.run(main())

