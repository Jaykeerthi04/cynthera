import sqlite3
import json

conn = sqlite3.connect("data/cynthera.db")
c = conn.cursor()
c.execute("SELECT resolved_id, response_json FROM raw_response_cache WHERE source_name='reactome_rxn_detail' AND resolved_id LIKE '%R-HSA-%' LIMIT 20")
rows = c.fetchall()
for idx, (res_id, resp_json) in enumerate(rows):
    d = json.loads(resp_json)
    lit = d.get("literatureReference")
    if lit:
        print(f"Reaction {res_id}: literatureReference={lit}")
