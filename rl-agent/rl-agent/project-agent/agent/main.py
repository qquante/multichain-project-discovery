# agent/main.py
import sys
sys.path.append('..')

import time
import json
from .analyzer import TweetAnalyzer
from .verifier import ProjectVerifier
from .monitor import ProjectMonitor
from .database import (
    init_db,
    get_triaged_projects,
    get_triage_stats,
    get_pending_tweets,
    get_pending_verifications,
    get_verified_projects,
    get_verification_stats,
    get_projects_to_monitor,
    get_monitoring_history,
    get_monitoring_stats,
    activate_monitoring_for_confirmed,
    get_fingerprints,
    get_project_journey,
    get_fingerprint_stats,
    MONITOR_INTERVALS
)

from config import ANALYSIS_BATCH_LIMIT, VERIFICATION_BATCH_LIMIT, MONITORING_BATCH_LIMIT


# STAGE 1: Tweet Analysis (Triage)

def run_analysis(limit: int = None, delay: float = 1.0, verbose: bool = True):
    """Stage 1: Run tweet analysis. Default limit from config."""
    init_db()
    limit = limit or ANALYSIS_BATCH_LIMIT
    analyzer = TweetAnalyzer(verbose=verbose)
    return analyzer.run(limit=limit, delay=delay)


def show_pending(limit: int = 10):
    """Show pending tweets to be analyzed."""
    init_db()
    pending = get_pending_tweets(limit=limit)
    
    print(f"\n[PENDING_TWEETS] count={len(pending)}")
    print("-" * 60)
    
    for i, t in enumerate(pending, 1):
        text = t.get('text', '')[:50].replace('\n', ' ')
        print(f"{i:2}. @{t.get('author_username', ''):<16} | {text}...")


def show_triaged(limit: int = 20):
    """Show triaged projects."""
    init_db()
    projects = get_triaged_projects(limit=limit)
    
    print(f"\n[TRIAGED] count={len(projects)}")
    print("-" * 60)
    
    for p in projects:
        print(f"  @{p['twitter_handle']:<16} | {p['project_name'] or 'Unknown':<15} | chain={p['project_chain']:<10} | type={p['project_type']:<8} | conf={p['confidence']:.2f}")


def show_triage_stats():
    """Show triage statistics."""
    init_db()
    stats = get_triage_stats()
    
    print(f"\n[TRIAGE STATS]")
    print("-" * 60)
    print(f"  Total tweets processed: {stats['total_processed']}")
    print(f"  Total projects found:   {stats['total_projects_found']}")
    print(f"  Total triaged:          {stats['total_triaged']}")
    print(f"  Pre-launch (no CA):     {stats['pre_launch_projects']}")
    print(f"\n  By chain:")
    for chain, count in stats['by_chain'].items():
        print(f"    {chain}: {count}")


# STAGE 2: Project Verification

def run_verification(limit: int = None, delay: float = 2.0, verbose: bool = True):
    """Stage 2: Run project verification on triaged projects. Default limit from config."""
    init_db()
    limit = limit or VERIFICATION_BATCH_LIMIT
    verifier = ProjectVerifier(verbose=verbose)
    return verifier.run(limit=limit, delay=delay)


def show_pending_verifications(limit: int = 10):
    """Show triaged projects pending verification."""
    init_db()
    pending = get_pending_verifications(limit=limit)
    
    print(f"\n[PENDING_VERIFICATION] count={len(pending)}")
    print("-" * 60)
    
    for i, p in enumerate(pending, 1):
        print(f"{i:2}. @{p['twitter_handle']:<16} | {p['project_name'] or 'Unknown':<15} | chain={p['project_chain']:<10} | triage_conf={p['confidence']:.2f}")


def show_verified(status: str = None, limit: int = 20):
    """Show verified projects. Status can be 'confirmed', 'rejected', 'pending', or None for all."""
    init_db()
    projects = get_verified_projects(status=status, limit=limit)
    
    status_label = status.upper() if status else "ALL"
    print(f"\n[VERIFIED - {status_label}] count={len(projects)}")
    print("-" * 60)
    
    for p in projects:
        status_icon = {
            'confirmed': 'OK',
            'rejected': 'NO',
            'pending': '??'
        }.get(p['verification_status'], '??')
        
        reason = p.get('rejection_reason', '') or ''
        reason_str = f" | reason={reason}" if reason else ""
        
        print(f"  [{status_icon}] @{p['twitter_handle']:<16} | {p['project_name'] or 'Unknown':<15} | chain={p['project_chain']:<10} | conf={p['verification_confidence']:.2f}{reason_str}")


