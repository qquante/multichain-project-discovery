"""
AlphaGate Service
Fetches pre-filtered projects from AlphaGate API.

FLOW NOTE: 
  AlphaGate projects SKIP the Triage LLM analysis because they are already
  pre-filtered by AlphaGate's algorithm. They go directly to triaged_projects
  and then to the Verifier service.
  
  Pipeline: AlphaGate API -> triaged_projects -> Verifier -> Monitor
  (vs Collector: tweets.db -> Triage LLM -> triaged_projects -> Verifier -> Monitor)
  
  To identify AlphaGate projects: discovery_source='alphagate'
"""

import os
import sys
import json
import asyncio
import redis.asyncio as redis
import requests
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, '/app')

from agent.database import (
    init_db, 
    is_handle_triaged, 
    save_triage_result
)

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6388')
ALPHAGATE_INTERVAL_HOURS = int(os.getenv('ALPHAGATE_INTERVAL_HOURS', '2'))  # Every 2 hours
ALPHAGATE_MAX_FOLLOWERS = int(os.getenv('ALPHAGATE_MAX_FOLLOWERS', '50000'))
ALPHAGATE_MIN_KEY_FOLLOWERS = int(os.getenv('ALPHAGATE_MIN_KEY_FOLLOWERS', '1'))
ALPHAGATE_PAGES = int(os.getenv('ALPHAGATE_PAGES', '5'))
ALPHAGATE_LIMIT = int(os.getenv('ALPHAGATE_LIMIT', '60'))

# AlphaGate API
ALPHAGATE_URL = "https://api.alphagate.io/api/v1/child/discover"

# Complete headers for API (all required for authentication)
# Note: Do NOT include accept-encoding - let requests handle decompression automatically
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

# Cookies for authentication (required for API access)
COOKIES = {
    'userId': os.environ.get("ALPHAGATE_USER_ID", ""),
    'extensionSessionId': os.environ.get("ALPHAGATE_SESSION_ID", "")
}

# Redis channel
CHANNEL_TRIAGED = 'projects:triaged'


