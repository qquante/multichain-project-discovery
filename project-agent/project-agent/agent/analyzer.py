# agent/analyzer.py
"""
Stage 1 - Triage Analyzer
Uses 2 specialized LLM calls:
1. CLASSIFIER - Decides if project + who is author + extracts mentions
2. EXTRACTOR - Extracts full details (only if classifier approves)
"""
import time
import json
from typing import Dict, Any, List, Optional

from .api_client import OpenRouterClient, MODEL
from .prompts_stage1 import (
    get_classifier_system_prompt,
    get_extractor_system_prompt,
    build_classifier_prompt,
    build_extractor_prompt
)
from .database import (
    init_db,
    is_tweet_processed,
    is_handle_triaged,
    mark_tweet_processed,
    save_triage_result,
    save_fingerprint,
    save_mention,
    get_pending_tweets,
    get_triaged_projects,
    get_triage_stats
)


class TweetAnalyzer:
    
    def __init__(self, verbose: bool = True):
        self.client = OpenRouterClient(verbose=verbose)
        self.verbose = verbose
        init_db()
    
    def _log(self, msg: str):
        if self.verbose:
            print(msg)
    
    def _call_classifier(self, tweet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        LLM 1: CLASSIFIER
        Decides: is_project, is_author_the_project, mentioned_projects, has_ca
        """
        user_prompt = build_classifier_prompt(tweet)
        
        response = self.client.chat(
            system_prompt=get_classifier_system_prompt(),
            user_prompt=user_prompt
        )
        
        if "error" in response:
            return None
        
        content = response.get("content", "")
        result = self.client.parse_json_response(content)
        
        if result:
            result["_tokens"] = response.get("usage", {}).get("total_tokens", 0)
        
        return result
    
    def _call_extractor(self, tweet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        LLM 2: EXTRACTOR
        Extracts: project details, launch info, signals
        """
        user_prompt = build_extractor_prompt(tweet)
        
        response = self.client.chat(
            system_prompt=get_extractor_system_prompt(),
            user_prompt=user_prompt
        )
        
        if "error" in response:
            return None
        
        content = response.get("content", "")
        result = self.client.parse_json_response(content)
        
        if result:
            result["_tokens"] = response.get("usage", {}).get("total_tokens", 0)
        
        return result
    
    def _validate_mentions_from_api(self, tweet: Dict[str, Any], classifier_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        CRITICAL VALIDATION: Use Twitter API data to validate/override LLM decisions.
        The API gives us entities.user_mentions - this is 100% reliable!
        """
        entities_json = tweet.get('entities_json')
        real_mentions = []
        
        if entities_json:
            try:
                entities = json.loads(entities_json) if isinstance(entities_json, str) else entities_json
                real_mentions = [
                    (m.get('screen_name') or '').lower()
                    for m in entities.get('user_mentions', [])
                    if m.get('screen_name')
                ]
            except:
                pass
        
        author_lower = (tweet.get('author_username') or '').lower()
        is_author_the_project = classifier_result.get('is_author_the_project', False)
        mentioned_projects = classifier_result.get('mentioned_projects', [])
        
        # VALIDATION: If there are mentions AND author is NOT one of them
        # → The author is NOT the project, they're mentioning other projects!
        if real_mentions and author_lower not in real_mentions:
            if is_author_the_project:
                self._log(f"[OVERRIDE] LLM said is_author=TRUE but @{author_lower} NOT in mentions {real_mentions} → Forcing FALSE")
                classifier_result['is_author_the_project'] = False
                classifier_result['author_type'] = 'user'
            
            # If LLM didn't extract mentioned_projects, use the REAL mentions
            if not mentioned_projects:
                self._log(f"[OVERRIDE] LLM returned empty mentioned_projects → Using API mentions: {real_mentions}")
                classifier_result['mentioned_projects'] = [
                    {
                        "handle": f"@{m}",
                        "context": f"mentioned in tweet by @{author_lower}",
                        "confidence": 0.7
                    }
                    for m in real_mentions
                ]
        
        return classifier_result
    
    def analyze_tweet(self, tweet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyze a single tweet using 2-step LLM process."""
        
        tweet_id = tweet.get('id', '')
        author = tweet.get('author_username', '')
        author_id = tweet.get('author_id', '')
        tweet_text = tweet.get('text', '')
        
        # Check if already processed
        if is_tweet_processed(tweet_id):
            self._log(f"[SKIP] tweet_id={tweet_id} | reason=already_processed")
            return None
        
        start_time = time.time()
        total_tokens = 0
        
        # ============================================
        # STEP 1: CLASSIFIER
        # ============================================
        self._log(f"[CLASSIFY] tweet_id={tweet_id} | @{author}")
        
        classifier_result = self._call_classifier(tweet)
        
        if not classifier_result:
            self._log(f"[ERROR] tweet_id={tweet_id} | classifier_failed")
            mark_tweet_processed(tweet_id, False, 0, "classifier_error", "")
            return None
        
        total_tokens += classifier_result.get("_tokens", 0)
        
        # Apply API-based validation
        classifier_result = self._validate_mentions_from_api(tweet, classifier_result)
        
        # Extract classifier decisions
        is_project = classifier_result.get("is_project", False)
        confidence = classifier_result.get("confidence", 0)
        rejection_reason = classifier_result.get("rejection_reason")
        has_ca = classifier_result.get("has_ca", False)
        is_author_the_project = classifier_result.get("is_author_the_project", False)
        author_type = classifier_result.get("author_type", "unknown")
        mentioned_projects = classifier_result.get("mentioned_projects", [])
        
        # ============================================
        # DECISION TREE (without calling extractor yet)
        # ============================================
        
        # Case 1: Not a project → REJECT
        if not is_project:
            mark_tweet_processed(tweet_id, False, confidence, rejection_reason, json.dumps(classifier_result))
            self._save_fingerprint(tweet, classifier_result, None, "rejected", start_time, total_tokens)
            self._log(f"[REJECT] tweet_id={tweet_id} | @{author} | reason={rejection_reason} | conf={confidence:.2f}")
            return {"is_project": False, "rejection_reason": rejection_reason, "confidence": confidence}
        
        # Case 2: Has CA → Already launched
        if has_ca:
            mark_tweet_processed(tweet_id, True, confidence, "already_launched", json.dumps(classifier_result))
            self._save_fingerprint(tweet, classifier_result, None, "has_ca", start_time, total_tokens)
            ca_found = classifier_result.get("ca_found", "")
            self._log(f"[HAS_CA] tweet_id={tweet_id} | @{author} | ca={ca_found[:20]}... | conf={confidence:.2f}")
            return {"is_project": True, "has_ca": True, "ca_found": ca_found, "confidence": confidence}
        
        # Case 3: Author is NOT the project → Save mentions
        if not is_author_the_project:
            if mentioned_projects:
                for mentioned in mentioned_projects:
                    mention_data = {
                        "source_tweet_id": tweet_id,
                        "source_author_handle": author,
                        "source_author_id": author_id,
                        "source_author_followers": tweet.get('author_followers', 0),
                        "source_tweet_text": tweet_text[:500],
                        "source_tweet_date": tweet.get('created_at'),
                        "mentioned_handle": (mentioned.get('handle') or '').lstrip('@'),
                        "mentioned_handles_found": [(m.get('handle') or '').lstrip('@') for m in mentioned_projects],
                        "mention_type": author_type,
                        "author_type": author_type,
                        "confidence": mentioned.get('confidence', confidence),
                        "raw_response": classifier_result
                    }
                    mention_id = save_mention(mention_data)
                    is_inferred = mentioned.get('is_inferred', False)
                    inferred_tag = " (INFERRED)" if is_inferred else ""
                    self._log(f"[MENTION] tweet_id={tweet_id} | @{author} mentioned @{mentioned.get('handle', '')}{inferred_tag} | mention_id={mention_id}")
                
                mark_tweet_processed(tweet_id, True, confidence, "mention_saved", json.dumps(classifier_result))
                self._save_fingerprint(tweet, classifier_result, None, "mention_saved", start_time, total_tokens)
            else:
                mark_tweet_processed(tweet_id, True, confidence, "not_project_author", json.dumps(classifier_result))
                self._save_fingerprint(tweet, classifier_result, None, "not_project_skipped", start_time, total_tokens)
                self._log(f"[SKIP] tweet_id={tweet_id} | @{author} | author_type={author_type} | no_handles_found")
            
            return {"is_project": True, "is_author_the_project": False, "mentioned_projects": mentioned_projects}
        
        # Case 4: Author IS the project → Check duplicate then extract details
        twitter_handle = f"@{author}"
        
        if is_handle_triaged(twitter_handle):
            mark_tweet_processed(tweet_id, True, confidence, "duplicate", json.dumps(classifier_result))
            self._save_fingerprint(tweet, classifier_result, None, "duplicate", start_time, total_tokens)
            self._log(f"[DUPLICATE] tweet_id={tweet_id} | @{author} | already_triaged")
            return {"is_project": True, "is_author_the_project": True, "duplicate": True}
        
        # ============================================
        # STEP 2: EXTRACTOR (only for new projects where author IS the project)
        # ============================================
        self._log(f"[EXTRACT] tweet_id={tweet_id} | @{author} | extracting details...")
        
        extractor_result = self._call_extractor(tweet)
        
        if not extractor_result:
            self._log(f"[ERROR] tweet_id={tweet_id} | extractor_failed | saving with classifier data only")
            # Save with minimal data from classifier
            extractor_result = {
                "project": {"name": author, "type": "token", "chain": "unknown"},
                "launch": {"status": "pre_launch", "platform": "unknown"},
                "source": {"twitter_handle": twitter_handle, "tweet_id": tweet_id},
                "signals": {}
            }
        
        total_tokens += extractor_result.get("_tokens", 0)
        
        # Merge classifier + extractor results
        full_result = self._merge_results(classifier_result, extractor_result, tweet)
        
        # Save to triage
        saved = save_triage_result(full_result)
        mark_tweet_processed(tweet_id, True, confidence, None, json.dumps(full_result))
        
        processing_time = time.time() - start_time
        self._save_fingerprint(tweet, classifier_result, extractor_result, "triaged", start_time, total_tokens)
        
        project_data = extractor_result.get("project", {})
        project_name = project_data.get("name", author)
        project_chain = project_data.get("chain", "unknown")
        project_type = project_data.get("type", "token")
        
        self._log(f"[TRIAGED] tweet_id={tweet_id} | @{author} | name={project_name} | chain={project_chain} | type={project_type} | conf={confidence:.2f} | tokens={total_tokens}")
        
        return full_result
    
    def _merge_results(self, classifier: Dict, extractor: Dict, tweet: Dict) -> Dict:
        """Merge classifier and extractor results into final format."""
        author = tweet.get('author_username', '')
        
        return {
            "is_project": True,
            "confidence": classifier.get("confidence", 0.5),
            "rejection_reason": None,
            
            "author_analysis": {
                "is_author_the_project": classifier.get("is_author_the_project", True),
                "author_type": classifier.get("author_type", "project_official"),
                "author_credibility": classifier.get("confidence", 0.5),
                "reasoning": classifier.get("author_reasoning", "")
            },
            
            "project": extractor.get("project", {}),
            "mentioned_projects": classifier.get("mentioned_projects", []),
            "launch": extractor.get("launch", {}),
            "source": extractor.get("source", {"twitter_handle": f"@{author}"}),
            "mentions": extractor.get("mentions", {}),
            "signals": extractor.get("signals", {})
        }
    
    def _save_fingerprint(
        self,
        tweet: Dict,
        classifier: Dict,
        extractor: Optional[Dict],
        decision: str,
        start_time: float,
        total_tokens: int
    ):
        """Save decision fingerprint for debugging."""
        processing_time = time.time() - start_time
        author = tweet.get('author_username', '')
        tweet_text = tweet.get('text', '')
        
        project_data = {}
        signals = {}
        if extractor:
            project_data = extractor.get("project", {})
            signals = extractor.get("signals", {})
        
        fingerprint = {
            "twitter_handle": f"@{author}",
            "tweet_id": tweet.get('id', ''),
            "author_id": tweet.get('author_id', ''),
            "stage": 1,
            "stage_name": "triage",
            "decision": decision,
            "confidence": classifier.get("confidence", 0),
            "reason": classifier.get("rejection_reason") or decision,
            "input_type": "tweet",
            "input_summary": f"Tweet from @{author}: {tweet_text[:100]}...",
            "input_tweet_text": tweet_text[:500],
            "input_followers": tweet.get('author_followers', 0),
            "llm_reasoning": classifier.get("author_reasoning", ""),
            "key_factors": {
                "is_author_the_project": classifier.get("is_author_the_project", False),
                "author_type": classifier.get("author_type", "unknown"),
                "has_ca": classifier.get("has_ca", False),
                "mentioned_projects_count": len(classifier.get("mentioned_projects", [])),
                "keywords_found": signals.get("keywords_found", []),
                "has_links": signals.get("has_links", False),
                "has_telegram": signals.get("has_telegram", False),
                "has_website": signals.get("has_website", False),
                "has_discord": signals.get("has_discord", False)
            },
            "project_name": project_data.get("name"),
            "project_chain": project_data.get("chain"),
            "project_type": project_data.get("type"),
            "ca_detected": classifier.get("has_ca", False),
            "ca_address": classifier.get("ca_found"),
            "raw_input": {"tweet": tweet},
            "raw_output": {"classifier": classifier, "extractor": extractor},
            "model_used": MODEL,
            "tokens_used": total_tokens,
            "processing_time": processing_time
        }
        save_fingerprint(fingerprint)
    
    def analyze_batch(
        self,
        tweets: List[Dict[str, Any]],
        delay_between: float = 1.0
    ) -> Dict[str, int]:
        """Analyze a batch of tweets."""
        
        stats = {
            "total": len(tweets),
            "processed": 0,
            "projects": 0,
            "triaged": 0,
            "rejected": 0,
            "has_ca": 0,
            "mentions": 0,
            "duplicates": 0,
            "errors": 0
        }
        
        start_time = time.time()
        
        self._log(f"\n{'='*60}")
        self._log(f"[BATCH] total_tweets={len(tweets)}")
        self._log(f"{'='*60}")
        
        for i, tweet in enumerate(tweets, 1):
            self._log(f"\n[{i}/{len(tweets)}] Processing tweet...")
            
            result = self.analyze_tweet(tweet)
            
            if result is None:
                stats["errors"] += 1
            elif not result.get("is_project", False):
                stats["rejected"] += 1
            elif result.get("has_ca", False):
                stats["has_ca"] += 1
            elif not result.get("is_author_the_project", True):
                stats["mentions"] += 1
                if result.get("mentioned_projects"):
                    stats["projects"] += len(result.get("mentioned_projects", []))
            elif result.get("duplicate", False):
                stats["duplicates"] += 1
            else:
                stats["projects"] += 1
                stats["triaged"] += 1
            
            stats["processed"] += 1
            
            if i < len(tweets):
                time.sleep(delay_between)
        
        elapsed = time.time() - start_time
        
        self._log(f"\n{'='*60}")
        self._log(f"[BATCH_DONE] processed={stats['processed']} | triaged={stats['triaged']} | mentions={stats['mentions']} | rejected={stats['rejected']} | time={elapsed:.2f}s")
        self._log(f"{'='*60}")
        
        return stats
    
    def run(self, limit: int = 10, delay: float = 1.0) -> Dict[str, int]:
        """Run analyzer on pending tweets."""
        
        self._log(f"\n{'='*60}")
        self._log(f"[RUN] agent.analyzer | limit={limit}")
        self._log(f"{'='*60}")
        
        # Get pending tweets
        pending = get_pending_tweets(limit=limit)
        self._log(f"[PENDING] tweets={len(pending)}")
        
        if not pending:
            self._log("[INFO] No pending tweets to process")
            return {"total": 0, "processed": 0}
        
        # Analyze batch
        stats = self.analyze_batch(pending, delay_between=delay)
        
        # Show final stats
        triage_stats = get_triage_stats()
        self._log(f"\n[STATS] total_processed={triage_stats['total_processed']} | total_triaged={triage_stats['total_triaged']} | by_chain={triage_stats['by_chain']}")
        
        return stats
