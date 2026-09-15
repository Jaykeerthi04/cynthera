import json
import sqlite3

cases_to_inspect = ["CYN-109", "CYN-111", "CYN-117", "CYN-125", "CYN-137"]

with open("evaluation_outputs/25_case_freeze_v3_2/results.jsonl", "r", encoding="utf-8") as f:
    eval_cases = {json.loads(line)["case_id"]: json.loads(line) for line in f if line.strip()}

conn = sqlite3.connect("data/cynthera.db")

for cid in cases_to_inspect:
    data = eval_cases.get(cid, {})
    drug = data.get("drug")
    disease = data.get("disease")
    print(f"\n{'='*70}\nCASE {cid}: {drug} -> {disease}\n{'='*70}")
    print(f"Prediction: {data.get('prediction')} (Expected: {data.get('original_expected_label')} / {data.get('expected_3class')})")
    print(f"Recommendation: {data.get('recommendation')}")
    print(f"Decision gate: {data.get('decision_gate')}")
    print(f"Scores: SS={data.get('support_score')} | MS={data.get('mechanistic_score')} | RS={data.get('opposition_score')}")
    
    # Query cached ReasoningResult
    c = conn.cursor()
    c.execute(
        "SELECT result_json FROM evaluation_cache WHERE drug_name=? AND disease_name=? ORDER BY created_at DESC LIMIT 1",
        (drug.lower(), disease.lower()),
    )
    row = c.fetchone()
    if row:
        res = json.loads(row[0])
        opp = res.get("opposition_assessment") or {}
        print(f"OppositionAssessment:")
        print(f"  score: {opp.get('score')}")
        print(f"  level: {opp.get('level')}")
        print(f"  qualified_negative_claims: {opp.get('qualified_negative_claim_count')}")
        print(f"  rationale: {opp.get('rationale')}")
        
        # Check retrieval package from DB
        c.execute(
            "SELECT data_json FROM retrieval_packages WHERE hypothesis_id=?",
            (res.get("hypothesis_id"),),
        )
        pkg_row = c.fetchone()
        if pkg_row:
            pkg = json.loads(pkg_row[0])
            trials = pkg.get("clinical_trials", [])
            lit = pkg.get("literature_evidence", [])
            print(f"Retrieval Package:")
            print(f"  Total clinical trials retrieved: {len(trials)}")
            print(f"  Total literature records retrieved: {len(lit)}")
            
            terminated_trials = [t for t in trials if t.get("status") in ("TERMINATED_LACK_OF_EFFICACY", "TERMINATED_SAFETY", "TERMINATED_ADMINISTRATIVE")]
            print(f"  Terminated trials count: {len(terminated_trials)}")
            for tt in terminated_trials:
                print(f"    NCT: {tt.get('nct_id')} | Status: {tt.get('status')} | Why: {tt.get('why_stopped')}")
                
            completed_trials = [t for t in trials if t.get("status") in ("UNKNOWN", "COMPLETED")]
            print(f"  Completed/Unknown trials count: {len(completed_trials)}")
            
            # Check lit titles / snippets for negative terms
            neg_lit = []
            for le in lit:
                txt = (le.get("title", "") + " " + le.get("abstract", "")).lower()
                if any(w in txt for w in ["not improve", "no benefit", "did not prevent", "failed to", "no significant difference", "ineffective"]):
                    neg_lit.append(le.get("title", "")[:80])
            print(f"  Literature with negative phrasing: {len(neg_lit)}")
            for nl in neg_lit[:3]:
                print(f"    - {nl}")
