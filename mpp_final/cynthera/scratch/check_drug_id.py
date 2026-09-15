import sqlite3, json
conn = sqlite3.connect("data/cynthera.db")
r = conn.execute("SELECT data_json FROM retrieval_packages WHERE hypothesis_id='52b0090e-3437-4209-884b-086a69c23e4a'").fetchone()
pkg = json.loads(r[0])
print("drug:", pkg.get("drug"))
