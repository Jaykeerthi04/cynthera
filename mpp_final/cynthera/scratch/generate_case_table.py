import json
import os

filepath = "evaluation_outputs/25_case_freeze_v3_2/results.jsonl"
with open(filepath, "r", encoding="utf-8") as f:
    lines = [json.loads(line) for line in f if line.strip()]

print(f"Total lines: {len(lines)}")

rows = []
for d in lines:
    case_id = d.get("case_id")
    drug = d.get("drug")
    disease = d.get("disease")
    exp_3class = d.get("expected_3class")
    epistemic_exp = d.get("epistemic_expected_class")
    pred = d.get("prediction")
    rec = d.get("recommendation")
    mech_score = d.get("mechanistic_score", 0.0)
    supp_score = d.get("support_score", 0.0)
    
    # Check opposition details
    opp_score = d.get("opposition_score")
    opp_eval = d.get("opposition_evaluation") or {}
    if opp_score is None:
        opp_score = opp_eval.get("score", 0.0)
    opp_cnt = opp_eval.get("qualified_negative_claim_count", 0)
    contradiction_state = d.get("contradiction_state") or opp_eval.get("contradiction_state", "NONE")
    
    # Therapeutic anchor
    anchor = d.get("therapeutic_anchor")
    if anchor is None:
        # check high_quality_therapeutic or approval_signal
        app_sig = d.get("approval_signal") or {}
        is_app = app_sig.get("is_approved", False)
        # also check decision_gate or therapeutic_reasons
        anchor = "YES" if (is_app or d.get("has_high_quality_therapeutic")) else "NO"
        if is_app:
            anchor = f"Approved ({app_sig.get('matched_indication_term', '')})"
        elif d.get("has_high_quality_therapeutic"):
            anchor = "Trial Evidence"
        else:
            anchor = "None"

    rule_fired = d.get("rule_fired")
    if not rule_fired:
        dg = d.get("decision_gate")
        if dg:
            rule_fired = dg.split(":")[0] if ":" in dg else dg[:25]
        else:
            rule_fired = "Standard"

    rows.append({
        "case_id": case_id,
        "drug": drug,
        "disease": disease,
        "expected_3class": exp_3class,
        "epistemic_expected_class": epistemic_exp,
        "prediction": pred,
        "recommendation": rec,
        "mechanistic_score": mech_score,
        "support_score": supp_score,
        "opposition_score": opp_score,
        "contradiction_state": contradiction_state,
        "therapeutic_anchor": anchor,
        "opposition_evidence_count": opp_cnt,
        "rule_fired": rule_fired,
    })

import pandas as pd
df = pd.DataFrame(rows)
print(df.to_string())

with open("scratch/case_by_case_table.json", "w") as out:
    json.dump(rows, out, indent=2)
