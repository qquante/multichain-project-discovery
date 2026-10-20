# agent/project_scorer.py
"""
Project Scoring Module - Uses ALL 137 parameters to score projects.
Integrates with verifier to provide quality scores and red flag detection.
"""

from typing import Dict, Any, List, Tuple
from datetime import datetime


# RED FLAG THRESHOLDS

RED_FLAGS = {
    # Tweet Analysis
    "emoji_abuse_ratio": 0.3,       # 30%+ tweets have 3+ emojis
    "hashtag_abuse_avg": 5.0,       # Average 5+ hashtags per tweet
    "has_presale_mentions": True,   # Any presale mention = instant red flag
    "has_giveaway_mentions": True,  # Any giveaway mention = instant red flag
    
    # Profile 
    "rename_count": 2,              # 2+ renames = suspicious (MAX 2)
    "is_automated": True,           # Bot accounts
    "is_protected": True,           # Protected accounts
    
    # Contract suspicion
    "ca_count": 2,                  # 2+ CAs = suspicious (MAX 2)
    "deleted_tweets_ratio": 0.2,    # 20%+ deleted tweets
    
    # Low engagement
    "avg_engagement_rate": 0.001,   # Less than 0.1% = fake followers
}

# POSITIVE SIGNALS

POSITIVE_SIGNALS = {
    # Verification
    "is_blue_verified": 3,          # +3 points
    "verified_score": {1: 1, 2: 3, 3: 5},  # Business gets more
    
    # Alpha quality
    "alpha_hunters_count": {5: 2, 10: 5, 20: 8},  # Points by count
    "hunters_with_60plus_wr": {2: 3, 5: 6, 10: 10},
    "best_hunter_winrate": {60: 2, 70: 4, 80: 6},
    
    # Key followers (pelo menos 1 = bom sinal)
    "key_followers_count": {1: 3, 3: 5, 10: 8, 20: 10},
    "max_key_follower_reach": {10000: 2, 50000: 4, 100000: 6},
    
    # Profile quality
    "good_words_count": {3: 2, 5: 4, 10: 6},
    "has_website": 2,
    "has_telegram": 1,
    "has_discord": 1,
    
    # Content quality
    "original_ratio": {0.5: 1, 0.7: 2, 0.9: 4},  # High original content
    "account_age_days": {30: 1, 90: 2, 365: 4},
    
    # Growth
    "followers_growth_daily_avg": {10: 1, 50: 2, 100: 4},
}


