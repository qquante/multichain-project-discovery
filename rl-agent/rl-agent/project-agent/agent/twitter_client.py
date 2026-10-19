#!/usr/bin/env python3
"""
Twitter API Client - Complete Implementation
Endpoints: /user/info, /user_about, /user/last_tweets

Extrai dados de perfil e analisa tweets para detectar:
- Verificação (blue, business, government)
- Rename count
- Emoji abuse, hashtag abuse
- Presale/giveaway mentions
- Engagement metrics
"""

import re
import requests
import time
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("TWITTER_API_KEY", "")
BASE_URL = "https://api.twitterapi.io/twitter"

# === WORD LISTS ===
PRESALE_WORDS = [
    "presale", "pre-sale", "pre sale",
    "whitelist", "wl", "white list",
    "private sale", "seed round",
    "early access", "exclusive access"
]

GIVEAWAY_WORDS = [
    "giveaway", "give away", "giveaways",
    "airdrop", "air drop", "airdrops",
    "free tokens", "free mint",
    "claim free", "get free"
]

GOOD_WORDS = [
    "audit", "audited", "certik",
    "doxxed", "kyc", "verified team",
    "mainnet", "testnet", "beta",
    "partnership", "partnered",
    "listing", "listed", "cex",
    "roadmap", "milestone"
]

# Emoji pattern
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols extended-A
    "]+", flags=re.UNICODE
)


