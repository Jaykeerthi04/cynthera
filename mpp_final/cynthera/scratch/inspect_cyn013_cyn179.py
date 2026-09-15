import sqlite3
import json

conn = sqlite3.connect("data/cynthera.db")
c = conn.cursor()

for drug, disease in [
    ("aspirin", "secondary prevention of cardiovascular disease"),
    ("propranolol", "depression"),
]:
    print(f"\n==========================================")
    print(f"Inspecting DB for {drug} -> {disease}")
    print(f"==========================================")
    c.execute(
        "SELECT cache_key, created_at, result_json FROM evaluation_cache WHERE drug_name=? AND disease_name=? ORDER BY created_at DESC",
        (drug, disease),
    )
    rows = c.fetchall()
    print(f"Found {len(rows)} cached results in evaluation_cache")
    for i, (ck, ca, r_json) in enumerate(rows):
        res = json.loads(r_json)
        print(f"\n--- Entry {i+1} (Key: {ck}, Created: {ca}) ---")
        print(f"rule_set_version: {res.get('rule_set_version')}")
        opp_ass = res.get("opposition_assessment")
        print(f"opposition_assessment: {opp_ass}")
        risk_ass = res.get("risk_assessment")
        print(f"risk_assessment.score: {risk_ass.get('score') if risk_ass else None}")
        supp_ass = res.get("support_assessment")
        print(f"support_assessment.score: {supp_ass.get('score') if supp_ass else None}")
        reasons = res.get("recommendation_reasons")
        print(f"decision_gate: {reasons[0] if reasons else None}")
