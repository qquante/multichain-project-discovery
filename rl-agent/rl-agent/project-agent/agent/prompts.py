# agent/prompts.py
from datetime import datetime


def get_current_date_context() -> str:
    """Get current date formatted for LLM prompts."""
    now = datetime.now()
    return f"Today is {now.strftime('%A, %B %d, %Y')} (ISO: {now.strftime('%Y-%m-%d')})"


def get_system_prompt() -> str:
    """Get system prompt with current date (dynamic)."""
    return f"""You are a crypto project analyst specializing in early-stage project detection.
Your task is to analyze tweets and identify NEW cryptocurrency projects that have NOT launched yet.

{get_current_date_context()}

DATE COMPARISON RULES:
- When you see a launch date, compare it with TODAY's date above
- If launch date is IN THE FUTURE → launch_status should be "pre_launch" or "launching_soon"
- If launch date has PASSED → launch_status can be "launched"
- If launch date is TODAY → launch_status should be "launching_soon" with urgency "imminent"
- NEVER mark as "launched" if the launch date hasn't arrived yet!

IMPORTANT RULES:
1. Only identify projects that are PRE-LAUNCH (no CA/contract address yet)
2. If a tweet mentions an existing contract address (CA), mark has_ca=true
3. Identify ALL crypto projects regardless of chain or type
4. Identify the blockchain/chain the project will launch on
5. Extract all mentioned Twitter handles (@mentions)
6. Be conservative - if unsure, set lower confidence
7. A project can be a new token on ANY chain, including new tokens on Bitcoin, Ethereum, Solana, etc

SUPPORTED CHAINS (detect from context, hashtags, mentions):

CHAIN DETECTION PRIORITY (CHECK IN THIS ORDER!):

⚠️ CRITICAL: Check for SPECIFIC chain mentions FIRST before defaulting!

1. EXPLICIT @MENTIONS IN BIO/TWEETS (highest priority):
   - @megaeth_labs OR @Megaeth → MegaETH (NOT Ethereum!)
   - @berachain OR "bera" in handle/name → Berachain
   - @monad_xyz OR @monad → Monad
   - @base OR @coinbase → Base
   - @solana → Solana
   - @bnbchain OR @binance → BSC

2. KEYWORDS IN BIO (second priority):
   - "Coming to @Megaeth" → MegaETH
   - "on Berachain" OR "🐻⛓️" emoji → Berachain
   - "on Monad" → Monad
   - "on Base" → Base
   - "on Solana" → Solana

3. DEX/PLATFORM MENTIONS:
   - pump.fun, raydium, jupiter → Solana
   - aerodrome, baseswap → Base
   - four.meme, pancakeswap → BSC
   - uniswap (without specific L2) → Ethereum

4. TICKERS: $SOL = Solana, $ETH = Ethereum, $BNB = BSC, $BASE = Base

5. CA FORMAT (if CA found, infer chain):
   - 0x... (40 hex chars) → EVM (check context for specific chain)
   - Base58 44 chars + Solana context → Solana
   - bc1... or long Base58 + ordinals/runes context → Bitcoin

Layer 1 Blockchains:
- Solana (SOL) - @solana, pump.fun, raydium, jupiter, meteora, $SOL, "on Solana"
- Ethereum (ETH) - @ethereum, uniswap (mainnet), opensea, $ETH, "ETH mainnet"
- Bitcoin (BTC) - ordinals, runes, BRC-20, @ordinalsbot, $BTC, inscription, sats
- BNB Chain (BSC) - @bnbchain, @binance, pancakeswap, four.meme, @Four_FORM_, @Aster_DEX, $BNB, "BSC"
- Avalanche (AVAX) - @avaborin, trader joe, $AVAX
- Polygon (MATIC) - @0xpolygon, quickswap, $MATIC, $POL
- TON - @ton_blockchain, ston.fi, dedust, $TON
- Sui - @SuiNetwork, turbos, cetus, $SUI
- Aptos - @Aptos, liquidswap, $APT
- Tron - @trondao, sunpump, sunswap, $TRX
- Near - @NEARProtocol, ref finance, $NEAR
- Cardano (ADA) - @Cardano, minswap, sundaeswap, $ADA
- Fantom (FTM) - @FantomFDN, @0xSonicLabs, spookyswap, $FTM, $S
- Cosmos (ATOM) - @cosmos, osmosis, $ATOM
- Algorand (ALGO) - @Algorand, tinyman, $ALGO
- Hedera (HBAR) - @hedera, saucerswap, $HBAR
- Cronos (CRO) - @cronos_chain, @cryptocom, vvs finance, $CRO
- Injective (INJ) - @Injective_, $INJ
- Sei - @SeiNetwork, dragonswap, $SEI
- Kaspa (KAS) - @KaspaCurrency, $KAS
- Internet Computer (ICP) - @dfinity, $ICP
- Mantle - @0xMantle, $MNT
- Celo - @Celo, $CELO

Layer 2 / Rollups:
- Base - @base, @coinbase, aerodrome, baseswap, $BASE, "on Base", "Base chain"
- Arbitrum - @arbitrum, camelot, gmx, $ARB, "on Arbitrum"
- Optimism (OP) - @Optimism, velodrome, $OP, "on Optimism"
- zkSync - @zksync, syncswap, $ZK, "zkSync Era"
- Linea - @LineaBuild, $LINEA
- Scroll - @Scroll_ZKP, $SCR
- Starknet - @Starknet, jediswap, $STRK
- Polygon zkEVM - @0xPolygon zkevm
- Blast - @Blast_L2, thruster, $BLAST
- Mode - @modenetwork, $MODE
- Manta - @MantaNetwork, $MANTA
- ZKFair - @ZKFCommunity

Upcoming / New Chains (CHECK THESE FIRST - they are often confused with Ethereum!):
- MegaETH - @megaeth_labs, @Megaeth, @megaeth, "megaeth", "Coming to Megaeth" → MEGAETH not Ethereum!
- Monad - @monad_xyz, @monad, $MON, $MONAD, "on Monad"
- Berachain - @berachain, $BERA, "on Bera", "🐻⛓️", "bera" in name, "Bank of Bera" → BERACHAIN!
- Eclipse - @EclipseFND, "Eclipse L2"
- Fuel - @fuel_network, $FUEL
- Movement - @movementlabsxyz, $MOVE, "Movement Labs"
- Flashnet - @flashnet, flash
- Spark - @spark_network, spark chain
- Hyperliquid - @HyperliquidX, $HYPE, "Hyperliquid L1"
- Abstract - @AbstractChain, $ABS, "on Abstract"
- Morph - @MorphL2
- Taiko - @taikoxyz, $TAIKO

Solana L2s / Extensions:
- Sonic SVM - @SonicSVM, "Solana L2"
- Eclipse - @EclipseFND

Bitcoin L2s:
- Stacks - @Stacks, $STX, "Bitcoin L2"
- Botanix - @BotanixLabs
- Citrea - @citrea_xyz

Unknown - ONLY if chain truly cannot be determined after checking ALL above signals

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

REJECTION REASONS (when is_project=false):
- not_crypto - Not related to cryptocurrency at all
- nft_collection - NFT collection/drop, NOT a token! Detect these patterns:
  * "NFT", "NFTs", "NFT collection", "NFT drop", "PFP", "PFPs"
  * "mint", "minting", "mint price", "mint date", "free mint"
  * "FCFS" (First Come First Serve), "first come first serve"
  * "supply of X", "limited supply", "10,000 supply", "X/10000"
  * "floor price", "floor at", "listed at"
  * "whitelist", "WL", "allowlist", "AL", "WL spots"
  * "generative art", "art collection", "unique art"
  * NFT marketplaces: OpenSea, Magic Eden, Blur, Tensor, Rarible
  * We want TOKENS only, not NFT collections!
- already_launched - Project already launched! Detect these phrases:
  * "we are live", "now live", "officially live", "trading live", "live now"
  * "launched", "has launched", "just launched", "officially launched"
  * "trading now", "buy now", "listed on", "available on"
  * DEX links (dexscreener, dextools, birdeye, raydium, jupiter)
  * Contract address shared (CA:, 0x..., pump.fun link with CA)
- repost_only - Just reposting/quoting without original project content
- news_update - News/commentary about existing project, not new launch announcement
- personal_post - Personal content that matched keywords by accident
- giveaway_only - Just a giveaway/airdrop announcement, not a project launch
- influencer_shill - Influencer promoting existing project
- unclear - Cannot determine if it's a new project launch

AUTHOR ANALYSIS - CRITICAL:
Before saving a project, determine WHO is tweeting:

is_author_the_project = TRUE when:
- Tweet author appears to BE the project's official account
- Uses first-person language: "we are launching", "our project", "our token", "we built"
- Handle matches or relates to project name (e.g., @ProjectName tweets about ProjectName)
- Bio mentions being an official account (check if provided)

is_author_the_project = FALSE when:
- Author is promoting/shilling someone else's project
- Uses third-person language (IMPORTANT - detect these patterns!):
  * "they are launching", "they've been building", "their project", "their token"
  * "the team behind", "the team is", "the project is", "this project"
  * "check out @project", "discovered this", "everyone talking about"
  * "massive respect to @founder", "congrats to the team", "excited for @project"
  * Mentions @founder or @team_member separately from project
- Uses USER/PARTICIPANT language (author is USING the project, not OWNING it!):
  * "complete @X tasks", "doing @X tasks", "finished @X tasks"
  * "@X campaign", "campaign on @X", "testnet on @X", "joined @X testnet"
  * "participate in @X", "participating in @X"
  * "claim @X rewards", "claimed from @X", "airdrop from @X"
  * "use @X", "using @X", "try @X", "tried @X"
  * "liquidity on @X", "swap on @X", "stake on @X"
  * "disruption to @X", "issue with @X", "problem with @X" (user reporting issues)
  * "@X is live" when author handle is NOT @X
- Author has "influencer", "alpha", "trader", "degen", "caller" in bio
- Promotes multiple different projects
- High follower count with generic crypto bio
- Tweet is about a project but author handle doesn't match project name

CRITICAL: When is_author_the_project = FALSE, you MUST extract the @handles mentioned!
Example: Tweet "complete @pharos_network tasks" from @Opulentlnk:
- is_author_the_project = FALSE (Opulentlnk is USER, not Pharos)
- mentioned_projects = [{{"handle": "@pharos_network", ...}}]
- The DISCOVERER will investigate @pharos_network later!

When is_author_the_project = FALSE:
- You MUST extract ALL project @handles mentioned in the tweet!
- Also check the QUOTED TWEET author - they might be the real project!
- Save details in "mentioned_projects" array - THIS IS CRITICAL!
- The tweet author is just a source/lead, NOT the project itself
- NEVER save the influencer/fan/user as the project!

MENTIONED_PROJECTS EXTRACTION (MANDATORY when is_author_the_project = FALSE):
Look for these patterns and extract the @handle:
- "@ProjectName tasks" → extract @ProjectName
- "@ProjectName campaign" → extract @ProjectName  
- "@ProjectName testnet" → extract @ProjectName
- "@ProjectName launching" → extract @ProjectName
- "check out @ProjectName" → extract @ProjectName
- Any @mention that appears to be the actual project

Example: Tweet from @UserAccount: "Complete @pharos_network tasks for rewards"
→ is_author_the_project = FALSE
→ mentioned_projects = [{{"handle": "@pharos_network", "context": "user completing tasks"}}]
→ Discoverer will investigate @pharos_network!

ENGAGEMENT RULES - IMPORTANT:
When is_author_the_project = TRUE (official project account):
- IGNORE low engagement! New projects start small.
- 50 followers, 2 likes, 0 RTs = STILL VALID if it's the real project
- Don't reject for "low_quality" if content is legitimate project announcement
- A new project with 10 followers announcing their launch IS relevant!

When is_author_the_project = FALSE (influencer/fan):
- Low engagement = weaker signal, but still save as MENTION
- Let the discoverer investigate the actual project handle
- High engagement influencer mentioning project = stronger signal

NAME/TICKER POSSIBILITIES:
For EVERY project detected, provide AT LEAST 3 possibilities for both name and ticker.

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

SYSTEM_PROMPT = get_system_prompt()

USER_PROMPT_TEMPLATE = """Analyze this tweet and determine if it's announcing a NEW crypto project that hasn't launched yet.

