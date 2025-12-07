# services/telegram/formatter.py
"""
Telegram Message Formatter
COMPLETE data, no truncation, HTML formatting, emojis, compact inline format.
Returns both message text and inline keyboard buttons.
"""

import json
from typing import Dict, Any, List, Tuple, Optional


def safe_get(data: Dict, *keys, default=""):
    """Safely get nested dict value."""
    val = data
    for key in keys:
        if isinstance(val, dict):
            val = val.get(key, default)
        else:
            return default
    return val if val is not None else default


def format_list(items: Any) -> str:
    """Format list or JSON string to readable format."""
    if not items:
        return "None"
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except:
            return items
    if isinstance(items, list):
        if len(items) == 0:
            return "None"
        return ", ".join(str(i) for i in items)
    return str(items)


def format_bool(val: Any) -> str:
    """Format boolean to Yes/No."""
    if val in [True, 1, "1", "true", "True", "yes", "Yes"]:
        return "Yes"
    return "No"


def format_number(val: Any) -> str:
    """Format number with commas."""
    try:
        num = int(val) if val else 0
        return f"{num:,}"
    except:
        return str(val) if val else "0"


def build_buttons(
    tweet_url: str = None,
    profile_url: str = None,
    twitter_handle: str = None,
    tweet_id: str = None,
    show_delete: bool = False
) -> List[List[Dict]]:
    """Build inline keyboard buttons."""
    buttons = []
    row1 = []
    
    # Build URLs if not provided
    if not tweet_url and tweet_id and twitter_handle:
        handle = twitter_handle.lstrip('@')
        tweet_url = f"https://x.com/{handle}/status/{tweet_id}"
    
    if not profile_url and twitter_handle:
        handle = twitter_handle.lstrip('@')
        profile_url = f"https://x.com/{handle}"
    
    # Row 1: View Tweet + View Profile
    if tweet_url:
        row1.append({"text": "🔗 Ver Tweet", "url": tweet_url})
    if profile_url:
        row1.append({"text": "👤 Ver Perfil", "url": profile_url})
    
    if row1:
        buttons.append(row1)
    
    # Row 2: Delete Monitoring (only for Stage 3)
    if show_delete and twitter_handle:
        handle = twitter_handle.lstrip('@')
        buttons.append([
            {"text": "❌ Deletar Monitoramento", "callback_data": f"delete_monitor:{handle}"}
        ])
    
    return buttons


# ============================================
# STAGE 0: COLLECTOR
# ============================================

