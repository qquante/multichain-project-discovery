# agent/discoverer.py
"""
Project Discoverer
Investigates handles mentioned by influencers to find real projects.
When multiple mentions point to the same @handle, we investigate if it's a real project.
"""

import sys
sys.path.append('..')

import time
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from .api_client import OpenRouterClient, MODEL
from .prompts import get_current_date_context
from .database import (
    init_db,
    get_handles_to_investigate,
    get_mentions_by_handle,
    mark_mentions_investigated_by_handle,
    convert_mention_to_project,
    save_triage_result,
    save_fingerprint,
    is_handle_triaged,
    get_mention_stats
)

from users.api_client import UserInfoClient, UserTweetsClient


DISCOVERY_SYSTEM_PROMPT = f"""You are a crypto project discovery analyst.
Your task is to investigate a Twitter handle that was mentioned by multiple users 
and determine if it represents a REAL crypto project.

{get_current_date_context()}

You will receive:
1. The handle being investigated
2. User profile information (bio, followers, etc.)
3. Recent tweets from the account
4. Context of how this handle was mentioned by others

YOUR TASK:
Determine if this @handle is a REAL crypto project account that:
1. Is preparing to launch a token/platform
2. Has not launched yet (no CA)
3. Shows signs of legitimacy

DECISION OPTIONS:
- confirmed_project: This IS a real crypto project account
- rejected_not_project: This is NOT a crypto project (personal account, news, etc.)
- rejected_influencer: This is an influencer/alpha caller, not a project
- rejected_launched: Project already launched (has CA)
- pending: Need more data to decide

For CONFIRMED projects, provide:
- At least 3 name possibilities
- At least 3 ticker possibilities
- Chain detection
- Project type
- Launch status"""

DISCOVERY_USER_PROMPT = """Investigate if @{handle} is a real crypto project.

=== MENTIONS CONTEXT ===
This handle was mentioned {mention_count} times by different users.
Example mentions:
{mentions_context}

=== USER PROFILE ===
Handle: @{handle}
Name: {user_name}
Bio: {bio}
Followers: {followers}
Following: {following}
Total Tweets: {total_tweets}
Account Created: {account_created}
Is Blue Verified: {is_blue_verified}

=== RECENT TWEETS ({tweets_count} tweets) ===
{tweets_text}

=== TASK ===
Analyze the profile and tweets to determine if this is a REAL crypto project.

Respond with valid JSON only:

{{
  "discovery_status": "confirmed_project" | "rejected_not_project" | "rejected_influencer" | "rejected_launched" | "pending",
  "confidence": float (0.0-1.0),
  "rejection_reason": string or null,
  
  "project": {{
    "name": string or null,
    "ticker": string or null,
    "type": string (token/dex/defi/nft/game/dao/infra/ai/social/bridge/launchpad/wallet/oracle/privacy/rwa/restaking/liquid_staking/other),
    "chain": string,
    "has_ca": boolean,
    "ca_address": string or null,
    
    "name_possibilities": [
      {{"name": string, "confidence": float, "source": "bio"|"handle"|"tweet"|"inferred"}}
    ],
    "ticker_possibilities": [
      {{"ticker": string, "confidence": float, "source": "tweet"|"bio"|"inferred"}}
    ],
    "name_validated": boolean,
    "ticker_validated": boolean
  }},
  
  "launch": {{
    "status": "pre_launch" | "launching_soon" | "launched" | "unknown",
    "date": string or null,
    "platform": string or null
  }},
  
  "signals": {{
    "has_website": boolean,
    "website_url": string or null,
    "has_telegram": boolean,
    "telegram_url": string or null,
    "has_discord": boolean,
    "discord_url": string or null,
    "keywords_found": [list of launch-related keywords found]
  }},
  
  "reasoning": string (explanation of decision)
}}"""


