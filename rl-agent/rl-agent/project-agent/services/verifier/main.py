# services/verifier/main.py
"""
Stage 2: Verifier Service
Runs continuously, processes ALL pending verifications.
Publishes EACH result (confirmed OR rejected) + fingerprint to Telegram.
"""

import os
import sys
import time
import json
import redis
from datetime import datetime

# Add shared modules to path
sys.path.insert(0, '/app/shared')
sys.path.insert(0, '/app')

from agent.verifier import ProjectVerifier
from agent.database import init_db, get_pending_verifications, get_verification_stats, get_fingerprints
from agent.calendar_agent import CalendarAgent
from agent.chain_utils import get_chain_group

# Configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6388')
BATCH_SIZE = 999999  # Process ALL - no limit
POLL_INTERVAL = 30  # Check for pending verifications every 30 seconds
DELAY_BETWEEN_PROJECTS = 2.0  # Delay between verifications

# Redis channels
CHANNEL_TRIAGED = 'projects:triaged'
CHANNEL_CONFIRMED = 'projects:confirmed'
CHANNEL_REJECTED = 'projects:rejected'
CHANNEL_FINGERPRINT = 'fingerprint:new'


class VerifierService:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        self.pubsub = self.redis.pubsub()
        self.verifier = ProjectVerifier(verbose=True)
        self.calendar_agent = CalendarAgent(verbose=False)  # Calendar agent for date extraction
        init_db()
        
    def log(self, msg: str):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [VERIFIER] {msg}", flush=True)
    
    def publish_confirmed_project(self, result: dict, triage_data: dict):
        """Publish confirmed project to Redis for monitoring and Telegram."""
        handle = result.get('twitter_handle', 'unknown')
        self.log(f"[VERBOSE] publish_confirmed_project START for @{handle}")
        
        user_profile = result.get('user_profile', {}) or {}
        tweet_analysis = result.get('tweet_analysis', {}) or {}
        signals = result.get('verification_signals', {}) or {}
        site = result.get('site_analysis', {}) or {}
        
        self.log(f"[VERBOSE] Building message for @{handle}...")
        
        message = {
            # Basic info
            "twitter_handle": result.get('twitter_handle', ''),
            "project_name": triage_data.get('project_name'),
            "project_ticker": triage_data.get('project_ticker') or result.get('ticker_confirmed'),
            "ticker_possibilities": result.get('ticker_possibilities', []),
            "project_type": triage_data.get('project_type'),
            "project_chain": triage_data.get('project_chain'),
            "verification_confidence": result.get('verification_confidence', 0),
            
            # User profile
            "user_profile": user_profile,
            "followers": user_profile.get('followers', 0),
            "following": user_profile.get('following', 0),
            "account_age_days": user_profile.get('account_age_days', 0),
            "account_created_at": user_profile.get('account_created_at', ''),
            "total_tweets": user_profile.get('total_tweets', 0),
            "media_count": user_profile.get('media_count', 0),
            "is_blue_verified": user_profile.get('is_blue_verified', False),
            "bio": user_profile.get('bio', ''),
            "bio_has_crypto_keywords": user_profile.get('bio_has_crypto_keywords', False),
            "bio_mentions_project": user_profile.get('bio_mentions_project', False),
            "website_url": user_profile.get('website_url', ''),
            "telegram_url": user_profile.get('telegram_url', ''),
            "discord_url": user_profile.get('discord_url', ''),
            
            # Tweet analysis
            "tweet_analysis": tweet_analysis,
            "tweets_analyzed": tweet_analysis.get('tweets_analyzed', 0),
            "crypto_related_count": tweet_analysis.get('crypto_related_count', 0),
            "project_mention_count": tweet_analysis.get('project_mention_count', 0),
            "launch_announcement_count": tweet_analysis.get('launch_announcement_count', 0),
            "spam_score": tweet_analysis.get('spam_score', 0),
            
            # Verification signals
            "verification_signals": signals,
            "consistent_project_messaging": signals.get('consistent_project_messaging', False),
            "has_pinned_tweet_about_project": signals.get('has_pinned_tweet_about_project', False),
            "multiple_launch_announcements": signals.get('multiple_launch_announcements', False),
            "bio_matches_tweets": signals.get('bio_matches_tweets', False),
            
            # Site analysis
            "site_analysis": site,
            "site_url": site.get('url', ''),
            "site_accessible": site.get('accessible', False),
            "site_title": site.get('title', ''),
            "site_description": site.get('description', ''),
            "site_has_whitepaper": site.get('has_whitepaper', False),
            "site_has_tokenomics": site.get('has_tokenomics', False),
            "site_has_roadmap": site.get('has_roadmap', False),
            "site_has_team": site.get('has_team', False),
            "site_has_audit": site.get('has_audit', False),
            "site_contract_found": site.get('contract_found', False),
            "site_contract_address": site.get('contract_address', ''),
            
            # AlphaGate enrichment
            "found_in_alphagate": result.get('found_in_alphagate', False),
            "key_followers": result.get('key_followers', []),
            "key_followers_count": result.get('key_followers_count', 0),
            "alpha_hunters": result.get('alpha_hunters', []),
            "alpha_hunters_count": result.get('alpha_hunters_count', 0),
            "followers_when_found": result.get('followers_when_found', 0),
            "best_hunter_winrate": result.get('best_hunter_winrate', 0.0),
            
            # NEW: Parâmetros adicionais do AlphaGate
            "avg_hunter_winrate": result.get('avg_hunter_winrate', 0.0),
            "hunters_with_60plus_wr": result.get('hunters_with_60plus_wr', 0),
            "ca_count": result.get('ca_count', 0),
            "rename_count": result.get('rename_count', 0),
            "alphagate_bio_changes": result.get('bio_changes_count', 0),
            "alphagate_username_changes": result.get('rename_count', 0),
            "alphagate_website_added": result.get('website_added_at') is not None,
            
            # NEW: ML Scoring data
            "ml_final_score": result.get('ml_final_score', 0) or result.get('final_score', 0),
            "ml_grade": result.get('ml_grade', '') or result.get('grade', ''),
            "ml_positive_signals": result.get('ml_positive_signals', []) or result.get('positive_signals', []),
            "ml_red_flags": result.get('ml_red_flags', []) or result.get('red_flags', []),
            "ml_recommendation": result.get('ml_recommendation', ''),
            
            # Discovery source tracking
            "discovery_source": triage_data.get('discovery_source', 'collector'),
            "discovery_keyword": triage_data.get('discovery_keyword'),
            
            # Launch info from calendar (use result first, then triage_data as fallback)
            "launch_date": result.get('launch_date') or triage_data.get('launch_date'),
            "launch_time": result.get('launch_time') or triage_data.get('launch_time'),
            "launch_urgency": result.get('launch_urgency') or triage_data.get('launch_urgency', 'unknown'),
            "launch_platform": triage_data.get('launch_platform'),
            
            # Reasoning
            "reasoning": result.get('reasoning', ''),
            
            # AI Summary in PT-BR (generated by CalendarAgent)
            "ai_summary": result.get('ai_summary', ''),
            
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            json_msg = json.dumps(message)
            self.log(f"[VERBOSE] JSON message size: {len(json_msg)} bytes")
            
            # Publish to main channel
            subscribers = self.redis.publish(CHANNEL_CONFIRMED, json_msg)
            self.log(f"[PUBLISH] {CHANNEL_CONFIRMED} | @{result.get('twitter_handle', '')} | subscribers={subscribers}")
            
            # Publish to chain-specific channel for telegram-chains service
            chain = (triage_data.get('project_chain') or 'unknown').lower()
            chain_channel = f"projects:confirmed:{get_chain_group(chain)}"
            chain_subs = self.redis.publish(chain_channel, json_msg)
            self.log(f"[PUBLISH] {chain_channel} | subscribers={chain_subs}")
            
            if subscribers == 0:
                self.log(f"[WARNING] NO SUBSCRIBERS for {CHANNEL_CONFIRMED}!")
        except Exception as e:
            self.log(f"[ERROR] Failed to publish confirmed: {str(e)}")
    
    def publish_rejected_project(self, result: dict):
        """Publish rejected project to Redis for Telegram."""
        handle = result.get('twitter_handle', 'unknown')
        self.log(f"[VERBOSE] publish_rejected_project START for @{handle}")
        
        user_profile = result.get('user_profile', {}) or {}
        tweet_analysis = result.get('tweet_analysis', {}) or {}
        
        message = {
            "twitter_handle": result.get('twitter_handle', ''),
            "rejection_reason": result.get('rejection_reason', ''),
            "verification_confidence": result.get('verification_confidence', 0),
            
            # User profile
            "user_profile": user_profile,
            "followers": user_profile.get('followers', 0),
            "following": user_profile.get('following', 0),
            "account_age_days": user_profile.get('account_age_days', 0),
            "total_tweets": user_profile.get('total_tweets', 0),
            "media_count": user_profile.get('media_count', 0),
            "is_blue_verified": user_profile.get('is_blue_verified', False),
            "bio": user_profile.get('bio', ''),
            
            # Tweet analysis
            "tweet_analysis": tweet_analysis,
            "tweets_analyzed": tweet_analysis.get('tweets_analyzed', 0),
            "crypto_related_count": tweet_analysis.get('crypto_related_count', 0),
            "spam_score": tweet_analysis.get('spam_score', 0),
            
            # NEW: AlphaGate data para projetos rejeitados
            "ca_count": result.get('ca_count', 0),
            "rename_count": result.get('rename_count', 0),
            
            # NEW: ML Scoring data para projetos rejeitados
            "ml_final_score": result.get('ml_final_score', 0) or result.get('final_score', 0),
            "ml_grade": result.get('ml_grade', '') or result.get('grade', ''),
            "ml_positive_signals": result.get('ml_positive_signals', []) or result.get('positive_signals', []),
            "ml_red_flags": result.get('ml_red_flags', []) or result.get('red_flags', []),
            "blacklist_matched": result.get('blacklist_matched', []),
            
            # Discovery source tracking
            "discovery_source": result.get('discovery_source', 'collector'),
            "discovery_keyword": result.get('discovery_keyword'),
            
            # Reasoning
            "reasoning": result.get('reasoning', ''),
            
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            json_msg = json.dumps(message)
            self.log(f"[VERBOSE] JSON message size: {len(json_msg)} bytes")
            subscribers = self.redis.publish(CHANNEL_REJECTED, json_msg)
            self.log(f"[PUBLISH] {CHANNEL_REJECTED} | @{result.get('twitter_handle', '')} | subscribers={subscribers}")
            if subscribers == 0:
                self.log(f"[WARNING] NO SUBSCRIBERS for {CHANNEL_REJECTED}!")
        except Exception as e:
            self.log(f"[ERROR] Failed to publish rejected: {str(e)}")
    
    def publish_fingerprint(self, twitter_handle: str):
        """Publish latest fingerprint for this project to Redis."""
        self.log(f"[VERBOSE] publish_fingerprint START for @{twitter_handle}")
        fingerprints = get_fingerprints(twitter_handle=twitter_handle, stage=2, limit=1)
        
        if fingerprints:
            fp = fingerprints[0]
            try:
                json_msg = json.dumps(fp)
                subscribers = self.redis.publish(CHANNEL_FINGERPRINT, json_msg)
                self.log(f"[PUBLISH] {CHANNEL_FINGERPRINT} | @{twitter_handle} | decision={fp.get('decision')} | subscribers={subscribers}")
                if subscribers == 0:
                    self.log(f"[WARNING] NO SUBSCRIBERS for {CHANNEL_FINGERPRINT}!")
            except Exception as e:
                self.log(f"[ERROR] Failed to publish fingerprint: {str(e)}")
        else:
            self.log(f"[VERBOSE] No fingerprints found for @{twitter_handle}")
    
    def process_pending_verifications(self):
        """Process ALL pending verifications."""
        pending = get_pending_verifications(limit=BATCH_SIZE)
        
        if not pending:
            return 0
        
        self.log(f"Processing {len(pending)} pending verifications...")
        
        start_time = time.time()
        processed = 0
        confirmed = 0
        rejected = 0
        
        for i, project in enumerate(pending, 1):
            try:
                handle = project.get('twitter_handle', 'unknown')
                source = project.get('discovery_source', 'collector')
                source_tag = "[ALPHAGATE]" if source == 'alphagate' else "[COLLECTOR]"
                self.log(f"[{i}/{len(pending)}] {source_tag} Verifying @{handle}...")
                
                result = self.verifier.verify_project(project)
                processed += 1
                
                if result:
                    status = result.get('verification_status', 'pending')
                    
                    if status == 'confirmed':
                        confirmed += 1
                        
                        user_profile = result.get('user_profile', {}) or {}
                        site_analysis = result.get('site_analysis', {}) or {}
                        raw_tweets = result.get('raw_tweets', [])
                        pinned_tweet = result.get('pinned_tweet', '')
                        website_content = site_analysis.get('raw_content', '') or site_analysis.get('content_preview', '')
                        
                        # 1. Analyze calendar data FIRST to get ticker_possibilities
                        try:
                            calendar_result = self.calendar_agent.analyze_and_save(
                                twitter_handle=handle,
                                bio=user_profile.get('bio', ''),
                                tweets=raw_tweets,
                                pinned_tweet=pinned_tweet,
                                website_content=website_content,
                                chain=project.get('project_chain', 'unknown'),
                                project_name=project.get('project_name'),
                                project_ticker=project.get('project_ticker'),
                                current_urgency=result.get('launch_urgency', 'unknown'),
                                current_launch_date=result.get('launch_date')
                            )
                            # Get ticker_possibilities from calendar analysis
                            if calendar_result:
                                result['ticker_possibilities'] = calendar_result.get('ticker_possibilities', [])
                                result['ticker_confirmed'] = calendar_result.get('ticker_confirmed')
                                # Update launch info if found
                                if calendar_result.get('launch_date'):
                                    result['launch_date'] = calendar_result.get('launch_date')
                                    result['launch_time'] = calendar_result.get('launch_time')
                                    result['launch_urgency'] = calendar_result.get('launch_urgency')
                            self.log(f"[CALENDAR] Analyzed @{handle} | tickers={result.get('ticker_possibilities', [])[:2]}")
                        except Exception as cal_e:
                            self.log(f"[CALENDAR_ERROR] @{handle}: {str(cal_e)[:50]}")
                            result['ticker_possibilities'] = []
                        
                        # 2. Generate AI summary in PT-BR (with tweets for context!)
                        try:
                            ai_summary = self.calendar_agent.generate_project_summary(
                                project_name=project.get('project_name'),
                                chain=project.get('project_chain', 'unknown'),
                                project_type=project.get('project_type'),
                                bio=user_profile.get('bio', ''),
                                tweets=raw_tweets,  # Pass tweets for better context
                                website_summary=site_analysis.get('content_preview', ''),
                                launch_date=result.get('launch_date'),
                                launch_urgency=result.get('launch_urgency', 'unknown')
                            )
                            result['ai_summary'] = ai_summary
                            self.log(f"[AI_SUMMARY] Generated {len(ai_summary)} chars for @{handle}")
                        except Exception as sum_e:
                            self.log(f"[AI_SUMMARY_ERROR] @{handle}: {str(sum_e)[:50]}")
                            result['ai_summary'] = ''
                        
                        # 3. Now publish with all data
                        self.publish_confirmed_project(result, project)
                        self.log(f"[CALENDAR] Saved @{handle} to launch calendar")
                        
                    elif status == 'rejected':
                        rejected += 1
                        self.publish_rejected_project(result)
                    
                    # Always publish fingerprint
                    self.publish_fingerprint(handle)
                
                time.sleep(DELAY_BETWEEN_PROJECTS)
                
            except Exception as e:
                self.log(f"[ERROR] Verification failed for @{handle}: {str(e)}")
                continue
        
        elapsed = time.time() - start_time
        self.log(f"Batch complete | processed={processed} | confirmed={confirmed} | rejected={rejected} | time={elapsed:.1f}s")
        
        return processed
    
    def handle_triaged_notification(self, message):
        """Handle notification of new triaged project."""
        try:
            data = json.loads(message['data'])
            handle = data.get('twitter_handle', 'unknown')
            
            self.log(f"[NOTIFICATION] New triaged project: @{handle}")
            
            # Process pending verifications
            self.process_pending_verifications()
            
        except Exception as e:
            self.log(f"[ERROR] Failed to handle notification: {str(e)}")
    
    def run(self):
        """Main loop: listen to Redis and verify projects continuously."""
        self.log("Service started")
        self.log(f"Redis: {REDIS_URL}")
        self.log(f"Batch size: UNLIMITED (processing all)")
        
        # Show initial stats
        stats = get_verification_stats()
        self.log(f"[STATS] total={stats['total_verified']} | confirmed={stats['confirmed']} | rejected={stats['rejected']}")
        
        # Subscribe to triaged projects channel
        self.pubsub.subscribe(CHANNEL_TRIAGED)
        self.log(f"Subscribed to: {CHANNEL_TRIAGED}")
        
        # Process any existing pending verifications first
        self.process_pending_verifications()
        
        last_poll = time.time()
        
        while True:
            try:
                # Check for Redis messages (non-blocking)
                message = self.pubsub.get_message(timeout=1.0)
                
                if message and message['type'] == 'message':
                    self.handle_triaged_notification(message)
                
                # Also poll periodically in case we missed messages
                if time.time() - last_poll > POLL_INTERVAL:
                    pending = get_pending_verifications(limit=1)
                    if pending:
                        self.log(f"[POLL] Found pending verifications, processing...")
                        self.process_pending_verifications()
                    last_poll = time.time()
                
                time.sleep(0.1)  # Small sleep to prevent CPU spinning
                
            except KeyboardInterrupt:
                self.log("Shutting down...")
                self.pubsub.close()
                break
            except Exception as e:
                self.log(f"[ERROR] {str(e)}")
                time.sleep(5)  # Wait before retry


if __name__ == "__main__":
    service = VerifierService()
    service.run()
