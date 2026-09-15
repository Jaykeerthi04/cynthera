import sqlite3
import json

conn = sqlite3.connect("data/cynthera.db")
c = conn.cursor()
c.execute("SELECT data_json FROM retrieval_packages WHERE hypothesis_id='52b0090e-3437-4209-884b-086a69c23e4a'")
row = c.fetchone()
pkg = json.loads(row[0])
print("Clinical trials for Lisinopril -> Hypertension:")
for t in pkg.get("clinical_trials", []):
    print(f"  NCT: {t.get('nct_id')} | Phase: {t.get('phase')} | Status: {t.get('status')} | Title: {t.get('title')[:60] if t.get('title') else 'None'}")