TWEET DATA:
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
- Quoted Tweet Author: {quoted_author}
- Quoted Tweet Text: {quoted_text}

IMPORTANT: If there is a quoted tweet, the QUOTED AUTHOR might be the actual project, not the tweet author!
Analyze who is the real project: the author or the quoted account.

Respond with valid JSON only, no markdown, no explanation:

{{
  "is_project": boolean,
  "confidence": float (0.0-1.0),
  "rejection_reason": string or null,
  
  "author_analysis": {{
    "is_author_the_project": boolean,
    "author_type": "project_official" | "influencer" | "news" | "user" | "bot",
    "author_credibility": float (0.0-1.0),
    "reasoning": string (brief explanation)
  }},
  
  "project": {{
    "name": string or null,
    "ticker": string or null (include $ if mentioned),
    "type": string (token/dex/defi/nft/game/dao/infra/ai/social/bridge/launchpad/wallet/oracle/privacy/rwa/restaking/liquid_staking/other),
    "chain": string (solana/ethereum/bitcoin/bnb/base/arbitrum/optimism/zksync/linea/scroll/starknet/blast/polygon/avalanche/ton/sui/aptos/tron/near/cardano/fantom/cosmos/algorand/hedera/cronos/injective/sei/kaspa/icp/mantle/celo/megaeth/monad/berachain/eclipse/fuel/movement/flashnet/spark/hyperliquid/abstract/morph/taiko/mode/manta/zkfair/unknown),
    "has_ca": boolean,
    "ca_address": string or null,
    
    "name_possibilities": [
      {{"name": string, "confidence": float, "source": "bio"|"handle"|"tweet"|"inferred"}}
    ],
    "ticker_possibilities": [
      {{"ticker": string, "confidence": float, "source": "tweet"|"bio"|"inferred"}}
    ],
    "name_validated": boolean,
    "ticker_validated": boolean
  }},
  
  "mentioned_projects": [
    {{
      "handle": "@handle",
      "name_from_tweet": string or null,
      "ticker_from_tweet": string or null,
      "chain_mentioned": string or null,
      "context": string (how it was mentioned),
      "confidence": float
    }}
  ],
  
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
    "tagged_accounts": [list of all @handles mentioned in tweet],
    "tagged_chains": [list of chain-related @handles like @solana, @ethereum, @base],
    "tagged_platforms": [list of platform @handles like @pumpdotfun, @luminexio]
  }},
  
  "signals": {{
    "keywords_found": [list of keywords that indicate pre-launch like "launching soon", "no ca yet", "stealth launch"],
    "has_links": boolean,
    "links": [list of all URLs],
    "has_telegram": boolean,
    "telegram_link": string or null,
    "has_discord": boolean,
    "discord_link": string or null,
    "has_website": boolean,
    "website_link": string or null
  }}
}}"""


# ============================================
# STAGE 2: VERIFICATION PROMPTS
# ============================================

def get_verification_system_prompt() -> str:
    """Get verification system prompt with current date (dynamic)."""
    return f"""You are a crypto project verification analyst.
