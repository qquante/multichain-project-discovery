# agent/verifier.py
import sys
sys.path.append('..')

import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from .api_client import OpenRouterClient, MODEL
from .prompts import get_verification_system_prompt, build_verification_prompt
from .website_reader import WebsiteReader, extract_site_info
from .database import (
    init_db,
    get_pending_verifications,
    is_handle_verified,
    save_verification_result,
    save_fingerprint,
    get_verified_projects,
    get_verification_stats
)
from .alphagate_client import AlphaGateClient
from .ca_detector import is_project_launched, detect_ca

# Import user clients
from users.api_client import UserInfoClient, UserTweetsClient
from agent.twitter_cache import get_or_fetch_user_tweets, get_or_fetch_user_info


class ProjectVerifier:
    """Stage 2: Verify triaged projects by analyzing user profile, tweets, and website."""
    
    def __init__(self, verbose: bool = True):
        self.llm_client = OpenRouterClient(verbose=verbose)
        self.user_info_client = UserInfoClient(verbose=verbose)
        self.user_tweets_client = UserTweetsClient(verbose=verbose)
        self.website_reader = WebsiteReader(verbose=verbose)
        self.alphagate_client = AlphaGateClient(verbose=verbose, delay=1.0)  # 1s delay between requests
        self.verbose = verbose
        init_db()
    
    def _log(self, msg: str):
        if self.verbose:
            print(msg)
    
    def fetch_user_data(
        self,
        author_id: Optional[str],
        twitter_handle: str
    ) -> Dict[str, Any]:
        """Fetch user info and recent tweets INCLUDING pinned tweet."""
        
        user_info = None
        tweets = []
        pin_tweet = None
        
        # Try cache/user info first
        if author_id:
            user_info = get_or_fetch_user_info(
                self.user_info_client,
                author_id=author_id,
                handle=twitter_handle,
                ttl_hours=6
            )
        
        # Get recent tweets (cached)
        try:
            response = get_or_fetch_user_tweets(
                self.user_tweets_client,
                handle=twitter_handle,
                author_id=author_id,
                include_replies=False,
                ttl_hours=6
            )
            
            tweets = response.get('tweets', []) or []
            pin_tweet = response.get('pin_tweet')  # CRITICAL: Capture pinned tweet!
            
            # CRITICAL: Include pinned tweet at the START of the list
            # This ensures the LLM analyzes it for CA detection
            if pin_tweet:
                # Mark it as pinned so prompt can highlight it
                pin_tweet['_is_pinned'] = True
                # Check if pin_tweet is already in tweets list (avoid duplicates)
                pin_id = pin_tweet.get('id')
                tweet_ids = [t.get('id') for t in tweets]
                if pin_id not in tweet_ids:
                    tweets = [pin_tweet] + tweets
                    self._log(f"[PIN_TWEET] Added pinned tweet to analysis: {pin_tweet.get('text', '')[:50]}...")
                else:
                    # Mark the existing tweet as pinned
                    for t in tweets:
                        if t.get('id') == pin_id:
                            t['_is_pinned'] = True
                            break
            
            # If we didn't get user_info, extract from first tweet
            if not user_info and tweets:
                user_info = tweets[0].get('author', {}) or {}
                
        except Exception as e:
            self._log(f"[ERROR] Failed to fetch tweets: {e}")
        
        return {
            "user_info": user_info or {},
            "tweets": tweets,
            "pin_tweet": pin_tweet
        }
    
    def verify_project(self, triage_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Verify a single triaged project."""
        
        twitter_handle = triage_data.get('twitter_handle', '')
        author_id = triage_data.get('author_id', '')
        
        self._log(f"\n[VERIFY] @{twitter_handle} | author_id={author_id}")
        
        # Check if already verified
        if is_handle_verified(twitter_handle):
            self._log(f"[SKIP] @{twitter_handle} | already_verified")
            return None
        
        # Fetch user data
        self._log(f"[FETCH] Getting user info and tweets...")
        user_data = self.fetch_user_data(author_id, twitter_handle)
        
        user_info = user_data.get('user_info', {})
        tweets = user_data.get('tweets', [])
        
        self._log(f"[DATA] user_info={'yes' if user_info else 'no'} | tweets={len(tweets)}")
        
        # Enrich with AlphaGate data
        alphagate_data = {}
        try:
            twitter_id = user_info.get('id') or author_id
            if twitter_id:
                self._log(f"[ALPHAGATE] Enriching @{twitter_handle}...")
                alphagate_data = self.alphagate_client.enrich_project(twitter_handle, twitter_id)
                if alphagate_data.get('found_in_alphagate'):
                    self._log(f"[ALPHAGATE] Found! key_followers={alphagate_data.get('key_followers_count', 0)} | hunters={alphagate_data.get('alpha_hunters_count', 0)}")
                else:
                    self._log(f"[ALPHAGATE] Not found in AlphaGate database")
        except Exception as e:
            self._log(f"[ALPHAGATE] Error: {str(e)[:50]}")
        
        # If no data at all, mark as pending
        if not user_info and not tweets:
            self._log(f"[PENDING] @{twitter_handle} | no_data_available")
            return {
                "verification_status": "pending",
                "verification_confidence": 0.0,
                "rejection_reason": "no_data_available",
                "twitter_handle": twitter_handle,
                "user_profile": {},
                "tweet_analysis": {"tweets_analyzed": 0},
                "verification_signals": {},
                "site_analysis": {},
                "reasoning": "Could not fetch user data"
            }
        
        # ============================================
        # PRE-LLM CHECK: Detect CA programmatically
        # ============================================
        # This catches CAs that the LLM might miss!
        bio = user_info.get('description', '') or user_info.get('bio', '') or ''
        pin_tweet_data = user_data.get('pin_tweet')
        pin_tweet_text = ''
        if pin_tweet_data:
            pin_tweet_text = pin_tweet_data.get('text', '') or ''
        
        # Get tweet texts
        tweet_texts = [t.get('text', '') for t in tweets if t.get('text')]
        
        # Check for CA/launch indicators BEFORE calling LLM
        launched, reason, evidence = is_project_launched(
            bio=bio,
            tweets=tweet_texts,
            pinned_tweet=pin_tweet_text
        )
        
        if launched:
            self._log(f"[PRE-CHECK] @{twitter_handle} | ALREADY LAUNCHED | {reason}")
            if evidence:
                self._log(f"[PRE-CHECK] Evidence: {evidence[:60]}...")
            
            # Return rejection without calling LLM (save tokens!)
            return {
                "verification_status": "rejected",
                "verification_confidence": 0.95,
                "rejection_reason": "already_launched",
                "twitter_handle": twitter_handle,
                "user_profile": {
                    "bio": bio[:200],
                    "followers": user_info.get('followers_count', 0),
                    "following": user_info.get('following_count', 0),
                    "account_created_at": user_info.get('created_at', ''),
                    "total_tweets": user_info.get('statuses_count', 0),
                },
                "tweet_analysis": {"tweets_analyzed": len(tweets)},
                "verification_signals": {},
                "site_analysis": {},
                "reasoning": f"Project already launched: {reason}. Evidence: {evidence}",
                "ca_detected": True,
                "ca_address": evidence if 'CA found' in reason else None,
                "pre_check_rejection": True
            }
        
        # Find and fetch website content
        site_url = None
        site_content = None
        site_raw_info = {}
        
        # Try to find project website
        site_url = self.website_reader.find_project_website(user_info, tweets)
        
        if site_url:
            self._log(f"[WEBSITE] Found URL: {site_url[:50]}...")
            site_result = self.website_reader.read_url(site_url)
            
            if site_result.get('success'):
                site_content = site_result.get('content', '')
                site_raw_info = extract_site_info(site_content)
                site_raw_info['url'] = site_url
                site_raw_info['accessible'] = True
                site_raw_info['checked_at'] = datetime.now().isoformat()
                site_raw_info['raw_content'] = site_content
                self._log(f"[WEBSITE] Content fetched: {len(site_content)} chars")
            else:
                site_raw_info = {
                    'url': site_url,
                    'accessible': False,
                    'error': site_result.get('error', 'Unknown error'),
                    'checked_at': datetime.now().isoformat()
                }
                self._log(f"[WEBSITE] Failed to fetch: {site_result.get('error', '')[:30]}")
        else:
            self._log(f"[WEBSITE] No project website found")
        
        # Build prompt with website content AND AlphaGate data
        prompt = build_verification_prompt(
            triage_data, 
            user_info, 
            tweets,
            site_url=site_url,
            site_content=site_content,
            alphagate_data=alphagate_data
        )
        
        # Call LLM
        response = self.llm_client.chat(
            system_prompt=get_verification_system_prompt(),
            user_prompt=prompt
        )
        
        if "error" in response:
            self._log(f"[ERROR] @{twitter_handle} | {response.get('error', '')[:50]}")
            return None
        
        # Parse response
        content = response.get("content", "")
        result = self.llm_client.parse_json_response(content)
        
        if not result:
            self._log(f"[PARSE_ERROR] @{twitter_handle}")
            return None
        
        # Add raw data for storage
        result['raw_user_info'] = user_info
        result['raw_tweets'] = tweets
        result['pinned_tweet'] = pin_tweet_text
        
        # Add AlphaGate enrichment data (ALL fields)
        result['alphagate_data'] = alphagate_data
        result['key_followers'] = alphagate_data.get('key_followers', [])
        result['key_followers_count'] = alphagate_data.get('key_followers_count', 0)
        result['alpha_hunters'] = alphagate_data.get('alpha_hunters', [])
        result['alpha_hunters_count'] = alphagate_data.get('alpha_hunters_count', 0)
        result['followers_when_found'] = alphagate_data.get('followers_when_found', 0)
        result['best_hunter_winrate'] = alphagate_data.get('best_hunter_winrate', 0.0)
        result['found_in_alphagate'] = alphagate_data.get('found_in_alphagate', False)
        # Alerts data (historical changes)
        result['alphagate_alerts'] = alphagate_data.get('alerts', [])
        alerts_summary = alphagate_data.get('alerts_summary', {})
        result['alphagate_bio_changes'] = alerts_summary.get('bio_changes', 0)
        result['alphagate_username_changes'] = alerts_summary.get('username_changes', 0)
        result['alphagate_website_added'] = alerts_summary.get('website_added', False)
        result['alphagate_last_website'] = alerts_summary.get('last_website')
        
        # Merge site analysis: LLM analysis (semantic) + extracted data (structural)
        llm_site_analysis = result.get('site_analysis', {})
        if site_raw_info or llm_site_analysis:
            merged_site = {}
            
            # Add structural data from extraction
            if site_raw_info:
                merged_site['url'] = site_raw_info.get('url')
                merged_site['accessible'] = site_raw_info.get('accessible', False)
                merged_site['checked_at'] = site_raw_info.get('checked_at')
                merged_site['raw_content'] = site_raw_info.get('raw_content')
                merged_site['social_links'] = site_raw_info.get('social_links', [])
                # Contract detection is mathematical, keep from extraction
                if site_raw_info.get('contract_found'):
                    merged_site['contract_found'] = True
                    merged_site['contract_address'] = site_raw_info.get('contract_address')
            
            # Add semantic analysis from LLM (whitepaper, tokenomics, etc)
            if llm_site_analysis:
                merged_site['title'] = llm_site_analysis.get('title') or llm_site_analysis.get('site_title')
                merged_site['description'] = llm_site_analysis.get('description') or llm_site_analysis.get('site_description')
                merged_site['content_preview'] = llm_site_analysis.get('content_preview')
                merged_site['has_whitepaper'] = llm_site_analysis.get('has_whitepaper', False)
                merged_site['has_tokenomics'] = llm_site_analysis.get('has_tokenomics', False)
                merged_site['has_roadmap'] = llm_site_analysis.get('has_roadmap', False)
                merged_site['has_team'] = llm_site_analysis.get('has_team', llm_site_analysis.get('has_team_info', False))
                merged_site['has_audit'] = llm_site_analysis.get('has_audit', False)
                merged_site['analysis'] = llm_site_analysis.get('analysis', llm_site_analysis.get('analysis_summary', ''))
                # LLM may also find CA contextually
                if llm_site_analysis.get('contract_found') and not merged_site.get('contract_found'):
                    merged_site['contract_found'] = True
                    merged_site['contract_address'] = llm_site_analysis.get('contract_address')
            
            result['site_analysis'] = merged_site
        
        # Log result
        status = result.get('verification_status', 'unknown')
        confidence = result.get('verification_confidence', 0)
        rejection = result.get('rejection_reason', '')
        has_site = 'site=yes' if site_url else 'site=no'
        
        if status == 'confirmed':
            self._log(f"[CONFIRMED] @{twitter_handle} | conf={confidence:.2f} | {has_site}")
        elif status == 'rejected':
            self._log(f"[REJECTED] @{twitter_handle} | reason={rejection} | conf={confidence:.2f} | {has_site}")
        else:
            self._log(f"[PENDING] @{twitter_handle} | conf={confidence:.2f} | {has_site}")
        
        # Save fingerprint
        user_profile = result.get('user_profile', {})
        tweet_analysis = result.get('tweet_analysis', {})
        verification_signals = result.get('verification_signals', {})
        
        fingerprint = {
            "twitter_handle": twitter_handle,
            "tweet_id": triage_data.get('source_tweet_id'),
            "author_id": author_id,
            "stage": 2,
            "stage_name": "verification",
            "decision": status,
            "confidence": confidence,
            "reason": rejection if status == 'rejected' else "legitimate_project" if status == 'confirmed' else "needs_more_data",
            "input_type": "profile_tweets_site",
            "input_summary": f"Verified @{twitter_handle}: {len(tweets)} tweets, {user_info.get('followers', 0)} followers, site={'yes' if site_url else 'no'}",
            "input_bio": user_info.get('description', '')[:300],
            "input_followers": user_info.get('followers', 0),
            "input_tweets_count": len(tweets),
            "input_site_url": site_url,
            "llm_reasoning": result.get('reasoning', ''),
            "key_factors": {
                "bio_has_crypto_keywords": user_profile.get('bio_has_crypto_keywords', False),
                "bio_mentions_project": user_profile.get('bio_mentions_project', False),
                "consistent_project_messaging": verification_signals.get('consistent_project_messaging', False),
                "has_pinned_tweet_about_project": verification_signals.get('has_pinned_tweet_about_project', False),
                "bio_matches_tweets": verification_signals.get('bio_matches_tweets', False),
                "has_website": user_profile.get('has_website', False),
                "has_telegram": user_profile.get('has_telegram', False),
                "has_discord": user_profile.get('has_discord', False),
                "crypto_related_tweets": tweet_analysis.get('crypto_related_count', 0),
                "spam_score": tweet_analysis.get('spam_score', 0),
                "site_has_whitepaper": result.get('site_analysis', {}).get('has_whitepaper', False),
                "site_has_tokenomics": result.get('site_analysis', {}).get('has_tokenomics', False)
            },
            "project_name": triage_data.get('project_name'),
            "project_chain": triage_data.get('project_chain'),
            "project_type": triage_data.get('project_type'),
            "ca_detected": result.get('site_analysis', {}).get('contract_found', False),
            "ca_address": result.get('site_analysis', {}).get('contract_address'),
            "raw_input": {
                "triage_data": triage_data,
                "user_info_summary": {
                    "followers": user_info.get('followers'),
                    "bio": user_info.get('description', '')[:200]
                },
                "tweets_count": len(tweets),
                "site_url": site_url
            },
            "raw_output": result,
            "model_used": MODEL,
            "tokens_used": response.get("usage", {}).get("total_tokens", 0),
            "processing_time": response.get("elapsed", 0)
        }
        save_fingerprint(fingerprint)
        
        # Save result
        saved = save_verification_result(result, triage_data)
        if saved:
            self._log(f"[SAVED] @{twitter_handle}")
        
        return result
    
    def verify_batch(
        self,
        projects: List[Dict[str, Any]],
        delay_between: float = 2.0
    ) -> Dict[str, int]:
        """Verify a batch of triaged projects."""
        
        stats = {
            "total": len(projects),
            "verified": 0,
            "confirmed": 0,
            "rejected": 0,
            "pending": 0,
            "errors": 0
        }
        
        start_time = time.time()
        
        self._log(f"\n{'='*60}")
        self._log(f"[BATCH_VERIFY] total_projects={len(projects)}")
        self._log(f"{'='*60}")
        
        for i, project in enumerate(projects, 1):
            self._log(f"\n[{i}/{len(projects)}] Verifying...")
            
            result = self.verify_project(project)
            
            if result is None:
                stats["errors"] += 1
            else:
                stats["verified"] += 1
                status = result.get("verification_status", "")
                
                if status == "confirmed":
                    stats["confirmed"] += 1
                elif status == "rejected":
                    stats["rejected"] += 1
                else:
                    stats["pending"] += 1
            
            if i < len(projects):
                time.sleep(delay_between)
        
        elapsed = time.time() - start_time
        
        self._log(f"\n{'='*60}")
        self._log(f"[BATCH_DONE] verified={stats['verified']} | confirmed={stats['confirmed']} | rejected={stats['rejected']} | pending={stats['pending']} | time={elapsed:.2f}s")
        self._log(f"{'='*60}")
        
        return stats
    
    def run(self, limit: int = 10, delay: float = 2.0) -> Dict[str, int]:
        """Run verifier on pending triaged projects."""
        
        self._log(f"\n{'='*60}")
        self._log(f"[RUN] agent.verifier | limit={limit}")
        self._log(f"{'='*60}")
        
        # Get pending verifications
        pending = get_pending_verifications(limit=limit)
        self._log(f"[PENDING] projects={len(pending)}")
        
        if not pending:
            self._log("[INFO] No pending projects to verify")
            return {"total": 0, "verified": 0}
        
        # Verify batch
        stats = self.verify_batch(pending, delay_between=delay)
        
        # Show final stats
        verification_stats = get_verification_stats()
        self._log(f"\n[STATS] confirmed={verification_stats['confirmed']} | rejected={verification_stats['rejected']} | pending_verification={verification_stats['pending_verification']}")
        
        return stats

