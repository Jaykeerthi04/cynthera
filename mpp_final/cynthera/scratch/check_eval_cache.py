import sqlite3
import json

conn = sqlite3.connect("data/cynthera.db")
c = conn.cursor()
c.execute("SELECT result_json FROM evaluation_cache WHERE result_json LIKE '%Lisinopril%' AND result_json LIKE '%Hypertension%' LIMIT 1")
row = c.fetchone()
res = json.loads(row[0])
print("recommendation_status:", res.get("recommendation_status"))
print("recommendation_reasons:")
for r in res.get("recommendation_reasons", []):
    print("  *", r)
