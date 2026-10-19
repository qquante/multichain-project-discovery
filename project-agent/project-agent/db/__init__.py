# db/__init__.py
"""
Database module - Dual-write support for SQLite (local) and Supabase (cloud).
"""

from .supabase_client import (
    SupabaseClient,
    get_supabase_client,
    sync_to_supabase,
    batch_sync_to_supabase,
    sync_tweet,
    sync_processed_tweet,
    sync_triaged_project,
    sync_verified_project,
    sync_monitoring_history,
    sync_fingerprint,
    sync_mention,
    sync_collection_history,
    sync_keyword_batch,
    SUPABASE_ENABLED
)

__all__ = [
    'SupabaseClient',
    'get_supabase_client',
    'sync_to_supabase',
    'batch_sync_to_supabase',
    'sync_tweet',
    'sync_processed_tweet',
    'sync_triaged_project',
    'sync_verified_project',
    'sync_monitoring_history',
    'sync_fingerprint',
    'sync_mention',
    'sync_collection_history',
    'sync_keyword_batch',
    'SUPABASE_ENABLED'
]

