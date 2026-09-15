import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

db_path = 'data/cynthera.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Searching raw_response_cache in data/cynthera.db...")
rows = cursor.execute("SELECT source_name, resolved_id, endpoint, response_json FROM raw_response_cache WHERE resolved_id LIKE '%fluvoxamine%' OR response_json LIKE '%fluvoxamine%'").fetchall()
print(f"Total matching rows: {len(rows)}")

for source_name, resolved_id, endpoint, raw_data in rows:
    if "llm_claims" in source_name.lower():
        print(f"\n--- DOI/PMID: {resolved_id} ---")
        print(raw_data)
