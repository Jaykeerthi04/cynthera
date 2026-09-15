import json
from pathlib import Path

ledger_path = Path("backend/evaluation/post_clinicaltrials_50_fast_ledger.json")
with open(ledger_path, "r", encoding="utf-8") as f:
    ledger = json.load(f)

cases = ledger["cases"]

for cid in ["TC-043", "TC-072"]:
    c = [x for x in cases if x["case_id"] == cid][0]
    print("=" * 80)
    print(f"{cid}: {c['drug']} -> {c['disease']}")
    print(f"  Gold: {c['standard_gold']}, Base Pred: {c['baseline_prediction']}, Post Pred: {c['prediction']}")
    print(f"  Base Opp: {c['baseline_opposition_score']}, Post Opp: {c['opposition_score']} ({c['opposition_level']})")
    print(f"  Rule: {c['decision_rule']}")
    print(f"  Approval Anchor in Post: {c['approval_anchor']}")
    print(f"  Trials retrieved: {c['clinical_trials_retrieved']}, Parsed: {c['clinical_trials_parsed']}")
    print(f"  Attributed negative trials: {c['attributed_negative_trials']}")
    print("  Trial telemetry:")
    for t in c["trial_telemetry"]:
        if t["attribution_decision"] == "ATTRIBUTED" or t["negative_claim_generated"]:
            print(f"    NCT: {t['nct_id']} | Status: {t['status']} | NegClaims: {t['negative_claim_generated']} | Role: {t['candidate_drug_role']}")
            print(f"      Reason: {t['attribution_reason']}")