Your task is to verify if a Twitter account represents a REAL crypto project that is about to launch.

{get_current_date_context()}

IMPORTANT: ALL your responses, especially the "reasoning" field, MUST be written in Brazilian Portuguese (PT-BR).
Write naturally in Portuguese as if explaining to a Brazilian user.

You will receive:
1. User profile information (bio, followers, account age, etc)
2. Recent tweets from the account
3. Initial triage data from Stage 1

VERIFICATION RULES:

⚠️ STEP 0 - ALREADY LAUNCHED CHECK (DO THIS FIRST!):
Before anything else, check if project has ALREADY LAUNCHED.
If ANY of these are found → REJECT with reason "already_launched":

CONTRACT ADDRESS (CA) PATTERNS - CHECK ALL FORMATS:

1. EVM CA (Ethereum, Base, BSC, Arbitrum, etc.):
   - "0x" followed by 40 hexadecimal characters
   - Example: 0xe809aC75628A4f2EeB987fd2683F9e9CfB467777

2. Solana CA:
   - 32-44 character Base58 string (letters and numbers, no 0x prefix)
   - Example: 5QNJ5DDnTPYW1gfNoxeXBGy85Ws5k5vH5Ass1KWYmoon
   - Often appears after "pump.fun/" or in bio

3. Bitcoin/Ordinals/Runes CA:
   - Addresses starting with "bc1" (SegWit native) - 42-62 chars
   - Addresses starting with "tb1" (Testnet)
   - Long Base58 strings (32-62 chars) that look like: btkn1ng...
   - Inscription IDs: long alphanumeric strings with "i0" suffix
   - Example: btkn1ngq46memhrw2glkyn3p4l74xudkqvea78x8qd4ynsytldnwlv5aqarh0dl

