# agent/prompts_stage1.py
"""
Stage 1 prompts divididos em 2 chamadas especializadas:
1. CLASSIFICADOR - Decide se é projeto, autor, extraí mentions
2. EXTRATOR - Extrai detalhes completos (só se classificador aprovar)
"""

from datetime import datetime


def get_current_date_context() -> str:
    """Get current date formatted for LLM prompts."""
    now = datetime.now()
    return f"Today is {now.strftime('%A, %B %d, %Y')} (ISO: {now.strftime('%Y-%m-%d')})"


# ============================================
# LLM 1: CLASSIFICADOR
# Tarefa: Decidir se é projeto e quem é o autor
# Tokens: ~1200 (muito menor que antes!)
# ============================================

def get_classifier_system_prompt() -> str:
    """Prompt do classificador - decisões críticas apenas."""
    return f"""You are a crypto tweet classifier.
Your ONLY task is to classify tweets and identify WHO is the project.

{get_current_date_context()}

You must answer 4 critical questions:
1. Is this tweet about a NEW crypto project (pre-launch)?
2. Is the tweet AUTHOR the project's official account?
3. If NOT the author, what is the project name/handle to investigate?
4. Has the project already launched (has CA)?

REJECTION REASONS (is_project = false):
- not_crypto - Not about cryptocurrency
- nft_collection - NFT collection (mint, PFP, whitelist, FCFS, floor price, OpenSea, Magic Eden)
- already_launched - Already launched (CA found, "we are live", "launched", DEX links)
- repost_only - Just repost without project content
- news_update - News about existing project
- personal_post - Personal content
- giveaway_only - Just giveaway/airdrop
- influencer_shill - Influencer promoting existing project
- unclear - Cannot determine

CONTRACT ADDRESS (CA) DETECTION:
- EVM: 0x + 40 hex characters (0xe809aC75628A4f2EeB987fd2683F9e9CfB467777)
- Solana: 32-44 Base58 characters (5QNJ5DDnTPYW1gfNoxeXBGy85Ws5k5vH5Ass1KWYmoon)
- pump.fun links with token
- DEX links (dexscreener, dextools, birdeye)

============================================
AUTHOR ANALYSIS - CRITICAL (FOLLOW THESE STEPS!)
============================================

STEP 1: Extract the PROJECT NAME from the tweet text
- Look for capitalized names, brand names, protocol names
- Example: "AlignerZ optimizes for..." → project_name = "AlignerZ"

STEP 2: Compare AUTHOR HANDLE vs PROJECT NAME
- Does @author_handle match or relate to project_name?
- @AlignerZ tweeting about AlignerZ → MATCH
- @cephas_ine tweeting about AlignerZ → NO MATCH

STEP 3: Check for FIRST PERSON language
- "we", "our", "us", "my" + project context = first person
- "[ProjectName] does X" WITHOUT "we/our" = third person

STEP 4: Make decision based on BOTH checks

is_author_the_project = TRUE ONLY when BOTH:
- Author handle matches/contains/relates to project name
- OR uses genuine first person: "we are launching", "our project"

is_author_the_project = FALSE when ANY of these:
- Author handle does NOT match project name (e.g., @cephas_ine ≠ AlignerZ)
- "[ProjectName] does X" without "we/our" (this is THIRD PERSON!)
- Third-person language: "they are launching", "their project"
- User/participant language: "@X tasks", "@X campaign", "@X testnet"
- Influencer patterns: "alpha", "caller", promotes multiple projects

CRITICAL EXAMPLES:

Example 1: @AlignerZ tweets "AlignerZ optimizes for what happens after..."
- STEP 1: project_name = "AlignerZ"
- STEP 2: @AlignerZ matches AlignerZ? YES
- STEP 3: Speaking about their own project
- RESULT: is_author_the_project = TRUE

Example 2: @cephas_ine tweets "AlignerZ optimizes for what happens after..."
- STEP 1: project_name = "AlignerZ"
- STEP 2: @cephas_ine matches AlignerZ? NO!
- STEP 3: "AlignerZ optimizes" is THIRD PERSON (no "we/our")
- RESULT: is_author_the_project = FALSE
- ACTION: Extract project for investigation!

============================================
WHEN is_author_the_project = FALSE:
============================================

You MUST extract the project for investigation!

1. If @handle is mentioned: use the @handle
   Example: "check out @pharos_network" → handle: "@pharos_network"

2. If only NAME is mentioned (no @): infer the likely handle
   Example: "AlignerZ optimizes" → handle: "@AlignerZ" (inferred)
   Example: "Pharos Network is..." → handle: "@pharos_network" (inferred)

The Discoverer will then search Twitter to find the real project account.

QUOTED TWEETS:
- If there's a quoted tweet, the QUOTED AUTHOR might be the real project
- Check who is actually the project: tweet author or quoted author"""


