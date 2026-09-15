import sqlite3
import json

conn = sqlite3.connect("data/cynthera.db")
c = conn.cursor()
c.execute("SELECT hypothesis_id, data_json FROM retrieval_packages WHERE data_json LIKE '%Lisinopril%' LIMIT 3")
rows = c.fetchall()
print(f"Found {len(rows)} Lisinopril retrieval packages.")
for hyp_id, data_json in rows:
    pkg = json.loads(data_json)
    drug = pkg.get("drug", {}).get("name")
    disease = pkg.get("disease", {}).get("name")
    sig = pkg.get("approval_signal")
    print(f"Hyp: {hyp_id} | Drug: {drug} | Disease: {disease}")
    print(f"  Approval Signal: {sig}")
    trials = pkg.get("clinical_trials", [])
    print(f"  Trials count: {len(trials)}")
    targets = pkg.get("targets", [])
    print(f"  Targets count: {len(targets)}")
    for t in targets[:3]:
        print(f"    Target: name={t.get('name')}, uniprot={t.get('protein_uniprot')}, mech={t.get('mechanism')}")
