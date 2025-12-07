# agent/calendar_agent.py
"""
Calendar Agent
Specialized LLM agent for extracting and validating launch dates.
"""

import sys
import os
import re
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.api_client import OpenRouterClient, MODEL
from agent.database import save_to_calendar, get_calendar_stats


def get_current_date_context() -> str:
    now = datetime.now()
    return f"Today is {now.strftime('%A, %B %d, %Y')} (ISO: {now.strftime('%Y-%m-%d')})"


CALENDAR_SYSTEM_PROMPT = f"""You are a crypto launch date extraction specialist.
Your ONLY task is to extract and validate launch dates from project data.

{get_current_date_context()}

URGENCY CLASSIFICATION:
- "imminent": Launching today, tonight, in hours, any moment, right now
- "24h": Launching tomorrow, in ~24 hours, next day
- "this_week": Launching this week (2-7 days away)
- "scheduled": Has specific date > 7 days away
- "tba": "Soon", "Coming", no specific date but launching
- "unknown": No launch information found

DATE EXTRACTION RULES:
1. Look for EXPLICIT dates: "Dec 15", "December 15th", "2025-12-15", "15/12"
2. Look for RELATIVE dates: "tomorrow", "next week", "in 3 days", "this Friday"
3. Look for TIME: "6PM UTC", "tonight", "morning", "noon"
4. Cross-reference bio vs tweets vs pinned tweet
5. Website announcements have HIGH confidence
6. Convert relative dates to absolute dates using today's date

CONFIDENCE SCORING:
- 0.9+: Explicit date with time from official announcement
- 0.7-0.9: Explicit date without time
- 0.5-0.7: Relative date ("this week", "next Monday")
- 0.3-0.5: Vague hints ("coming", "almost ready", "soon")
- <0.3: No clear date information

DATE INDICATORS TO LOOK FOR:
- "launching on/at", "going live", "release date", "launch date"
- "presale starts", "IDO on", "token sale"
- "countdown", "X days left", "only X hours"
- Times: "UTC", "EST", "GMT", specific hours
- Platforms: "pump.fun at", "uniswap listing"

IMPORTANT: Always output launch_date in YYYY-MM-DD format!"""


CALENDAR_USER_PROMPT = """Extract launch date information for @{handle}:

=== BIO ===
{bio}

=== PINNED TWEET ===
{pinned_tweet}

=== RECENT TWEETS ({tweets_count} tweets) ===
{tweets}

=== WEBSITE CONTENT (if available) ===
{website_content}

=== CURRENT DATA ===
Chain: {chain}
Project Name: {project_name}
Current Ticker: {current_ticker}
Current urgency: {current_urgency}
Current launch_date: {current_launch_date}

TODAY'S DATE: {today}

TASK: Extract launch date information AND ticker possibilities. Convert any relative dates to absolute dates.

TICKER EXTRACTION RULES:
1. Look for explicit ticker with $ symbol (e.g., $BEAR, $SOL)
2. If no explicit ticker, suggest 2-3 possible tickers based on:
   - Project name (e.g., "Bear Protocol" → $BEAR, $BRP)
   - Twitter handle (e.g., @BeartheBear → $BEAR, $BTB)
   - Keywords in bio (e.g., "moon" → $MOON)
3. Validate if ticker is explicitly confirmed (found with $) or just suggested

Respond with JSON only:

{{
  "launch_date": "YYYY-MM-DD" or null,
  "launch_time": "HH:MM UTC" or null,
  "launch_date_raw": "original text mentioning date (exact quote)",
  "launch_date_source": "bio" | "tweet" | "pinned" | "website" | "none",
  "launch_date_confidence": float (0.0-1.0),
  
  "launch_urgency": "imminent" | "24h" | "this_week" | "scheduled" | "tba" | "unknown",
  "days_until_launch": integer or null,
  
  "launch_platform": string or null (pump.fun, uniswap, raydium, etc.),
  
  "ticker_confirmed": string or null (explicit ticker with $ found),
  "ticker_possibilities": [
    {{"ticker": "$XXXX", "confidence": float, "source": "bio"|"tweet"|"handle"|"inferred"}}
  ],
  
  "reasoning": "brief explanation of how date was extracted",
  
  "date_changed": boolean (true if different from current_launch_date),
  "change_type": "new_date" | "date_updated" | "date_removed" | "no_change"
}}"""


