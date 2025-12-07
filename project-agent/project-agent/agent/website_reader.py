# agent/website_reader.py
import requests
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

JINA_READER_PREFIX = "https://r.jina.ai/"


class WebsiteReader:
    """Read website content using Jina AI Reader API."""
    
    def __init__(self, verbose: bool = True, timeout: int = 30):
        self.verbose = verbose
        self.timeout = timeout
    
    def _log(self, msg: str):
        if self.verbose:
            print(msg)
    
    def read_url(self, url: str) -> Dict[str, Any]:
        """
        Read website content via Jina Reader API.
        
        Args:
            url: Website URL to read
        
        Returns:
            Dict with content, success status, and metadata
        """
        if not url:
            return {"success": False, "error": "No URL provided", "content": ""}
        
        # Clean URL
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        jina_url = f"{JINA_READER_PREFIX}{url}"
        
        try:
            start_time = datetime.now()
            
            response = requests.get(
                jina_url,
                timeout=self.timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ProjectAgent/1.0)"
                }
            )
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            if response.status_code == 200:
                content = response.text
                self._log(f"[WEBSITE] url={url[:50]}... | chars={len(content)} | time={elapsed:.2f}s")
                
                return {
                    "success": True,
                    "content": content,
                    "url": url,
                    "chars": len(content),
                    "elapsed": elapsed
                }
            else:
                self._log(f"[WEBSITE_ERROR] url={url[:50]}... | status={response.status_code}")
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "content": "",
                    "url": url
                }
                
        except requests.exceptions.Timeout:
            self._log(f"[WEBSITE_TIMEOUT] url={url[:50]}...")
            return {"success": False, "error": "Timeout", "content": "", "url": url}
            
        except requests.exceptions.RequestException as e:
            self._log(f"[WEBSITE_ERROR] url={url[:50]}... | error={str(e)[:50]}")
            return {"success": False, "error": str(e), "content": "", "url": url}
    
    def extract_urls_from_bio(self, user_info: Dict[str, Any]) -> List[str]:
        """Extract website URLs from user bio."""
        urls = []
        
        # From profile_bio entities
        profile_bio = user_info.get('profile_bio', {}) or {}
        entities = profile_bio.get('entities', {}) or {}
        
        # URL in bio link
        url_entity = entities.get('url', {}) or {}
        for u in url_entity.get('urls', []):
            expanded = u.get('expanded_url', '')
            if expanded and self._is_website_url(expanded):
                urls.append(expanded)
        
        # URLs in description
        desc_entity = entities.get('description', {}) or {}
        for u in desc_entity.get('urls', []):
            expanded = u.get('expanded_url', '')
            if expanded and self._is_website_url(expanded):
                urls.append(expanded)
        
        return list(set(urls))
    
    def extract_urls_from_tweets(self, tweets: List[Dict[str, Any]]) -> List[str]:
        """Extract website URLs from tweets."""
        urls = []
        
        for tweet in tweets[:10]:  # Check first 10 tweets
            entities = tweet.get('entities', {}) or {}
            for u in entities.get('urls', []):
                expanded = u.get('expanded_url', '')
                if expanded and self._is_website_url(expanded):
                    urls.append(expanded)
        
        return list(set(urls))
    
    def _is_website_url(self, url: str) -> bool:
        """Check if URL is a project website (not social media)."""
        if not url:
            return False
        
        # Exclude social media and common non-project URLs
        excluded = [
            'twitter.com', 'x.com', 't.co',
            'telegram.org', 't.me',
            'discord.gg', 'discord.com',
            'youtube.com', 'youtu.be',
            'instagram.com',
            'facebook.com',
            'tiktok.com',
            'reddit.com',
            'medium.com',
            'github.com',
            'linkedin.com',
            'twitch.tv'
        ]
        
        url_lower = url.lower()
        for exc in excluded:
            if exc in url_lower:
                return False
        
        return True
    
    def find_project_website(
        self,
        user_info: Dict[str, Any],
        tweets: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Find the most likely project website URL."""
        
        # Priority 1: URL in bio link (most likely official)
        bio_urls = self.extract_urls_from_bio(user_info)
        if bio_urls:
            return bio_urls[0]
        
        # Priority 2: URL from tweets
        tweet_urls = self.extract_urls_from_tweets(tweets)
        if tweet_urls:
            return tweet_urls[0]
        
        return None


def extract_site_info(content: str) -> Dict[str, Any]:
    """
    Extract basic info from website content.
    Note: Detailed analysis (whitepaper, tokenomics, etc) is done by LLM.
    This function only extracts what can be done programmatically.
    """
    
    if not content:
        return {
            "title": None,
            "description": None,
            "content_preview": None,
            "social_links": [],
            "contract_found": False,
            "contract_address": None
        }
    
    # Try to extract title (markdown header)
    title = None
    title_match = re.search(r'^#\s*(.+?)$', content, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    
    # Try to extract description (first paragraph)
    description = None
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip() and not p.startswith('#')]
    if paragraphs:
        description = paragraphs[0][:300]
    
    # Find social links (URLs are structural, not semantic)
    social_links = []
    social_patterns = [
        (r'https?://(?:www\.)?twitter\.com/\w+', 'twitter'),
        (r'https?://(?:www\.)?x\.com/\w+', 'twitter'),
        (r'https?://t\.me/\w+', 'telegram'),
        (r'https?://discord\.gg/\w+', 'discord'),
        (r'https?://(?:www\.)?discord\.com/invite/\w+', 'discord'),
    ]
    
    for pattern, platform in social_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for match in matches:
            social_links.append({"platform": platform, "url": match})
    
    # Find contract address (mathematical format detection, not semantic)
    contract_found = False
    contract_address = None
    
    # Ethereum-like address (0x + 40 hex chars)
    eth_match = re.search(r'\b0x[a-fA-F0-9]{40}\b', content)
    if eth_match:
        contract_found = True
        contract_address = eth_match.group(0)
    
    # Solana address (base58, 32-44 chars) - only if no EVM found
    if not contract_found:
        sol_match = re.search(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b', content)
        if sol_match:
            potential = sol_match.group(0)
            if len(potential) >= 32 and len(potential) <= 44:
                contract_found = True
                contract_address = potential
    
    return {
        "title": title,
        "description": description,
        "content_preview": content[:500] if content else None,
        "social_links": social_links,
        "contract_found": contract_found,
        "contract_address": contract_address
    }