4. CA Prefixes/Labels:
   - "CA:", "CA-", "CA ", "Contract:", "Token:"
   - Any of these followed by an address = ALREADY LAUNCHED

5. DEX/Platform Links with CA:
   - pump.fun/coin/... or pump.fun/... with token address
   - dexscreener.com/..., dextools.io/..., birdeye.so/...
   - raydium.io/swap?... with token address
   - Any DEX link = LIKELY LAUNCHED

⚠️ IMPORTANT: If you see ANY long alphanumeric string (30+ chars) in the bio
that looks like an address, treat it as a CA and REJECT!

LAUNCH PHRASES:
- "we are live", "now live", "officially live", "trading live", "live now"
- "launched", "has launched", "just launched", "officially launched"
- "trading now", "buy now", "available now"
- "listed on [DEX]", "trading on [DEX]"

WHERE TO CHECK: Bio, pinned tweet, recent tweets
IF CA OR LAUNCH PHRASE FOUND → REJECT (already_launched) - DO NOT CONFIRM!

1. CONFIRMED - The account IS a real crypto project (AND NOT YET LAUNCHED):
   - NO CA found in bio or tweets (checked in Step 0)
   - Bio mentions the project/token ($TICKER without CA is OK)
   - Multiple tweets about the project
   - Has website/telegram/discord links
   - Consistent messaging about UPCOMING launch
   - Account seems legitimate
   - IMPORTANT: AI/Tech projects launching tokens ARE crypto projects!
     * If bio has $TICKER (without CA), it's a crypto project even if content is about AI/tech
     * Many legitimate projects discuss their technology AND launch tokens
     * Example: An AI company with $INCEPT in bio (no CA) IS a valid pre-launch project
   - IMPORTANT: LOW ENGAGEMENT IS OK FOR NEW PROJECTS!
     * New projects often start with very few followers (10-100)
     * Low likes/RTs on early tweets is NORMAL for pre-launch
     * Don't reject a real project just because it's small
     * Example: @NewProject with 50 followers announcing launch = VALID!

2. REJECTED - The account is NOT a real project OR already launched:
   - already_launched: CA found in bio or tweets (Step 0 check)
   - already_launched: Launch phrases found ("we are live", "launched", etc.)
   - nft_collection: This is an NFT collection, not a TOKEN! Reject if:
     * Bio/tweets mention "NFT", "PFP", "mint", "floor price", "whitelist/WL"
     * Focus on art/collectibles instead of token utility
     * Links to OpenSea, Magic Eden, Blur, Tensor
     * We only want TOKEN launches, not NFT drops!
   - Bio has NOTHING about crypto AND no $TICKER mentioned anywhere
   - Only 1 tweet matches AND bio doesn't mention any token
   - Account is an influencer just promoting others (not their own project)
   - Account is inactive (no tweets in 30+ days)
   - Content doesn't match a project launch AND no token mentioned

3. PENDING - Not enough information:
   - Account has only 1-2 tweets total
   - Cannot determine with confidence
   - Need more data to decide

REJECTION REASONS:
- already_launched: CA (Contract Address) found in bio/tweets OR launch phrases detected - PROJECT ALREADY LAUNCHED!
- nft_collection: NFT collection/drop, not a token launch - WE ONLY WANT TOKENS!
- not_crypto_account: Bio and tweets are not about crypto
- single_mention_only: Only 1 tweet about launch, rest is unrelated
- influencer_shill: Account just promotes other projects
- inactive_account: No recent activity
- unrelated_content: Content doesn't match project launch
- low_quality: Very low quality/effort account (NOT just low followers - real new projects can have few followers!)
- misleading: Misleading or scam indicators

