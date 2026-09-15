import sqlite3
import json

conn = sqlite3.connect("data/cynthera.db")
c = conn.cursor()
c.execute("SELECT resolved_id, response_json FROM raw_response_cache WHERE source_name LIKE '%indication%' OR endpoint LIKE '%indication%' LIMIT 10")
rows = c.fetchall()
print(f"Found {len(rows)} indication entries in cache.")
for res_id, resp_json in rows:
    d = json.loads(resp_json)
    print(f"  ChEMBL ID: {res_id} | count: {len(d) if isinstance(d, list) else (len(d.get('indications', [])) if isinstance(d, dict) else type(d))}")
    if isinstance(d, dict):
        inds = d.get("indications", [])
        for ind in inds[:3]:
            print(f"    ind: efo={ind.get('efo_term')}, mesh={ind.get('mesh_heading')}, max_phase={ind.get('max_phase_for_ind')}")
