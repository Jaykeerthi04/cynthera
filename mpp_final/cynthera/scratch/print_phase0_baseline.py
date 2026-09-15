import json

with open("scratch/phase0_baseline.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for cid, d in data.items():
    print(f"=== {cid}: {d['drug']} -> {d['disease']} ===")
    print(f"  prediction: {d['prediction']} | recommendation: {d['recommendation']}")
    sig = d["approval_signal"]
    print(f"  approval_signal.is_approved: {sig.get('is_approved')} | max_phase: {d['max_phase']} | term: {repr(d['matched_indication_term'])} | conf: {d['match_confidence']} | pathway: {d['evaluation_pathway']}")
    print(f"  has_high_quality_therapeutic: {d['has_high_quality_therapeutic']}")
    print(f"  opp_score: {d['opposition_score']} | opp_level: {d['opposition_level']} | qneg_count: {d['qualified_negative_claim_count']}")
    gate = d.get("decision_gate") or ""
    print(f"  decision_gate: {gate[:120]}...")
    audit = d.get("therapeutic_evidence_audit") or []
    audit_summary = [{"source": a.get("source"), "direction": a.get("direction"), "quality": a.get("quality"), "prov": a.get("provenance_id")} for a in audit[:3]]
    print(f"  therapeutic_evidence_audit ({len(audit)} records, first 3): {audit_summary}")
