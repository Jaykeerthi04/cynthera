import sqlite3
import json

conn = sqlite3.connect("data/cynthera.db")
c = conn.cursor()

c.execute("SELECT endpoint, response_json FROM raw_response_cache WHERE endpoint LIKE ? AND endpoint LIKE ?", ('%CHEMBL682%', '%drug_indication%'))
rows = c.fetchall()
print(f"Found {len(rows)} cached endpoints for Azithromycin drug_indication.")
for ep, r in rows:
    print(f"Endpoint: {ep}")
    data = json.loads(r)
    inds = data.get("drug_indications", [])
    print(f"Total indications: {len(inds)}")
    for ind in inds:
        t = f"{ind.get('efo_term')} | {ind.get('mesh_heading')}"
        p = ind.get("max_phase_for_ind")
        if any(w in t.lower() for w in ["covid", "sars", "corona", "respiratory", "pneumonia"]):
            print(f"  {t} -> max_phase={p}")
