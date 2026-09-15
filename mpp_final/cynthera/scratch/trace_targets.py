import sqlite3
import json

conn = sqlite3.connect("data/cynthera.db")
c = conn.cursor()

drugs = ["Tamoxifen", "Trastuzumab", "Aspirin", "Lithium"]
for d in drugs:
    c.execute("SELECT hypothesis_id, data_json FROM retrieval_packages WHERE data_json LIKE ? LIMIT 1", (f'%"{d}"%',))
    row = c.fetchone()
    if row:
        pkg = json.loads(row[1])
        targets = pkg.get("targets", [])
        disease = pkg.get("disease", {}).get("name")
        print(f"=== Drug: {d} -> {disease} ===")
        print(f"  Target count: {len(targets)}")
        for t in targets[:5]:
            print(f"    Target: symbol={t.get('gene_symbol')}, uniprot={t.get('protein_uniprot')}, mech={t.get('mechanism')}, name={t.get('name')}")
    else:
        print(f"=== Drug: {d} NOT FOUND in retrieval_packages ===")
