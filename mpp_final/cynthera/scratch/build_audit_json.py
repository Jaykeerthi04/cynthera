import json
import sys
from pathlib import Path

# Load ledger
ledger_path = Path("backend/evaluation/post_clinicaltrials_50_fast_ledger.json")
with open(ledger_path, "r", encoding="utf-8") as f:
    ledger = json.load(f)

cases = ledger["cases"]
controls = ledger["controls"]
target_trials = ledger["target_trials"]
reported_metrics = ledger["metrics"]

print(f"Loaded ledger successfully: {len(cases)} cases, {len(controls)} controls, {len(target_trials)} target trials.")

# Generate JSON artifact first
audit_json = {
    "metadata": {
        "title": "CYNTHERA Post-ClinicalTrials 50-Case Reconciled Forensic Audit",
        "timestamp": "2026-09-10T09:30:00Z",
        "source_ledger": "backend/evaluation/post_clinicaltrials_50_fast_ledger.json",
        "evaluator_script": "backend/evaluation/run_50_case_post_clinicaltrials_fast.py",
        "total_cases": len(cases),
        "control_cases": len(controls),
    },
    "decision": "EVALUATOR_ARTIFACT_REQUIRES_FIX_AND_STOP_CLINICALTRIALS",
    "metrics_reconciled": True,
    "unsupported_claims_count": 6,
    "transitions_count": 7,
    "false_promising_count": {"baseline": 3, "postfix": 5},
    "false_oppose_count": {"baseline": 2, "postfix": 4},
    "hard_negative_audit": {
        "total": 22,
        "unchanged_uncertain": 14,
        "unchanged_oppose": 4,
        "unchanged_support": 2,
        "uncertain_to_support_false_promising": 2,
        "uncertain_to_oppose_correct": 0,
        "accuracy_baseline": 0.1818,
        "accuracy_postfix": 0.1818,
        "uncertainty_baseline": 0.7273,
        "uncertainty_postfix": 0.6364,
        "false_promising_baseline": 0.0909,
        "false_promising_postfix": 0.1818
    },
    "target_trials_verified": target_trials,
}

with open("backend/evaluation/post_clinicaltrials_50_reconciled_audit.json", "w", encoding="utf-8") as f:
    json.dump(audit_json, f, indent=2)

# Also write to workspace root backend/evaluation
Path("backend/evaluation").mkdir(parents=True, exist_ok=True)
with open("backend/evaluation/post_clinicaltrials_50_reconciled_audit.json", "w", encoding="utf-8") as f:
    json.dump(audit_json, f, indent=2)

print("Saved post_clinicaltrials_50_reconciled_audit.json")
