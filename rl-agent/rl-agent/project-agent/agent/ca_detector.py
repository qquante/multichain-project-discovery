# agent/ca_detector.py
"""
Contract Address (CA) Detection - SIMPLE VERSION

Detects cryptocurrency contract addresses in text.
Used to reject already-launched projects BEFORE calling LLM.

Supported:
- EVM (Ethereum, Base, BSC, etc.): 0x + 40 hex
- Solana: Base58 32-44 chars
- Bitcoin: Legacy (1/3), SegWit (bc1), Taproot (bc1p)
- TRON: T + 33 chars
- TON: EQ/UQ format
"""

import re
from typing import Optional, Tuple, List


# ============================================
# REGEX PATTERNS - ONLY CA DETECTION
# ============================================

# EVM: 0x + 40 hex characters
EVM_PATTERN = re.compile(r'0x[a-fA-F0-9]{40}')

# Solana: Base58, 32-44 chars (no 0/O/I/l)
SOLANA_PATTERN = re.compile(r'[1-9A-HJ-NP-Za-km-z]{32,44}')

# Bitcoin Legacy: starts with 1 or 3
BTC_LEGACY_PATTERN = re.compile(r'[13][a-km-zA-HJ-NP-Z1-9]{25,34}')

# Bitcoin SegWit: starts with bc1
BTC_SEGWIT_PATTERN = re.compile(r'bc1[a-zA-HJ-NP-Z0-9]{25,62}', re.IGNORECASE)

# TRON: starts with T, 34 chars total
TRON_PATTERN = re.compile(r'T[a-zA-HJ-NP-Z0-9]{33}')

# TON: starts with EQ or UQ
TON_PATTERN = re.compile(r'[EU]Q[a-zA-Z0-9_-]{46}')

# CA with explicit prefix (CA:, Contract:)
CA_PREFIX_PATTERN = re.compile(r'(?:CA|Contract|Token)[\s:]+([a-zA-Z0-9]{30,})', re.IGNORECASE)


# ============================================
# DEX URL PATTERNS - Detect buy/trade links
# ============================================

# DEX domains that indicate token is ALREADY LAUNCHED
DEX_DOMAINS = [
    'pump.fun',
    'dexscreener.com',
    'dextools.io',
    'birdeye.so',
    'raydium.io',
    'jupiter-terminal',
    'jup.ag',
    'four.meme',
    'pancakeswap.finance',
    'aerodrome.finance',
    'uniswap.org',
    'ston.fi',
    'dedust.io',
    'sunpump.meme',
    'defined.fi',
    'geckoterminal.com',
]

# Pattern to match any DEX URL
DEX_URL_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?' + 
    r'(' + '|'.join(re.escape(d) for d in DEX_DOMAINS) + r')' +
    r'[/\w\-\?\=\&\#\.]*',
    re.IGNORECASE
)

# Pattern for pump.fun with token address
PUMP_FUN_CA_PATTERN = re.compile(
    r'pump\.fun/(?:coin/)?([1-9A-HJ-NP-Za-km-z]{32,44})',
    re.IGNORECASE
)

# Pattern for dexscreener with chain/token
DEXSCREENER_CA_PATTERN = re.compile(
    r'dexscreener\.com/(\w+)/([a-zA-Z0-9]{20,})',
    re.IGNORECASE
)

def _is_valid_solana_address(addr: str) -> bool:
    """Check if string looks like a real Solana address (mixed chars)."""
    if len(addr) < 32:
        return False
    has_upper = any(c.isupper() for c in addr)
    has_lower = any(c.islower() for c in addr)
    has_digit = any(c.isdigit() for c in addr)
    return has_upper and has_lower and has_digit