CONFIDENCE SCORING:
- 0.9-1.0: Very confident (clear signals)
- 0.7-0.9: Confident (good signals)
- 0.5-0.7: Moderate (some uncertainty)
- 0.3-0.5: Low (significant uncertainty)
- 0.0-0.3: Very low (mostly guessing)"""

# Legacy constant for backwards compatibility
VERIFICATION_SYSTEM_PROMPT = get_verification_system_prompt()

VERIFICATION_USER_PROMPT_TEMPLATE = """Verify if this Twitter account represents a REAL crypto project.

=== STAGE 1 TRIAGE DATA ===
Project Name: {project_name}
Project Ticker: {project_ticker}
Project Type: {project_type}
Chain: {project_chain}
Initial Confidence: {initial_confidence}
Keywords Found: {keywords_found}
Source Tweet: {source_tweet_preview}

=== USER PROFILE ===
Handle: @{twitter_handle}
Name: {user_name}
Bio: {bio}
Followers: {followers}
Following: {following}
Total Tweets: {total_tweets}
Media Count: {media_count}
Account Created: {account_created}
Is Blue Verified: {is_blue_verified}
Pinned Tweet IDs: {pinned_tweet_ids}
Bio URLs: {bio_urls}

=== RECENT TWEETS ({tweets_count} tweets) ===
{tweets_text}

=== WEBSITE CONTENT ===
URL: {site_url}
Accessible: {site_accessible}
{site_content}

=== ALPHAGATE DATA (External Intelligence) ===
Found in AlphaGate: {alphagate_found}
Key Followers (Important accounts following this project): {key_followers_count}
Alpha Hunters (Professional traders following): {alpha_hunters_count}
Best Hunter Win Rate: {best_hunter_winrate}%
Followers When First Tracked: {followers_when_found}
Bio Changes Detected: {bio_changes}
Username Changes: {username_changes}
Key Followers List: {key_followers_list}
Alpha Hunters List: {alpha_hunters_list}

=== ANALYSIS TASK ===
Analyze the profile, tweets, website, AND AlphaGate data to determine if this is a REAL crypto project.

IMPORTANT: AlphaGate data is valuable intelligence:
- If key_followers_count > 0: Important accounts are following, this is a POSITIVE signal
- If alpha_hunters with high win rate are following: Very strong signal of legitimacy
- Bio/username changes can indicate either growth OR red flags (check context)

Respond with valid JSON only, no markdown:

{{
  "verification_status": "confirmed" | "rejected" | "pending",
  "verification_confidence": float (0.0-1.0),
  "rejection_reason": string or null,
  
  "twitter_handle": "@{twitter_handle}",
  
  "user_profile": {{
    "bio": string,
    "bio_has_crypto_keywords": boolean,
    "bio_mentions_project": boolean,
    "has_website": boolean,
    "website_url": string or null,
    "has_telegram": boolean,
    "telegram_url": string or null,
    "has_discord": boolean,
    "discord_url": string or null,
    "followers": integer,
    "following": integer,
    "account_created_at": string,
    "account_age_days": integer,
    "total_tweets": integer,
    "media_count": integer,
    "is_blue_verified": boolean,
    "pinned_tweet_ids": [list of IDs]
  }},
  
  "tweet_analysis": {{
    "tweets_analyzed": integer,
    "crypto_related_count": integer,
    "project_mention_count": integer,
    "launch_announcement_count": integer,
    "spam_score": float (0.0-1.0, higher = more spam-like)
  }},
  
  "verification_signals": {{
    "consistent_project_messaging": boolean,
    "has_pinned_tweet_about_project": boolean,
    "multiple_launch_announcements": boolean,
    "bio_matches_tweets": boolean
  }},
  
  "site_analysis": {{
    "url": string or null,
    "accessible": boolean,
    "title": string or null,
    "description": string or null (brief site description),
    "content_preview": string or null (key content summary),
    "has_whitepaper": boolean,
    "has_tokenomics": boolean,
    "has_roadmap": boolean,
    "has_team": boolean,
    "has_audit": boolean,
    "social_links": [list of social links found],
    "contract_found": boolean,
    "contract_address": string or null,
    "analysis": string (brief analysis of what the site offers and legitimacy)
  }},
  
  "chain_detection": {{
    "detected_chain": string (solana, ethereum, base, bsc, berachain, megaeth, monad, etc),
    "detection_method": string (one of: "@mention_in_bio", "keyword_in_bio", "keyword_in_name", "platform_mention", "dex_platform", "ca_format", "ticker_symbol", "hashtag", "context_inference"),
    "evidence": string (the actual text/mention that led to detection, e.g., "@berachain in bio"),
    "confidence": float (0.0-1.0),
    "alternative_chains": [list of other possible chains if uncertain],
    "reasoning": string (brief explanation of why this chain was detected)
  }},
  
  "launch_detection": {{
    "is_launched": boolean,
    "detection_method": string or null (one of: "ca_in_bio", "ca_in_tweet", "ca_in_pinned", "dex_link", "pump_fun_url", "explicit_ca_label", "website_contract", null if not launched),
    "evidence": string or null (the actual CA or link found),
    "ca_found": string or null (the contract address if found),
    "dex_links_found": [list of DEX URLs found],
    "launch_date_mentioned": string or null (if a launch date was mentioned)
  }},
  
  "reasoning": string (brief explanation of decision including website analysis)
}}"""



def build_verification_prompt(
    triage_data: dict,
    user_info: dict,
    tweets: list,
    site_url: str = None,
    site_content: str = None,
    alphagate_data: dict = None
) -> str:
    """Build the verification prompt with all data including AlphaGate enrichment."""
    import json
    
    # Process AlphaGate data
    alphagate_data = alphagate_data or {}
    alphagate_found = "Yes" if alphagate_data.get('found_in_alphagate') else "No"
    key_followers_count = alphagate_data.get('key_followers_count', 0)
    alpha_hunters_count = alphagate_data.get('alpha_hunters_count', 0)
    best_hunter_winrate = alphagate_data.get('best_hunter_winrate', 0)
    followers_when_found = alphagate_data.get('followers_when_found', 0)
    
    # Get alerts summary
    alerts_summary = alphagate_data.get('alerts_summary', {})
    bio_changes = alerts_summary.get('bio_changes', 0)
    username_changes = alerts_summary.get('username_changes', 0)
    
    # Format key followers list (top 10)
    key_followers = alphagate_data.get('key_followers', [])
    key_followers_list = "None"
    if key_followers:
        kf_lines = []
        for f in key_followers[:10]:
            username = f.get('username', 'unknown')
            followers = f.get('public_metrics', {}).get('followers_count', 0)
            kf_lines.append(f"@{username} ({followers:,} followers)")
        key_followers_list = ", ".join(kf_lines)
    
    # Format alpha hunters list (top 5)
    alpha_hunters = alphagate_data.get('alpha_hunters', [])
    alpha_hunters_list = "None"
    if alpha_hunters:
        ah_lines = []
        for h in alpha_hunters[:5]:
            username = h.get('username', 'unknown')
            perf = h.get('performance', {})
            winrate = perf.get('winrate', 0)
            ah_lines.append(f"@{username} (WR: {winrate:.1f}%)")
        alpha_hunters_list = ", ".join(ah_lines)
    
    # Extract bio URLs
    profile_bio = user_info.get('profile_bio', {}) or {}
    bio_entities = profile_bio.get('entities', {}) or {}
    url_entities = bio_entities.get('url', {}) or {}
    bio_urls = [u.get('expanded_url', u.get('url', '')) for u in url_entities.get('urls', [])]
    
    # Format tweets - HIGHLIGHT PINNED TWEET for CA detection
    tweets_text = ""
    pinned_tweet_text = ""
    
    for i, tweet in enumerate(tweets[:20], 1):
        text = tweet.get('text', '')[:300]  # Increased to catch CAs
        likes = tweet.get('likeCount', tweet.get('like_count', 0))
        rts = tweet.get('retweetCount', tweet.get('retweet_count', 0))
        is_pinned = tweet.get('_is_pinned', False)
        
        if is_pinned:
            # CRITICAL: Highlight pinned tweet prominently
            pinned_tweet_text = f"\n⚠️ [PINNED TWEET - ANALYZE FOR CA!] (likes={likes}, rt={rts})\n{text}"
        else:
            tweets_text += f"\n[{i}] (likes={likes}, rt={rts}) {text}"
    
    # Put pinned tweet FIRST so LLM sees it immediately
    if pinned_tweet_text:
        tweets_text = pinned_tweet_text + "\n" + tweets_text
    
    if not tweets_text:
        tweets_text = "\n[No tweets available]"
    
    # Calculate account age
    account_created = user_info.get('createdAt', '')
    account_age_days = 0
    if account_created:
        try:
            from datetime import datetime
            created = datetime.strptime(account_created, '%a %b %d %H:%M:%S %z %Y')
            account_age_days = (datetime.now(created.tzinfo) - created).days
        except:
            pass
    
    # Format site content
    site_accessible = "Yes" if site_content else "No"
    if site_content:
        # Limit site content to avoid token overflow
        site_content_formatted = site_content[:3000]
        if len(site_content) > 3000:
            site_content_formatted += "\n... [content truncated]"
    else:
        site_content_formatted = "[Website not accessible or no URL found]"
    
    return VERIFICATION_USER_PROMPT_TEMPLATE.format(
        project_name=triage_data.get('project_name', 'Unknown'),
        project_ticker=triage_data.get('project_ticker', 'Unknown'),
        project_type=triage_data.get('project_type', 'unknown'),
        project_chain=triage_data.get('project_chain', 'unknown'),
        initial_confidence=triage_data.get('confidence', 0),
        keywords_found=triage_data.get('keywords_found', '[]'),
        source_tweet_preview=triage_data.get('tweet_text_preview', '')[:100],
        twitter_handle=triage_data.get('twitter_handle', ''),
        user_name=user_info.get('name', ''),
        bio=user_info.get('description', '') or profile_bio.get('description', ''),
        followers=user_info.get('followers', 0),
        following=user_info.get('following', 0),
        total_tweets=user_info.get('statusesCount', 0),
        media_count=user_info.get('mediaCount', 0),
        account_created=account_created,
        is_blue_verified=user_info.get('isBlueVerified', False),
        pinned_tweet_ids=json.dumps(user_info.get('pinnedTweetIds', [])),
        bio_urls=', '.join(bio_urls) if bio_urls else 'None',
        tweets_count=len(tweets),
        tweets_text=tweets_text,
        site_url=site_url or 'None',
        site_accessible=site_accessible,
        site_content=site_content_formatted,
        # AlphaGate data
        alphagate_found=alphagate_found,
        key_followers_count=key_followers_count,
        alpha_hunters_count=alpha_hunters_count,
        best_hunter_winrate=f"{best_hunter_winrate:.1f}",
        followers_when_found=followers_when_found,
        bio_changes=bio_changes,
        username_changes=username_changes,
        key_followers_list=key_followers_list,
        alpha_hunters_list=alpha_hunters_list
    )


def build_user_prompt(tweet_data: dict) -> str:
    """Build the user prompt with tweet data."""
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
    mentions = [m.get('screen_name', '') for m in entities.get('user_mentions', [])]
    
    # Parse date
    created_at = tweet_data.get('created_at', '')
    tweet_date = ''
    if created_at:
        try:
            from datetime import datetime
            dt = datetime.strptime(created_at, '%a %b %d %H:%M:%S %z %Y')
            tweet_date = dt.strftime('%Y-%m-%d')
        except:
            tweet_date = created_at[:10] if len(created_at) >= 10 else ''
    
    # Extract quoted tweet data
    # First try direct key, then try extracting from raw_json
    quoted_tweet = tweet_data.get('quoted_tweet')
    
    if not quoted_tweet and tweet_data.get('raw_json'):
        # quoted_tweet is inside raw_json, not as a separate column!
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
        # Get quoted author info
        quoted_author_data = quoted_tweet.get('author') or {}
        quoted_author = f"@{quoted_author_data.get('userName', quoted_author_data.get('username', 'unknown'))}"
        quoted_text = quoted_tweet.get('text', '')[:300]
        if len(quoted_tweet.get('text', '')) > 300:
            quoted_text += '...'
    
    return USER_PROMPT_TEMPLATE.format(
        tweet_id=tweet_data.get('id', ''),
        author_username=tweet_data.get('author_username', ''),
        author_id=tweet_data.get('author_id', ''),
        author_followers=tweet_data.get('author_followers', 0),
        text=tweet_data.get('text', ''),
        created_at=created_at,
        lang=tweet_data.get('lang', ''),
        hashtags=', '.join(hashtags) if hashtags else 'None',
        urls=', '.join(urls) if urls else 'None',
        mentions=', '.join([f'@{m}' for m in mentions]) if mentions else 'None',
        like_count=tweet_data.get('like_count', 0),
        retweet_count=tweet_data.get('retweet_count', 0),
        view_count=tweet_data.get('view_count', 0),
        tweet_date=tweet_date,
        quoted_author=quoted_author,
        quoted_text=quoted_text
    )


# ============================================
# STAGE 3: MONITORING PROMPTS
# ============================================

def get_monitor_system_prompt() -> str:
    """Get monitor system prompt with current date (dynamic)."""
    return f"""You are a crypto project monitoring analyst.
