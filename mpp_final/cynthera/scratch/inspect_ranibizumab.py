import sqlite3
import json

conn = sqlite3.connect("data/cynthera.db")
c = conn.cursor()
c.execute("SELECT cache_key, response_json FROM raw_response_cache WHERE endpoint LIKE '%drug_indication%'")
rows = c.fetchall()
print("drug_indication cached rows:", len(rows))
for k, r in rows:
    if "1201825" in k or "ranibizumab" in k.lower():
        print("Found key:", k)
        data = json.loads(r)
        for ind in data.get("drug_indications", []):
            print("  mesh:", ind.get("mesh_heading"), "| efo:", ind.get("efo_term"), "| max_phase:", ind.get("max_phase_for_ind"))