def show_verification_stats():
    """Show verification statistics."""
    init_db()
    stats = get_verification_stats()
    
    print(f"\n[VERIFICATION STATS]")
    print("-" * 60)
    print(f"  Total triaged:          {stats['total_triaged']}")
    print(f"  Total verified:         {stats['total_verified']}")
    print(f"  Pending verification:   {stats['pending_verification']}")
    print(f"\n  Results:")
    print(f"    Confirmed: {stats['confirmed']}")
    print(f"    Rejected:  {stats['rejected']}")
    print(f"    Pending:   {stats['pending']}")
    
    if stats['by_rejection_reason']:
        print(f"\n  By rejection reason:")
        for reason, count in stats['by_rejection_reason'].items():
            print(f"    {reason}: {count}")
    
    if stats['confirmed_by_chain']:
        print(f"\n  Confirmed by chain:")
        for chain, count in stats['confirmed_by_chain'].items():
            print(f"    {chain}: {count}")


# STAGE 3: Project Monitoring

def run_monitoring(limit: int = None, verbose: bool = True):
    """Stage 3: Run monitoring cycle for confirmed projects. Default limit from config."""
    init_db()
    limit = limit or MONITORING_BATCH_LIMIT
    monitor = ProjectMonitor(verbose=verbose)
    return monitor.run_monitoring_cycle(limit=limit)


def show_monitoring_queue(limit: int = 20):
    """Show projects in monitoring queue."""
    init_db()
    projects = get_projects_to_monitor(limit=limit)
    
    print(f"\n[MONITORING_QUEUE] count={len(projects)}")
    print("-" * 60)
    
    for p in projects:
        last_check = p.get('last_monitored_at', 'Never')
        if last_check and last_check != 'Never':
            last_check = last_check[:16]
        
        print(f"  @{p['twitter_handle']:<16} | "
              f"priority={p.get('priority', 'low'):<8} | "
              f"urgency={p.get('launch_urgency', 'unknown'):<10} | "
              f"last_check={last_check}")


def show_monitoring_history(handle: str = None, limit: int = 10):
    """Show monitoring history."""
    init_db()
    history = get_monitoring_history(twitter_handle=handle, limit=limit)
    
    label = f"@{handle}" if handle else "ALL"
    print(f"\n[MONITORING_HISTORY - {label}] count={len(history)}")
    print("-" * 60)
    
    for h in history:
        changes = h.get('changes_detected', '[]')
        if isinstance(changes, str):
            try:
                import json
                changes = json.loads(changes)
            except:
                changes = []
        
        changes_str = ', '.join(changes) if changes else 'none'
        
        print(f"  @{h['twitter_handle']:<16} | "
              f"{h['monitored_at'][:16]} | "
              f"changes: {changes_str[:30]}")


def show_launched(limit: int = 20):
    """Show projects that have launched (CA detected)."""
    init_db()
    projects = get_verified_projects(status='confirmed', limit=100)
    
    launched = [p for p in projects if p.get('monitoring_status') == 'launched' or p.get('ca_address')]
    
    print(f"\n[LAUNCHED] count={len(launched)}")
    print("-" * 60)
    
    for p in launched[:limit]:
        ca = p.get('ca_address', '')[:20] + '...' if p.get('ca_address') else 'Unknown'
        print(f"  @{p['twitter_handle']:<16} | "
              f"{p.get('project_name', 'Unknown'):<15} | "
              f"chain={p.get('project_chain', 'unknown'):<10} | "
              f"CA={ca}")


def show_critical_projects(limit: int = 20):
    """Show projects with critical/high priority (imminent launches)."""
    init_db()
    projects = get_projects_to_monitor(limit=100)
    
    critical = [p for p in projects if p.get('priority') in ('critical', 'high')]
    
    print(f"\n[CRITICAL/HIGH PRIORITY] count={len(critical)}")
    print("-" * 60)
    
    for p in critical[:limit]:
        urgency = p.get('launch_urgency', 'unknown')
        date = p.get('launch_date_announced', '')
        
        print(f"  @{p['twitter_handle']:<16} | "
              f"priority={p.get('priority'):<8} | "
              f"urgency={urgency:<10} | "
              f"date={date or 'N/A'}")