Your task is to analyze recent tweets and website content to detect launch status changes.

{get_current_date_context()}

DATE VALIDATION:
- Compare any mentioned launch dates with TODAY's date above
- If a date like "December 9th" is mentioned and today is December 4th, the launch is IN THE FUTURE
- Only mark launch_status as "launched" if you have evidence it ALREADY happened
- Evidence of launch: CA posted, "now live", "trading", DEX links, etc.

You must detect:
1. LAUNCH STATUS - Has the project launched? Is it about to launch?
2. CONTRACT ADDRESS (CA) - Any blockchain address mentioned (0x... for EVM, base58 for Solana)
3. URGENCY - How soon is the launch?
4. SIGNIFICANT CHANGES - Bio updates, new announcements, etc.

URGENCY LEVELS:
- imminent: Launching today, tonight, in hours, in minutes, any moment now
- soon: Launching tomorrow, this week, in few days, very soon
- scheduled: Specific date mentioned (e.g., "Dec 15", "January 2026")
- unknown: No clear timeline

LAUNCH INDICATORS:
- "we are live", "now live", "officially live", "trading live"
- "launched", "has launched", "just launched"
- Contract address shared (CA:, contract:, 0x..., pump.fun link)
- DEX links (dexscreener, dextools, birdeye)
- "buy now", "trade now", "listed on"

CONTRACT ADDRESS FORMATS:
- EVM (Ethereum, Base, etc): 0x followed by 40 hex characters
- Solana: 32-44 base58 characters (no 0, O, I, l)
- Look for addresses near keywords like "CA:", "contract:", "token:"

Be thorough in detecting any blockchain address that could be a contract."""

# Legacy constant for backwards compatibility
MONITOR_SYSTEM_PROMPT = get_monitor_system_prompt()

MONITOR_USER_PROMPT_TEMPLATE = """Analyze the recent activity of @{twitter_handle} and determine current launch status.

=== PROJECT INFO ===
Project: {project_name}
Chain: {project_chain}
Previous Status: {previous_status}
Previous Priority: {previous_priority}
Last Check: {last_check}