CLASSIFIER_USER_PROMPT = """Classify this tweet:

TWEET:
- Author: @{author_username}
- Followers: {author_followers}
- Text: {text}
- Mentions: {mentions}
- Quoted Author: {quoted_author}
- Quoted Text: {quoted_text}

THINK STEP BY STEP:
1. What is the PROJECT NAME mentioned in this tweet?
2. Does @{author_username} match or relate to that project name?
3. Is the language first person ("we/our") or third person ("[Name] does")?

Answer with JSON only:

{{
  "is_project": boolean,
  "rejection_reason": string or null,
  "confidence": float (0.0-1.0),
  
  "has_ca": boolean,
  "ca_found": string or null,
  
  "project_name_found": string or null (the project name mentioned in tweet),
  "author_handle_matches_project": boolean (does @{author_username} match project name?),
  
  "is_author_the_project": boolean,
  "author_type": "project_official" | "influencer" | "news" | "user" | "bot",
  "author_reasoning": string (explain your step-by-step reasoning),
  
  "mentioned_projects": [
    {{
      "handle": "@handle (use actual @mention OR infer from project name)",
      "name": "project name as mentioned in tweet",
      "is_inferred": boolean (true if handle was inferred from name, false if @mentioned),
      "context": string,
      "confidence": float
    }}
  ]
}}"""


def build_classifier_prompt(tweet_data: dict) -> str:
    """Build classifier prompt with tweet data."""
    import json
    
    # Extract mentions from entities
    entities_json = tweet_data.get('entities_json')
    mentions = []
    if entities_json:
        try:
            entities = json.loads(entities_json) if isinstance(entities_json, str) else entities_json
            mentions = [f"@{m.get('screen_name', '')}" for m in entities.get('user_mentions', []) if m.get('screen_name')]
        except:
            pass
    
    # Extract quoted tweet
    quoted_tweet = tweet_data.get('quoted_tweet')
    if not quoted_tweet and tweet_data.get('raw_json'):
        raw = tweet_data.get('raw_json')
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except:
                raw = {}
        quoted_tweet = raw.get('quoted_tweet') or {}
    
    quoted_tweet = quoted_tweet or {}
    quoted_author = 'None'
    quoted_text = 'None'
    
    if quoted_tweet:
        quoted_author_data = quoted_tweet.get('author') or {}
        quoted_author = f"@{quoted_author_data.get('userName', quoted_author_data.get('username', 'unknown'))}"
        quoted_text = quoted_tweet.get('text', '')[:300]
    
    return CLASSIFIER_USER_PROMPT.format(
        author_username=tweet_data.get('author_username', ''),
        author_followers=tweet_data.get('author_followers', 0),
        text=tweet_data.get('text', ''),
        mentions=', '.join(mentions) if mentions else 'None',
        quoted_author=quoted_author,
        quoted_text=quoted_text
    )


# ============================================
# LLM 2: EXTRATOR DE DETALHES
# Tarefa: Extrair TODOS os detalhes do projeto
# Tokens: ~2400 (só chamado se classificador aprovar)
# ============================================

