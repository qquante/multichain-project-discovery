# test_db.py - Database analysis
import sqlite3
import json
import os
from typing import Dict, List, Any

def analyze_database(db_path: str) -> Dict[str, Any]:
    """Analyze a SQLite database and return statistics."""
    
    if not os.path.exists(db_path):
        return {"error": f"Database not found: {db_path}"}
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    result = {
        "db_path": db_path,
        "db_size_kb": os.path.getsize(db_path) / 1024,
        "tables": {}
    }
    
    # Get all tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    
    for table in tables:
        table_info = {"columns": {}, "row_count": 0, "issues": []}
        
        # Get row count
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        table_info["row_count"] = cur.fetchone()[0]
        
        if table_info["row_count"] == 0:
            table_info["issues"].append("Table is empty")
            result["tables"][table] = table_info
            continue
        
        # Get column info
        cur.execute(f"PRAGMA table_info({table})")
        columns = cur.fetchall()
        
        for col in columns:
            col_name = col[1]
            col_type = col[2]
            col_notnull = col[3]
            col_default = col[4]
            
            col_info = {
                "type": col_type,
                "notnull": bool(col_notnull),
                "default": col_default,
                "null_count": 0,
                "empty_count": 0,
                "sample_values": [],
                "min": None,
                "max": None
            }
            
            # Count NULLs
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE [{col_name}] IS NULL")
            col_info["null_count"] = cur.fetchone()[0]
            
            # Count empty strings
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE [{col_name}] = ''")
            col_info["empty_count"] = cur.fetchone()[0]
            
            # Get sample values (non-null, non-empty)
            cur.execute(f"SELECT DISTINCT [{col_name}] FROM {table} WHERE [{col_name}] IS NOT NULL AND [{col_name}] != '' LIMIT 3")
            samples = [row[0] for row in cur.fetchall()]
            col_info["sample_values"] = [str(s)[:50] if s else None for s in samples]
            
            # Get min/max for numeric columns
            if col_type in ("INTEGER", "REAL", "NUMERIC"):
                cur.execute(f"SELECT MIN([{col_name}]), MAX([{col_name}]) FROM {table} WHERE [{col_name}] IS NOT NULL")
                row = cur.fetchone()
                col_info["min"] = row[0]
                col_info["max"] = row[1]
            
            # Check for issues
            null_pct = (col_info["null_count"] / table_info["row_count"]) * 100 if table_info["row_count"] > 0 else 0
            if null_pct == 100:
                table_info["issues"].append(f"Column [{col_name}] is 100% NULL")
            elif null_pct > 50:
                table_info["issues"].append(f"Column [{col_name}] is {null_pct:.1f}% NULL")
            
            table_info["columns"][col_name] = col_info
        
        result["tables"][table] = table_info
    
    conn.close()
    return result


def print_analysis(analysis: Dict[str, Any]):
    """Print analysis in readable format."""
    
    print(f"\n{'='*70}")
    print(f"[DB] {analysis['db_path']} ({analysis['db_size_kb']:.1f} KB)")
    print(f"{'='*70}")
    
    for table_name, table_info in analysis["tables"].items():
        print(f"\n[TABLE] {table_name} ({table_info['row_count']} rows)")
        print("-" * 70)
        
        if table_info["issues"]:
            print("[ISSUES]")
            for issue in table_info["issues"]:
                print(f"  - {issue}")
        
        # Group columns by status
        ok_cols = []
        warn_cols = []
        
        for col_name, col_info in table_info["columns"].items():
            null_pct = (col_info["null_count"] / table_info["row_count"]) * 100 if table_info["row_count"] > 0 else 0
            
            if null_pct == 100:
                warn_cols.append((col_name, col_info, null_pct))
            elif null_pct > 0:
                warn_cols.append((col_name, col_info, null_pct))
            else:
                ok_cols.append((col_name, col_info))
        
        # Print columns with data
        print(f"\n[COLUMNS WITH DATA] ({len(ok_cols)})")
        for col_name, col_info in ok_cols[:20]:  # Limit output
            sample = col_info["sample_values"][0] if col_info["sample_values"] else "N/A"
            if col_info["min"] is not None:
                print(f"  {col_name:<35} | type={col_info['type']:<10} | range={col_info['min']}-{col_info['max']}")
            else:
                print(f"  {col_name:<35} | type={col_info['type']:<10} | sample={sample[:30]}")
        
        if len(ok_cols) > 20:
            print(f"  ... and {len(ok_cols) - 20} more columns")
        
        # Print columns with NULLs
        if warn_cols:
            print(f"\n[COLUMNS WITH NULLS] ({len(warn_cols)})")
            for col_name, col_info, null_pct in warn_cols[:15]:
                status = "ALL NULL" if null_pct == 100 else f"{null_pct:.1f}% null"
                print(f"  {col_name:<35} | {status}")
            
            if len(warn_cols) > 15:
                print(f"  ... and {len(warn_cols) - 15} more columns with nulls")


def check_json_fields(db_path: str, table: str, json_columns: List[str]):
    """Check if JSON fields are valid JSON."""
    
    if not os.path.exists(db_path):
        return
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    print(f"\n[JSON VALIDATION] {db_path} -> {table}")
    print("-" * 70)
    
    for col in json_columns:
        try:
            cur.execute(f"SELECT [{col}] FROM {table} WHERE [{col}] IS NOT NULL AND [{col}] != '' LIMIT 5")
            rows = cur.fetchall()
            
            valid = 0
            invalid = 0
            
            for row in rows:
                try:
                    json.loads(row[0])
                    valid += 1
                except:
                    invalid += 1
            
            status = "OK" if invalid == 0 else f"INVALID ({invalid}/{valid+invalid})"
            print(f"  {col:<35} | {status}")
            
        except Exception as e:
            print(f"  {col:<35} | ERROR: {e}")
    
    conn.close()


def check_sample_records(db_path: str, table: str, limit: int = 2):
    """Show sample records."""
    
    if not os.path.exists(db_path):
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    print(f"\n[SAMPLE RECORDS] {db_path} -> {table}")
    print("-" * 70)
    
    cur.execute(f"SELECT * FROM {table} LIMIT {limit}")
    rows = cur.fetchall()
    
    for i, row in enumerate(rows, 1):
        print(f"\nRecord {i}:")
        row_dict = dict(row)
        for k, v in row_dict.items():
            if v is not None and v != "" and v != "[]" and v != "{}":
                val_str = str(v)[:60]
                if len(str(v)) > 60:
                    val_str += "..."
                print(f"  {k}: {val_str}")
    
    conn.close()


if __name__ == "__main__":
    import time
    start = time.time()
    
    # Analyze tweets.db
    tweets_analysis = analyze_database("tweets.db")
    print_analysis(tweets_analysis)
    
    # Check JSON fields in tweets
    check_json_fields("tweets.db", "tweets", [
        "display_text_range", "entities_json", "extended_entities_json", 
        "card_json", "place_json", "author_profile_bio", "raw_json"
    ])
    
    # Analyze users.db
    users_analysis = analyze_database("users.db")
    print_analysis(users_analysis)
    
    # Check JSON fields in users
    check_json_fields("users.db", "user_tweets", [
        "display_text_range", "entities_hashtags", "entities_urls",
        "entities_user_mentions", "extended_entities_json", "card_json",
        "place_json", "quoted_tweet_json", "retweeted_tweet_json", "raw_json"
    ])
    
    # Show sample records
    check_sample_records("tweets.db", "tweets", 1)
    check_sample_records("users.db", "user_tweets", 1)
    
    print(f"\n[TOTAL_TIME] {time.time() - start:.2f}s")