def format_tweet_collected(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format individual tweet collected message with buttons."""
    author = data.get('author_username', '')
    author_name = data.get('author_name', '')
    url = data.get('url', '')
    text = data.get('text', '')
    tweet_id = data.get('id', '')
    
    view_count = format_number(data.get('view_count', 0))
    like_count = format_number(data.get('like_count', 0))
    retweet_count = format_number(data.get('retweet_count', 0))
    reply_count = format_number(data.get('reply_count', 0))
    
    followers = format_number(data.get('author_followers', 0))
    following = format_number(data.get('author_following', 0))
    tweets = format_number(data.get('author_statuses_count', 0))
    media = format_number(data.get('author_media_count', 0))
    blue = format_bool(data.get('author_is_blue_verified'))
    
    bio = data.get('author_description', '') or ''
    batch = data.get('batch_name', data.get('query_used', ''))
    
    # Calculate account age
    account_age = "?"
    created = data.get('author_created_at', '')
    if created:
        try:
            from datetime import datetime
            created_dt = datetime.strptime(created.split()[0] + " " + created.split()[1] + " " + created.split()[2] + " " + created.split()[5], "%a %b %d %Y")
            age_days = (datetime.now() - created_dt).days
            account_age = str(age_days)
        except:
            pass
    
    message = f"""📥 <b>TWEET COLLECTED</b>
━━━━━━━━━━━━━━━━━━━━━━━━
👤 @{author} | {author_name}
📝 <b>TWEET</b>
{text}
📊 👁 {view_count} | ❤️ {like_count} | 🔁 {retweet_count} | 💬 {reply_count}
👤 Followers: {followers} | Following: {following} | Tweets: {tweets}
Age: {account_age}d | Media: {media} | Blue: {blue}
📋 <b>BIO</b>
{bio}
🏷️ Batch: {batch}
→ Sent to Stage 1 (Triage)"""

    buttons = build_buttons(
        tweet_url=url,
        twitter_handle=author,
        tweet_id=tweet_id
    )
    
    return message, buttons


# ============================================
# STAGE 1: TRIAGE
# ============================================

def format_project_triaged(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format triaged project message with buttons."""
    handle = data.get('twitter_handle', '').lstrip('@')
    project_name = data.get('project_name', '') or 'Unknown'
    project_ticker = data.get('project_ticker', '')
    project_chain = data.get('project_chain', '') or data.get('chain', '') or 'unknown'
    project_type = data.get('project_type', '') or data.get('type', '') or 'unknown'
    confidence = data.get('confidence', 0)
    followers = format_number(data.get('author_followers', 0))
    
    # Launch info
    launch_status = data.get('launch_status', '') or 'unknown'
    launch_date = data.get('launch_date', '') or 'TBA'
    launch_time = data.get('launch_time', '') or ''
    launch_platform = data.get('launch_platform', '') or ''
    
    # Signals
    keywords_raw = data.get('keywords_found', [])
    # Replace alphagate_discovery with discovery_alpha
    if isinstance(keywords_raw, list):
        keywords_raw = ['discovery_alpha' if k == 'alphagate_discovery' else k for k in keywords_raw]
    keywords = format_list(keywords_raw)
    has_ca = format_bool(data.get('has_ca'))
    ca_address = data.get('ca_address', '') or ''
    
    # Links
    telegram = data.get('telegram_link', '') or 'None'
    website = data.get('website_link', '') or 'None'
    
    # Mentions
    tagged_accounts = format_list(data.get('tagged_accounts', []))
    tagged_chains = format_list(data.get('tagged_chains', []))
    
    # Source
    source_tweet_id = data.get('source_tweet_id', '') or data.get('tweet_id', '')
    tweet_preview = data.get('tweet_text_preview', '') or ''
    
    ticker_str = f" | ${project_ticker}" if project_ticker else ""
    time_str = f" | {launch_time}" if launch_time else ""
    platform_str = f" | Platform: {launch_platform}" if launch_platform else ""
    
    message = f"""✅ <b>PROJECT TRIAGED</b>
━━━━━━━━━━━━━━━━━━━━━━━━
👤 <a href="https://x.com/{handle}">@{handle}</a> | {project_name}{ticker_str}
🔗 Chain: {project_chain} | Type: {project_type} | Conf: {confidence:.2f}
👥 Followers: {followers}
🚀 <b>LAUNCH</b>
Status: {launch_status} | Date: {launch_date}{time_str}{platform_str}
🔍 <b>SIGNALS</b>
Keywords: {keywords}
CA: {has_ca} | Address: {ca_address}
📱 TG: {telegram} | Web: {website}
👥 Tags: {tagged_accounts}
🔗 Chains: {tagged_chains}
📝 <b>TWEET</b>
{tweet_preview}
→ Sent to Stage 2 (Verification)"""

    buttons = build_buttons(
        twitter_handle=handle,
        tweet_id=source_tweet_id
    )
    
    return message, buttons


def format_tweet_rejected(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format rejected tweet message with buttons."""
    handle = data.get('twitter_handle', '').lstrip('@')
    tweet_id = data.get('tweet_id', '')
    confidence = data.get('confidence', 0)
    reason = data.get('rejection_reason', '') or data.get('reason', '') or 'unclear'
    
    tweet_text = data.get('input_tweet_text', '') or data.get('tweet_text', '') or ''
    followers = format_number(data.get('input_followers', 0) or data.get('author_followers', 0))
    
    reasoning = data.get('llm_reasoning', '') or ''
    
    message = f"""❌ <b>TWEET REJECTED</b>
━━━━━━━━━━━━━━━━━━━━━━━━
👤 @{handle} | Conf: {confidence:.2f} | Reason: {reason}
👥 Followers: {followers}
📝 <b>TWEET</b>
{tweet_text}
🤖 <b>REASONING</b>
{reasoning}"""

    buttons = build_buttons(
        twitter_handle=handle,
        tweet_id=tweet_id
    )
    
    return message, buttons


# ============================================
# STAGE 2: VERIFICATION
# ============================================

def format_key_followers(key_followers: list) -> str:
    """Format ALL key followers as HTML with clickable links. No limit."""
    if not key_followers:
        return "None"
    
    lines = []
    for f in key_followers:  # No limit - show ALL
        username = f.get('username', 'unknown')
        followers = f.get('public_metrics', {}).get('followers_count', 0)
        parent = f.get('parent')
        star = "⭐" if parent else ""
        lines.append(f'<a href="https://x.com/{username}">@{username}</a> ({followers:,}) {star}')
    
    return "\n".join(lines)


def format_alpha_hunters(alpha_hunters: list) -> str:
    """Format ALL alpha hunters as HTML with performance stats. No limit."""
    if not alpha_hunters:
        return "None"
    
    lines = []
    for h in alpha_hunters:  # No limit - show ALL
        username = h.get('username', 'unknown')
        followers = h.get('followers_count', 0)
        perf = h.get('performance', {})
        winrate = perf.get('winrate', 0)
        wins = perf.get('wins', 0)
        losses = perf.get('losses', 0)
        lines.append(f'<a href="https://x.com/{username}">@{username}</a> ({followers:,}) | WR: {winrate:.1f}% ({wins}W/{losses}L)')
    
    return "\n".join(lines)


def format_project_confirmed(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format confirmed project message with buttons."""
    handle = data.get('twitter_handle', '').lstrip('@')
    project_name = data.get('project_name', '') or 'Unknown'
    project_ticker = data.get('project_ticker', '')
    project_chain = data.get('project_chain', '') or 'unknown'
    project_type = data.get('project_type', '') or 'unknown'
    confidence = data.get('verification_confidence', 0)
    
    # Profile
    user_profile = data.get('user_profile', {}) or {}
    followers = format_number(user_profile.get('followers', 0) or data.get('followers', 0))
    following = format_number(user_profile.get('following', 0) or data.get('following', 0))
    account_age = user_profile.get('account_age_days', 0) or data.get('account_age_days', 0)
    total_tweets = format_number(user_profile.get('total_tweets', 0) or data.get('total_tweets', 0))
    media_count = format_number(user_profile.get('media_count', 0) or data.get('media_count', 0))
    blue = format_bool(user_profile.get('is_blue_verified') or data.get('is_blue_verified'))
    
    # Bio
    bio = user_profile.get('bio', '') or data.get('bio', '') or ''
    
    # Tweet analysis
    tweet_analysis = data.get('tweet_analysis', {}) or {}
    tweets_analyzed = tweet_analysis.get('tweets_analyzed', 0) or data.get('tweets_analyzed', 0)
    crypto_count = tweet_analysis.get('crypto_related_count', 0) or data.get('crypto_related_count', 0)
    spam_score = tweet_analysis.get('spam_score', 0) or data.get('spam_score', 0)
    
    # Signals
    signals = data.get('verification_signals', {}) or {}
    consistent = format_bool(signals.get('consistent_project_messaging') or data.get('consistent_project_messaging'))
    pinned = format_bool(signals.get('has_pinned_tweet_about_project') or data.get('has_pinned_tweet_about_project'))
    
    # Links
    website = user_profile.get('website_url', '') or data.get('website_url', '') or 'None'
    telegram = user_profile.get('telegram_url', '') or data.get('telegram_url', '') or 'None'
    discord = user_profile.get('discord_url', '') or data.get('discord_url', '') or 'None'
    
    # Site analysis
    site = data.get('site_analysis', {}) or {}
    site_url = site.get('url', '') or data.get('site_url', '') or ''
    site_access = format_bool(site.get('accessible') or data.get('site_accessible'))
    site_wp = format_bool(site.get('has_whitepaper') or data.get('site_has_whitepaper'))
    site_token = format_bool(site.get('has_tokenomics') or data.get('site_has_tokenomics'))
    site_road = format_bool(site.get('has_roadmap') or data.get('site_has_roadmap'))
    site_team = format_bool(site.get('has_team') or data.get('site_has_team'))
    
    # AlphaGate enrichment data
    key_followers = data.get('key_followers', [])
    key_followers_count = data.get('key_followers_count', 0)
    alpha_hunters = data.get('alpha_hunters', [])
    alpha_hunters_count = data.get('alpha_hunters_count', 0)
    followers_when_found = data.get('followers_when_found', 0)
    best_winrate = data.get('best_hunter_winrate', 0)
    found_in_alphagate = data.get('found_in_alphagate', False)
    
    # Reasoning
    reasoning = data.get('reasoning', '') or ''
    
    ticker_str = f" | ${project_ticker}" if project_ticker else ""
    
    # Build key followers section
    key_followers_str = format_key_followers(key_followers)
    alpha_hunters_str = format_alpha_hunters(alpha_hunters)
    
    # AlphaGate alerts data
    alphagate_bio_changes = data.get('alphagate_bio_changes', 0)
    alphagate_username_changes = data.get('alphagate_username_changes', 0)
    alphagate_website_added = data.get('alphagate_website_added', False)
    
    # AlphaGate section
    alphagate_section = ""
    if found_in_alphagate:
        website_str = "✅" if alphagate_website_added else "❌"
        alphagate_section = f"""
🔑 <b>KEY FOLLOWERS ({key_followers_count})</b>
{key_followers_str}
📊 <b>ALPHA HUNTERS ({alpha_hunters_count})</b>
{alpha_hunters_str}
📈 Found with {followers_when_found} followers | Best WR: {best_winrate:.1f}%
📝 Bio changes: {alphagate_bio_changes} | Username changes: {alphagate_username_changes} | Website: {website_str}"""
    
    message = f"""✅ <b>PROJECT CONFIRMED</b>
━━━━━━━━━━━━━━━━━━━━━━━━
👤 <a href="https://x.com/{handle}">@{handle}</a> | {project_name}{ticker_str}
🔗 Chain: {project_chain} | Type: {project_type} | Conf: {confidence:.2f}
👤 <b>PROFILE</b>
Followers: {followers} | Following: {following} | Age: {account_age}d
Tweets: {total_tweets} | Media: {media_count} | Blue: {blue}
📋 <b>BIO</b>
{bio}
🐦 <b>TWEETS</b>
Analyzed: {tweets_analyzed} | Crypto: {crypto_count} | Spam: {spam_score:.2f}
✅ <b>SIGNALS</b>
Consistent: {consistent} | Pinned: {pinned}
📱 <b>LINKS</b>
Web: {website} | TG: {telegram} | Discord: {discord}
🌐 <b>SITE</b>
URL: {site_url} | Access: {site_access}
WP: {site_wp} | Token: {site_token} | Road: {site_road} | Team: {site_team}{alphagate_section}
🤖 <b>REASONING</b>
{reasoning}
→ Sent to Stage 3 (Monitoring)"""

    buttons = build_buttons(twitter_handle=handle)
    
    return message, buttons


def format_project_rejected_verification(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format rejected project from verification with buttons."""
    handle = data.get('twitter_handle', '')
    reason = data.get('rejection_reason', '') or 'unknown'
    confidence = data.get('verification_confidence', 0)
    
    # Profile
    user_profile = data.get('user_profile', {}) or {}
    followers = format_number(user_profile.get('followers', 0) or data.get('followers', 0))
    following = format_number(user_profile.get('following', 0) or data.get('following', 0))
    account_age = user_profile.get('account_age_days', 0) or data.get('account_age_days', 0)
    total_tweets = format_number(user_profile.get('total_tweets', 0) or data.get('total_tweets', 0))
    blue = format_bool(user_profile.get('is_blue_verified') or data.get('is_blue_verified'))
    
    # Bio
    bio = user_profile.get('bio', '') or data.get('bio', '') or ''
    
    # Tweet analysis
    tweet_analysis = data.get('tweet_analysis', {}) or {}
    tweets_analyzed = tweet_analysis.get('tweets_analyzed', 0) or data.get('tweets_analyzed', 0)
    crypto_count = tweet_analysis.get('crypto_related_count', 0) or data.get('crypto_related_count', 0)
    spam_score = tweet_analysis.get('spam_score', 0) or data.get('spam_score', 0)
    
    # Reasoning
    reasoning = data.get('reasoning', '') or ''
    
    message = f"""❌ <b>PROJECT REJECTED</b>
━━━━━━━━━━━━━━━━━━━━━━━━
👤 @{handle} | Reason: {reason} | Conf: {confidence:.2f}
👤 <b>PROFILE</b>
Followers: {followers} | Following: {following} | Age: {account_age}d
Tweets: {total_tweets} | Blue: {blue}
📋 <b>BIO</b>
{bio}
🐦 Analyzed: {tweets_analyzed} | Crypto: {crypto_count} | Spam: {spam_score:.2f}
🤖 <b>REASONING</b>
{reasoning}"""

    buttons = build_buttons(twitter_handle=handle)
    
    return message, buttons


# ============================================
# STAGE 3: MONITORING
# ============================================

def format_project_monitored(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format monitored project update - COMPACT but COMPLETE."""
    handle = data.get('twitter_handle', '').lstrip('@')
    project_name = data.get('project_name', '') or 'Unknown'
    project_chain = data.get('project_chain', '') or '?'
    
    # Status
    status_before = data.get('status_before', '') or 'active'
    status_after = data.get('status_after', '') or data.get('status', '') or status_before
    priority_before = data.get('priority_before', '') or 'low'
    priority_after = data.get('priority_after', '') or data.get('priority', '') or priority_before
    urgency = data.get('launch_urgency', '') or '?'
    
    # Followers
    followers = format_number(data.get('followers', 0) or data.get('followers_current', 0))
    followers_change = data.get('followers_change', 0)
    change_str = f"+{followers_change}" if followers_change > 0 else str(followers_change)
    growth = data.get('followers_growth', 0)
    growth_str = f" ({growth:+.1f}%)" if growth else ""
    
    # Activity
    new_tweets = data.get('new_tweets_count', 0)
    inactive_days = data.get('inactive_days', 0)
    activity = data.get('activity_level', '') or ('🔴' if inactive_days > 7 else '🟢' if new_tweets > 3 else '🟡')
    
    # Last tweet (compact)
    last_tweet_text = data.get('last_tweet_text', '') or ''
    last_tweet_preview = last_tweet_text[:100] + "..." if len(last_tweet_text) > 100 else last_tweet_text
    
    # Launch/CA detection
    ca_detected = data.get('ca_mentioned') or data.get('ca_detected')
    ca_address = data.get('ca_address', '') or ''
    ca_source = data.get('ca_source', '') or ''
    launch_date = data.get('launch_date_detected', '') or data.get('launch_date_mentioned', '') or ''
    
    # Site
    site_access = "✅" if data.get('site_accessible') else "❌"
    site_changed = "📝" if data.get('site_changed') else ""
    site_ca = "💎" if data.get('site_ca_found') else ""
    
    # Bio changes
    bio_changed = data.get('bio_changed', False)
    bio_new = data.get('bio_new', '') or ''
    pinned_changed = data.get('pinned_changed', False)
    
    # Changes list
    changes = data.get('changes_detected', []) or data.get('changes', [])
    changes_str = ", ".join(changes) if changes else "None"
    
    # AI Summary (compact)
    ai_analysis = data.get('ai_analysis', '') or data.get('summary', '') or ''
    ai_preview = ai_analysis[:200] + "..." if len(ai_analysis) > 200 else ai_analysis
    
    # AlphaGate data
    found_in_alphagate = data.get('found_in_alphagate', False)
    key_followers = data.get('key_followers', [])
    key_followers_count = data.get('key_followers_count', 0)
    alpha_hunters = data.get('alpha_hunters', [])
    alpha_hunters_count = data.get('alpha_hunters_count', 0)
    followers_when_found = data.get('followers_when_found', 0)
    best_winrate = data.get('best_hunter_winrate', 0)
    ag_bio_changes = data.get('alphagate_bio_changes', 0)
    ag_username_changes = data.get('alphagate_username_changes', 0)
    
    # Build CA line
    ca_line = "❌ No"
    if ca_detected and ca_address:
        ca_line = f"✅ <code>{ca_address[:20]}...</code> ({ca_source})"
    elif ca_detected:
        ca_line = "✅ Detected"
    
    # Build launch line
    launch_line = f"📅 {launch_date}" if launch_date else "📅 TBA"
    
    # Build bio section (only if changed)
    bio_section = ""
    if bio_changed and bio_new:
        bio_preview = bio_new[:150] + "..." if len(bio_new) > 150 else bio_new
        bio_section = f"\n📝 <b>NEW BIO:</b> {bio_preview}"
    
    # Build AlphaGate section (compact)
    ag_section = ""
    if found_in_alphagate:
        # Key followers - compact (top 5 with links)
        kf_parts = []
        for f in key_followers[:5]:
            username = f.get('username', '?')
            f_count = f.get('public_metrics', {}).get('followers_count', 0)
            star = "⭐" if f.get('parent') else ""
            kf_parts.append(f'<a href="https://x.com/{username}">@{username}</a>({f_count:,}){star}')
        kf_str = " | ".join(kf_parts) if kf_parts else "None"
        kf_more = f" +{key_followers_count - 5} more" if key_followers_count > 5 else ""
        
        # Alpha hunters - compact (top 5 with WR)
        ah_parts = []
        for h in alpha_hunters[:5]:
            username = h.get('username', '?')
            perf = h.get('performance', {})
            wr = perf.get('winrate', 0)
            ah_parts.append(f'<a href="https://x.com/{username}">@{username}</a>({wr:.0f}%)')
        ah_str = " | ".join(ah_parts) if ah_parts else "None"
        ah_more = f" +{alpha_hunters_count - 5} more" if alpha_hunters_count > 5 else ""
        
        ag_section = f"""
🔑 <b>KEY({key_followers_count})</b> {kf_str}{kf_more}
📊 <b>HUNTERS({alpha_hunters_count})</b> {ah_str}{ah_more}
📈 Found@{followers_when_found} | BestWR:{best_winrate:.1f}% | ΔBio:{ag_bio_changes} ΔUser:{ag_username_changes}"""
    
    message = f"""🔄 <b>MONITORED</b> | <a href="https://x.com/{handle}">@{handle}</a>
━━━━━━━━━━━━━━━━━━
📛 {project_name} | {project_chain}
📊 {status_before}→{status_after} | {priority_before}→{priority_after} | ⏰{urgency}
👥 {followers} ({change_str}){growth_str} | 🐦{new_tweets} | {activity} {inactive_days}d
🚀 CA: {ca_line} | {launch_line}
🌐 Site:{site_access}{site_changed}{site_ca}{bio_section}{ag_section}
📋 <b>CHANGES:</b> {changes_str}
💬 {last_tweet_preview}
🤖 {ai_preview}"""

    buttons = build_buttons(twitter_handle=handle, show_delete=True)
    return message, buttons


def format_launch_alert(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format launch alert with buttons."""
    handle = data.get('twitter_handle', '')
    project_name = data.get('project_name', '') or 'Unknown'
    project_chain = data.get('project_chain', '') or 'unknown'
    urgency = data.get('launch_urgency', '') or 'unknown'
    priority = data.get('priority', '') or 'medium'
    
    hours = data.get('estimated_hours_until_launch', '')
    hours_str = f" | Est: {hours}h" if hours else ""
    
    launch_date = data.get('launch_date_mentioned', '') or ''
    summary = data.get('summary', '') or ''
    
    changes = format_list(data.get('changes_detected', []))
    
    followers = format_number(data.get('followers_current', 0))
    followers_change = data.get('followers_change', 0)
    change_str = f"+{followers_change}" if followers_change > 0 else str(followers_change)
    
    message = f"""⚠️ <b>LAUNCH ALERT</b>
━━━━━━━━━━━━━━━━━━━━━━━━
👤 @{handle} | {project_name} | {project_chain}
🚨 Urgency: {urgency} | Priority: {priority}{hours_str}
📅 Launch: {launch_date}
👥 Followers: {followers} ({change_str})
📋 <b>CHANGES</b>
{changes}
📊 <b>SUMMARY</b>
{summary}
⚡ ACTION: Monitor closely for CA"""

    buttons = build_buttons(
        twitter_handle=handle,
        show_delete=True
    )
    
    return message, buttons


def format_project_launched(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format project launched message with buttons."""
    handle = data.get('twitter_handle', '')
    project_name = data.get('project_name', '') or 'Unknown'
    project_chain = data.get('project_chain', '') or 'unknown'
    
    ca_address = data.get('ca_address', '') or 'Not detected'
    ca_source = data.get('ca_source', '') or ''
    
    summary = data.get('summary', '') or ''
    
    source_str = f" ({ca_source})" if ca_source else ""
    
    message = f"""🚀 <b>PROJECT LAUNCHED!</b>
━━━━━━━━━━━━━━━━━━━━━━━━
👤 @{handle} | {project_name} | {project_chain}
💎 <b>CONTRACT ADDRESS</b>
{ca_address}{source_str}
📊 <b>SUMMARY</b>
{summary}
⚡ ACTION: Check DEX for trading"""

    buttons = build_buttons(
        twitter_handle=handle,
        show_delete=True
    )
    
    return message, buttons


def format_project_abandoned(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format project abandoned message with buttons."""
    handle = data.get('twitter_handle', '')
    project_name = data.get('project_name', '') or 'Unknown'
    project_chain = data.get('project_chain', '') or 'unknown'
    
    inactive_days = data.get('inactive_days', 0)
    last_tweet = data.get('last_tweet_at', '') or 'Unknown'
    last_tweet_text = data.get('last_tweet_text', '') or ''
    followers = format_number(data.get('followers_current', 0) or data.get('followers', 0))
    followers_change = data.get('followers_change', 0)
    change_str = f"+{followers_change}" if followers_change > 0 else str(followers_change)
    
    ai_analysis = data.get('ai_analysis', '') or data.get('summary', '') or ''
    
    message = f"""💀 <b>PROJECT ABANDONED</b>
━━━━━━━━━━━━━━━━━━━━━━━━
👤 @{handle} | {project_name} | {project_chain}
📊 Inactive: {inactive_days}d | Followers: {followers} ({change_str})
📅 Last: {last_tweet}
{last_tweet_text}
🤖 <b>AI ANALYSIS</b>
{ai_analysis}
🚫 Removed from monitoring"""

    buttons = build_buttons(twitter_handle=handle)
    
    return message, buttons


# ============================================
# ABANDONED CHECKER
# ============================================

def format_project_removed(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format project removed from monitoring message."""
    handle = data.get('twitter_handle', '')
    project_name = data.get('project_name', '') or 'Unknown'
    project_chain = data.get('project_chain', '') or 'unknown'
    inactive_days = data.get('inactive_days', 0)
    reason = data.get('reason', '') or f'{inactive_days} days without posting'
    
    message = f"""🚫 <b>PROJECT REMOVED</b>
━━━━━━━━━━━━━━━━━━━━━━━━
👤 @{handle} | {project_name} | {project_chain}
📊 Inactive: {inactive_days} days
📝 Reason: {reason}
⛔ Stopped monitoring permanently"""

    buttons = build_buttons(twitter_handle=handle)
    
    return message, buttons


def format_project_reactivated(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format project reactivated message."""
    handle = data.get('twitter_handle', '')
    project_name = data.get('project_name', '') or 'Unknown'
    project_chain = data.get('project_chain', '') or 'unknown'
    inactive_days = data.get('inactive_days', 0)
    reason = data.get('reason', '') or 'Posted recently'
    
    message = f"""✅ <b>PROJECT REACTIVATED</b>
━━━━━━━━━━━━━━━━━━━━━━━━
👤 @{handle} | {project_name} | {project_chain}
📊 Last post: {inactive_days} days ago
📝 Reason: {reason}
🔄 Monitoring resumed"""

    buttons = build_buttons(
        twitter_handle=handle,
        show_delete=True
    )
    
    return message, buttons


# ============================================
# MENTIONS (Influencer tweets about projects)
# ============================================

def format_mention_detected(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format mention detected message with buttons."""
    source_author = data.get('source_author_handle', '')
    source_followers = format_number(data.get('source_author_followers', 0))
    tweet_text = data.get('source_tweet_text', '') or ''
    tweet_id = data.get('source_tweet_id', '')
    
    mentioned_handle = data.get('mentioned_handle', '')
    project_name = data.get('project_name_extracted', '') or 'Unknown'
    project_chain = data.get('project_chain_extracted', '') or 'unknown'
    project_ticker = data.get('project_ticker_extracted', '')
    
    # Name/Ticker possibilities
    name_poss = format_list(data.get('name_possibilities', []))
    ticker_poss = format_list(data.get('ticker_possibilities', []))
    
    launch_date = data.get('launch_date_mentioned', '') or 'TBA'
    mention_type = data.get('mention_type', '') or data.get('author_type', '') or 'shill'
    confidence = data.get('confidence', 0)
    
    ticker_str = f" | ${project_ticker}" if project_ticker else ""
    
    message = f"""📢 <b>MENTION DETECTED</b>
━━━━━━━━━━━━━━━━━━━━━━━━
👤 Author: @{source_author} ({source_followers} followers)
🏷️ Type: {mention_type} | Conf: {confidence:.2f}
📝 <b>TWEET</b>
{tweet_text}

🎯 <b>PROJECT MENTIONED</b>
Handle: @{mentioned_handle}
Name: {project_name}{ticker_str}
Chain: {project_chain}
Launch: {launch_date}

📋 <b>POSSIBILITIES</b>
Names: {name_poss}
Tickers: {ticker_poss}

🔍 Status: Pending investigation
→ Will be investigated in Discovery Stage"""

    buttons = [
        [
            {"text": "🔗 Ver Tweet", "url": f"https://x.com/{source_author}/status/{tweet_id}"},
            {"text": "🎯 Ver Projeto", "url": f"https://x.com/{mentioned_handle}"}
        ]
    ]
    
    return message, buttons


def format_project_discovered(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format discovered project message with buttons."""
    handle = data.get('handle', '') or data.get('twitter_handle', '')
    project_name = data.get('project_name', '') or 'Unknown'
    project_chain = data.get('project_chain', '') or 'unknown'
    status = data.get('status', '') or data.get('discovery_status', '')
    confidence = data.get('confidence', 0)
    
    mention_count = data.get('mention_count', 0)
    reasoning = data.get('reasoning', '') or ''
    
    # Determine emoji based on status
    if status == 'confirmed_project':
        emoji = "✅"
        status_text = "CONFIRMED"
    elif status.startswith('rejected'):
        emoji = "❌"
        status_text = "REJECTED"
    else:
        emoji = "⏳"
        status_text = "PENDING"
    
    message = f"""{emoji} <b>PROJECT DISCOVERED - {status_text}</b>
━━━━━━━━━━━━━━━━━━━━━━━━
👤 @{handle} | {project_name}
🔗 Chain: {project_chain} | Conf: {confidence:.2f}
📊 Mentioned by: {mention_count} users

🤖 <b>REASONING</b>
{reasoning}

→ {"Sent to Stage 1 (Triage)" if status == 'confirmed_project' else "Not added to pipeline"}"""

    buttons = build_buttons(twitter_handle=handle)
    
    return message, buttons


# ============================================
# FINGERPRINTS
# ============================================

def format_fingerprint(data: Dict[str, Any]) -> Tuple[str, List]:
    """Format fingerprint message with buttons."""
    stage = data.get('stage', 0)
    stage_name = data.get('stage_name', '') or ''
    handle = data.get('twitter_handle', '')
    tweet_id = data.get('tweet_id', '') or ''
    
    decision = data.get('decision', '')
    confidence = data.get('confidence', 0)
    reason = data.get('reason', '') or ''
    
    # Input
    input_type = data.get('input_type', '') or ''
    input_summary = data.get('input_summary', '') or ''
    input_followers = format_number(data.get('input_followers', 0))
    input_tweets = data.get('input_tweets_count', 0)
    input_site = data.get('input_site_url', '') or 'None'
    input_bio = data.get('input_bio', '') or ''
    input_tweet_text = data.get('input_tweet_text', '') or ''
    
    # LLM
    llm_reasoning = data.get('llm_reasoning', '') or ''
    
    # Key factors
    key_factors = data.get('key_factors', {})
    if isinstance(key_factors, str):
        try:
            key_factors = json.loads(key_factors)
        except:
            key_factors = {}
    
    factors_lines = []
    for k, v in key_factors.items():
        if isinstance(v, list):
            v = ", ".join(str(i) for i in v) if v else "None"
        elif isinstance(v, bool):
            v = "Yes" if v else "No"
        factors_lines.append(f"{k}: {v}")
    key_factors_str = " | ".join(factors_lines) if factors_lines else "None"
    
    # Project
    project_name = data.get('project_name', '') or ''
    project_chain = data.get('project_chain', '') or ''
    project_type = data.get('project_type', '') or ''
    ca_detected = format_bool(data.get('ca_detected'))
    ca_address = data.get('ca_address', '') or ''
    launch_urgency = data.get('launch_urgency', '') or ''
    launch_date = data.get('launch_date', '') or ''
    
    # Metadata
    model = data.get('model_used', '') or ''
    tokens = data.get('tokens_used', 0)
    proc_time = data.get('processing_time', 0)
    created = data.get('created_at', '') or ''
    
    ca_str = f" | CA: {ca_address}" if ca_address else ""
    urgency_str = f" | Urgency: {launch_urgency}" if launch_urgency else ""
    date_str = f" | Date: {launch_date}" if launch_date else ""
    
    message = f"""🔍 <b>FINGERPRINT</b> Stage {stage} - {stage_name}
━━━━━━━━━━━━━━━━━━━━━━━━
👤 @{handle} | Decision: {decision} | Conf: {confidence:.2f}
📝 Reason: {reason}
📥 <b>INPUT</b>
Type: {input_type} | Followers: {input_followers} | Tweets: {input_tweets}
Site: {input_site}
Summary: {input_summary}
📋 <b>BIO</b>
{input_bio}
📝 <b>TWEET</b>
{input_tweet_text}
🤖 <b>LLM REASONING</b>
{llm_reasoning}
🔑 <b>KEY FACTORS</b>
{key_factors_str}
📊 <b>PROJECT</b>
Name: {project_name} | Chain: {project_chain} | Type: {project_type}
CA: {ca_detected}{ca_str}{urgency_str}{date_str}
⚙️ Model: {model} | Tokens: {tokens} | Time: {proc_time:.2f}s
📅 {created}"""

    buttons = build_buttons(
        twitter_handle=handle,
        tweet_id=tweet_id
    )
    
    return message, buttons


# ============================================
# LEGACY WRAPPERS (for backward compatibility)
# Returns just string if needed
# ============================================

def format_collection_complete(data: Dict[str, Any]) -> str:
    """REMOVED - no batch summaries."""
    return ""

def format_triage_batch_complete(data: Dict[str, Any]) -> str:
    """REMOVED - no batch summaries."""
    return ""

def format_verification_batch_complete(data: Dict[str, Any]) -> str:
    """REMOVED - no batch summaries."""
    return ""

def format_monitor_batch_complete(data: Dict[str, Any]) -> str:
    """REMOVED - no batch summaries."""
    return ""