class TwitterAPIClient:
    """Complete client for Twitter API with profile and tweets analysis."""
    
    def __init__(self, api_key: str = API_KEY, verbose: bool = True):
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key}
        self.verbose = verbose
        self.request_count = 0
        self.rate_limit_delay = 0.5
    
    def _log(self, msg: str):
        if self.verbose:
            ts = datetime.now().strftime('%H:%M:%S')
            print(f"[{ts}] [TWITTER] {msg}", flush=True)
    
    def _request(self, endpoint: str, params: dict) -> Optional[dict]:
        """Make request with error handling."""
        url = f"{BASE_URL}{endpoint}"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            self.request_count += 1
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    return data.get("data")
            return None
        except Exception as e:
            self._log(f"Error: {str(e)[:50]}")
            return None
    
    # =========================================================================
    # ENDPOINT 1: /user/info
    # =========================================================================
    
    def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """Get basic profile data."""
        return self._request("/user/info", {"userName": username})
    
    # =========================================================================
    # ENDPOINT 2: /user_about
    # =========================================================================
    
    def get_user_about(self, username: str) -> Optional[Dict[str, Any]]:
        """Get extended profile data (rename count, affiliates)."""
        return self._request("/user_about", {"userName": username})
    
    # =========================================================================
    # ENDPOINT 3: /user/last_tweets
    # =========================================================================
    
    def get_last_tweets(self, username: str) -> Optional[Dict[str, Any]]:
        """Get last tweets from user."""
        return self._request("/user/last_tweets", {"userName": username})
    
    # =========================================================================
    # TWEET ANALYSIS
    # =========================================================================
    
    def analyze_tweets(self, tweets: List[dict]) -> Dict[str, Any]:
        """
        Analyze last 20 tweets for various metrics.
        Returns emoji abuse, hashtag abuse, presale mentions, engagement, etc.
        """
        if not tweets:
            return {
                "tweets_analyzed": 0,
                "emoji_abuse_ratio": 0,
                "hashtag_abuse_avg": 0,
                "has_presale_mentions": False,
                "has_giveaway_mentions": False,
                "good_words_count": 0
            }
        
        # Limit to 20 tweets
        tweets = tweets[:20]
        
        # Counters
        emoji_abuse_count = 0  # Tweets with 3+ emojis
        total_hashtags = 0
        total_emojis = 0
        presale_count = 0
        giveaway_count = 0
        good_words_found = set()
        
        total_likes = 0
        total_views = 0
        total_replies = 0
        total_retweets = 0
        
        original_count = 0
        reply_count = 0
        retweet_count = 0
        
        languages = set()
        cashtags = set()
        
        for tweet in tweets:
            text = (tweet.get("text") or "").lower()
            
            # Count emojis
            emojis = EMOJI_PATTERN.findall(text)
            emoji_count = len(emojis)
            total_emojis += emoji_count
            if emoji_count >= 3:
                emoji_abuse_count += 1
            
            # Count hashtags
            entities = tweet.get("entities", {})
            hashtags = entities.get("hashtags", [])
            if isinstance(hashtags, list):
                total_hashtags += len(hashtags)
            
            # Detect presale words
            for word in PRESALE_WORDS:
                if word in text:
                    presale_count += 1
                    break
            
            # Detect giveaway words
            for word in GIVEAWAY_WORDS:
                if word in text:
                    giveaway_count += 1
                    break
            
            # Detect good words
            for word in GOOD_WORDS:
                if word in text:
                    good_words_found.add(word)
            
            # Engagement
            total_likes += tweet.get("likeCount", 0) or 0
            total_views += tweet.get("viewCount", 0) or 0
            total_replies += tweet.get("replyCount", 0) or 0
            total_retweets += tweet.get("retweetCount", 0) or 0
            
            # Tweet types
            if tweet.get("retweeted_tweet"):
                retweet_count += 1
            elif tweet.get("isReply"):
                reply_count += 1
            else:
                original_count += 1
            
            # Language
            lang = tweet.get("lang")
            if lang:
                languages.add(lang)
            
            # Cashtags
            for ct in entities.get("cashtags", []) or []:
                if isinstance(ct, dict):
                    cashtags.add(ct.get("tag", ""))
        
        n = len(tweets)
        
        result = {
            # Metadata
            "tweets_analyzed": n,
            "first_tweet_at": tweets[-1].get("createdAt") if tweets else None,
            "last_tweet_at": tweets[0].get("createdAt") if tweets else None,
            
            # Abuse detection
            "emoji_abuse_ratio": emoji_abuse_count / n if n > 0 else 0,
            "emoji_abuse_count": emoji_abuse_count,
            "avg_emojis_per_tweet": total_emojis / n if n > 0 else 0,
            "hashtag_abuse_avg": total_hashtags / n if n > 0 else 0,
            "total_hashtags": total_hashtags,
            
            # Red flag words
            "has_presale_mentions": presale_count > 0,
            "presale_mentions_count": presale_count,
            "has_giveaway_mentions": giveaway_count > 0,
            "giveaway_mentions_count": giveaway_count,
            
            # Good words
            "good_words_count": len(good_words_found),
            "good_words_found": list(good_words_found),
            
            # Engagement
            "total_likes": total_likes,
            "total_views": total_views,
            "total_replies": total_replies,
            "total_retweets": total_retweets,
            "avg_likes_per_tweet": total_likes / n if n > 0 else 0,
            "avg_views_per_tweet": total_views / n if n > 0 else 0,
            "avg_engagement_rate": (total_likes + total_replies + total_retweets) / max(total_views, 1),
            
            # Tweet types
            "original_tweets_count": original_count,
            "reply_tweets_count": reply_count,
            "retweet_count": retweet_count,
            "original_ratio": original_count / n if n > 0 else 0,
            "reply_ratio": reply_count / n if n > 0 else 0,
            "retweet_ratio": retweet_count / n if n > 0 else 0,
            
            # Language
            "primary_language": list(languages)[0] if languages else None,
            "languages_used": list(languages),
            "is_multilingual": len(languages) > 1,
            
            # Cashtags
            "cashtags_used": list(cashtags),
            "cashtag_count": len(cashtags),
            
            # Raw tweets data (for future analysis)
            "raw_tweets": [
                {
                    "id": t.get("id"),
                    "text": t.get("text", ""),
                    "created_at": t.get("createdAt"),
                    "likes": t.get("likeCount", 0),
                    "views": t.get("viewCount", 0),
                    "replies": t.get("replyCount", 0),
                    "retweets": t.get("retweetCount", 0),
                    "is_reply": t.get("isReply", False),
                    "is_retweet": bool(t.get("retweeted_tweet")),
                    "lang": t.get("lang"),
                    "hashtags": [h.get("tag") for h in (t.get("entities", {}).get("hashtags") or []) if isinstance(h, dict)],
                    "mentions": [m.get("username") for m in (t.get("entities", {}).get("mentions") or []) if isinstance(m, dict)],
                    "cashtags": [c.get("tag") for c in (t.get("entities", {}).get("cashtags") or []) if isinstance(c, dict)],
                    "urls": [u.get("expanded_url") or u.get("url") for u in (t.get("entities", {}).get("urls") or []) if isinstance(u, dict)],
                    "has_media": bool(t.get("media")),
                    "media_count": len(t.get("media") or []),
                    "media_urls": [m.get("media_url_https") or m.get("url") for m in (t.get("media") or []) if isinstance(m, dict)],
                    "quoted_tweet_id": t.get("quoted_tweet", {}).get("id") if t.get("quoted_tweet") else None
                }
                for t in tweets
            ]
        }
        
        return result
    
    # =========================================================================
    # FULL PROFILE
    # =========================================================================
    
    def get_full_profile(self, username: str) -> Dict[str, Any]:
        """
        Get complete profile data from all endpoints.
        """
        self._log(f"=== Fetching @{username} ===")
        
        # 1. Get user info
        user_info = self.get_user_info(username)
        time.sleep(self.rate_limit_delay)
        
        if not user_info:
            return {"error": f"User @{username} not found"}
        
        # 2. Get user about
        user_about = self.get_user_about(username)
        time.sleep(self.rate_limit_delay)
        
        # 3. Get last tweets
        tweets_data = self.get_last_tweets(username)
        tweets = tweets_data.get("tweets", []) if tweets_data else []
        
        # Build profile
        profile = {
            # === IDENTIFICATION ===
            "twitter_id": user_info.get("id"),
            "username": user_info.get("userName"),
            "name": user_info.get("name"),
            "followers": user_info.get("followers", 0),
            "following": user_info.get("following", 0),
            "total_tweets": user_info.get("statusesCount", 0),
            "media_count": user_info.get("mediaCount", 0),
            "likes_count": user_info.get("favouritesCount", 0),
            "bio": user_info.get("description", ""),
            "url": user_info.get("url"),
            "location": user_info.get("location"),
            "created_at": user_info.get("createdAt"),
            "profile_picture": user_info.get("profilePicture"),
            "cover_picture": user_info.get("coverPicture"),
            "pinned_tweet_ids": user_info.get("pinnedTweetIds", []),
            
            # === VERIFICATION ===
            "is_blue_verified": user_info.get("isBlueVerified", False),
            "is_legacy_verified": user_info.get("isVerified", False),
            "verified_type": user_info.get("verifiedType"),
            
            # === FLAGS ===
            "is_automated": user_info.get("isAutomated", False),
            "can_dm": user_info.get("canDm", False),
            "is_protected": user_info.get("protected", False),
        }
        
        # Add user_about data
        if user_about:
            about_profile = user_about.get("about_profile", {})
            username_changes = about_profile.get("username_changes", {})
            affiliates = user_about.get("affiliates_highlighted_label", {}).get("label", {})
            identity = user_about.get("identity_profile_labels_highlighted_label", {}).get("label", {})
            
            profile.update({
                "rename_count": int(username_changes.get("count", 0)),
                "last_rename_at": username_changes.get("last_changed_at_msec"),
                "account_region": about_profile.get("account_based_in"),
                "location_verified": about_profile.get("location_accurate", False),
                "account_source": about_profile.get("source"),
                "affiliated_with": about_profile.get("affiliate_username"),
                "affiliate_name": affiliates.get("description") or identity.get("description"),
                "user_label_type": affiliates.get("userLabelType") or identity.get("userLabelType"),
            })
        
        # Add tweet analysis
        tweet_analysis = self.analyze_tweets(tweets)
        profile.update(tweet_analysis)
        
        # Calculate verification score
        score_data = self.extract_verification_score(profile)
        profile.update(score_data)
        
        self._log(f"@{username}: followers={profile['followers']} | verified={profile['verified_type_final']} | tweets_analyzed={profile['tweets_analyzed']}")
        
        return profile
    
    def extract_verification_score(self, profile: Dict) -> Dict[str, Any]:
        """Calculate verification score."""
        score = 0
        verified_type = "none"
        
        if profile.get("is_blue_verified"):
            score = 1
            verified_type = "blue"
        
        vtype = profile.get("verified_type") or ""
        label_type = profile.get("user_label_type") or ""
        
        if vtype == "Business" or "Business" in label_type:
            score = 2
            verified_type = "business"
        elif vtype == "Government" or "Government" in label_type:
            score = 3
            verified_type = "government"
        
        return {
            "verified_score": score,
            "verified_type_final": verified_type
        }


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    import json
    import sys
    
    client = TwitterAPIClient(verbose=True)
    
    test_username = sys.argv[1] if len(sys.argv) > 1 else "elonmusk"
    
    print(f"\n🐦 Testing with @{test_username}...\n")
    
    profile = client.get_full_profile(test_username)
    
    print("\n" + "="*60)
    print("📊 RESULT:")
    print("="*60)
    
    fields = [
        'username', 'followers', 'is_blue_verified', 'verified_type_final',
        'rename_count', 'is_automated', 'tweets_analyzed',
        'emoji_abuse_ratio', 'hashtag_abuse_avg',
        'has_presale_mentions', 'has_giveaway_mentions',
        'good_words_count', 'avg_likes_per_tweet'
    ]
    
    for f in fields:
        if f in profile:
            val = profile[f]
            if isinstance(val, float):
                print(f"  {f}: {val:.2f}")
            else:
                print(f"  {f}: {val}")
    
    output_file = f"twitter_{test_username}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(profile, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n✅ Full data saved to: {output_file}")

