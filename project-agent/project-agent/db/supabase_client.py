# db/supabase_client.py
"""
Supabase Client for Dual-Write Operations
Mirrors all data to Supabase PostgreSQL alongside local SQLite.
"""

import os
import json
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime

# Supabase Configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://dfslhabqmerrheijrlfm.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '[REMOVED_CREDENTIAL]')

# Enable/disable Supabase sync
SUPABASE_ENABLED = os.environ.get('SUPABASE_ENABLED', 'true').lower() == 'true'


class SupabaseClient:
    """Client for Supabase REST API operations."""
    
    def __init__(self, verbose: bool = False):
        self.url = SUPABASE_URL
        self.key = SUPABASE_KEY
        self.verbose = verbose
        self.enabled = SUPABASE_ENABLED and bool(SUPABASE_KEY)
        
        if self.verbose:
            status = "ENABLED" if self.enabled else "DISABLED"
            print(f"[SUPABASE] {status} | URL: {self.url[:50]}...")
    
    def _log(self, msg: str):
        if self.verbose:
            print(f"[SUPABASE] {msg}")
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    
    def _convert_for_postgres(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert data types for PostgreSQL compatibility."""
        converted = {}
        
        for key, value in data.items():
            if value is None:
                converted[key] = None
            elif isinstance(value, bool):
                converted[key] = value
            elif isinstance(value, (list, dict)):
                # JSON fields - keep as is for JSONB
                converted[key] = value
            elif isinstance(value, str):
                converted[key] = value
            elif isinstance(value, (int, float)):
                converted[key] = value
            else:
                converted[key] = str(value)
        
        return converted
    
    def insert(self, table: str, data: Dict[str, Any], upsert: bool = False) -> Dict[str, Any]:
        """Insert a record into a table."""
        if not self.enabled:
            return {"status": "disabled"}
        
        url = f"{self.url}/rest/v1/{table}"
        headers = self._get_headers()
        
        if upsert:
            headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        
        # Convert data for PostgreSQL
        pg_data = self._convert_for_postgres(data)
        
        try:
            response = requests.post(
                url,
                headers=headers,
                json=pg_data,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                self._log(f"[INSERT] {table} | OK")
                return {"status": "ok", "data": response.json()}
            elif response.status_code == 409:
                # Conflict - record exists
                self._log(f"[INSERT] {table} | exists (conflict)")
                return {"status": "exists"}
            else:
                self._log(f"[INSERT] {table} | ERROR {response.status_code}: {response.text[:100]}")
                return {"status": "error", "code": response.status_code, "message": response.text[:200]}
                
        except Exception as e:
            self._log(f"[INSERT] {table} | EXCEPTION: {str(e)[:50]}")
            return {"status": "error", "message": str(e)}
    
    def upsert(self, table: str, data: Dict[str, Any], on_conflict: str = None) -> Dict[str, Any]:
        """Upsert (insert or update) a record."""
        if not self.enabled:
            return {"status": "disabled"}
        
        url = f"{self.url}/rest/v1/{table}"
        headers = self._get_headers()
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        
        # Convert data for PostgreSQL
        pg_data = self._convert_for_postgres(data)
        
        try:
            response = requests.post(
                url,
                headers=headers,
                json=pg_data,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                self._log(f"[UPSERT] {table} | OK")
                return {"status": "ok", "data": response.json()}
            else:
                self._log(f"[UPSERT] {table} | ERROR {response.status_code}")
                return {"status": "error", "code": response.status_code, "message": response.text[:200]}
                
        except Exception as e:
            self._log(f"[UPSERT] {table} | EXCEPTION: {str(e)[:50]}")
            return {"status": "error", "message": str(e)}
    
    def update(self, table: str, data: Dict[str, Any], filters: Dict[str, Any]) -> Dict[str, Any]:
        """Update records matching filters."""
        if not self.enabled:
            return {"status": "disabled"}
        
        # Build filter query string
        filter_parts = []
        for key, value in filters.items():
            filter_parts.append(f"{key}=eq.{value}")
        
        filter_string = "&".join(filter_parts)
        url = f"{self.url}/rest/v1/{table}?{filter_string}"
        
        headers = self._get_headers()
        pg_data = self._convert_for_postgres(data)
        
        try:
            response = requests.patch(
                url,
                headers=headers,
                json=pg_data,
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                self._log(f"[UPDATE] {table} | OK")
                return {"status": "ok"}
            else:
                self._log(f"[UPDATE] {table} | ERROR {response.status_code}")
                return {"status": "error", "code": response.status_code, "message": response.text[:200]}
                
        except Exception as e:
            self._log(f"[UPDATE] {table} | EXCEPTION: {str(e)[:50]}")
            return {"status": "error", "message": str(e)}
    
    def select(self, table: str, columns: str = "*", filters: Dict[str, Any] = None, limit: int = 100) -> Dict[str, Any]:
        """Select records from a table."""
        if not self.enabled:
            return {"status": "disabled", "data": []}
        
        url = f"{self.url}/rest/v1/{table}?select={columns}&limit={limit}"
        
        if filters:
            for key, value in filters.items():
                url += f"&{key}=eq.{value}"
        
        headers = self._get_headers()
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return {"status": "ok", "data": response.json()}
            else:
                return {"status": "error", "code": response.status_code, "data": []}
                
        except Exception as e:
            return {"status": "error", "message": str(e), "data": []}
    
    def delete(self, table: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Delete records matching filters."""
        if not self.enabled:
            return {"status": "disabled"}
        
        filter_parts = []
        for key, value in filters.items():
            filter_parts.append(f"{key}=eq.{value}")
        
        filter_string = "&".join(filter_parts)
        url = f"{self.url}/rest/v1/{table}?{filter_string}"
        
        headers = self._get_headers()
        
        try:
            response = requests.delete(url, headers=headers, timeout=10)
            
            if response.status_code in [200, 204]:
                return {"status": "ok"}
            else:
                return {"status": "error", "code": response.status_code}
                
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def test_connection(self) -> bool:
        """Test if Supabase connection works."""
        if not self.enabled:
            return False
        
        url = f"{self.url}/rest/v1/"
        headers = self._get_headers()
        
        try:
            response = requests.get(url, headers=headers, timeout=5)
            return response.status_code == 200
        except:
            return False


# Global client instance
_supabase_client: Optional[SupabaseClient] = None


def get_supabase_client(verbose: bool = False) -> SupabaseClient:
    """Get or create Supabase client singleton."""
    global _supabase_client
    
    if _supabase_client is None:
        _supabase_client = SupabaseClient(verbose=verbose)
    
    return _supabase_client


# ============================================
# DUAL-WRITE HELPER FUNCTIONS
# ============================================

def sync_to_supabase(table: str, data: Dict[str, Any], upsert: bool = True) -> bool:
    """
    Sync a record to Supabase.
    Call this AFTER saving to SQLite.
    
    Args:
        table: Table name
        data: Record data
        upsert: If True, use upsert (insert or update)
    
    Returns:
        True if successful or Supabase disabled, False on error
    """
    client = get_supabase_client()
    
    if not client.enabled:
        return True  # Consider success if disabled
    
    if upsert:
        result = client.upsert(table, data)
    else:
        result = client.insert(table, data)
    
    return result.get("status") in ["ok", "exists", "disabled"]


def batch_sync_to_supabase(table: str, records: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Sync multiple records to Supabase.
    
    Args:
        table: Table name
        records: List of record data
    
    Returns:
        Dict with success/failure counts
    """
    client = get_supabase_client()
    
    if not client.enabled:
        return {"success": len(records), "failed": 0, "status": "disabled"}
    
    success = 0
    failed = 0
    
    for record in records:
        result = client.upsert(table, record)
        if result.get("status") in ["ok", "exists"]:
            success += 1
        else:
            failed += 1
    
    return {"success": success, "failed": failed}


# ============================================
# TABLE-SPECIFIC SYNC FUNCTIONS
# ============================================

def sync_tweet(tweet_data: Dict[str, Any]) -> bool:
    """Sync a tweet to Supabase tweets table."""
    return sync_to_supabase("tweets", tweet_data, upsert=True)


def sync_processed_tweet(data: Dict[str, Any]) -> bool:
    """Sync processed tweet to Supabase."""
    return sync_to_supabase("processed_tweets", data, upsert=True)


def sync_triaged_project(data: Dict[str, Any]) -> bool:
    """Sync triaged project to Supabase."""
    return sync_to_supabase("triaged_projects", data, upsert=True)


def sync_verified_project(data: Dict[str, Any]) -> bool:
    """Sync verified project to Supabase."""
    return sync_to_supabase("verified_projects", data, upsert=True)


def sync_monitoring_history(data: Dict[str, Any]) -> bool:
    """Sync monitoring history to Supabase."""
    return sync_to_supabase("monitoring_history", data, upsert=False)  # History is insert-only


def sync_fingerprint(data: Dict[str, Any]) -> bool:
    """Sync decision fingerprint to Supabase."""
    return sync_to_supabase("decision_fingerprints", data, upsert=False)  # Insert-only


def sync_mention(data: Dict[str, Any]) -> bool:
    """Sync mention to Supabase."""
    return sync_to_supabase("mentions", data, upsert=True)


def sync_collection_history(data: Dict[str, Any]) -> bool:
    """Sync collection history to Supabase."""
    return sync_to_supabase("collection_history", data, upsert=False)


def sync_keyword_batch(data: Dict[str, Any]) -> bool:
    """Sync keyword batch config to Supabase."""
    return sync_to_supabase("keyword_batches", data, upsert=True)


# ============================================
# TESTING
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("SUPABASE CLIENT TEST")
    print("=" * 60)
    
    client = SupabaseClient(verbose=True)
    
    print(f"\nEnabled: {client.enabled}")
    print(f"URL: {client.url}")
    
    # Test connection
    if client.test_connection():
        print("\n[OK] Connection successful!")
        
        # Test insert
        test_data = {
            "tweet_id": "test_123",
            "processed_at": datetime.now().isoformat(),
            "is_project": False,
            "confidence": 0.5,
            "rejection_reason": "test"
        }
        
        result = client.upsert("processed_tweets", test_data)
        print(f"[UPSERT TEST] Result: {result}")
        
    else:
        print("\n[ERROR] Connection failed!")