def detect_ca(text: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Detect contract address in text.
    
    Returns: (found, address, chain)
    """
    if not text:
        return False, None, None
    
    # 1. Check for explicit CA prefix first
    prefix_match = CA_PREFIX_PATTERN.search(text)
    if prefix_match:
        ca = prefix_match.group(1)
        # Determine chain
        if ca.startswith('0x') and len(ca) == 42:
            return True, ca, 'evm'
        elif ca.startswith('T') and len(ca) == 34:
            return True, ca, 'tron'
        elif _is_valid_solana_address(ca):
            return True, ca, 'solana'
        else:
            return True, ca, 'unknown'
    
    # 2. EVM (0x...)
    evm_match = EVM_PATTERN.search(text)
    if evm_match:
        return True, evm_match.group(0), 'evm'
    
    # 3. Bitcoin SegWit (bc1...)
    btc_segwit = BTC_SEGWIT_PATTERN.search(text)
    if btc_segwit:
        return True, btc_segwit.group(0), 'bitcoin'
    
    # 4. TRON (T...)
    tron_match = TRON_PATTERN.search(text)
    if tron_match:
        return True, tron_match.group(0), 'tron'
    
    # 5. TON (EQ/UQ...)
    ton_match = TON_PATTERN.search(text)
    if ton_match:
        return True, ton_match.group(0), 'ton'
    
    # 6. Bitcoin Legacy (1... or 3...)
    btc_legacy = BTC_LEGACY_PATTERN.search(text)
    if btc_legacy:
        addr = btc_legacy.group(0)
        # Avoid false positives - must be standalone
        if len(addr) >= 26:
            return True, addr, 'bitcoin'
    
    # 7. Solana (Base58) - check last to avoid false positives
    solana_matches = SOLANA_PATTERN.findall(text)
    for addr in solana_matches:
        if _is_valid_solana_address(addr):
            return True, addr, 'solana'
    
    return False, None, None


def has_ca(text: str) -> bool:
    """Simple check if text has CA."""
    found, _, _ = detect_ca(text)
    return found


def detect_dex_link(text: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Detect DEX/trading links in text.
    
    Returns: (found, url, platform, ca_if_found)
    """
    if not text:
        return False, None, None, None
    
    # 1. Check for pump.fun with CA
    pump_match = PUMP_FUN_CA_PATTERN.search(text)
    if pump_match:
        ca = pump_match.group(1)
        url = pump_match.group(0)
        return True, url, 'pump.fun', ca
    
    # 2. Check for dexscreener with CA
    dex_match = DEXSCREENER_CA_PATTERN.search(text)
    if dex_match:
        chain = dex_match.group(1)
        ca = dex_match.group(2)
        url = dex_match.group(0)
        return True, url, f'dexscreener/{chain}', ca
    
    # 3. Check for any DEX URL (even without CA)
    url_match = DEX_URL_PATTERN.search(text)
    if url_match:
        url = url_match.group(0)
        platform = url_match.group(1)
        return True, url, platform, None
    
    return False, None, None, None


def has_dex_link(text: str) -> bool:
    """Simple check if text has DEX link."""
    found, _, _, _ = detect_dex_link(text)
    return found


def check_project_ca(bio: str = "", tweets: List[str] = None, pinned: str = "") -> Tuple[bool, Optional[str], Optional[str], str]:
    """
    Check bio and tweets for CA.
    
    Returns: (found, address, chain, source)
    """
    tweets = tweets or []
    
    # Check bio
    found, ca, chain = detect_ca(bio)
    if found:
        return True, ca, chain, 'bio'
    
    # Check pinned tweet
    if pinned:
        found, ca, chain = detect_ca(pinned)
        if found:
            return True, ca, chain, 'pinned'
    
    # Check tweets
    for i, tweet in enumerate(tweets[:10]):
        found, ca, chain = detect_ca(tweet)
        if found:
            return True, ca, chain, f'tweet_{i}'
    
    return False, None, None, ''


def check_project_dex_links(bio: str = "", tweets: List[str] = None, pinned: str = "", profile_url: str = "") -> Tuple[bool, Optional[str], Optional[str], str]:
    """
    Check bio, tweets, and profile URL for DEX links.
    
    Returns: (found, url, platform, source)
    """
    tweets = tweets or []
    
    # Check profile URL field first (most common place for buy links)
    if profile_url:
        found, url, platform, _ = detect_dex_link(profile_url)
        if found:
            return True, url, platform, 'profile_url'
    
    # Check bio
    found, url, platform, _ = detect_dex_link(bio)
    if found:
        return True, url, platform, 'bio'
    
    # Check pinned tweet
    if pinned:
        found, url, platform, _ = detect_dex_link(pinned)
        if found:
            return True, url, platform, 'pinned'
    
    # Check tweets
    for i, tweet in enumerate(tweets[:10]):
        found, url, platform, _ = detect_dex_link(tweet)
        if found:
            return True, url, platform, f'tweet_{i}'
    
    return False, None, None, ''


# Main function for verifier.py
def is_project_launched(
    bio: str = "", 
    tweets: List[str] = None, 
    pinned_tweet: str = "",
    profile_url: str = "",
    name: str = "",
    location: str = "",
    expanded_urls: List[str] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    Check if project has CA or DEX link (already launched).
    
    Checks in order:
    1. Contract Address (CA) in name/bio/tweets/pinned
    2. DEX links (pump.fun, dexscreener, etc) in name/bio/tweets/pinned/profile_url/location
    3. Expanded URLs from tweet entities
    
    Returns: (launched, reason, evidence)
    """
    expanded_urls = expanded_urls or []
    
    # 0. Check NAME first (often has CA or DEX link)
    if name:
        found, ca, chain = detect_ca(name)
        if found:
            return True, f"CA found in name (chain={chain})", ca
        found, url, platform, _ = detect_dex_link(name)
        if found:
            return True, f"DEX link found in name ({platform})", url
    
    # 1. Check for CA in bio/tweets/pinned
    found, ca, chain, source = check_project_ca(bio, tweets, pinned_tweet)
    if found:
        return True, f"CA found in {source} (chain={chain})", ca
    
    # 2. Check for DEX links in bio/tweets/pinned/profile_url
    found, url, platform, source = check_project_dex_links(bio, tweets, pinned_tweet, profile_url)
    if found:
        return True, f"DEX link found in {source} ({platform})", url
    
    # 3. Check location (sometimes has CA)
    if location:
        found, ca, chain = detect_ca(location)
        if found:
            return True, f"CA found in location (chain={chain})", ca
        found, url, platform, _ = detect_dex_link(location)
        if found:
            return True, f"DEX link found in location ({platform})", url
    
    # 4. Check expanded URLs from tweet entities
    for i, url in enumerate(expanded_urls[:20]):  # Limit to 20 URLs
        found, dex_url, platform, ca = detect_dex_link(url)
        if found:
            return True, f"DEX link found in expanded_url_{i} ({platform})", dex_url
    
    return False, "", None


if __name__ == "__main__":
    print("=== CA DETECTION TESTS ===")
    ca_tests = [
        "CA: 0xf7951D9a5C558f8C37071da4CdCaf23b0bE1BFb3",
        "Fuj6EDWQHBnQ3eEvYDujNQ4rPLSkhm3pBySbQ79Bpump",
        "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
        "TC74QG8tbtixG5Raa4fEifywgjrFs45fNz",
        "Launching soon! $TOKEN",  # No CA
    ]
    
    for t in ca_tests:
        found, ca, chain = detect_ca(t)
        print(f"'{t[:50]}' -> found={found}, chain={chain}")
    
    print("\n=== DEX LINK DETECTION TESTS ===")
    dex_tests = [
        "Buy on pump.fun/Fuj6EDWQHBnQ3eEvYDujNQ4rPLSkhm3pBySbQ79Bpump",
        "https://dexscreener.com/solana/ABC123xyz456",
        "Trade at four.meme now!",
        "Check birdeye.so/token/xyz",
        "Coming soon on Solana",  # No DEX link
        "https://www.pump.fun/coin/Abc123DefGhi456JklMno789PqrStu",
    ]
    
    for t in dex_tests:
        found, url, platform, ca = detect_dex_link(t)
        print(f"'{t[:50]}' -> found={found}, platform={platform}, ca={ca[:15] if ca else None}...")
    
    print("\n=== FULL is_project_launched TESTS ===")
    launch_tests = [
        {"bio": "🚀 New memecoin launching!", "profile_url": "https://pump.fun/ABC123", "expected": True},
        {"bio": "Building something cool", "profile_url": "https://twitter.com/project", "expected": False},
        {"bio": "CA: 0xf7951D9a5C558f8C37071da4CdCaf23b0bE1BFb3", "profile_url": "", "expected": True},
    ]
    
    for test in launch_tests:
        launched, reason, evidence = is_project_launched(
            bio=test["bio"],
            profile_url=test.get("profile_url", "")
        )
        status = "✅" if launched == test["expected"] else "❌"
        print(f"{status} bio='{test['bio'][:30]}...' | launched={launched} | reason={reason[:40] if reason else 'None'}")
