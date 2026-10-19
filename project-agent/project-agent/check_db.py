# check_db.py
import sqlite3
import json

conn = sqlite3.connect('agent.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 60)
print("MENTIONS TABLE")
print("=" * 60)
cur.execute("SELECT * FROM mentions")
mentions = cur.fetchall()
print(f"Total: {len(mentions)}")
for row in mentions:
    src = row["source_author_handle"] or "?"
    mentioned = row["mentioned_handle"] or "?"
    name = row["project_name_extracted"] or "?"
    conf = row["confidence"] or 0
    print(f"  @{src} mentioned @{mentioned} | name={name} | conf={conf}")

print()
print("=" * 60)
print("TRIAGED_PROJECTS TABLE")
print("=" * 60)
cur.execute("SELECT * FROM triaged_projects")
triaged = cur.fetchall()
print(f"Total: {len(triaged)}")
for row in triaged:
    handle = row["twitter_handle"] or "?"
    name = row["project_name"] or "?"
    chain = row["project_chain"] or "?"
    print(f"  @{handle} | {name} | {chain}")

print()
print("=" * 60)
print("DECISION FINGERPRINTS (Stage 1)")
print("=" * 60)
cur.execute("SELECT twitter_handle, decision, confidence FROM decision_fingerprints WHERE stage=1")
fps = cur.fetchall()
print(f"Total: {len(fps)}")
for row in fps:
    handle = row[0] or "?"
    decision = row[1] or "?"
    conf = row[2] or 0
    print(f"  @{handle:20} | decision={decision:20} | conf={conf:.2f}")

print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)

# Count decisions
cur.execute("SELECT decision, COUNT(*) FROM decision_fingerprints WHERE stage=1 GROUP BY decision")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

conn.close()

