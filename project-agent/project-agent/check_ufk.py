import sqlite3
import os

db_path = os.environ.get('DB_PATH', '/app/data')
agent_db = os.path.join(db_path, 'agent.db')

if not os.path.exists(agent_db):
    agent_db = 'agent.db'

print(f"Using DB: {agent_db}")

conn = sqlite3.connect(agent_db)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Counts
cur.execute('SELECT COUNT(*) FROM triaged_projects')
triaged = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM verified_projects')
verified = cur.fetchone()[0]

print(f"Total triaged: {triaged}")
print(f"Total verified: {verified}")

# Check ufksolana
print("\n=== @ufksolana ===")
cur.execute("SELECT * FROM verified_projects WHERE LOWER(twitter_handle) LIKE '%ufk%'")
rows = cur.fetchall()
for row in rows:
    print(f"Handle: {row['twitter_handle']}")
    print(f"Status: {row['verification_status']}")
    print(f"Monitoring: {row['monitoring_status']}")
    print(f"Created: {row['created_at']}")

# Fingerprints
print("\n=== Fingerprints ===")
cur.execute("SELECT stage, stage_name, decision, created_at FROM decision_fingerprints WHERE LOWER(twitter_handle) LIKE '%ufk%' ORDER BY created_at")
for row in cur.fetchall():
    print(f"Stage {row['stage']} ({row['stage_name']}): {row['decision']} @ {row['created_at']}")

conn.close()



