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


# Alias for verifier.py
def is_project_launched(bio: str = "", tweets: List[str] = None, pinned_tweet: str = "") -> Tuple[bool, str, Optional[str]]:
    """Check if project has CA (already launched)."""
    found, ca, chain, source = check_project_ca(bio, tweets, pinned_tweet)
    if found:
        return True, f"CA found in {source}", ca
    return False, "", None


if __name__ == "__main__":
    tests = [
        "CA: 0xf7951D9a5C558f8C37071da4CdCaf23b0bE1BFb3",
        "Fuj6EDWQHBnQ3eEvYDujNQ4rPLSkhm3pBySbQ79Bpump",
        "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
        "TC74QG8tbtixG5Raa4fEifywgjrFs45fNz",
        "Launching soon! $TOKEN",  # No CA
    ]
    
    for t in tests:
        found, ca, chain = detect_ca(t)
        print(f"'{t[:50]}' -> found={found}, chain={chain}, ca={ca[:20] if ca else None}...")