class ProjectDiscoverer:
    """Investigates handles mentioned by influencers to discover real projects."""
    
    def __init__(self, verbose: bool = True):
        self.llm_client = OpenRouterClient(verbose=verbose)
        self.user_info_client = UserInfoClient(verbose=verbose)
        self.user_tweets_client = UserTweetsClient(verbose=verbose)
        self.verbose = verbose
        init_db()
    
    def _log(self, msg: str):
        if self.verbose:
            print(msg)
    
    def investigate_handle(self, handle: str, mentions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Investigate a single handle to determine if it's a real project."""
        
        handle = handle.lstrip('@')
        self._log(f"\n[DISCOVER] Investigating @{handle} | mentions={len(mentions)}")
        
        start_time = time.time()
        
        # Check if already triaged
        if is_handle_triaged(handle):
            self._log(f"[SKIP] @{handle} | already_triaged")
            mark_mentions_investigated_by_handle(handle)
            return None
        
        # Fetch user info
        self._log(f"[FETCH] Getting user info...")
        user_info = {}
        try:
            result = self.user_tweets_client.get_user_tweets(
                user_name=handle,
                include_replies=False
            )
            tweets = result.get('tweets', [])
            if tweets:
                user_info = tweets[0].get('author', {})
        except Exception as e:
            self._log(f"[ERROR] Failed to fetch user: {e}")
            tweets = []
        
        if not user_info:
            self._log(f"[ERROR] Could not fetch user info for @{handle}")
            return None
        
        self._log(f"[DATA] tweets={len(tweets)} | followers={user_info.get('followers', 0)}")
        
        # Build mentions context
        mentions_context = ""
        for i, m in enumerate(mentions[:5], 1):
            mentions_context += f"\n[{i}] @{m.get('source_author_handle', '?')} ({m.get('source_author_followers', 0)} followers): {m.get('source_tweet_text', '')[:150]}..."
        
        # Build tweets text
        tweets_text = ""
        for i, tweet in enumerate(tweets[:15], 1):
            text = tweet.get('text', '')[:200]
            likes = tweet.get('likeCount', 0)
            tweets_text += f"\n[{i}] (likes={likes}) {text}"
        
        if not tweets_text:
            tweets_text = "\n[No tweets available]"
        
        # Build prompt
        prompt = DISCOVERY_USER_PROMPT.format(
            handle=handle,
            mention_count=len(mentions),
            mentions_context=mentions_context,
            user_name=user_info.get('name', ''),
            bio=user_info.get('description', ''),
            followers=user_info.get('followers', 0),
            following=user_info.get('following', 0),
            total_tweets=user_info.get('statusesCount', 0),
            account_created=user_info.get('createdAt', ''),
            is_blue_verified=user_info.get('isBlueVerified', False),
            tweets_count=len(tweets),
            tweets_text=tweets_text
        )
        
        # Call LLM
        self._log(f"[ANALYZE] Using LLM for discovery analysis...")
        response = self.llm_client.chat(
            system_prompt=DISCOVERY_SYSTEM_PROMPT,
            user_prompt=prompt
        )
        
        if "error" in response:
            self._log(f"[ERROR] LLM error: {response.get('error', '')[:50]}")
            return None
        
        # Parse response
        content = response.get("content", "")
        result = self.llm_client.parse_json_response(content)
        
        if not result:
            self._log(f"[PARSE_ERROR] @{handle}")
            return None
        
        # Process result
        discovery_status = result.get('discovery_status', 'pending')
        confidence = result.get('confidence', 0)
        project_data = result.get('project') or {}
        signals = result.get('signals') or {}
        launch_data = result.get('launch') or {}
        reasoning = result.get('reasoning', '')
        
        processing_time = time.time() - start_time
        
        self._log(f"[RESULT] @{handle} | status={discovery_status} | conf={confidence:.2f}")
        
        # Save fingerprint
        fingerprint = {
            "twitter_handle": handle,
            "tweet_id": mentions[0].get('source_tweet_id') if mentions else None,
            "author_id": user_info.get('id'),
            "stage": 0,  # Discovery stage
            "stage_name": "discovery",
            "decision": discovery_status,
            "confidence": confidence,
            "reason": result.get('rejection_reason') or reasoning[:100],
            "input_type": "discovery",
            "input_summary": f"Discovered @{handle} via {len(mentions)} mentions, {len(tweets)} tweets, {user_info.get('followers', 0)} followers",
            "input_bio": user_info.get('description', '')[:300],
            "input_followers": user_info.get('followers', 0),
            "input_tweets_count": len(tweets),
            "llm_reasoning": reasoning,
            "key_factors": {
                "mention_count": len(mentions),
                "has_website": signals.get('has_website', False),
                "has_telegram": signals.get('has_telegram', False),
                "has_discord": signals.get('has_discord', False),
                "keywords_found": signals.get('keywords_found', [])
            },
            "project_name": project_data.get('name'),
            "project_chain": project_data.get('chain'),
            "project_type": project_data.get('type'),
            "ca_detected": project_data.get('has_ca', False),
            "ca_address": project_data.get('ca_address'),
            "raw_input": {"handle": handle, "mention_count": len(mentions)},
            "raw_output": result,
            "model_used": MODEL,
            "tokens_used": response.get("usage", {}).get("total_tokens", 0),
            "processing_time": processing_time
        }
        save_fingerprint(fingerprint)
        
        # If confirmed project, save to triage
        if discovery_status == 'confirmed_project':
            triage_result = {
                "is_project": True,
                "confidence": confidence,
                "project": project_data,
                "launch": launch_data,
                "source": {
                    "tweet_id": mentions[0].get('source_tweet_id') if mentions else None,
                    "twitter_handle": f"@{handle}",
                    "author_id": user_info.get('id'),
                    "author_followers": user_info.get('followers', 0),
                    "tweet_date": datetime.now().strftime('%Y-%m-%d'),
                    "tweet_text_preview": f"Discovered via {len(mentions)} mentions"
                },
                "mentions": {
                    "tagged_accounts": [],
                    "tagged_chains": [],
                    "tagged_platforms": []
                },
                "signals": signals
            }
            
            saved = save_triage_result(triage_result)
            if saved:
                self._log(f"[SAVED] @{handle} | saved to triage")
                # Mark all mentions as converted
                for m in mentions:
                    if m.get('id'):
                        convert_mention_to_project(m['id'], 0)  # Project ID will be set later
        
        # Mark mentions as investigated
        mark_mentions_investigated_by_handle(handle)
        
        return {
            "handle": handle,
            "status": discovery_status,
            "confidence": confidence,
            "project_name": project_data.get('name'),
            "project_chain": project_data.get('chain'),
            "reasoning": reasoning
        }
    
    def run_discovery_cycle(self, min_mentions: int = 2, limit: int = 20) -> Dict[str, Any]:
        """Run a discovery cycle - investigate handles with multiple mentions."""
        
        self._log("\n" + "=" * 60)
        self._log(f"[RUN] agent.discoverer | min_mentions={min_mentions} | limit={limit}")
        self._log("=" * 60)
        
        start_time = time.time()
        
        # Get handles to investigate
        handles = get_handles_to_investigate(min_mentions=min_mentions, limit=limit)
        
        self._log(f"[QUEUE] handles_to_investigate={len(handles)}")
        
        if not handles:
            self._log("[DONE] No handles to investigate")
            return {"investigated": 0, "confirmed": 0, "rejected": 0}
        
        results = {
            "investigated": 0,
            "confirmed": 0,
            "rejected": 0,
            "pending": 0,
            "errors": 0
        }
        
        for i, handle_data in enumerate(handles, 1):
            handle = handle_data.get('mentioned_handle', '')
            mention_count = handle_data.get('mention_count', 0)
            
            self._log(f"\n[{i}/{len(handles)}] @{handle} | mentions={mention_count}")
            
            try:
                # Get all mentions for this handle
                mentions = get_mentions_by_handle(handle)
                
                result = self.investigate_handle(handle, mentions)
                
                if result:
                    results["investigated"] += 1
                    status = result.get('status', '')
                    
                    if status == 'confirmed_project':
                        results["confirmed"] += 1
                    elif status.startswith('rejected'):
                        results["rejected"] += 1
                    else:
                        results["pending"] += 1
                else:
                    results["errors"] += 1
                
                # Rate limiting
                time.sleep(2)
                
            except Exception as e:
                self._log(f"[ERROR] @{handle}: {str(e)[:50]}")
                results["errors"] += 1
        
        elapsed = time.time() - start_time
        
        self._log("\n" + "=" * 60)
        self._log(f"[DONE] investigated={results['investigated']} | confirmed={results['confirmed']} | rejected={results['rejected']} | time={elapsed:.2f}s")
        self._log("=" * 60)
        
        # Show stats
        stats = get_mention_stats()
        self._log(f"\n[STATS] total_mentions={stats.get('total_mentions', 0)} | pending={stats.get('pending_investigation', 0)} | converted={stats.get('converted_to_projects', 0)}")
        
        return results

