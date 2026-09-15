import sqlite3
import json

conn = sqlite3.connect("data/cynthera.db")
c = conn.cursor()

c.execute("SELECT drug_name, disease_name, result_json FROM evaluation_cache")
rows = c.fetchall()

v32_cases = []
for drug, disease, r_json in rows:
    res = json.loads(r_json)
    if res.get("rule_set_version") == "3.2":
        opp = res.get("opposition_assessment") or {}
        risk = res.get("risk_assessment") or {}
        v32_cases.append({
            "drug": drug,
            "disease": disease,
            "opp_score": opp.get("score"),
            "opp_qual_count": opp.get("qualified_negative_claim_count"),
            "risk_score": risk.get("score"),
            "status": res.get("recommendation_status"),
        })

print(f"Total v3.2 cases in cache: {len(v32_cases)}")
for item in v32_cases:
    opp_s = item['opp_score']
    qual_c = item['opp_qual_count']
    risk_s = item['risk_score']
    print(f"{item['drug']:15s} -> {item['disease']:35s} | opp_score: {opp_s} | qual_cnt: {qual_c} | risk_score: {risk_s}")
    if opp_s is not None and opp_s > 0 and qual_c == 0:
        print(f"  >>> ANOMALY DETECTED: opp_score > 0 but qual_cnt == 0!")
