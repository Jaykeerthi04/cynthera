import json
import sys
from pathlib import Path
sys.path.insert(0, '.')

# Let's inspect the exact 50 cases
resolved_50_path = Path("scratch/resolved_50_cases.json")
with open(resolved_50_path, "r", encoding="utf-8") as f:
    resolved_50 = json.load(f)

results_100_path = Path("evaluation_outputs/100_case_final/results.jsonl")
baseline_100 = {}
with open(results_100_path, "r", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        baseline_100[d["case_id"]] = d

print(f"Loaded 50 cases and {len(baseline_100)} baseline 100 records.")

# The 7 transitions from post_clinicaltrials_50_reconciled_audit.md
# which distinguished the post-CT 50-case run from the 100-case baseline:
transitions_post_ct = {
    "TC-019": {"pred": "SUPPORT", "rec": "PROMISING", "rule": "Rule 1 (PROMISING)", "opp": 0.0},
    "TC-025": {"pred": "SUPPORT", "rec": "PROMISING", "rule": "Rule 1 (PROMISING)", "opp": 0.3187},
    "TC-043": {"pred": "OPPOSE", "rec": "NOT_RECOMMENDED", "rule": "Rule 2b (EMPIRICAL OPPOSITION VETO)", "opp": 0.5120},
    "TC-047": {"pred": "SUPPORT", "rec": "PROMISING", "rule": "Rule 1 (PROMISING)", "opp": 0.3700},
    "TC-053": {"pred": "SUPPORT", "rec": "PROMISING", "rule": "Rule 1 (PROMISING)", "opp": 0.0},
    "TC-062": {"pred": "SUPPORT", "rec": "PROMISING", "rule": "Rule 1 (PROMISING)", "opp": 0.0},
    "TC-072": {"pred": "OPPOSE", "rec": "NOT_RECOMMENDED", "rule": "Rule 2b (EMPIRICAL OPPOSITION VETO)", "opp": 0.5120},
}

before_cases = {}
for c in resolved_50:
    cid = c["case_id"]
    base = baseline_100[cid]
    if cid in transitions_post_ct:
        t = transitions_post_ct[cid]
        pred = t["pred"]
        rec = t["rec"]
        rule = t["rule"]
        opp = t["opp"]
    else:
        pred = base["prediction"]
        rec = base.get("recommendation", "UNCERTAIN")
        rule = base.get("decision_rule", "")
        opp = float(base.get("opposition_score", 0.0))
    
    before_cases[cid] = {
        "case_id": cid,
        "drug": c["drug"],
        "disease": c["disease"],
        "standard_gold": c["standard_gold"],
        "epistemic_gold": c["epistemic_gold"],
        "prediction": pred,
        "epistemic_prediction": pred,
        "support_score": float(base.get("support_score", 0.0)),
        "mechanistic_score": float(base.get("mechanistic_score", 0.0)),
        "risk_score": float(base.get("risk_score", 0.0)),
        "opposition_score": opp,
        "recommendation": rec,
        "decision_rule": rule,
    }

# Verify metrics on before_cases
from backend.evaluation.run_50_case_post_clinicaltrials_fast import compute_metrics
std_golds = [c["standard_gold"] for c in resolved_50]
std_preds = [before_cases[c["case_id"]]["prediction"] for c in resolved_50]
epi_golds = [c["epistemic_gold"] for c in resolved_50]
epi_preds = [before_cases[c["case_id"]]["epistemic_prediction"] for c in resolved_50]

m_std = compute_metrics(std_golds, std_preds)
m_epi = compute_metrics(epi_golds, epi_preds)

print("BEFORE Standard Metrics:")
print(f"  Accuracy: {m_std['accuracy']} (correct: {m_std['correct_cases']})")
print(f"  Balanced Acc: {m_std['balanced_accuracy']}")
print(f"  Macro P: {m_std['macro_precision']}")
print(f"  Macro R: {m_std['macro_recall']}")
print(f"  Macro F1: {m_std['macro_f1']}")
print(f"  Weighted F1: {m_std['weighted_f1']}")
print(f"  MCC: {m_std['mcc']}")

print("BEFORE Epistemic Metrics:")
print(f"  Accuracy: {m_epi['accuracy']} (correct: {m_epi['correct_cases']})")
print(f"  Balanced Acc: {m_epi['balanced_accuracy']}")
print(f"  Macro P: {m_epi['macro_precision']}")
print(f"  Macro R: {m_epi['macro_recall']}")
print(f"  Macro F1: {m_epi['macro_f1']}")
print(f"  Weighted F1: {m_epi['weighted_f1']}")
print(f"  MCC: {m_epi['mcc']}")
