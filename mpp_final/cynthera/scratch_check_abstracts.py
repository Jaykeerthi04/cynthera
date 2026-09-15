import sqlite3
import json

conn = sqlite3.connect("data/cynthera.db")
cur = conn.cursor()

for drug, dis in [("Fluvoxamine", "COVID-19"), ("Aspirin", "COVID-19"), ("Atorvastatin", "Alzheimer disease")]:
    cur.execute("""
        SELECT id, drug_name, disease_name FROM hypotheses 
        WHERE lower(drug_name) = ? AND lower(disease_name) = ?
        ORDER BY created_at DESC LIMIT 1
    """, (drug.lower(), dis.lower()))
    row = cur.fetchone()
    if row:
        hid = row[0]
        cur.execute("SELECT data_json FROM retrieval_packages WHERE hypothesis_id = ?", (hid,))
        pkg_row = cur.fetchone()
        if pkg_row:
            pkg = json.loads(pkg_row[0])
            evs = pkg.get("evidence_records", [])
            lit = [e for e in evs if e.get("abstract") and drug.lower() in (e.get("title", "") + e.get("abstract", "")).lower()]
            print(f"=== {drug} -> {dis}: {len(lit)} drug-mentioning abstracts ===")
            for i, e in enumerate(lit[:5]):
                txt = e.get("abstract", "")[:250].encode("ascii", "replace").decode()
                title = e.get("title", "")[:80].encode("ascii", "replace").decode()
                src = e.get("provenance", {}).get("source_name", "")
                print(f"   [{src}] {title}")
                print(f"       {txt}...\n")

conn.close()
