import sqlite3
import json

conn = sqlite3.connect('data/cynthera.db')
rows = conn.execute('SELECT drug_name, disease_name, hit_count, result_json FROM evaluation_cache').fetchall()
print(f"Total cache rows: {len(rows)}")

zero_cases = []
for r in rows:
    drug, disease, hit_count, result_json = r
    data = json.loads(result_json)
    ma = data.get("mechanistic_assessment", {})
    score = ma.get("score")
    level = ma.get("level")
    cands = ma.get("candidate_mechanisms", [])
    print(f"{drug.title()} -> {disease.title()}: MS={score} ({level}), Cands={len(cands)}, Hits={hit_count}")
    if score == 0:
        zero_cases.append((drug, disease, ma))

print("\n--- ZERO SCORE CASES ---")
for drug, disease, ma in zero_cases:
    print(f"{drug.title()} -> {disease.title()}: MS={ma.get('score')} ({ma.get('level')}), rationale: {ma.get('rationale')[:100]}...")