def get_extractor_system_prompt() -> str:
    """Prompt do extrator - todos os detalhes."""
    return f"""You are a crypto project data extractor.
The tweet was already classified as a VALID pre-launch project by another agent.
Your ONLY task is to extract ALL details about the project.

{get_current_date_context()}

SUPPORTED CHAINS (detect from context, hashtags, mentions):

Layer 1 Blockchains:
- Solana (SOL) - mentions @solana, pump.fun, raydium, jupiter, meteora
- Ethereum (ETH) - mentions @ethereum, uniswap, opensea
- Bitcoin (BTC) - mentions ordinals, runes, BRC-20, @ordinalsbot
- BNB Chain (BSC) - mentions @bnbchain, pancakeswap, @binance, four.meme
- Avalanche (AVAX) - mentions @avaborin, trader joe
- Polygon (MATIC) - mentions @0xpolygon, quickswap
- TON - mentions @ton_blockchain, telegram, ston.fi, dedust
- Sui - mentions @suinetwork, turbos, cetus
- Aptos - mentions @aptos, liquidswap
- Tron - mentions @traborin, sunpump, sunswap
- Near - mentions @nearprotocol, ref finance
- Cardano (ADA) - mentions @cardano, minswap, sundaeswap
- Fantom (FTM) - mentions @fantomfdn, spookyswap
- Cosmos (ATOM) - mentions @cosmos, osmosis
- Algorand (ALGO) - mentions @algorand, tinyman
- Hedera (HBAR) - mentions @hedera, saucerswap
- Cronos (CRO) - mentions @cronaborin, vvs finance
- Injective (INJ) - mentions @injective
- Sei - mentions @seinetwork, dragonswap
- Kaspa (KAS) - mentions @kaborin
- Internet Computer (ICP) - mentions @dfinity
- Mantle - mentions @0xmantle
- Celo - mentions @celoorg

Layer 2 / Rollups:
- Base - mentions @base, @coinbase, aerodrome, baseswap
- Arbitrum - mentions @arbitrum, camelot, gmx
- Optimism (OP) - mentions @optimism, velodrome
- zkSync - mentions @zaborin, syncswap
- Linea - mentions @lineabuild
- Scroll - mentions @scroll_zkp
- Starknet - mentions @starknet, jediswap
- Polygon zkEVM - mentions @0xpolygon zkevm
- Blast - mentions @blast, thruster
- Mode - mentions @modenetwork
- Manta - mentions @mantanetwork
- ZKFair - mentions @zkfair_official

Upcoming / New Chains:
- MegaETH - mentions @megaeth_labs, megaeth
- Monad - mentions @moaborin, monad
- Berachain - mentions @beaborin, bera
- Eclipse - mentions @eclipsaborin
- Fuel - mentions @fuel_network
- Movement - mentions @movaborin
- Flashnet - mentions @flashnet, flash
- Spark - mentions @spark_network, spark chain
- Hyperliquid - mentions @hyperliquid, hyperliquid L1
- Abstract - mentions @abstractchain
- Morph - mentions @morphl2
- Taiko - mentions @taborin

Other Networks:
- Solana L2s - mentions @sonicaborin, @eclipsaborin
- Bitcoin L2s - mentions @staborin, @botanixlabs, @citaborin
- Unknown - if chain cannot be determined

PROJECT TYPES:
- token - Simple token/memecoin
- dex - Decentralized exchange
- defi - DeFi protocol (lending, staking, yield, perps)
- nft - NFT project/collection
- game - GameFi/Play-to-earn
- dao - DAO/Governance
- infra - Infrastructure/Tools/RPC/Indexer
- ai - AI-related project
- social - SocialFi
- bridge - Cross-chain bridge
- launchpad - Token launchpad
- wallet - Wallet application
- oracle - Oracle service
- privacy - Privacy protocol
- rwa - Real World Assets
- restaking - Restaking protocol
- liquid_staking - Liquid staking
- other - Other type

LAUNCH PLATFORMS:
Solana:
- pump.fun - Solana memecoin launchpad (@pumpdotfun)
- raydium - Solana DEX (@raaborin)
- meteora - Solana DEX (@meteaborin)
- jupiter - Solana aggregator (@jupiterexchange)

Ethereum/L2s:
- uniswap - Ethereum/L2 DEX (@uniswap)
- aerodrome - Base DEX (@aaborin)
- velodrome - Optimism DEX (@velodromeFi)
- camelot - Arbitrum DEX (@caaborin)

BNB Chain:
- pancakeswap - BSC DEX (@pancakeswap)
- four.meme - BSC memecoin launchpad (@four_meme_)

TON:
- ston.fi - TON DEX (@ston_fi)
- dedust - TON DEX (@dedaborin)

Tron:
- sunpump - Tron launchpad (@sunpaborin)
- sunswap - Tron DEX

Multi-chain Launchpads:
- luminex - Multi-chain launchpad (@luminexio)
- pinksale - Multi-chain launchpad (@paborin)
- gempad - Multi-chain launchpad (@gemaborin)
- dxsale - Multi-chain launchpad
- unicrypt - Multi-chain launchpad (@uniaborin)

Other:
- other - Other platform
- unknown - Not mentioned
- direct - Direct contract deployment

NAME/TICKER POSSIBILITIES:
For EVERY project, provide AT LEAST 3 possibilities for both name and ticker.

name_possibilities rules:
1. First: Most likely name from explicit mention
2. Second: Derived from Twitter handle
3. Third+: Inferred variations (Protocol, Network, Fi, etc.)

ticker_possibilities rules:
1. First: Explicitly mentioned ticker (with $)
2. Second: Derived from project name initials
3. Third+: Common variations (3-4 letters)

Validation:
- name_validated = true if name appears in bio/handle/multiple tweets
- ticker_validated = true if ticker explicitly mentioned with $"""


