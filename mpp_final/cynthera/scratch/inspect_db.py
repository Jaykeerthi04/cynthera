import sqlite3
import json

con = sqlite3.connect("data/cynthera.db")
cur = con.cursor()
cur.execute("PRAGMA table_info(hypotheses);")
print("hypotheses cols:", cur.fetchall())

cur.execute("""
    SELECT h.drug_name, h.disease_name, rp.data_json
    FROM hypotheses h
    JOIN retrieval_packages rp ON h.id = rp.hypothesis_id
    LIMIT 1;
""")
row = cur.fetchone()
if row:
    drug, disease, data_json = row
    pkg = json.loads(data_json)
    print(f"Sample: {drug} -> {disease}")
    print("Package keys:", list(pkg.keys()))
    if "clinical_trials" in pkg:
        print("Clinical trials count:", len(pkg["clinical_trials"]))

con.close()