def show_monitoring_stats_full():
    """Show detailed monitoring statistics."""
    init_db()
    stats = get_monitoring_stats()
    
    print(f"\n[MONITORING STATS]")
    print("-" * 60)
    
    print(f"\n  By monitoring status:")
    for status, count in stats.get('by_monitoring_status', {}).items():
        print(f"    {status}: {count}")
    
    print(f"\n  By priority:")
    for priority, count in stats.get('by_priority', {}).items():
        interval = MONITOR_INTERVALS.get(priority, 12)
        print(f"    {priority}: {count} (check every {interval}h)")
    
    print(f"\n  Totals:")
    print(f"    Total monitoring checks: {stats.get('total_monitoring_checks', 0)}")
    print(f"    CA detected: {stats.get('ca_detected_count', 0)}")
    print(f"    Launched: {stats.get('launched_count', 0)}")


# FINGERPRINTS: Decision Audit Trail

def show_project_journey(handle: str):
    """Show complete journey of a project through all stages."""
    init_db()
    journey = get_project_journey(handle)
    
    print(f"\n{'='*60}")
    print(f"[PROJECT JOURNEY] @{journey['twitter_handle']}")
    print(f"{'='*60}")
    print(f"Current Status: {journey['current_status']}")
    print(f"Total Fingerprints: {journey['total_fingerprints']}")
    
    # Stage 1
    s1 = journey['stage_1_triage']
    print(f"\n[STAGE 1 - TRIAGE]")
    print("-" * 40)
    if s1['fingerprints']:
        for fp in s1['fingerprints']:
            print(f"  Decision: {fp['decision']} | Confidence: {fp['confidence']:.2f}")
            print(f"  Reason: {fp['reason']}")
            if fp['key_factors']:
                factors = json.loads(fp['key_factors']) if isinstance(fp['key_factors'], str) else fp['key_factors']
                print(f"  Key Factors: {factors}")
            print(f"  LLM: {fp['llm_reasoning'][:100]}..." if fp['llm_reasoning'] else "")
    else:
        print("  No fingerprints")
    
    # Stage 2
    s2 = journey['stage_2_verification']
    print(f"\n[STAGE 2 - VERIFICATION]")
    print("-" * 40)
    if s2['fingerprints']:
        for fp in s2['fingerprints']:
            print(f"  Decision: {fp['decision']} | Confidence: {fp['confidence']:.2f}")
            print(f"  Reason: {fp['reason']}")
            if fp['key_factors']:
                factors = json.loads(fp['key_factors']) if isinstance(fp['key_factors'], str) else fp['key_factors']
                print(f"  Key Factors: {factors}")
            print(f"  LLM: {fp['llm_reasoning'][:100]}..." if fp['llm_reasoning'] else "")
    else:
        print("  No fingerprints")
    
    # Stage 3
    s3 = journey['stage_3_monitoring']
    print(f"\n[STAGE 3 - MONITORING]")
    print("-" * 40)
    if s3['fingerprints']:
        for fp in s3['fingerprints'][:5]:  # Last 5
            print(f"  [{fp['created_at'][:16]}] Decision: {fp['decision']}")
            print(f"  Reason: {fp['reason']}")
            if fp['llm_reasoning']:
                print(f"  Summary: {fp['llm_reasoning'][:80]}...")
    else:
        print("  No fingerprints")
    
    return journey


