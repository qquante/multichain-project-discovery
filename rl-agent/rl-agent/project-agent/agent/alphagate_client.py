"""
AlphaGate API Client - Complete Implementation
Fetches all available data from AlphaGate API for project enrichment.

Endpoints:
- /child - Profile data + daily_stats
- /child/first-followers - Key followers list
- /child/parents - Alpha hunters with performance
- /child/alerts - Historical changes (renames, bio, website)
- /tweets/contract-tweets - Tweets mentioning CAs
"""

import time
import os
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class AlphaGateClient:
    """Complete client for AlphaGate API with all endpoints."""
    
    BASE_URL = "https://api.alphagate.io/api/v1"
    
    # Headers required for API
    HEADERS = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'origin': 'https://alphagate.io',
        'referer': 'https://alphagate.io/',
        'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    def __init__(self, verbose: bool = True, delay: float = 1.0):
        self.verbose = verbose
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        
        # Load cookies from environment
        cookies = {
            'userId': os.getenv('ALPHAGATE_USER_ID', ''),
            'extensionSessionId': os.getenv('ALPHAGATE_SESSION_ID', '')
        }
        self.session.cookies.update(cookies)
        self.last_request_time = 0
    
    def _log(self, msg: str):
        if self.verbose:
            ts = datetime.now().strftime('%H:%M:%S')
            print(f"[{ts}] [ALPHAGATE] {msg}", flush=True)
    
    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request_time = time.time()
    
    def _request(self, endpoint: str, params: dict = None, max_retries: int = 3) -> Optional[dict]:
        """Make request with retry/backoff."""
        self._rate_limit()
        url = f"{self.BASE_URL}{endpoint}"
        
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('message') in ['Fetched data successfully', 'Fetched alerts', 'Fetched tweets']:
                        return data.get('data', {})
                    return None
                elif response.status_code == 404:
                    return None
                elif response.status_code >= 500:
                    if attempt < max_retries - 1:
                        time.sleep((attempt + 1) * 3)
                        continue
                    return None
                else:
                    self._log(f"Request failed: {response.status_code}")
                    return None
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 3)
                    continue
                self._log(f"Error: {str(e)[:50]}")
                return None
        
        return None

    # ENDPOINT 1: /child - Profile + daily_stats
    
    def get_child(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get complete profile data for a project.
        Returns: twitter_id, name, bio, socials, contracts, daily_stats, etc.
        """
        data = self._request('/child', {'username': username.lstrip('@')})
        
        if not data:
            return None
        
        child = data.get('child')
        if not child:
            return None
        
        # Parse daily_stats for derived metrics
        daily_stats = child.get('daily_stats', []) or []
        
        result = {
            # Identification
            'twitter_id': child.get('id'),
            'username': child.get('username'),
            'name': child.get('name'),
            'bio': child.get('description'),
            
            # Profile
            'created_at': child.get('created_at'),
            'profile_picture': child.get('profile_image_url'),
            'cover_picture': child.get('profile_banner_url'),
            'is_unavailable': child.get('unavailable', False),
            'is_flagged': child.get('flag', False),
            
            # Metrics (current)
            'followers_count': child.get('followers_count', 0),
            'key_followers_count': child.get('key_followers_count', 0),
            'followers_when_found': child.get('followers_when_found', 0),
            
            # From last daily_stat
            'following_count': daily_stats[-1].get('following_count', 0) if daily_stats else 0,
            'tweet_count': daily_stats[-1].get('tweet_count', 0) if daily_stats else 0,
            'listed_count': daily_stats[-1].get('listed_count', 0) if daily_stats else 0,
            'alphagate_score': daily_stats[-1].get('score', 0) if daily_stats else 0,
            
            # Classification
            'project_tags': child.get('tag', []),
            'project_chains': child.get('chain', []),
            'primary_tag': (child.get('tag') or [None])[0],
            'primary_chain': (child.get('chain') or [None])[0],
            
            # Contracts
            'contracts': child.get('contracts', []),
            'ca_count': len(child.get('contracts', [])),
            
            # Socials
            'socials': child.get('social', {}).get('socials', []),
            'has_website': 'website' in child.get('social', {}).get('socials', []),
            'has_telegram': 'telegram' in child.get('social', {}).get('socials', []),
            'has_discord': 'discord' in child.get('social', {}).get('socials', []),
            'site_url': child.get('social', {}).get('website', {}).get('expanded_url'),
            'telegram_url': child.get('social', {}).get('telegram', {}).get('expanded_url'),
            
            # Renames
            'prev_usernames': child.get('prev_usernames', []),
            'rename_count': len(child.get('prev_usernames', [])),
            
            # Discovery
            'found_at': child.get('timestamp'),
            'found_in_alphagate': True,
            
            # Temporal data
            'daily_stats': daily_stats,
            'days_tracked': len(daily_stats),
            'first_tracked_at': daily_stats[0].get('timestamp') if daily_stats else None,
            'last_tracked_at': daily_stats[-1].get('timestamp') if daily_stats else None,
        }
        
        # Calculate growth metrics
        if len(daily_stats) >= 2:
            first = daily_stats[0]
            last = daily_stats[-1]
            days = max(1, len(daily_stats) - 1)
            
            result['followers_growth_total'] = last.get('followers_count', 0) - first.get('followers_count', 0)
            result['followers_growth_daily_avg'] = result['followers_growth_total'] / days
            result['tweets_growth_total'] = last.get('tweet_count', 0) - first.get('tweet_count', 0)
            result['score_growth'] = last.get('score', 0) - first.get('score', 0)
        
        self._log(f"@{username}: profile loaded | followers={result['followers_count']} | days_tracked={result['days_tracked']}")
        return result

    # ENDPOINT 2: /child/first-followers - Key followers list
    
    def get_first_followers(self, twitter_id: str) -> Dict[str, Any]:
        """
        Get first followers and key followers.
        Key followers have parent != null.
        """
        data = self._request('/child/first-followers', {'twitterId': twitter_id})
        
        if not data or 'followers' not in data:
            return {
                'first_followers_count': 0,
                'key_followers_count': 0,
                'key_followers_list': [],
                'max_key_follower_reach': 0
            }
        
        followers = data['followers']
        key_followers = [f for f in followers if f.get('parent') is not None]
        
        result = {
            'first_followers_count': len(followers),
            'key_followers_count': len(key_followers),
            'key_followers_list': [f.get('username') for f in key_followers],
            'key_followers': [
                {
                    'username': f.get('username'),
                    'followers_count': f.get('public_metrics', {}).get('followers_count', 0)
                }
                for f in key_followers
            ],
            'max_key_follower_reach': max(
                [f.get('public_metrics', {}).get('followers_count', 0) for f in key_followers],
                default=0
            ),
            'avg_key_follower_reach': sum(
                [f.get('public_metrics', {}).get('followers_count', 0) for f in key_followers]
            ) / max(len(key_followers), 1),
            'total_first_follower_reach': sum(
                [f.get('public_metrics', {}).get('followers_count', 0) for f in followers]
            )
        }
        
        self._log(f"twitter_id={twitter_id}: {result['key_followers_count']} key followers / {result['first_followers_count']} total")
        return result

    # ENDPOINT 3: /child/parents - Alpha hunters with performance
    
    def get_parents(self, username: str, twitter_id: str) -> Dict[str, Any]:
        """
        Get alpha hunters that follow this project.
        Includes performance stats (wins, losses, winrate, points).
        """
        data = self._request('/child/parents', {
            'page': 1,
            'username': username.lstrip('@'),
            'twitterId': twitter_id,
            'sortBy': 'timestamp',
            'order': 1
        })
        
        if not data or 'followings' not in data:
            return {
                'alpha_hunters_count': 0,
                'alpha_hunters': [],
                'best_hunter_winrate': 0
            }
        
        followings = data['followings']
        hunters = []
        
        for f in followings:
            parent = f.get('parent_id', {})
            if parent:
                perf = parent.get('performance', {})
                hunters.append({
                    'username': parent.get('username'),
                    'followers_count': parent.get('followers_count', 0),
                    'tags': parent.get('tag', []),
                    'winrate': perf.get('winrate', 0),
                    'wins': perf.get('wins', 0),
                    'losses': perf.get('losses', 0),
                    'points': perf.get('points', 0),
                    'followed_at': f.get('timestamp'),
                    'project_followers_then': f.get('followers_when_found', 0)
                })
        
        # Sort by timestamp
        hunters.sort(key=lambda x: x.get('followed_at', 0))
        
        result = {
            'alpha_hunters_count': len(hunters),
            'alpha_hunters': hunters,
            'alpha_hunters_list': [h['username'] for h in hunters],
            
            # First hunter info
            'first_hunter_at': hunters[0]['followed_at'] if hunters else None,
            'first_hunter_username': hunters[0]['username'] if hunters else None,
            'followers_at_first_hunter': hunters[0]['project_followers_then'] if hunters else 0,
            
            # Last hunter
            'last_hunter_at': hunters[-1]['followed_at'] if hunters else None,
            
            # Aggregated metrics
            'best_hunter_winrate': max([h['winrate'] for h in hunters], default=0),
            'avg_hunter_winrate': sum([h['winrate'] for h in hunters]) / max(len(hunters), 1),
            'best_hunter_followers': max([h['followers_count'] for h in hunters], default=0),
            'total_hunter_wins': sum([h['wins'] for h in hunters]),
            'total_hunter_losses': sum([h['losses'] for h in hunters]),
            'total_hunter_points': sum([h['points'] for h in hunters]),
            'hunters_with_60plus_wr': len([h for h in hunters if h['winrate'] >= 60])
        }
        
        self._log(f"@{username}: {result['alpha_hunters_count']} hunters | best_wr={result['best_hunter_winrate']:.1f}%")
        return result

    # ENDPOINT 4: /child/alerts - Historical changes
    
    def get_alerts(self, username: str) -> Dict[str, Any]:
        """
        Get historical alerts: renames, bio changes, website/social adds.
        """
        data = self._request('/child/alerts', {'username': username.lstrip('@')})
        
        if not data or 'alerts' not in data:
            return {
                'total_alerts': 0,
                'rename_count': 0,
                'bio_changes_count': 0
            }
        
        alerts = data['alerts']
        
        # Separate by type
        renames = [a for a in alerts if a.get('key') == 'username']
        bio_changes = [a for a in alerts if a.get('key') == 'description']
        website_alerts = [a for a in alerts if a.get('key') == 'website']
        telegram_alerts = [a for a in alerts if a.get('key') == 'telegram']
        discord_alerts = [a for a in alerts if a.get('key') == 'discord']
        
        # Build rename history
        rename_history = []
        for r in renames:
            # Parse the text to extract from/to
            rename_history.append({
                'from': r.get('from'),
                'text': r.get('text'),
                'at': r.get('timestamp')
            })
        
        # Build bio history
        bio_history = []
        for b in bio_changes:
            bio_history.append({
                'bio': b.get('text'),
                'at': b.get('timestamp'),
                'action': 'updated' if b.get('code') == 1 else 'added',
                'from': b.get('from')
            })
        
        result = {
            'total_alerts': len(alerts),
            'first_alert_at': min([a.get('timestamp', 0) for a in alerts]) if alerts else None,
            'last_alert_at': max([a.get('timestamp', 0) for a in alerts]) if alerts else None,
            
            # Renames
            'rename_count': len(renames),
            'rename_history': rename_history,
            'first_rename_at': min([r.get('timestamp', 0) for r in renames]) if renames else None,
            'last_rename_at': max([r.get('timestamp', 0) for r in renames]) if renames else None,
            
            # Bio
            'bio_changes_count': len(bio_changes),
            'bio_history': bio_history,
            'first_bio_at': min([b.get('timestamp', 0) for b in bio_changes]) if bio_changes else None,
            
            # Socials added
            'website_added_at': min([w.get('timestamp', 0) for w in website_alerts]) if website_alerts else None,
            'telegram_added_at': min([t.get('timestamp', 0) for t in telegram_alerts]) if telegram_alerts else None,
            'discord_added_at': min([d.get('timestamp', 0) for d in discord_alerts]) if discord_alerts else None,
            
            # Raw alerts for reference
            'alerts_raw': alerts
        }
        
        self._log(f"@{username}: {result['total_alerts']} alerts | renames={result['rename_count']} | bio_changes={result['bio_changes_count']}")
        return result

    # ENDPOINT 5: /tweets/contract-tweets - Tweets with CA
    
    def get_contract_tweets(self, twitter_id: str, contracts: List[str]) -> Dict[str, Any]:
        """
        Get tweets that mention any of the contracts.
        """
        if not contracts:
            return {'ca_tweets_count': 0, 'tweets': []}
        
        params = {'twitterId': twitter_id}
        for i, ca in enumerate(contracts):
            params[f'contracts[{i}]'] = ca
        
        data = self._request('/tweets/contract-tweets', params)
        
        if not data or 'tweets' not in data:
            return {'ca_tweets_count': 0, 'tweets': []}
        
        tweets = data['tweets']
        
        # Aggregate CA mentions
        ca_posts = {}
        total_hashtags = 0
        total_cashtags = 0
        total_mentions = 0
        deleted_count = 0
        pump_fun_links = 0
        
        for t in tweets:
            # Count deleted
            if t.get('deleted'):
                deleted_count += 1
            
            # Count entities
            entities = t.get('entities', {})
            total_hashtags += len(entities.get('hashtags', []))
            total_cashtags += len(entities.get('cashtags', []))
            total_mentions += len(entities.get('mentions', []))
            
            # Check pump.fun links
            for url in entities.get('urls', []):
                if 'pump.fun' in url.get('expanded_url', ''):
                    pump_fun_links += 1
            
            # Track CA posts
            for ca in t.get('contracts', []):
                if ca not in ca_posts:
                    ca_posts[ca] = {
                        'ca': ca,
                        'first_at': t.get('created_at'),
                        'times': 0
                    }
                ca_posts[ca]['times'] += 1
        
        # Sort tweets by date
        tweets.sort(key=lambda x: x.get('created_at', ''))
        
        result = {
            'ca_tweets_count': len(tweets),
            'deleted_tweets_count': deleted_count,
            'deleted_tweets_ratio': deleted_count / max(len(tweets), 1),
            
            'first_ca_tweet_at': tweets[0].get('created_at') if tweets else None,
            'last_ca_tweet_at': tweets[-1].get('created_at') if tweets else None,
            
            'total_hashtags_used': total_hashtags,
            'avg_hashtags_per_tweet': total_hashtags / max(len(tweets), 1),
            'total_cashtags': total_cashtags,
            'total_mentions': total_mentions,
            'pump_fun_links_count': pump_fun_links,
            'has_pump_fun_links': pump_fun_links > 0,
            
            'ca_posts_history': list(ca_posts.values()),
            'unique_cas_posted': len(ca_posts),
            
            'tweets': tweets
        }
        
        self._log(f"twitter_id={twitter_id}: {result['ca_tweets_count']} CA tweets | pump_fun_links={pump_fun_links}")
        return result

    # FULL ENRICHMENT - All endpoints combined
    
    def enrich_project(self, username: str) -> Dict[str, Any]:
        """
        Fully enrich a project with ALL available data from AlphaGate.
        Calls all 5 endpoints and merges the results.
        """
        username = username.lstrip('@')
        self._log(f"=== Enriching @{username} ===")
        
        result = {
            'found_in_alphagate': False,
            'enriched_at': datetime.now().isoformat()
        }
        
        # 1. Get profile
        profile = self.get_child(username)
        if not profile:
            self._log(f"@{username}: NOT FOUND in AlphaGate")
            return result
        
        result['found_in_alphagate'] = True
        result.update(profile)
        
        twitter_id = profile.get('twitter_id')
        if not twitter_id:
            return result
        
        # 2. Get first followers
        followers_data = self.get_first_followers(twitter_id)
        result.update(followers_data)
        
        # 3. Get alpha hunters
        hunters_data = self.get_parents(username, twitter_id)
        result.update(hunters_data)
        
        # 4. Get alerts
        alerts_data = self.get_alerts(username)
        result.update(alerts_data)
        
        # 5. Get contract tweets (if has contracts)
        contracts = profile.get('contracts', [])
        if contracts:
            tweets_data = self.get_contract_tweets(twitter_id, contracts)
            result.update(tweets_data)
        
        self._log(f"=== @{username} enriched: hunters={result.get('alpha_hunters_count', 0)} | key_followers={result.get('key_followers_count', 0)} | alerts={result.get('total_alerts', 0)} ===")
        
        return result


# CLI TEST

if __name__ == "__main__":
    import json
    import sys
    
    client = AlphaGateClient(verbose=True, delay=1.0)
    
    # Test with a project
    test_username = sys.argv[1] if len(sys.argv) > 1 else "MTFSOL"
    
    print(f"\n🔍 Testing with @{test_username}...\n")
    
    data = client.enrich_project(test_username)
    
    # Pretty print
    print("\n" + "="*60)
    print("📊 RESULT:")
    print("="*60)
    
    # Show key fields
    fields = [
        'found_in_alphagate', 'twitter_id', 'username', 'name',
        'followers_count', 'key_followers_count', 'alpha_hunters_count',
        'ca_count', 'rename_count', 'total_alerts', 'days_tracked',
        'best_hunter_winrate', 'followers_growth_total'
    ]
    
    for f in fields:
        if f in data:
            print(f"  {f}: {data[f]}")
    
    # Save full result
    output_file = f"alphagate_{test_username}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n✅ Full data saved to: {output_file}")
