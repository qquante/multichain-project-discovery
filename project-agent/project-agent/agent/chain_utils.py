# agent/chain_utils.py
"""
Shared chain utilities for consistent chain mapping across all services.
Single source of truth for chain groups and emojis.
"""

# Chain name to group mapping
CHAIN_MAP = {
    'sol': 'solana', 'solana': 'solana',
    'base': 'base',
    'eth': 'ethereum', 'ethereum': 'ethereum',
    'bsc': 'bsc', 'bnb': 'bsc', 'binance': 'bsc',
    'monad': 'monad',
    'megaeth': 'megaeth',
}

# Chain group to emoji mapping
CHAIN_EMOJIS = {
    'solana': '🟣',
    'base': '🔵',
    'ethereum': '🔷',
    'bsc': '🔶',
    'megaeth': '⚡',
    'monad': '🟪',
    'berachain': '🐻',
    'other': '⚪',
    'unknown': '❓'
}


def get_chain_group(chain: str) -> str:
    """
    Map chain name to standard group key.
    
    Args:
        chain: Chain name (e.g., 'solana', 'sol', 'ethereum', 'eth')
    
    Returns:
        Standard group key: solana, base, ethereum, bsc, monad, megaeth, other, unknown
    """
    chain_lower = (chain or '').lower().strip()
    
    if not chain_lower:
        return 'unknown'
    
    # Direct mapping
    if chain_lower in CHAIN_MAP:
        return CHAIN_MAP[chain_lower]
    
    # Check if it's already a valid group
    valid_groups = {'solana', 'base', 'ethereum', 'bsc', 'monad', 'megaeth', 'other', 'unknown'}
    if chain_lower in valid_groups:
        return chain_lower
    
    return 'other'


def get_chain_emoji(chain: str) -> str:
    """
    Get emoji for a chain.
    
    Args:
        chain: Chain name or group
    
    Returns:
        Emoji string for the chain
    """
    group = get_chain_group(chain)
    return CHAIN_EMOJIS.get(group, '🔷')


def get_chain_channel(chain: str, channel_type: str = 'confirmed') -> str:
    """
    Get Redis channel name for a chain.
    
    Args:
        chain: Chain name
        channel_type: 'confirmed' or 'monitored'
    
    Returns:
        Redis channel name (e.g., 'projects:confirmed:solana')
    """
    group = get_chain_group(chain)
    return f"projects:{channel_type}:{group}"