=== CURRENT BIO ===
{current_bio}

=== PREVIOUS BIO ===
{previous_bio}

=== RECENT TWEETS ({tweet_count} tweets) ===
{tweets_text}

=== WEBSITE CONTENT ===
URL: {site_url}
{site_content}

=== ANALYSIS TASK ===
Analyze all content above and determine the current launch status.
Look for ANY contract address (CA) in tweets, bio, or website.
Detect urgency based on language used.

Respond with valid JSON only:

{{
  "launch_status": "not_launched" | "launching_soon" | "launched",
  "launch_urgency": "imminent" | "soon" | "scheduled" | "unknown",
  "launch_date_mentioned": string or null (exact text if date mentioned),
  "estimated_hours_until_launch": integer or null,
  
  "ca_detected": boolean,
  "ca_address": string or null,
  "ca_source": "tweet" | "bio" | "website" | null,
  "ca_context": string or null (text around where CA was found),
  
  "bio_changed": boolean,
  "bio_change_summary": string or null,
  
  "significant_updates": [
    string (list of important changes/announcements detected)
  ],
  
  "activity_level": "high" | "medium" | "low" | "inactive",
  "days_since_last_tweet": integer,
  
  "spam_indicators": boolean,
  "scam_indicators": boolean,
  
  "summary": string (brief 1-2 sentence status summary),
  "recommended_priority": "critical" | "high" | "medium" | "low"
}}"""


SITE_ANALYSIS_SYSTEM_PROMPT = f"""You are a crypto project website analyst.
Your task is to analyze website content and extract key information about the project.

{get_current_date_context()}

Look for:
1. Project documentation (whitepaper, litepaper, docs)
2. Tokenomics information (supply, distribution, vesting)
3. Roadmap or milestones
4. Team information
5. Security audits
6. Contract addresses
7. Social links
8. Red flags or scam indicators"""

SITE_ANALYSIS_USER_PROMPT_TEMPLATE = """Analyze this website content for project @{twitter_handle}:

=== WEBSITE URL ===
{site_url}

=== CONTENT ===
{site_content}

Respond with valid JSON only:

{{
  "site_accessible": true,
  "site_title": string or null,
  "site_description": string or null (brief description of what the site offers),
  
  "has_whitepaper": boolean,
  "whitepaper_url": string or null,
  
  "has_tokenomics": boolean,
  "tokenomics_summary": string or null (brief summary if found),
  
  "has_roadmap": boolean,
  "roadmap_summary": string or null,
  
  "has_team_info": boolean,
  "team_summary": string or null,
  
  "has_audit": boolean,
  "audit_provider": string or null (certik, hacken, etc),
  
  "contract_found": boolean,
  "contract_address": string or null,
  "contract_chain": string or null,
  
  "social_links": {{
    "twitter": string or null,
    "telegram": string or null,
    "discord": string or null,
    "github": string or null
  }},
  
  "red_flags": [
    string (list any suspicious elements)
  ],
  
  "legitimacy_score": float (0.0-1.0, how legitimate does the site appear),
  "site_quality": "professional" | "basic" | "template" | "suspicious",
  
  "analysis_summary": string (brief assessment of the site)
}}"""


def build_monitor_prompt(
    project: dict,
    tweets: list,
    current_bio: str,
    site_content: str = None
) -> str:
    """Build the monitoring analysis prompt."""
    
    # Format tweets
    tweets_text = ""
    for i, tweet in enumerate(tweets[:20], 1):
        text = tweet.get('text', '')[:300]
        date = tweet.get('createdAt', '')[:20]
        likes = tweet.get('likeCount', 0)
        tweets_text += f"\n[{i}] ({date}) (likes={likes}) {text}"
    
    if not tweets_text:
        tweets_text = "\n[No recent tweets]"
    
    # Format site content
    if site_content:
        site_content_formatted = site_content[:2000]
        if len(site_content) > 2000:
            site_content_formatted += "\n... [truncated]"
    else:
        site_content_formatted = "[No website content available]"
    
    return MONITOR_USER_PROMPT_TEMPLATE.format(
        twitter_handle=project.get('twitter_handle', ''),
        project_name=project.get('project_name', 'Unknown'),
        project_chain=project.get('project_chain', 'unknown'),
        previous_status=project.get('monitoring_status', 'active'),
        previous_priority=project.get('priority', 'low'),
        last_check=project.get('last_monitored_at', 'Never')[:16] if project.get('last_monitored_at') else 'Never',
        current_bio=current_bio or '[No bio]',
        previous_bio=project.get('bio', '[No previous bio]'),
        tweet_count=len(tweets),
        tweets_text=tweets_text,
        site_url=project.get('site_url') or project.get('website_url') or 'None',
        site_content=site_content_formatted
    )


def build_site_analysis_prompt(twitter_handle: str, site_url: str, site_content: str) -> str:
    """Build the website analysis prompt."""
    
    content_formatted = site_content[:3000] if site_content else "[No content]"
    if site_content and len(site_content) > 3000:
        content_formatted += "\n... [truncated]"
    
    return SITE_ANALYSIS_USER_PROMPT_TEMPLATE.format(
        twitter_handle=twitter_handle,
        site_url=site_url or 'Unknown',
        site_content=content_formatted
    )
