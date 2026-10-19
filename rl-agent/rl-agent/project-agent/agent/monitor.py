# agent/monitor.py
"""
Stage 3: Project Monitoring
Monitor confirmed projects for launches, CA announcements, and status changes.
Uses LLM for intelligent detection instead of hardcoded patterns.
"""

import sys
sys.path.append('..')

import re
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from .api_client import OpenRouterClient, MODEL
from .prompts import get_monitor_system_prompt, build_monitor_prompt
from .website_reader import WebsiteReader
from .alphagate_client import AlphaGateClient
from .database import (
    init_db,
    get_projects_to_monitor,
    update_project_monitoring,
    save_monitoring_history,
    save_fingerprint,
    get_monitoring_stats,
    activate_monitoring_for_confirmed,
    MONITOR_INTERVALS
)

from users.api_client import UserInfoClient, UserTweetsClient, TweetsByIdClient
from agent.twitter_cache import get_or_fetch_user_tweets, get_or_fetch_user_info
from .ca_detector import is_project_launched, detect_ca, detect_dex_link


def parse_launch_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats from LLM response."""
    if not date_str:
        return None
    
    date_str = date_str.strip()
    now = datetime.now()
    
    # Try various patterns
    patterns = [
        # ISO format: 2025-12-09
        (r'(\d{4})-(\d{2})-(\d{2})', lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        # US format: 12/09/2025
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', lambda m: datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))),
        # EU format: 09/12/2025
        (r'(\d{1,2})\.(\d{1,2})\.(\d{4})', lambda m: datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))),
    ]
    
    for pattern, parser in patterns:
        match = re.search(pattern, date_str)
        if match:
            try:
                return parser(match)
            except:
                continue
    
    # Month name patterns: December 9, Dec 9th, 9 December
    month_names = {
        'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
        'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6,
        'jul': 7, 'july': 7, 'aug': 8, 'august': 8, 'sep': 9, 'september': 9,
        'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12
    }
    
    # Pattern: December 9, Dec 9th, December 9th 2025
    month_day_pattern = r'(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?'
    match = re.search(month_day_pattern, date_str.lower())
    if match:
        month = month_names.get(match.group(1).lower())
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else now.year
        # If date would be in past this year, assume next year
        try:
            result = datetime(year, month, day)
            if result < now and not match.group(3):
                result = datetime(year + 1, month, day)
            return result
        except:
            pass
    
    # Pattern: 9 December, 9th of December
    day_month_pattern = r'(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
    match = re.search(day_month_pattern, date_str.lower())
    if match:
        day = int(match.group(1))
        month = month_names.get(match.group(2).lower())
        year = now.year
        try:
            result = datetime(year, month, day)
            if result < now:
                result = datetime(year + 1, month, day)
            return result
        except:
            pass
    
    # Relative patterns: today, tomorrow, in X days/hours
    lower_str = date_str.lower()
    
    if 'today' in lower_str or 'tonight' in lower_str:
        return now
    
    if 'tomorrow' in lower_str:
        return now + timedelta(days=1)
    
    # "in X days/hours"
    in_days_match = re.search(r'in\s+(\d+)\s+days?', lower_str)
    if in_days_match:
        return now + timedelta(days=int(in_days_match.group(1)))
    
    in_hours_match = re.search(r'in\s+(\d+)\s+hours?', lower_str)
    if in_hours_match:
        return now + timedelta(hours=int(in_hours_match.group(1)))
    
    # "this week" - assume end of week
    if 'this week' in lower_str:
        return now + timedelta(days=(7 - now.weekday()))
    
    # "next week"
    if 'next week' in lower_str:
        return now + timedelta(days=(14 - now.weekday()))
    
    return None


def is_launch_date_in_future(date_str: str) -> bool:
    """Check if launch date is in the future."""
    parsed = parse_launch_date(date_str)
    if parsed:
        # Add some buffer - if it's today, consider it could be launching
        return parsed.date() > datetime.now().date()
    return False


def is_launch_date_passed(date_str: str) -> bool:
    """Check if launch date has passed."""
    parsed = parse_launch_date(date_str)
    if parsed:
        return parsed.date() < datetime.now().date()
    return False


def calculate_days_since_tweet(tweet_date_str: str) -> int:
    """Calculate days since a tweet was posted.
    
    Args:
        tweet_date_str: Tweet date in Twitter format (e.g., "Thu Dec 04 11:27:17 +0000 2025")
    
    Returns:
        Number of days since the tweet, or 999 if parsing fails
    """
    if not tweet_date_str:
        return 999
    
    try:
        # Try Twitter date format: "Thu Dec 04 11:27:17 +0000 2025"
        tweet_dt = datetime.strptime(tweet_date_str, "%a %b %d %H:%M:%S %z %Y")
        now = datetime.now(tweet_dt.tzinfo)
        days = (now - tweet_dt).days
        return max(0, days)
    except:
        try:
            # Try ISO format
            tweet_dt = datetime.fromisoformat(tweet_date_str.replace('Z', '+00:00'))
            now = datetime.now(tweet_dt.tzinfo) if tweet_dt.tzinfo else datetime.now()
            days = (now - tweet_dt).days
            return max(0, days)
        except:
            return 999


class ProjectMonitor:
    """Stage 3: Monitor confirmed projects for launches and updates using LLM."""
    
    def __init__(self, verbose: bool = True):
        self.llm_client = OpenRouterClient(verbose=verbose)
        self.user_info_client = UserInfoClient(verbose=verbose)
        self.user_tweets_client = UserTweetsClient(verbose=verbose)
        self.website_reader = WebsiteReader(verbose=verbose)
        self.alphagate_client = AlphaGateClient(verbose=verbose, delay=1.0)
        self.tweets_by_id_client = TweetsByIdClient(verbose=verbose)  # NEW: Fetch tweets by ID
        self.verbose = verbose
        init_db()
    
    def _log(self, msg: str):
        if self.verbose:
            print(msg)
    
    def analyze_with_llm(
        self,
        project: Dict[str, Any],
        tweets: List[Dict[str, Any]],
        current_bio: str,
        site_content: str = None
    ) -> Optional[Dict[str, Any]]:
        """Use LLM to analyze project status intelligently."""
        
        prompt = build_monitor_prompt(project, tweets, current_bio, site_content)
        
        response = self.llm_client.chat(
            system_prompt=get_monitor_system_prompt(),
            user_prompt=prompt
        )
        
        if "error" in response:
            self._log(f"[LLM_ERROR] {response.get('error', '')[:50]}")
            return None
        
        content = response.get("content", "")
        result = self.llm_client.parse_json_response(content)
        
        return result
    
    def monitor_project(self, project: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Monitor a single project for updates using LLM analysis."""
        
        project_id = project.get('id')
        twitter_handle = project.get('twitter_handle', '')
        author_id = project.get('author_id', '')
        
        self._log(f"\n[MONITOR] @{twitter_handle} | priority={project.get('priority', 'low')}")
        
        start_time = time.time()
        
        # Store previous state
        status_before = project.get('monitoring_status', 'active')
        priority_before = project.get('priority', 'low')
        previous_bio = project.get('bio', '')
        previous_followers = project.get('followers_current') or project.get('followers') or 0
        site_url = project.get('site_url') or project.get('website_url')
        
        # Fetch current data
        self._log(f"[FETCH] Getting latest data...")
        
        # Get user info (cached)
        user_info = {}
        if author_id:
            cached_info = get_or_fetch_user_info(
                self.user_info_client,
                author_id=author_id,
                handle=twitter_handle,
                ttl_hours=6
            )
            if cached_info:
                user_info = cached_info
        
        # Get latest tweets (cached)
        tweets = []
        pin_tweet = None
        if twitter_handle or author_id:
            try:
                result = get_or_fetch_user_tweets(
                    self.user_tweets_client,
                    handle=twitter_handle,
                    author_id=author_id,
                    include_replies=False,
                    ttl_hours=6
                )
                if result:
                    tweets = result.get('tweets', []) or []
                    pin_tweet = result.get('pin_tweet')
                    
                    # FALLBACK: If no pin_tweet but user_info has pinnedTweetIds, fetch by ID
                    if not pin_tweet and user_info:
                        pinned_ids = user_info.get('pinnedTweetIds', [])
                        if pinned_ids:
                            self._log(f"[PIN_TWEET] Fetching pinned tweet by ID: {pinned_ids[0]}")
                            pin_tweet = self.tweets_by_id_client.get_tweet_by_id(pinned_ids[0])
                            if pin_tweet:
                                pin_tweet['_is_pinned'] = True
                                # Add to tweets list if not already there
                                pin_id = pin_tweet.get('id')
                                tweet_ids = [t.get('id') for t in tweets]
                                if pin_id not in tweet_ids:
                                    tweets = [pin_tweet] + tweets
                                    self._log(f"[PIN_TWEET] Added: {pin_tweet.get('text', '')[:50]}...")
            except Exception as e:
                self._log(f"[TWEETS_ERROR] @{twitter_handle}: {str(e)[:50]}")
                tweets = []

        
        # === CHECK: User not found (deleted, suspended, or renamed) ===
        # If we have no user_info AND no tweets, the account likely doesn't exist
        if not user_info and not tweets:
            self._log(f"[NOT_FOUND] @{twitter_handle} - account deleted/suspended/renamed - marking as not_found")
            
            # Update status to not_found so we don't keep trying
            now = datetime.now().isoformat()
            update_project_monitoring(project_id, {
                "monitoring_status": "not_found",
                "last_monitored_at": now,
                "updated_at": now
            })
            
            return None
        
        current_bio = user_info.get('description', '')
        current_followers = user_info.get('followers', 0)
        
        self._log(f"[DATA] tweets={len(tweets)} | followers={current_followers}")
        
        # Fetch website content
        site_content = None
        if site_url:
            site_result = self.website_reader.read_url(site_url)
            if site_result.get('success'):
                site_content = site_result.get('content', '')
        
        # Fetch AlphaGate data for tracking changes
        alphagate_data = {}
        try:
            twitter_id = user_info.get('id') or author_id
            if twitter_id:
                self._log(f"[ALPHAGATE] Fetching enrichment data...")
                alphagate_data = self.alphagate_client.enrich_project(twitter_handle.lstrip('@'))
                if alphagate_data.get('found_in_alphagate'):
                    self._log(f"[ALPHAGATE] key_followers={alphagate_data.get('key_followers_count', 0)} | hunters={alphagate_data.get('alpha_hunters_count', 0)}")
                    
                    # CHECK: AlphaGate already has contracts?
                    ag_contracts = alphagate_data.get('contracts', [])
                    ag_ca_count = alphagate_data.get('ca_count', 0)
                    if ag_contracts and ag_ca_count > 0:
                        self._log(f"[ALPHAGATE] CA DETECTED! contracts={ag_contracts[:2]} | ca_count={ag_ca_count}")
                        
                        # RETURN IMMEDIATELY - AlphaGate confirmed CA!
                        now = datetime.now().isoformat()
                        
                        update_project_monitoring(project_id, {
                            "monitoring_status": "launched",
                            "ca_address": ag_contracts[0] if ag_contracts else None,
                            "launch_status": "launched",
                            "last_monitored_at": now,
                            "updated_at": now,
                            "detection_method": "alphagate"
                        })
                        
                        save_monitoring_history(project_id, {
                            "twitter_handle": twitter_handle,
                            "status_before": status_before,
                            "status_after": "launched",
                            "detection_method": "alphagate",
                            "evidence": ag_contracts[0] if ag_contracts else None,
                            "reason": f"AlphaGate has {ag_ca_count} contracts",
                            "timestamp": now
                        })
                        
                        return {
                            "twitter_handle": twitter_handle,
                            "status": "launched",
                            "launch_status": "launched",
                            "detection_method": "alphagate",
                            "evidence": ag_contracts[0] if ag_contracts else None,
                            "reason": f"AlphaGate has {ag_ca_count} contracts",
                            "priority": "none",
                            "skip_llm": True
                        }
        except Exception as e:
            self._log(f"[ALPHAGATE] Error: {str(e)[:50]}")
        
        # ============================================
        # PRE-LLM CHECK: Detect CA/DEX programmatically
        # ============================================
        # This catches CAs that the LLM might miss - saves tokens!
        profile_url = user_info.get('url', '') or ''
        name = user_info.get('name', '') or ''
        location = user_info.get('location', '') or ''
        
        # Extract tweet texts AND expanded URLs
        tweet_texts = []
        expanded_urls = []
        for t in tweets:
            text = t.get('text', '')
            if text:
                tweet_texts.append(text)
            for url_entity in t.get('entities', {}).get('urls', []) or []:
                expanded = url_entity.get('expanded_url', '')
                if expanded:
                    expanded_urls.append(expanded)
        
        regex_launched, regex_reason, regex_evidence = is_project_launched(
            bio=current_bio,
            tweets=tweet_texts,
            profile_url=profile_url,
            name=name,
            location=location,
            expanded_urls=expanded_urls
        )
        
        if regex_launched:
            self._log(f"[PRE-CHECK] @{twitter_handle} | LAUNCHED via REGEX | {regex_reason}")
            if regex_evidence:
                self._log(f"[PRE-CHECK] Evidence: {regex_evidence[:60]}...")
            
            # RETURN IMMEDIATELY - No need to call LLM (saves tokens!)
            now = datetime.now().isoformat()
            
            # Update database
            update_project_monitoring(project_id, {
                "monitoring_status": "launched",
                "ca_address": regex_evidence if 'CA found' in regex_reason else None,
                "dex_url": regex_evidence if 'DEX' in regex_reason else None,
                "launch_status": "launched",
                "last_monitored_at": now,
                "updated_at": now,
                "detection_method": "regex"
            })
            
            # Save to history
            save_monitoring_history(project_id, {
                "twitter_handle": twitter_handle,
                "status_before": status_before,
                "status_after": "launched",
                "detection_method": "regex",
                "evidence": regex_evidence,
                "reason": regex_reason,
                "timestamp": now
            })
            
            return {
                "twitter_handle": twitter_handle,
                "status": "launched",
                "launch_status": "launched",
                "detection_method": "regex",
                "evidence": regex_evidence,
                "reason": regex_reason,
                "priority": "none",
                "skip_llm": True
            }
        
        # Use LLM to analyze everything (only if regex didn't find anything)
        self._log(f"[ANALYZE] Using LLM for intelligent analysis...")
        
        llm_result = self.analyze_with_llm(project, tweets, current_bio, site_content)


        
        if not llm_result:
            self._log(f"[ERROR] LLM analysis failed for @{twitter_handle}")
            return None
        
        # Extract LLM analysis results (use `or` to handle None values)
        launch_status = llm_result.get('launch_status') or 'not_launched'
        launch_urgency = llm_result.get('launch_urgency') or 'unknown'
        ca_detected = llm_result.get('ca_detected') or False
        ca_address = llm_result.get('ca_address')
        ca_source = llm_result.get('ca_source')
        bio_changed = llm_result.get('bio_changed') or False
        recommended_priority = llm_result.get('recommended_priority') or 'low'
        significant_updates = llm_result.get('significant_updates') or []
        summary = llm_result.get('summary') or ''
        
        # Calculate days_inactive from ACTUAL tweet date (don't trust LLM!)
        if tweets:
            last_tweet_date = tweets[0].get('createdAt')
            days_inactive = calculate_days_since_tweet(last_tweet_date)
            self._log(f"[DAYS] Calculated from tweet: {days_inactive} days (last: {last_tweet_date})")
        else:
            # No tweets available - use LLM value as fallback
            days_inactive = llm_result.get('days_since_last_tweet') or 0
            self._log(f"[DAYS] From LLM (no tweets): {days_inactive} days")
        
        # Determine new status based on LLM analysis with DATE VALIDATION
        launch_date = llm_result.get('launch_date_mentioned')
        
        if ca_detected and ca_address:
            # CA detected = definitely launched (strongest evidence)
            new_status = 'launched'
            self._log(f"[STATUS] LAUNCHED - CA detected: {ca_address[:20]}...")
        elif launch_status == 'launched':
            # LLM says launched - but VALIDATE with evidence
            if launch_date:
                if is_launch_date_in_future(launch_date):
                    # Date is in FUTURE - NOT launched yet!
                    new_status = 'active'
                    launch_urgency = 'scheduled'
                    self._log(f"[DATE_CHECK] Launch date '{launch_date}' is in FUTURE - NOT launched")
                elif is_launch_date_passed(launch_date):
                    # Date has passed - likely launched
                    new_status = 'launched'
                    self._log(f"[DATE_CHECK] Launch date '{launch_date}' has PASSED - marking launched")
                else:
                    # Date is today - could be launching
                    new_status = 'active'
                    launch_urgency = 'imminent'
                    self._log(f"[DATE_CHECK] Launch date '{launch_date}' is TODAY - imminent")
            else:
                # LLM says launched but no date - check summary for evidence
                summary_lower = summary.lower() if summary else ''
                launch_evidence = any(phrase in summary_lower for phrase in [
                    'now live', 'is live', 'already live', 'trading live',
                    'has launched', 'just launched', 'officially launched',
                    'contract deployed', 'ca:', 'contract:'
                ])
                if launch_evidence:
                    new_status = 'launched'
                    self._log(f"[STATUS] LAUNCHED - evidence in summary")
                else:
                    # No clear evidence - keep active
                    new_status = 'active'
                    self._log(f"[STATUS] LLM said launched but no evidence - keeping active")
        elif days_inactive >= 30:
            new_status = 'abandoned'
        else:
            new_status = 'active'
        
        # Use LLM recommended priority
        new_priority = recommended_priority
        
        # Build changes list
        changes = significant_updates.copy() if significant_updates else []
        if bio_changed:
            changes.append("bio_changed")
        if ca_detected:
            changes.append("ca_detected")
        if launch_status == 'launched':
            changes.append("launch_announced")
        
        # Calculate followers change (handle None values)
        previous_followers = previous_followers or 0
        current_followers = current_followers or 0
        followers_change = current_followers - previous_followers
        
        # Calculate followers growth
        initial_followers = project.get('followers_initial') or previous_followers or 0
        followers_growth = 0
        if initial_followers and initial_followers > 0:
            followers_growth = ((current_followers - initial_followers) / initial_followers) * 100
        
        # Get last tweet info
        last_tweet_at = None
        last_tweet_text = None
        if tweets:
            last_tweet_at = tweets[0].get('createdAt')
            last_tweet_text = tweets[0].get('text', '')[:200]
        
        # Log results
        if changes:
            self._log(f"[CHANGES] {', '.join(changes)}")
        if launch_urgency != "unknown":
            self._log(f"[URGENCY] {launch_urgency}")
        if ca_detected:
            self._log(f"[CA_DETECTED] {ca_address} | source={ca_source}")
        if new_status != status_before:
            self._log(f"[STATUS] {status_before} -> {new_status}")
        if new_priority != priority_before:
            self._log(f"[PRIORITY] {priority_before} -> {new_priority}")
        if summary:
            self._log(f"[SUMMARY] {summary[:80]}...")
        
        # Prepare update data
        now = datetime.now().isoformat()
        
        update_data = {
            "last_monitored_at": now,
            "monitor_count": (project.get('monitor_count', 0) or 0) + 1,
            "monitoring_status": new_status,
            "launch_urgency": launch_urgency,
            "priority": new_priority,
            "followers_current": current_followers,
            "followers_growth": followers_growth,
            "last_tweet_at": last_tweet_at,
            "inactive_days": days_inactive,
            "updated_at": now
        }
        
        if launch_date:
            update_data["launch_date_announced"] = launch_date
            update_data["launch_date_detected_at"] = now
        
        if ca_detected and not project.get('ca_address'):
            update_data["ca_detected_at"] = now
            update_data["ca_address"] = ca_address
        
        if launch_status == 'launched' and not project.get('launch_detected_at'):
            update_data["launch_detected_at"] = now
        
        # Save to database
        update_project_monitoring(project_id, update_data)
        
        # Save history
        history_data = {
            "followers": current_followers,
            "followers_change": followers_change,
            "new_tweets_count": len(tweets),
            "last_tweet_text": last_tweet_text,
            "last_tweet_at": last_tweet_at,
            "ca_mentioned": ca_detected,
            "ca_address": ca_address,
            "ca_source": ca_source,
            "launch_mentioned": launch_status == 'launched',
            "launch_urgency": launch_urgency,
            "launch_date_detected": launch_date,
            "site_accessible": site_content is not None,
            "site_changed": False,  # LLM doesn't track this currently
            "site_ca_found": ca_source == 'website',
            "bio_changed": bio_changed,
            "bio_new": current_bio if bio_changed else None,
            "status_before": status_before,
            "status_after": new_status,
            "priority_before": priority_before,
            "priority_after": new_priority,
            "changes_detected": changes,
            "ai_analysis": summary,
            "raw_response": llm_result,
            # AlphaGate data
            "found_in_alphagate": alphagate_data.get('found_in_alphagate', False),
            "key_followers": alphagate_data.get('key_followers', []),
            "key_followers_count": alphagate_data.get('key_followers_count', 0),
            "alpha_hunters": alphagate_data.get('alpha_hunters', []),
            "alpha_hunters_count": alphagate_data.get('alpha_hunters_count', 0),
            "followers_when_found": alphagate_data.get('followers_when_found', 0),
            "best_hunter_winrate": alphagate_data.get('best_hunter_winrate', 0),
            "alphagate_alerts": alphagate_data.get('alerts', []),
            "alphagate_bio_changes": alphagate_data.get('alerts_summary', {}).get('bio_changes', 0),
            "alphagate_username_changes": alphagate_data.get('alerts_summary', {}).get('username_changes', 0),
        }
        
        save_monitoring_history(project_id, twitter_handle, history_data)
        
        # Save fingerprint
        fingerprint = {
            "twitter_handle": twitter_handle,
            "author_id": author_id,
            "stage": 3,
            "stage_name": "monitoring",
            "decision": new_status,
            "confidence": llm_result.get('verification_confidence', 0.8) if new_status == 'launched' else 0.5,
            "reason": f"Status: {status_before} -> {new_status}" if new_status != status_before else "no_status_change",
            "input_type": "monitoring_check",
            "input_summary": f"Monitor @{twitter_handle}: {len(tweets)} tweets, {current_followers} followers, priority={priority_before}",
            "input_bio": current_bio[:300] if current_bio else None,
            "input_followers": current_followers,
            "input_tweets_count": len(tweets),
            "input_site_url": site_url,
            "llm_reasoning": summary,
            "key_factors": {
                "status_change": new_status != status_before,
                "priority_change": new_priority != priority_before,
                "ca_detected": ca_detected,
                "launch_mentioned": launch_status == 'launched',
                "urgency": launch_urgency,
                "bio_changed": llm_result.get('bio_changed', False),
                "significant_updates": significant_updates,
                "days_inactive": days_inactive,
                "followers_change": followers_change,
                "spam_indicators": llm_result.get('spam_indicators', False),
                "scam_indicators": llm_result.get('scam_indicators', False)
            },
            "project_name": project.get('project_name'),
            "project_chain": project.get('project_chain'),
            "ca_detected": ca_detected,
            "ca_address": ca_address,
            "launch_urgency": launch_urgency,
            "launch_date": launch_date,
            "raw_input": {
                "project_id": project_id,
                "previous_status": status_before,
                "previous_priority": priority_before,
                "tweets_count": len(tweets)
            },
            "raw_output": llm_result,
            "model_used": MODEL,
            "processing_time": time.time() - start_time
        }
        save_fingerprint(fingerprint)
        
        elapsed = time.time() - start_time
        self._log(f"[SAVED] @{twitter_handle} | time={elapsed:.2f}s")
        
        return {
            "twitter_handle": twitter_handle,
            "status": new_status,
            "priority": new_priority,
            "changes": changes,
            "ca_found": ca_detected,
            "ca_address": ca_address,
            "ca_source": ca_source,
            "summary": summary,
            # Additional fields for complete Telegram messages
            "launch_urgency": launch_urgency,
            "launch_date": launch_date,
            "followers_change": followers_change,
            "followers_growth": followers_growth,
            "inactive_days": days_inactive,
            "last_tweet_at": last_tweet_at,
            "last_tweet_text": last_tweet_text,
            "new_tweets_count": len(tweets),
            "bio_changed": bio_changed,
            "site_accessible": site_content is not None,
            "activity_level": "active" if len(tweets) > 5 else ("low" if len(tweets) > 0 else "inactive"),
            # AlphaGate data for Telegram
            "found_in_alphagate": alphagate_data.get('found_in_alphagate', False),
            "key_followers": alphagate_data.get('key_followers', []),
            "key_followers_count": alphagate_data.get('key_followers_count', 0),
            "alpha_hunters": alphagate_data.get('alpha_hunters', []),
            "alpha_hunters_count": alphagate_data.get('alpha_hunters_count', 0),
            "followers_when_found": alphagate_data.get('followers_when_found', 0),
            "best_hunter_winrate": alphagate_data.get('best_hunter_winrate', 0),
            "alphagate_alerts": alphagate_data.get('alerts', []),
            "alphagate_bio_changes": alphagate_data.get('alerts_summary', {}).get('bio_changes', 0),
            "alphagate_username_changes": alphagate_data.get('alerts_summary', {}).get('username_changes', 0),
        }
    
    def run_monitoring_cycle(self, limit: int = 50) -> Dict[str, Any]:
        """Run a monitoring cycle for projects that need it."""
        
        self._log("\n" + "=" * 60)
        self._log(f"[RUN] agent.monitor | limit={limit}")
        self._log("=" * 60)
        
        start_time = time.time()
        
        # Activate monitoring for any new confirmed projects
        activated = activate_monitoring_for_confirmed()
        if activated > 0:
            self._log(f"[ACTIVATED] {activated} new projects for monitoring")
        
        # Get projects to monitor
        projects = get_projects_to_monitor(limit)
        
        self._log(f"[QUEUE] projects_to_monitor={len(projects)}")
        
        if not projects:
            self._log("[DONE] No projects need monitoring at this time")
            return {"monitored": 0, "changes": 0, "launched": 0}
        
        self._log("\n" + "=" * 60)
        self._log(f"[BATCH_MONITOR] total_projects={len(projects)}")
        self._log("=" * 60)
        
        results = {
            "monitored": 0,
            "changes": 0,
            "launched": 0,
            "ca_detected": 0,
            "priority_critical": 0,
            "priority_high": 0
        }
        
        for i, project in enumerate(projects, 1):
            self._log(f"\n[{i}/{len(projects)}] Monitoring...")
            
            try:
                result = self.monitor_project(project)
                
                if result:
                    results["monitored"] += 1
                    
                    if result.get("changes"):
                        results["changes"] += 1
                    
                    if result.get("status") == "launched":
                        results["launched"] += 1
                    
                    if result.get("ca_found"):
                        results["ca_detected"] += 1
                    
                    if result.get("priority") == "critical":
                        results["priority_critical"] += 1
                    elif result.get("priority") == "high":
                        results["priority_high"] += 1
                
                # Rate limiting
                time.sleep(1)
                
            except Exception as e:
                self._log(f"[ERROR] {project.get('twitter_handle')}: {str(e)[:50]}")
        
        elapsed = time.time() - start_time
        
        self._log("\n" + "=" * 60)
        self._log(f"[BATCH_DONE] monitored={results['monitored']} | "
                  f"changes={results['changes']} | "
                  f"launched={results['launched']} | "
                  f"ca_detected={results['ca_detected']} | "
                  f"time={elapsed:.2f}s")
        self._log("=" * 60)
        
        # Show stats
        stats = get_monitoring_stats()
        self._log(f"\n[STATS] by_priority={stats.get('by_priority', {})} | "
                  f"launched_total={stats.get('launched_count', 0)}")
        
        return results