class CalendarAgent:
    """Agent specialized in extracting and validating launch dates."""
    
    def __init__(self, verbose: bool = True):
        self.llm_client = OpenRouterClient(verbose=verbose)
        self.verbose = verbose
    
    def _log(self, msg: str):
        if self.verbose:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] [CALENDAR] {msg}", flush=True)
    
    def analyze_project(
        self,
        twitter_handle: str,
        bio: str = "",
        tweets: List[Dict[str, Any]] = None,
        pinned_tweet: str = "",
        website_content: str = "",
        chain: str = "unknown",
        project_name: str = "",
        project_ticker: str = "",
        current_urgency: str = "unknown",
        current_launch_date: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze project data to extract launch date information and ticker.
        
        Returns:
            Dict with launch date info and ticker possibilities or None if error
        """
        handle = twitter_handle.lstrip('@')
        self._log(f"Analyzing @{handle}...")
        
        # Build tweets text
        tweets_text = ""
        if tweets:
            for i, tweet in enumerate(tweets[:20], 1):
                text = tweet.get('text', '')[:200]
                created = tweet.get('createdAt', '')[:10]
                tweets_text += f"\n[{i}] ({created}) {text}"
        else:
            tweets_text = "[No tweets available]"
        
        # Build prompt
        prompt = CALENDAR_USER_PROMPT.format(
            handle=handle,
            bio=bio or "[No bio]",
            pinned_tweet=pinned_tweet or "[No pinned tweet]",
            tweets_count=len(tweets) if tweets else 0,
            tweets=tweets_text,
            website_content=website_content[:2000] if website_content else "[No website content]",
            chain=chain,
            project_name=project_name or "Unknown",
            current_ticker=project_ticker or "None",
            current_urgency=current_urgency,
            current_launch_date=current_launch_date or "None",
            today=datetime.now().strftime('%Y-%m-%d')
        )
        
        # Call LLM
        response = self.llm_client.chat(
            system_prompt=CALENDAR_SYSTEM_PROMPT,
            user_prompt=prompt
        )
        
        if "error" in response:
            self._log(f"[ERROR] LLM error: {response.get('error', '')[:50]}")
            return None
        
        # Parse response
        content = response.get("content", "")
        result = self.llm_client.parse_json_response(content)
        
        if not result:
            self._log(f"[PARSE_ERROR] Could not parse LLM response")
            return None
        
        # Calculate days until launch if we have a date
        launch_date = result.get('launch_date')
        if launch_date:
            try:
                launch_dt = datetime.strptime(launch_date, '%Y-%m-%d')
                days_until = (launch_dt - datetime.now()).days
                result['days_until_launch'] = max(0, days_until)
                
                # Auto-adjust urgency based on days
                if days_until <= 0:
                    result['launch_urgency'] = 'imminent'
                elif days_until == 1:
                    result['launch_urgency'] = '24h'
                elif days_until <= 7:
                    result['launch_urgency'] = 'this_week'
                else:
                    result['launch_urgency'] = 'scheduled'
            except ValueError:
                pass
        
        self._log(f"[RESULT] @{handle} | urgency={result.get('launch_urgency')} | "
                  f"date={result.get('launch_date')} | conf={result.get('launch_date_confidence', 0):.2f}")
        
        return result
    
    def save_analysis(
        self,
        twitter_handle: str,
        analysis: Dict[str, Any],
        project_id: int = None,
        project_name: str = None,
        project_ticker: str = None,
        chain: str = "unknown"
    ) -> int:
        """Save calendar analysis to database."""
        
        # Use confirmed ticker from analysis if found, else use provided
        ticker = analysis.get('ticker_confirmed') or project_ticker
        
        # Serialize ticker possibilities
        ticker_possibilities = analysis.get('ticker_possibilities', [])
        if ticker_possibilities:
            ticker_possibilities_json = json.dumps(ticker_possibilities)
        else:
            ticker_possibilities_json = None
        
        calendar_data = {
            'twitter_handle': twitter_handle,
            'project_id': project_id,
            'project_name': project_name,
            'project_ticker': ticker,
            'ticker_possibilities': ticker_possibilities_json,
            'chain': chain,
            'launch_date': analysis.get('launch_date'),
            'launch_time': analysis.get('launch_time'),
            'launch_date_raw': analysis.get('launch_date_raw'),
            'launch_date_source': analysis.get('launch_date_source'),
            'launch_date_confidence': analysis.get('launch_date_confidence', 0),
            'launch_urgency': analysis.get('launch_urgency', 'unknown'),
            'days_until_launch': analysis.get('days_until_launch'),
            'launch_platform': analysis.get('launch_platform'),
            'calendar_status': 'pending',
            'analysis_notes': analysis.get('reasoning')
        }
        
        return save_to_calendar(calendar_data)
    
    def analyze_and_save(
        self,
        twitter_handle: str,
        bio: str = "",
        tweets: List[Dict[str, Any]] = None,
        pinned_tweet: str = "",
        website_content: str = "",
        chain: str = "unknown",
        project_name: str = "",
        project_ticker: str = "",
        project_id: int = None,
        current_urgency: str = "unknown",
        current_launch_date: str = None
    ) -> Optional[Dict[str, Any]]:
        """Analyze project and save to calendar in one call."""
        
        analysis = self.analyze_project(
            twitter_handle=twitter_handle,
            bio=bio,
            tweets=tweets,
            pinned_tweet=pinned_tweet,
            website_content=website_content,
            chain=chain,
            project_name=project_name,
            project_ticker=project_ticker,
            current_urgency=current_urgency,
            current_launch_date=current_launch_date
        )
        
        if analysis:
            calendar_id = self.save_analysis(
                twitter_handle=twitter_handle,
                analysis=analysis,
                project_id=project_id,
                project_name=project_name,
                project_ticker=project_ticker,
                chain=chain
            )
            analysis['calendar_id'] = calendar_id
            self._log(f"[SAVED] @{twitter_handle} | calendar_id={calendar_id}")
        
        return analysis


def run_calendar_analysis(limit: int = 50, verbose: bool = True) -> Dict[str, Any]:
    """
    Run calendar analysis for confirmed projects that don't have calendar entries.
    
    This is a standalone function that can be called from services.
    """
    from agent.database import init_db, get_connection
    
    init_db()
    agent = CalendarAgent(verbose=verbose)
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Get confirmed projects not in calendar
    cur.execute('''
        SELECT v.* FROM verified_projects v
        LEFT JOIN launch_calendar c ON LOWER(v.twitter_handle) = LOWER(c.twitter_handle)
        WHERE v.verification_status = 'confirmed'
        AND c.id IS NULL
        LIMIT ?
    ''', (limit,))
    
    projects = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    if verbose:
        print(f"\n[CALENDAR] Found {len(projects)} projects without calendar entries")
    
    results = {
        'analyzed': 0,
        'with_date': 0,
        'errors': 0
    }
    
    for project in projects:
        handle = project.get('twitter_handle', '')
        
        try:
            analysis = agent.analyze_and_save(
                twitter_handle=handle,
                bio=project.get('bio', ''),
                chain=project.get('project_chain', 'unknown'),
                project_name=project.get('project_name'),
                project_ticker=project.get('project_ticker'),
                project_id=project.get('id'),
                current_urgency=project.get('launch_urgency', 'unknown'),
                current_launch_date=project.get('launch_date_announced')
            )
            
            if analysis:
                results['analyzed'] += 1
                if analysis.get('launch_date'):
                    results['with_date'] += 1
        except Exception as e:
            if verbose:
                print(f"[ERROR] @{handle}: {str(e)[:50]}")
            results['errors'] += 1
    
    if verbose:
        stats = get_calendar_stats()
        print(f"\n[CALENDAR_STATS] {stats}")
    
    return results

