# agent/blacklist.py
"""
Blacklist Module - Words/phrases that should trigger rejection or low score.
Used to filter out scam projects, NFT projects, and pump-and-dump schemes.
"""

from typing import List, Tuple
import re


# ============================================
# BLACKLIST WORDS - Instant rejection or low score
# ============================================

# NFT/Game related (not crypto tokens we want)
NFT_WORDS = [
    "opensea", "magiceden", "magic eden",
    "nft game", "game nft", "nft project",
    "play to earn", "p2e"
]

# Political/Meme (often scams)
POLITICAL_WORDS = [
    "trump", "biden", "elon", "musk"
]

# AI/Other tech (not our target)
AI_WORDS = [
    "grok", "chatgpt", "claude"
]

# Scam indicators
SCAM_WORDS = [
    "100x", "1000x", "100xgem", "1000xgem",
    "#100x", "#1000x", "#100xgem", "#1000xgem",
    "#x100", "#gem", "#crypto signals",
    "guaranteed profit", "guaranteed gains",
    "free tokens", "free money"
]

# Paid promotion indicators
PAID_PROMO_WORDS = [
    "dex paid", "dexscreener paid", 
    "dexscreener has been paid", "dex has been paid",
    "trending paid", "cmc paid", "coingecko paid"
]

# Pre-sale/Pinksale (often rugs)
PRESALE_WORDS = [
    "pinksale", "#pinksale",
    "presale live", "whitelist spots"
]

# Streaming/Influencer (not projects)
INFLUENCER_WORDS = [
    "streamer", "youtuber", "tiktoker"
]

# Lock services (could be legitimate but often fake)
LOCK_WORDS = [
    "tokens locked", "liquidity locked",
    "streamflow.finance"
]

# Hunter word (false positive filter)
HUNTER_WORDS = [
    "hunter"  # Often matches "alpha hunter" accounts, not projects
]

# Combine all blacklist words
ALL_BLACKLIST_WORDS = (
    NFT_WORDS + 
    POLITICAL_WORDS + 
    AI_WORDS + 
    SCAM_WORDS + 
    PAID_PROMO_WORDS + 
    PRESALE_WORDS + 
    INFLUENCER_WORDS + 
    LOCK_WORDS +
    HUNTER_WORDS
)


def check_blacklist(text: str) -> Tuple[bool, List[str]]:
    """
    Check if text contains any blacklisted words.
    
    Args:
        text: Text to check (bio, tweet, etc)
    
    Returns:
        (is_blacklisted, list of matched words)
    """
    if not text:
        return False, []
    
    text_lower = text.lower()
    matched = []
    
    for word in ALL_BLACKLIST_WORDS:
        if word.lower() in text_lower:
            matched.append(word)
    
    return len(matched) > 0, matched


def check_bio_blacklist(bio: str) -> Tuple[bool, List[str]]:
    """Check bio for blacklisted words."""
    return check_blacklist(bio)


def check_tweets_blacklist(tweets: List[str]) -> Tuple[bool, List[str], int]:
    """
    Check tweets for blacklisted words.
    
    Returns:
        (has_blacklist, list of matched words, count of tweets with blacklist)
    """
    all_matched = set()
    count = 0
    
    for tweet in tweets:
        is_black, matched = check_blacklist(tweet)
        if is_black:
            count += 1
            all_matched.update(matched)
    
    return len(all_matched) > 0, list(all_matched), count


def get_blacklist_penalty(matched_words: List[str]) -> int:
    """
    Calculate penalty score based on blacklisted words found.
    
    Returns negative points to subtract from score.
    """
    if not matched_words:
        return 0
    
    penalty = 0
    
    for word in matched_words:
        word_lower = word.lower()
        
        # Critical words = instant high penalty
        if word_lower in ["100x", "1000x", "100xgem", "1000xgem", "pinksale"]:
            penalty += 20
        elif word_lower in ["trump", "biden", "elon"]:
            penalty += 15
        elif word_lower in SCAM_WORDS:
            penalty += 10
        elif word_lower in NFT_WORDS:
            penalty += 5
        else:
            penalty += 3
    
    return penalty


if __name__ == "__main__":
    # Test blacklist
    test_texts = [
        "Check out this 100x gem! 🚀",
        "Building a new protocol on Solana",
        "NFT game coming soon, play to earn!",
        "Pinksale presale live now!",
        "Trump token launching tomorrow",
        "Fair launch, no snipers, building in public"
    ]
    
    print("=== BLACKLIST TESTS ===")
    for text in test_texts:
        is_black, matched = check_blacklist(text)
        penalty = get_blacklist_penalty(matched)
        status = "❌ BLACKLISTED" if is_black else "✅ OK"
        print(f"{status} | penalty={penalty} | matched={matched}")
        print(f"   '{text[:50]}...'")
        print()