def calculate_red_flags(data: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    Check for red flags in project data.
    Returns: (red_flag_count, list of flags triggered)
    """
    flags = []
    
    # Emoji abuse
    if data.get("emoji_abuse_ratio", 0) >= RED_FLAGS["emoji_abuse_ratio"]:
        flags.append(f"abuso_emojis ({data.get('emoji_abuse_ratio', 0):.1%})")
    
    # Hashtag abuse
    if data.get("hashtag_abuse_avg", 0) >= RED_FLAGS["hashtag_abuse_avg"]:
        flags.append(f"abuso_hashtags ({data.get('hashtag_abuse_avg', 0):.1f}/tweet)")
    
    # Presale mentions
    if data.get("has_presale_mentions"):
        flags.append("mencoes_presale")
    
    # Giveaway mentions
    if data.get("has_giveaway_mentions"):
        flags.append("mencoes_giveaway")
    
    # Too many renames
    rename_count = data.get("rename_count", 0)
    if rename_count >= RED_FLAGS["rename_count"]:
        flags.append(f"muitos_renames ({rename_count})")
    
    # Bot account
    if data.get("is_automated"):
        flags.append("conta_automatizada")
    
    # Protected account
    if data.get("is_protected"):
        flags.append("conta_protegida")
    
    # Multiple CAs
    ca_count = data.get("ca_count", 0)
    if ca_count >= RED_FLAGS["ca_count"]:
        flags.append(f"varios_cas ({ca_count})")
    
    # Deleted tweets
    deleted_ratio = data.get("deleted_tweets_ratio", 0)
    if deleted_ratio >= RED_FLAGS["deleted_tweets_ratio"]:
        flags.append(f"tweets_deletados ({deleted_ratio:.1%})")
    
    # Very low engagement (fake followers)
    engagement = data.get("avg_engagement_rate", 0)
    if engagement > 0 and engagement < RED_FLAGS["avg_engagement_rate"]:
        flags.append(f"engajamento_baixo ({engagement:.4%})")
    
    return len(flags), flags


def calculate_positive_score(data: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    Calculate positive signals score.
    Returns: (score, list of signals contributing)
    """
    score = 0
    signals = []
    
    # Blue verified
    if data.get("is_blue_verified"):
        score += POSITIVE_SIGNALS["is_blue_verified"]
        signals.append("verificado_azul (+3)")
    
    # Verified score
    vs = data.get("verified_score", 0)
    if vs >= 3:
        score += 5
        signals.append("verificado_gov (+5)")
    elif vs >= 2:
        score += 3
        signals.append("verificado_empresa (+3)")
    elif vs >= 1:
        score += 1
        signals.append("verificado (+1)")
    
    # Alpha hunters
    hunters = data.get("alpha_hunters_count", 0)
    if hunters >= 20:
        score += 8
        signals.append(f"caçadores_20+ (+8)")
    elif hunters >= 10:
        score += 5
        signals.append(f"caçadores_10+ (+5)")
    elif hunters >= 5:
        score += 2
        signals.append(f"caçadores_5+ (+2)")
    
    # High winrate hunters
    wr_hunters = data.get("hunters_with_60plus_wr", 0)
    if wr_hunters >= 10:
        score += 10
        signals.append(f"caçadores_qualidade_10+ (+10)")
    elif wr_hunters >= 5:
        score += 6
        signals.append(f"caçadores_qualidade_5+ (+6)")
    elif wr_hunters >= 2:
        score += 3
        signals.append(f"caçadores_qualidade_2+ (+3)")
    
    # Best hunter winrate
    best_wr = data.get("best_hunter_winrate", 0)
    if best_wr >= 80:
        score += 6
        signals.append(f"melhor_wr_80%+ (+6)")
    elif best_wr >= 70:
        score += 4
        signals.append(f"melhor_wr_70%+ (+4)")
    elif best_wr >= 60:
        score += 2
        signals.append(f"melhor_wr_60%+ (+2)")
    
    # Key followers
    kf = data.get("key_followers_count", 0)
    if kf >= 20:
        score += 10
        signals.append(f"seguidores_chave_20+ (+10)")
    elif kf >= 10:
        score += 8
        signals.append(f"seguidores_chave_10+ (+8)")
    elif kf >= 3:
        score += 5
        signals.append(f"seguidores_chave_3+ (+5)")
    elif kf >= 1:
        score += 3
        signals.append(f"tem_seguidor_chave (+3)")
    
    # Key follower reach
    reach = data.get("max_key_follower_reach", 0)
    if reach >= 100000:
        score += 6
        signals.append(f"alcance_100k+ (+6)")
    elif reach >= 50000:
        score += 4
        signals.append(f"alcance_50k+ (+4)")
    elif reach >= 10000:
        score += 2
        signals.append(f"alcance_10k+ (+2)")
    
    # Good words
    gw = data.get("good_words_count", 0)
    if gw >= 10:
        score += 6
        signals.append(f"palavras_boas_10+ (+6)")
    elif gw >= 5:
        score += 4
        signals.append(f"palavras_boas_5+ (+4)")
    elif gw >= 3:
        score += 2
        signals.append(f"palavras_boas_3+ (+2)")
    
    # Socials
    if data.get("has_website"):
        score += 2
        signals.append("tem_website (+2)")
    if data.get("has_telegram"):
        score += 1
        signals.append("tem_telegram (+1)")
    if data.get("has_discord"):
        score += 1
        signals.append("tem_discord (+1)")
    
    # Original content
    orig = data.get("original_ratio", 0)
    if orig >= 0.9:
        score += 4
        signals.append(f"conteudo_muito_original (+4)")
    elif orig >= 0.7:
        score += 2
        signals.append(f"conteudo_original (+2)")
    elif orig >= 0.5:
        score += 1
        signals.append(f"conteudo_razoavel (+1)")
    
    # Account age
    age = data.get("account_age_days", 0)
    if age >= 365:
        score += 4
        signals.append(f"conta_1ano+ (+4)")
    elif age >= 90:
        score += 2
        signals.append(f"conta_3meses+ (+2)")
    elif age >= 30:
        score += 1
        signals.append(f"conta_1mes+ (+1)")
    
    # Follower growth
    growth = data.get("followers_growth_daily_avg", 0)
    if growth >= 100:
        score += 4
        signals.append(f"crescimento_alto (+4)")
    elif growth >= 50:
        score += 2
        signals.append(f"crescimento_bom (+2)")
    elif growth >= 10:
        score += 1
        signals.append(f"algum_crescimento (+1)")
    
    return score, signals


def calculate_tier(data: Dict[str, Any], score: int, red_flags: List[str]) -> Dict[str, Any]:
    """
    Calculate project tier based on quality signals.
    
    Tier A (🟢 Alta Confiança):
      - key_followers >= 3
      - alpha_hunters >= 1
      - score >= 50
      - No critical red flags
    
    Tier B (🟡 Média Confiança):
      - key_followers >= 1 OR found_in_alphagate
      - score >= 30
      - Few red flags (<=2)
    
    Tier C (🟠 Baixa Confiança):
      - score >= 15
      - Passed LLM verification
      - Save but flag for review
    """
    key_followers = data.get('key_followers_count', 0)
    alpha_hunters = data.get('alpha_hunters_count', 0)
    found_in_alphagate = data.get('found_in_alphagate', False)
    
    # Critical red flags count
    critical_flags = 0
    for flag in red_flags:
        if 'presale' in flag.lower() or 'giveaway' in flag.lower() or 'automated' in flag.lower():
            critical_flags += 1
    
    tier = 'C'
    tier_emoji = '🟠'
    tier_label = 'Baixa Confiança'
    tier_confidence = 'low'
    
    if (key_followers >= 3 and alpha_hunters >= 1 and 
        score >= 50 and critical_flags == 0):
        tier = 'A'
        tier_emoji = '🟢'
        tier_label = 'Alta Confiança'
        tier_confidence = 'high'
    elif ((key_followers >= 1 or found_in_alphagate) and 
          score >= 30 and len(red_flags) <= 2):
        tier = 'B'
        tier_emoji = '🟡'
        tier_label = 'Média Confiança'
        tier_confidence = 'medium'
    
    return {
        'tier': tier,
        'tier_emoji': tier_emoji,
        'tier_label': tier_label,
        'tier_confidence': tier_confidence
    }


def calculate_final_score(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate final project score combining positive signals and red flags.
    
    Returns:
        {
            'final_score': int (0-100),
            'grade': str ('A', 'B', 'C', 'D', 'F'),
            'positive_score': int,
            'positive_signals': list,
            'red_flag_count': int,
            'red_flags': list,
            'recommendation': str ('APPROVED', 'REVIEW', 'REJECTED'),
            'tier': str ('A', 'B', 'C'),
            'tier_emoji': str,
            'tier_label': str,
            'tier_confidence': str
        }
    """
    # Calculate positive score
    positive_score, positive_signals = calculate_positive_score(data)
    
    # Calculate red flags
    red_flag_count, red_flags = calculate_red_flags(data)
    
    # Base score: positive points
    raw_score = positive_score
    
    # Apply red flag penalties
    # Critical flags get -5 penalty each (instead of auto-reject)
    critical_penalty = 0
    for flag in red_flags:
        if 'presale_mentions' in flag:
            critical_penalty += 5
        elif 'giveaway_mentions' in flag:
            critical_penalty += 5
        elif 'automated_account' in flag:
            critical_penalty += 5
    
    # Other red flags get -10 each
    non_critical_count = red_flag_count - (critical_penalty // 5)
    other_penalty = non_critical_count * 10
    
    total_penalty = critical_penalty + other_penalty
    raw_score = max(0, raw_score - total_penalty)
    
    # Normalize to 0-100
    # Max positive score is approximately 60
    final_score = min(100, int((raw_score / 60) * 100))
    
    # Determine grade
    if final_score >= 80:
        grade = 'A'
    elif final_score >= 60:
        grade = 'B'
    elif final_score >= 40:
        grade = 'C'
    elif final_score >= 20:
        grade = 'D'
    else:
        grade = 'F'
    
    # Determine recommendation based on SCORE (REDUCED THRESHOLDS)
    # - REJECTED: Score < 15 (was 20)
    # - REVIEW: Score 15-40 (was 20-50)
    # - APPROVED: Score > 40 (was 50)
    
    if final_score < 15:
        recommendation = 'REJECTED'
    elif red_flag_count > 0 or final_score < 40:
        recommendation = 'REVIEW'
    else:
        recommendation = 'APPROVED'
    
    # Calculate tier
    tier_result = calculate_tier(data, final_score, red_flags)
    
    return {
        'final_score': final_score,
        'grade': grade,
        'positive_score': positive_score,
        'positive_signals': positive_signals,
        'red_flag_count': red_flag_count,
        'red_flags': red_flags,
        'recommendation': recommendation,
        # Tier data
        'tier': tier_result['tier'],
        'tier_emoji': tier_result['tier_emoji'],
        'tier_label': tier_result['tier_label'],
        'tier_confidence': tier_result['tier_confidence']
    }



def enrich_with_score(
    alphagate_data: Dict[str, Any],
    twitter_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Combine AlphaGate and Twitter data and calculate score.
    
    This is the main function to call from the verifier.
    """
    # Merge data
    combined = {}
    combined.update(alphagate_data or {})
    combined.update(twitter_data or {})
    
    # Calculate account age
    created_at = combined.get("created_at")
    if created_at:
        try:
            if isinstance(created_at, str):
                created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            else:
                created = created_at
            combined["account_age_days"] = (datetime.now(created.tzinfo) - created).days
        except:
            pass
    
    # Calculate score
    score_result = calculate_final_score(combined)
    
    return {
        **combined,
        **score_result
    }


def format_score_for_telegram(score_data: Dict[str, Any]) -> str:
    """Format score data as HTML for Telegram message."""
    grade = score_data.get('grade', '?')
    score = score_data.get('final_score', 0)
    recommendation = score_data.get('recommendation', 'UNKNOWN')
    
    # Grade emoji
    grade_emoji = {
        'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🟠', 'F': '🔴'
    }.get(grade, '⚪')
    
    # Recommendation emoji
    rec_emoji = {
        'APPROVED': '✅', 'REVIEW': '⚠️', 'REJECTED': '❌'
    }.get(recommendation, '❓')
    
    lines = [
        f"<b>📊 ML Score:</b> {grade_emoji} {score}/100 (Grade {grade})",
        f"<b>Recommendation:</b> {rec_emoji} {recommendation}"
    ]
    
    # Add red flags if any
    red_flags = score_data.get('red_flags', [])
    if red_flags:
        lines.append(f"<b>🚨 Red Flags:</b> {', '.join(red_flags)}")
    
    # Add top positive signals
    signals = score_data.get('positive_signals', [])[:5]
    if signals:
        lines.append(f"<b>✨ Signals:</b> {', '.join(signals)}")
    
    return "\n".join(lines)