def log(msg: str):
    """Log with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [ALPHAGATE] {msg}", flush=True)


def fetch_alphagate_page(page: int = 1) -> list:
    """Fetch a page of projects from AlphaGate API."""
    params = {
        'ontop': 'true',
        'page': page,
        'limit': ALPHAGATE_LIMIT,
        'unfiltered': 'false',
        'exclude_tags[]': 'Launched',  # Exclude already launched
        'order': '-1',
        'min_followers': 0,
        'max_followers': ALPHAGATE_MAX_FOLLOWERS,
        'min_key_followers': ALPHAGATE_MIN_KEY_FOLLOWERS,
        'max_key_followers': 5000,
        'min_kp_followers': 0,
        'max_kp_followers': 0
    }
    
    try:
        # Create session for persistent cookies
        session = requests.Session()
        session.headers.update(HEADERS)
        session.cookies.update(COOKIES)
        
        response = session.get(
            ALPHAGATE_URL, 
            params=params,
            timeout=30
        )
        
        # Log response details for debugging
        log(f"Response status: {response.status_code}")
        
        if response.status_code != 200:
            log(f"Response text: {response.text[:500]}")
            return []
        
        # Check if response is empty
        if not response.text:
            log("Empty response received")
            return []
        
        data = response.json()
        
        if data.get('message') == 'Fetched data successfully':
            children = data.get('data', {}).get('children', [])
            log(f"Got {len(children)} projects from API")
            return children
        else:
            log(f"API returned: {data.get('message')}")
            return []
            
    except requests.exceptions.HTTPError as e:
        log(f"HTTP Error page {page}: {e.response.status_code}")
        log(f"Response: {e.response.text[:500] if e.response.text else 'empty'}")
        return []
    except json.JSONDecodeError as e:
        log(f"JSON decode error: {e}")
        log(f"Response text: {response.text[:500] if response.text else 'empty'}")
        return []
    except Exception as e:
        log(f"Error fetching page {page}: {e}")
        import traceback
        traceback.print_exc()
        return []


def convert_alphagate_to_triage(project: dict) -> dict:
    """
    Convert AlphaGate project format to our triage result format.
    AlphaGate already filters projects, so we trust their data.
    """
    username = project.get('username', '').lstrip('@')
    name = project.get('name', '')
    description = project.get('description', '')
    tags = project.get('tag', [])
    chains = project.get('chain', [])
    contracts = project.get('contracts', [])
    followers = project.get('followers_count', 0)
    key_followers = project.get('key_followers_count', 0)
    social = project.get('social', {})
    
    # Determine project type from tags
    project_type = tags[0] if tags else 'unknown'
    
    # Determine chain
    chain = chains[0] if chains else 'unknown'
    
    # Check if has contract address
    has_ca = len(contracts) > 0
    ca_address = contracts[0] if contracts else None
    
    # Get website
    website_info = social.get('website', {})
    website_url = website_info.get('expanded_url', '') if website_info else ''
    
    # Build triage result format
    result = {
        'is_project': True,
        'confidence': 85,  # AlphaGate already filtered, high confidence
        'rejection_reason': None,
        
        'project': {
            'name': name,
            'ticker': None,  # AlphaGate doesn't provide ticker
            'type': project_type,
            'chain': chain,
            'has_ca': has_ca,
            'ca_address': ca_address
        },
        
        'source': {
            'twitter_handle': username,
            'author_id': project.get('id'),
            'author_followers': followers,
            'tweet_id': f"alphagate_{project.get('id', '')}",
            'tweet_date': project.get('created_at'),
            'tweet_text_preview': description[:200] if description else ''
        },
        
        'launch': {
            'status': 'launched' if has_ca else 'pre_launch',
            'date': None,
            'time': None,
            'platform': None
        },
        
        'signals': {
            'keywords_found': ['discovery_alpha'],
            'has_links': bool(website_url),
            'links': [website_url] if website_url else [],
            'has_website': bool(website_url),
            'website_link': website_url,
            'has_telegram': 'telegram' in social.get('socials', []),
            'telegram_link': None,
            'has_discord': 'discord' in social.get('socials', []),
            'key_followers': key_followers
        },
        
        'mentions': {
            'tagged_accounts': [],
            'tagged_chains': chains,
            'tagged_platforms': []
        },
        
        'alphagate_data': {
            'tags': tags,
            'key_followers_count': key_followers,
            'followers_when_found': project.get('followers_when_found', 0),
            'parent_tag': project.get('parent_id', {}).get('tag', []) if project.get('parent_id') else []
        },
        
        # Discovery source tracking
        'discovery_source': 'alphagate',
        'discovery_keyword': None
    }
    
    return result


async def process_alphagate_project(redis_client, project: dict) -> bool:
    """Process a single project from AlphaGate and save to database."""
    username = project.get('username', '').lstrip('@')
    
    if not username:
        return False
    
    # Check if already in our system
    if is_handle_triaged(username):
        return False
    
    # Skip if has contract (already launched)
    contracts = project.get('contracts', [])
    if contracts:
        log(f"Skipping @{username} - already has CA")
        return False
    
    # NEW: Validation to reject personal accounts
    
    # Check 3: Bio is just a @mention? (indicates person, not project)
    # Example: bio = "@konnex_world" means this is a person pointing to the real project
    description = project.get('description', '').strip()
    if description:
        words = description.split()
        # If bio has 1-2 words and starts with @, it's likely a person account
        if len(words) <= 2 and description.startswith('@'):
            # Extract the mentioned handle to potentially add it to discovery
            mentioned_handle = words[0].lstrip('@')
            log(f"Skipping @{username} - bio is just '@{mentioned_handle}' (person, not project)")
            log(f"NOTE: Consider adding @{mentioned_handle} to discovery queue")
            return False
    
    # Check 4: Account too old - REMOVED
    # Old accounts can be legitimate crypto projects reusing existing handles
    
    # Check 5: Name looks like a person (has first + last name pattern)?
    name = project.get('name', '').strip()
    if name and ' ' in name:
        # Check if looks like "FirstName LastName" pattern (2 words, both capitalized)
        name_parts = name.split()
        if len(name_parts) == 2:
            # If both parts are capitalized words (not abbreviations), likely a person
            if (name_parts[0][0].isupper() and name_parts[0][1:].islower() and
                name_parts[1][0].isupper() and name_parts[1][1:].islower() and
                len(name_parts[0]) > 2 and len(name_parts[1]) > 2):
                log(f"Skipping @{username} - name looks like person: '{name}'")
                return False
    
    # End of validation checks
    
    # Convert to our format
    result = convert_alphagate_to_triage(project)
    
    # Save to database
    saved = save_triage_result(result)
    
    if saved:
        tags = project.get('tag', [])
        chains = project.get('chain', [])
        followers = project.get('followers_count', 0)
        social = project.get('social', {})
        website_info = social.get('website', {})
        website_url = website_info.get('expanded_url', '') if website_info else ''
        
        log(f"Saved @{username} | {project.get('name', '')} | {tags} | {chains}")
        
        # Publish COMPLETE data for Telegram formatter
        message = {
            # Basic
            'twitter_handle': username,
            'project_name': project.get('name', ''),
            'project_ticker': None,
            'project_chain': chains[0] if chains else 'unknown',
            'project_type': tags[0] if tags else 'unknown',
            'confidence': 85,
            'author_followers': followers,
            
            # Launch
            'launch_status': 'pre_launch',
            'launch_date': 'TBA',
            'launch_time': None,
            'launch_platform': None,
            
            # Signals
            'keywords_found': ['discovery_alpha'],
            'has_ca': False,
            'ca_address': None,
            
            # Links
            'telegram_link': None,
            'website_link': website_url,
            
            # Mentions
            'tagged_accounts': [],
            'tagged_chains': chains,
            
            # Source
            'source_tweet_id': f"alphagate_{project.get('id', '')}",
            'tweet_text_preview': project.get('description', '')[:200],
            
            # Discovery source tracking
            'discovery_source': 'alphagate',
            'discovery_keyword': None,
            
            # Meta
            'source': 'alphagate',
            'timestamp': datetime.now().isoformat()
        }
        await redis_client.publish(CHANNEL_TRIAGED, json.dumps(message))
        
        return True
    
    return False


async def collect_alphagate():
    """Main collection function."""
    log("=" * 60)
    log(f"Starting collection at {datetime.now().isoformat()}")
    log(f"Max followers: {ALPHAGATE_MAX_FOLLOWERS}")
    log(f"Min key followers: {ALPHAGATE_MIN_KEY_FOLLOWERS}")
    log(f"Pages to fetch: {ALPHAGATE_PAGES}")
    log("=" * 60)
    
    # Initialize database
    init_db()
    
    # Connect to Redis
    redis_client = await redis.from_url(REDIS_URL)
    
    total_found = 0
    total_saved = 0
    
    for page in range(1, ALPHAGATE_PAGES + 1):
        log(f"Fetching page {page}/{ALPHAGATE_PAGES}...")
        
        projects = fetch_alphagate_page(page)
        
        if not projects:
            log(f"No projects on page {page}")
            break
        
        log(f"Found {len(projects)} projects on page {page}")
        total_found += len(projects)
        
        page_saved = 0
        
        for project in projects:
            saved = await process_alphagate_project(redis_client, project)
            if saved:
                page_saved += 1
                total_saved += 1
        
        log(f"Page {page}: saved {page_saved} new projects")
        
        # Small delay between pages
        await asyncio.sleep(1)
    
    log("=" * 60)
    log("Collection complete!")
    log(f"Total projects found: {total_found}")
    log(f"Total projects saved: {total_saved}")
    log(f"Next collection in {ALPHAGATE_INTERVAL_HOURS} hours")
    log("=" * 60)
    
    await redis_client.aclose()


async def main():
    """Main loop - runs collection every ALPHAGATE_INTERVAL_HOURS."""
    log("Service starting...")
    log(f"Collection interval: {ALPHAGATE_INTERVAL_HOURS} hours")
    log(f"Max followers filter: {ALPHAGATE_MAX_FOLLOWERS}")
    
    while True:
        try:
            await collect_alphagate()
        except Exception as e:
            log(f"Error during collection: {e}")
            import traceback
            traceback.print_exc()
        
        # Wait for next collection
        wait_seconds = ALPHAGATE_INTERVAL_HOURS * 3600
        log(f"Sleeping for {ALPHAGATE_INTERVAL_HOURS} hours...")
        await asyncio.sleep(wait_seconds)


if __name__ == "__main__":
    asyncio.run(main())

