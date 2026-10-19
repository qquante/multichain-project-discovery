# agent/alphagate_client.py
"""
AlphaGate API Client for enriching project data.
Fetches alerts, first-followers, and alpha hunters for any project.
"""

import os
import time
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime


class AlphaGateClient:
    """Client for AlphaGate API enrichment endpoints."""
    
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
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'
    }
    
    # Cookies for authentication
    COOKIES = {'userId': os.environ.get('ALPHAGATE_USER_ID', ""), 'extensionSessionId': os.environ.get('ALPHAGATE_SESSION_ID', "")}
    
    def __init__(self, verbose: bool = True, delay: float = 1.0):
        self.verbose = verbose
        self.delay = delay  # Delay between requests
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.session.cookies.update(self.COOKIES)
        self.last_request_time = 0
    
    def _log(self, msg: str):
        if self.verbose:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] [ALPHAGATE_CLIENT] {msg}", flush=True)
    
    def _rate_limit(self):
        """Ensure delay between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request_time = time.time()
    
    def _request(self, endpoint: str, params: dict = None, max_retries: int = 3) -> Optional[dict]:
        """Make a request to AlphaGate API with retry/backoff."""
        self._rate_limit()
        
        url = f"{self.BASE_URL}{endpoint}"
        
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('message') in ['Fetched alerts', 'Fetched data successfully']:
                        return data.get('data', {})
                    else:
                        self._log(f"API returned: {data.get('message')}")
                        return None
                elif response.status_code == 404:
                    # Project not found in AlphaGate - this is normal
                    return None
                elif response.status_code >= 500:
                    # Server error - retry with backoff
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 3  # 3s, 6s, 9s
                        self._log(f"Server error {response.status_code}, retry {attempt + 1}/{max_retries} in {wait_time}s")
                        time.sleep(wait_time)
                        continue
                    self._log(f"Request failed after {max_retries} retries: {response.status_code}")
                    return None
                else:
                    self._log(f"Request failed: {response.status_code}")
                    return None
                    
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                # Connection/timeout error - retry with backoff
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 3  # 3s, 6s, 9s
                    self._log(f"Connection error, retry {attempt + 1}/{max_retries} in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                self._log(f"Request error after {max_retries} retries: {str(e)[:50]}")
                return None
            except Exception as e:
                self._log(f"Request error: {str(e)[:50]}")
                return None
        
        return None
    
    def get_alerts(self, username: str) -> List[dict]:
        """
        Get project alerts (bio changes, username changes, website added).
        Endpoint: /child/alerts?username=xxx
        """
        data = self._request('/child/alerts', {'username': username.lstrip('@')})
        
        if data and 'alerts' in data:
            alerts = data['alerts']
            self._log(f"@{username}: {len(alerts)} alerts found")
            return alerts
        
        return []
    
    def get_first_followers(self, twitter_id: str) -> Dict[str, Any]:
        """
        Get first followers of a project.
        Endpoint: /child/first-followers?twitterId=xxx
        
        Returns:
            {
                'followers': list of followers,
                'key_followers': list of followers with parent != null,
                'key_followers_count': int
            }
        """
        data = self._request('/child/first-followers', {'twitterId': twitter_id})
        
        if data and 'followers' in data:
            followers = data['followers']
            
            # Key followers are those with parent != null
            key_followers = [f for f in followers if f.get('parent') is not None]
            
            result = {
                'followers': followers,
                'key_followers': key_followers,
                'key_followers_count': len(key_followers),
                'total_followers_tracked': len(followers)
            }
            
            self._log(f"twitter_id={twitter_id}: {len(key_followers)} key followers / {len(followers)} total")
            return result
        
        return {
            'followers': [],
            'key_followers': [],
            'key_followers_count': 0,
            'total_followers_tracked': 0
        }
    
    def get_alpha_hunters(self, username: str, twitter_id: str) -> List[dict]:
        """
        Get alpha hunters that follow this project.
        Endpoint: /child/parents?username=xxx&twitterId=xxx
        
        Returns list of alpha hunters with their performance stats.
        """
        data = self._request('/child/parents', {
            'page': 1,
            'username': username.lstrip('@'),
            'twitterId': twitter_id,
            'sortBy': 'timestamp',
            'order': 1
        })
        
        if data and 'followings' in data:
            followings = data['followings']
            
            alpha_hunters = []
            for f in followings:
                parent = f.get('parent_id', {})
                if parent:
                    hunter = {
                        'username': parent.get('username', ''),
                        'followers_count': parent.get('followers_count', 0),
                        'tags': parent.get('tag', []),
                        'performance': parent.get('performance', {}),
                        'followers_when_found': f.get('followers_when_found', 0),
                        'timestamp': f.get('timestamp', 0)
                    }
                    alpha_hunters.append(hunter)
            
            self._log(f"@{username}: {len(alpha_hunters)} alpha hunters found")
            return alpha_hunters
        
        return []
    
    def enrich_project(self, username: str, twitter_id: str = None) -> Dict[str, Any]:
        """
        Fully enrich a project with all available data from AlphaGate.
        
        Args:
            username: Twitter username (without @)
            twitter_id: Twitter user ID (optional, needed for some endpoints)
        
        Returns:
            {
                'found_in_alphagate': bool,
                'alerts': list,
                'alerts_summary': {bio_changes, username_changes, website_added},
                'key_followers': list,
                'key_followers_count': int,
                'alpha_hunters': list,
                'alpha_hunters_count': int,
                'followers_when_found': int,
                'best_hunter_winrate': float
            }
        """
        username = username.lstrip('@')
        
        self._log(f"Enriching @{username}...")
        
        result = {
            'found_in_alphagate': False,
            'alerts': [],
            'alerts_summary': {
                'bio_changes': 0,
                'username_changes': 0,
                'website_added': False,
                'last_website': None
            },
            'key_followers': [],
            'key_followers_count': 0,
            'alpha_hunters': [],
            'alpha_hunters_count': 0,
            'followers_when_found': 0,
            'best_hunter_winrate': 0.0
        }
        
        # 1. Get alerts
        alerts = self.get_alerts(username)
        if alerts:
            result['found_in_alphagate'] = True
            result['alerts'] = alerts
            
            # Summarize alerts
            for alert in alerts:
                key = alert.get('key', '')
                if key == 'description':
                    result['alerts_summary']['bio_changes'] += 1
                elif key == 'username':
                    result['alerts_summary']['username_changes'] += 1
                elif key == 'website':
                    result['alerts_summary']['website_added'] = True
                    # Get the most recent website
                    if not result['alerts_summary']['last_website']:
                        text = alert.get('text', '')
                        if 'Added website:' in text:
                            result['alerts_summary']['last_website'] = text.replace('Added website:', '').strip()
        
        # 2. Get first followers (needs twitter_id)
        if twitter_id:
            followers_data = self.get_first_followers(twitter_id)
            if followers_data['key_followers']:
                result['found_in_alphagate'] = True
                result['key_followers'] = followers_data['key_followers']
                result['key_followers_count'] = followers_data['key_followers_count']
            
            # 3. Get alpha hunters
            hunters = self.get_alpha_hunters(username, twitter_id)
            if hunters:
                result['found_in_alphagate'] = True
                result['alpha_hunters'] = hunters
                result['alpha_hunters_count'] = len(hunters)
                
                # Get best winrate and followers_when_found
                for h in hunters:
                    perf = h.get('performance', {})
                    winrate = perf.get('winrate', 0)
                    if winrate > result['best_hunter_winrate']:
                        result['best_hunter_winrate'] = winrate
                    
                    if h.get('followers_when_found', 0) > 0:
                        result['followers_when_found'] = h['followers_when_found']
        
        self._log(f"@{username} enriched: alphagate={result['found_in_alphagate']} | key_followers={result['key_followers_count']} | hunters={result['alpha_hunters_count']}")
        
        return result


# Utility function for formatting key followers for Telegram
def format_key_followers_html(key_followers: List[dict], limit: int = 5) -> str:
    """Format key followers as HTML with clickable links."""
    if not key_followers:
        return "None"
    
    lines = []
    for i, f in enumerate(key_followers[:limit]):
        username = f.get('username', 'unknown')
        followers = f.get('public_metrics', {}).get('followers_count', 0)
        parent = f.get('parent', {})
        
        # Check if this is an alpha hunter
        is_alpha = parent is not None
        star = "⭐" if is_alpha else ""
        
        line = f'<a href="https://x.com/{username}">@{username}</a> ({followers:,}) {star}'
        lines.append(line)
    
    if len(key_followers) > limit:
        lines.append(f"... +{len(key_followers) - limit} more")
    
    return "\n".join(lines)


def format_alpha_hunters_html(alpha_hunters: List[dict], limit: int = 3) -> str:
    """Format alpha hunters as HTML with performance stats."""
    if not alpha_hunters:
        return "None"
    
    lines = []
    for h in alpha_hunters[:limit]:
        username = h.get('username', 'unknown')
        followers = h.get('followers_count', 0)
        perf = h.get('performance', {})
        winrate = perf.get('winrate', 0)
        wins = perf.get('wins', 0)
        losses = perf.get('losses', 0)
        
        line = f'<a href="https://x.com/{username}">@{username}</a> ({followers:,}) | WR: {winrate:.1f}% ({wins}W/{losses}L)'
        lines.append(line)
    
    if len(alpha_hunters) > limit:
        lines.append(f"... +{len(alpha_hunters) - limit} more")
    
    return "\n".join(lines)