EXTRACTOR_USER_PROMPT = """Extract ALL project details from this tweet:

TWEET:
- Tweet ID: {tweet_id}
- Author: @{author_username} (ID: {author_id})
- Author Followers: {author_followers}
- Text: {text}
- Created At: {created_at}
- Language: {lang}
- Hashtags: {hashtags}
- URLs: {urls}
- Mentions: {mentions}
- Like Count: {like_count}
- Retweet Count: {retweet_count}
- View Count: {view_count}

Extract all project details. Answer with JSON only:

{{
  "project": {{
    "name": string or null,
    "ticker": string or null (include $ if mentioned),
    "type": string (token/dex/defi/nft/game/dao/infra/ai/social/bridge/launchpad/wallet/oracle/privacy/rwa/restaking/liquid_staking/other),
    "chain": string (solana/ethereum/bitcoin/bnb/base/arbitrum/optimism/zksync/linea/scroll/starknet/blast/polygon/avalanche/ton/sui/aptos/tron/near/cardano/fantom/cosmos/algorand/hedera/cronos/injective/sei/kaspa/icp/mantle/celo/megaeth/monad/berachain/eclipse/fuel/movement/flashnet/spark/hyperliquid/abstract/morph/taiko/mode/manta/zkfair/unknown),
    
    "name_possibilities": [
      {{"name": string, "confidence": float, "source": "bio"|"handle"|"tweet"|"inferred"}}
    ],
    "ticker_possibilities": [
      {{"ticker": string, "confidence": float, "source": "tweet"|"bio"|"inferred"}}
    ],
    "name_validated": boolean,
    "ticker_validated": boolean
  }},
  
  "launch": {{
    "status": string (pre_launch/launching_soon/launching/launched/unknown),
    "date": string or null (YYYY-MM-DD if mentioned),
    "time": string or null (HH:MM UTC if mentioned),
    "platform": string (pump.fun/raydium/meteora/jupiter/uniswap/aerodrome/velodrome/camelot/pancakeswap/four.meme/ston.fi/dedust/sunpump/sunswap/luminex/pinksale/gempad/dxsale/unicrypt/direct/other/unknown)
  }},
  
  "source": {{
    "tweet_id": "{tweet_id}",
    "twitter_handle": "@{author_username}",
    "author_id": "{author_id}",
    "author_followers": {author_followers},
    "tweet_date": "{tweet_date}",
    "tweet_text_preview": string (first 100 chars)
  }},
  
  "mentions": {{
    "tagged_accounts": [list of all @handles],
    "tagged_chains": [list of chain @handles],
    "tagged_platforms": [list of platform @handles]
  }},
  
  "signals": {{
    "keywords_found": [list of keywords],
    "has_links": boolean,
    "links": [list of URLs],
    "has_telegram": boolean,
    "telegram_link": string or null,
    "has_discord": boolean,
    "discord_link": string or null,
    "has_website": boolean,
    "website_link": string or null
  }}
}}"""


def build_extractor_prompt(tweet_data: dict) -> str:
    """Build extractor prompt with tweet data."""
    import json
    
    # Extract entities
    entities_json = tweet_data.get('entities_json')
    entities = {}
    if entities_json:
        try:
            entities = json.loads(entities_json) if isinstance(entities_json, str) else entities_json
        except:
            pass
    
    hashtags = [h.get('text', '') for h in entities.get('hashtags', [])]
    urls = [u.get('expanded_url', u.get('url', '')) for u in entities.get('urls', [])]
    mentions = [f"@{m.get('screen_name', '')}" for m in entities.get('user_mentions', []) if m.get('screen_name')]
    
    # Parse date
    created_at = tweet_data.get('created_at', '')
    tweet_date = ''
    if created_at:
        try:
            dt = datetime.strptime(created_at, '%a %b %d %H:%M:%S %z %Y')
            tweet_date = dt.strftime('%Y-%m-%d')
        except:
            tweet_date = created_at[:10] if len(created_at) >= 10 else ''
    
    return EXTRACTOR_USER_PROMPT.format(
        tweet_id=tweet_data.get('id', ''),
        author_username=tweet_data.get('author_username', ''),
        author_id=tweet_data.get('author_id', ''),
        author_followers=tweet_data.get('author_followers', 0),
        text=tweet_data.get('text', ''),
        created_at=created_at,
        lang=tweet_data.get('lang', ''),
        hashtags=', '.join(hashtags) if hashtags else 'None',
        urls=', '.join(urls) if urls else 'None',
        mentions=', '.join(mentions) if mentions else 'None',
        like_count=tweet_data.get('like_count', 0),
        retweet_count=tweet_data.get('retweet_count', 0),
        view_count=tweet_data.get('view_count', 0),
        tweet_date=tweet_date
    )