def show_fingerprints(handle: str = None, stage: int = None, decision: str = None, limit: int = 10):
    """Show fingerprints with optional filters."""
    init_db()
    fps = get_fingerprints(twitter_handle=handle, stage=stage, decision=decision, limit=limit)
    
    filters = []
    if handle:
        filters.append(f"handle=@{handle}")
    if stage:
        filters.append(f"stage={stage}")
    if decision:
        filters.append(f"decision={decision}")
    filter_str = ", ".join(filters) if filters else "all"
    
    print(f"\n[FINGERPRINTS] filter={filter_str} | count={len(fps)}")
    print("-" * 60)
    
    for fp in fps:
        stage_name = {1: "TRIAGE", 2: "VERIFY", 3: "MONITOR"}.get(fp['stage'], "?")
        print(f"\n  @{fp['twitter_handle']:<16} | Stage {fp['stage']} ({stage_name})")
        print(f"  Decision: {fp['decision']} | Confidence: {fp['confidence']:.2f}")
        print(f"  Reason: {fp['reason']}")
        print(f"  Time: {fp['created_at'][:19]}")
        if fp['llm_reasoning']:
            print(f"  LLM: {fp['llm_reasoning'][:80]}...")


def show_fingerprint_stats():
    """Show fingerprint statistics."""
    init_db()
    stats = get_fingerprint_stats()
    
    print(f"\n[FINGERPRINT STATS]")
    print("-" * 60)
    print(f"  Total Fingerprints: {stats['total_fingerprints']}")
    print(f"  Unique Projects: {stats['unique_projects']}")
    
    print(f"\n  By Stage:")
    for stage, count in stats['by_stage'].items():
        print(f"    {stage}: {count}")
    
    print(f"\n  By Decision:")
    for decision, count in stats['by_decision'].items():
        print(f"    {decision}: {count}")
    
    print(f"\n  By Stage+Decision:")
    for key, count in stats['by_stage_decision'].items():
        print(f"    {key}: {count}")


def show_rejected_analysis(stage: int = 1, limit: int = 10):
    """Show analysis of rejected projects to understand AI decisions."""
    init_db()
    fps = get_fingerprints(stage=stage, decision="rejected", limit=limit)
    
    print(f"\n[REJECTED ANALYSIS - Stage {stage}] count={len(fps)}")
    print("-" * 60)
    
    for fp in fps:
        print(f"\n  @{fp['twitter_handle']}")
        print(f"  Reason: {fp['reason']}")
        print(f"  Confidence: {fp['confidence']:.2f}")
        if fp['input_tweet_text']:
            print(f"  Tweet: {fp['input_tweet_text'][:100]}...")
        if fp['llm_reasoning']:
            print(f"  LLM Analysis: {fp['llm_reasoning'][:150]}...")
        if fp['key_factors']:
            factors = json.loads(fp['key_factors']) if isinstance(fp['key_factors'], str) else fp['key_factors']
            print(f"  Factors: {factors}")


# Combined Stats

def show_stats():
    """Show all statistics."""
    show_triage_stats()
    show_verification_stats()
    show_monitoring_stats_full()
    show_fingerprint_stats()


if __name__ == "__main__":
    start = time.time()
    
    print("[INFO] Agent module ready")
    print("\n[STAGE 1 - TRIAGE]")
    print("  run_analysis(limit=10, delay=1.0)")
    print("  show_pending(limit=10)")
    print("  show_triaged(limit=20)")
    print("  show_triage_stats()")
    
    print("\n[STAGE 2 - VERIFICATION]")
    print("  run_verification(limit=10, delay=2.0)")
    print("  show_pending_verifications(limit=10)")
    print("  show_verified(status='confirmed')")
    print("  show_verified(status='rejected')")
    print("  show_verification_stats()")
    
    print("\n[STAGE 3 - MONITORING]")
    print("  run_monitoring(limit=50)")
    print("  show_monitoring_queue(limit=20)")
    print("  show_monitoring_history(handle='username')")
    print("  show_launched(limit=20)")
    print("  show_critical_projects(limit=20)")
    print("  show_monitoring_stats_full()")
    
    print("\n[FINGERPRINTS - AUDIT TRAIL]")
    print("  show_project_journey(handle='@username')")
    print("  show_fingerprints(handle='@username')")
    print("  show_fingerprints(stage=1, decision='rejected')")
    print("  show_rejected_analysis(stage=1)")
    print("  show_fingerprint_stats()")
    
    print("\n[COMBINED]")
    print("  show_stats()")
    
    print("\n[MONITORING INTERVALS]")
    for priority, hours in MONITOR_INTERVALS.items():
        print(f"  {priority}: every {hours}h")
    
    # Show current state
    show_pending(5)
    show_stats()
    
    print(f"\n[TOTAL_TIME] {time.time() - start:.2f}s")

