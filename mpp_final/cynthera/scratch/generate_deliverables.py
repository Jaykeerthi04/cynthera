import json
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, ".")

with open("scratch/now_50_eval_raw.json", "r", encoding="utf-8") as f:
    raw_data = json.load(f)

before_cases = raw_data["before_cases"]
now_cases = raw_data["now_cases"]
ct_diagnostics = raw_data["ct_diagnostics"]

with open("scratch/resolved_50_cases.json", "r", encoding="utf-8") as f:
    resolved_50 = json.load(f)

results_100_path = Path("evaluation_outputs/100_case_final/results.jsonl")
baseline_100 = {}
with open(results_100_path, "r", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        baseline_100[d["case_id"]] = d

cids = [c["case_id"] for c in resolved_50]

def compute_mcc_3x3(cm: dict[str, dict[str, int]], labels: list[str]) -> float:
    n = sum(cm[t][p] for t in labels for p in labels)
    if n == 0:
        return 0.0
    c = sum(cm[k][k] for k in labels)
    p_k = {k: sum(cm[t][k] for t in labels) for k in labels}
    t_k = {k: sum(cm[k][p] for p in labels) for k in labels}

    num = c * n - sum(p_k[k] * t_k[k] for k in labels)
    den1 = n**2 - sum(p_k[k] ** 2 for k in labels)
    den2 = n**2 - sum(t_k[k] ** 2 for k in labels)
    den = math.sqrt(den1 * den2)
    return round(num / den, 4) if den > 0 else 0.0

def compute_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    labels = ["SUPPORT", "OPPOSE", "UNCERTAIN"]
    cm = {t: {p: 0 for p in labels} for t in labels}
    for t, p in zip(y_true, y_pred):
        if t in cm and p in cm[t]:
            cm[t][p] += 1

    total = len(y_true)
    correct = sum(cm[k][k] for k in labels)
    accuracy = correct / total if total > 0 else 0.0

    precisions: dict[str, float] = {}
    recalls: dict[str, float] = {}
    f1s: dict[str, float] = {}
    tp_counts: dict[str, int] = {}
    fp_counts: dict[str, int] = {}
    fn_counts: dict[str, int] = {}

    for k in labels:
        tp = cm[k][k]
        fp = sum(cm[t][k] for t in labels if t != k)
        fn = sum(cm[k][p] for p in labels if p != k)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        precisions[k] = prec
        recalls[k] = rec
        f1s[k] = f1
        tp_counts[k] = tp
        fp_counts[k] = fp
        fn_counts[k] = fn

    macro_p = sum(precisions.values()) / 3.0
    macro_r = sum(recalls.values()) / 3.0
    macro_f1 = sum(f1s.values()) / 3.0
    balanced_acc = macro_r

    support_counts = {k: sum(cm[k][p] for p in labels) for k in labels}
    weighted_f1 = sum(f1s[k] * support_counts[k] for k in labels) / total if total > 0 else 0.0
    mcc = compute_mcc_3x3(cm, labels)

    return {
        "total_cases": total,
        "correct_cases": correct,
        "accuracy": round(accuracy, 4),
        "balanced_accuracy": round(balanced_acc, 4),
        "macro_precision": round(macro_p, 4),
        "macro_recall": round(macro_r, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "mcc": round(mcc, 4),
        "per_class": {
            k: {
                "precision": round(precisions[k], 4),
                "recall": round(recalls[k], 4),
                "f1": round(f1s[k], 4),
                "tp": tp_counts[k],
                "fp": fp_counts[k],
                "fn": fn_counts[k],
                "support": support_counts[k],
            }
            for k in labels
        },
        "confusion_matrix": cm,
    }

std_golds = [before_cases[cid]["standard_gold"] for cid in cids]
epi_golds = [before_cases[cid]["epistemic_gold"] for cid in cids]

before_std_preds = [before_cases[cid]["prediction"] for cid in cids]
before_epi_preds = [before_cases[cid]["epistemic_prediction"] for cid in cids]

now_std_preds = [now_cases[cid]["prediction"] for cid in cids]
now_epi_preds = [now_cases[cid]["epistemic_prediction"] for cid in cids]

m_before_std = compute_metrics(std_golds, before_std_preds)
m_now_std = compute_metrics(std_golds, now_std_preds)

m_before_epi = compute_metrics(epi_golds, before_epi_preds)
m_now_epi = compute_metrics(epi_golds, now_epi_preds)

# Classify drivers and root causes
# Taxonomy:
# A. Entity resolution / canonicalization
# B. Retrieval coverage
# C. Literature interpretation
# D. Mechanistic reasoning
# E. Therapeutic direction
# F. ClinicalTrials evidence
# G. Statistical outcome interpretation
# H. Opposition propagation
# I. Safety / contraindication
# J. Evidence weighting / score saturation
# K. Contradiction handling
# L. Independence / deduplication
# M. Rule-engine logic
# N. Benchmark/evaluator artifact
# O. Other

records = []
for cid in cids:
    b = before_cases[cid]
    n = now_cases[cid]
    b100 = baseline_100[cid]
    drug = b["drug"]
    dis = b["disease"]
    std_g = b["standard_gold"]
    epi_g = b["epistemic_gold"]
    b_p = b["prediction"]
    n_p = n["prediction"]

    pred_changed = (b_p != n_p)
    epi_pred_changed = (b["epistemic_prediction"] != n["epistemic_prediction"])
    c_b = (b_p == std_g)
    c_n = (n_p == std_g)

    if c_b and c_n:
        trans = "UNCHANGED_CORRECT"
    elif (not c_b) and (not c_n):
        trans = "UNCHANGED_INCORRECT"
    elif (not c_b) and c_n:
        trans = "IMPROVED"
    else:
        trans = "REGRESSED"

    # Primary change driver
    driver = "OTHER"
    if pred_changed:
        if cid in ("TC-001", "TC-003", "TC-062"):
            driver = "OPPOSITION"
        elif cid in ("TC-019", "TC-047", "TC-025", "TC-053"):
            driver = "RULE_ENGINE"
        elif cid in ("TC-043", "TC-072", "TC-022"):
            driver = "STATISTICAL_DIRECTION"
        elif cid in ("TC-021", "TC-023", "TC-030"):
            driver = "OPPOSITION"
    else:
        driver = "NO_CHANGE"

    # Evidence layer presence
    has_mech = float(n["mechanistic_score"]) > 0.0 or int(b100.get("mechanistic_path_count", 0)) > 0
    has_ther = bool(b100.get("high_quality_therapeutic_evidence", False))
    has_lit = float(n["support_score"]) > 0.0 or int(b100.get("literature_claims_count", 0)) > 0
    has_ct = int(n.get("trials_retrieved", 0)) > 0
    has_safe = float(n["risk_score"]) > 0.0 or bool(b100.get("safety_veto", False))
    has_contra = str(b100.get("contradiction_level", "NONE")) != "NONE"
    has_appr = bool(n.get("approval_anchor", False))

    # Root cause classification for NOW errors
    p_rc = "NONE"
    s_rc = "NONE"
    if not c_n:
        if std_g == "SUPPORT" and n_p == "OPPOSE":
            # Lisinopril, Budesonide, Gefitinib, Crizotinib, Ranibizumab
            if cid in ("TC-001", "TC-003", "TC-062"):
                p_rc = "M. Rule-engine logic" # Rule 2b fires before Rule -1
                s_rc = "H. Opposition propagation" # single small trial gets 0.5670
            elif cid in ("TC-056", "TC-058"):
                p_rc = "M. Rule-engine logic" # Safety veto / Rule 0 misclassification in baseline
                s_rc = "I. Safety / contraindication"
        elif std_g == "SUPPORT" and n_p == "UNCERTAIN":
            # TC-002, TC-019, TC-047, TC-057
            if cid in ("TC-019", "TC-047"):
                p_rc = "A. Entity resolution / canonicalization" # exact string match failed ChEMBL anchor
                s_rc = "M. Rule-engine logic" # Rule 1c gated to UNCERTAIN
            elif cid in ("TC-002", "TC-057"):
                p_rc = "A. Entity resolution / canonicalization" # Secondary prevention / EGFR-mutant
                s_rc = "M. Rule-engine logic"
        elif std_g == "OPPOSE" and n_p == "SUPPORT":
            # TC-079 Fenofibrate
            if cid == "TC-079":
                p_rc = "A. Entity resolution / canonicalization" # hypertriglyceridemia mapped to CVD
                s_rc = "J. Evidence weighting / score saturation"
        elif std_g == "OPPOSE" and n_p == "UNCERTAIN":
            # 15 hard negatives
            if cid in ("TC-081", "TC-082", "TC-085", "TC-088", "TC-044"):
                p_rc = "I. Safety / contraindication" # Absolute contraindication / toxicity
                s_rc = "E. Therapeutic direction"
            elif cid in ("TC-028", "TC-029", "TC-041", "TC-042", "TC-066", "TC-067", "TC-074"):
                p_rc = "B. Retrieval coverage" # Historical trials not in CT.gov or ongoing
                s_rc = "F. ClinicalTrials evidence"
            elif cid in ("TC-022", "TC-025", "TC-052", "TC-053"):
                p_rc = "F. ClinicalTrials evidence" # Trial structure lacked single agent contrast or neutral
                s_rc = "K. Contradiction handling"
        elif std_g == "UNCERTAIN" and n_p != "UNCERTAIN":
            # TC-051 Valproic acid -> glioblastoma
            p_rc = "J. Evidence weighting / score saturation"
            s_rc = "E. Therapeutic direction"

    records.append({
        "case_id": cid,
        "drug": drug,
        "disease": dis,
        "standard_gold": std_g,
        "epistemic_gold": epi_g,
        "before": {
            "prediction": b["prediction"],
            "epistemic_prediction": b["epistemic_prediction"],
            "support_score": b["support_score"],
            "mechanistic_score": b["mechanistic_score"],
            "risk_score": b["risk_score"],
            "opposition_score": b["opposition_score"],
            "recommendation": b["recommendation"],
            "decision_rule": b["decision_rule"],
        },
        "now": {
            "prediction": n["prediction"],
            "epistemic_prediction": n["epistemic_prediction"],
            "support_score": n["support_score"],
            "mechanistic_score": n["mechanistic_score"],
            "risk_score": n["risk_score"],
            "opposition_score": n["opposition_score"],
            "recommendation": n["recommendation"],
            "decision_rule": n["decision_rule"],
        },
        "change_analysis": {
            "prediction_changed": pred_changed,
            "epistemic_prediction_changed": epi_pred_changed,
            "correct_before": c_b,
            "correct_now": c_n,
            "transition": trans,
            "primary_change_driver": driver,
        },
        "evidence_diagnostics": {
            "mechanistic_evidence": has_mech,
            "therapeutic_evidence": has_ther,
            "literature_evidence": has_lit,
            "clinical_trial_evidence": has_ct,
            "safety_evidence": has_safe,
            "contradictory_evidence": has_contra,
            "approval_evidence": has_appr,
        },
        "root_cause_analysis": {
            "primary_root_cause": p_rc,
            "secondary_root_cause": s_rc,
        },
    })

# Write deliverable JSON ledger
ledger = {
    "metadata": {
        "title": "CYNTHERA Full End-to-End 50-Case Reevaluation Ledger: BEFORE vs NOW",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cases": 50,
        "before_source": "backend/evaluation/post_clinicaltrials_50_fast_ledger.json (Original Post-CT Baseline)",
        "now_source": "Current Full CYNTHERA Pipeline (Post P0 Evaluator Parity, P1 Statistical Direction Semantics, P2 Opposition Propagation)",
    },
    "metrics": {
        "standard_3class": {
            "before": m_before_std,
            "now": m_now_std,
        },
        "epistemic_3class": {
            "before": m_before_epi,
            "now": m_now_epi,
        },
    },
    "clinicaltrials_diagnostics": ct_diagnostics,
    "cases": records,
}

out_ledger_path = Path("backend/evaluation/before_vs_now_50_end_to_end_ledger.json")
with open(out_ledger_path, "w", encoding="utf-8") as f:
    json.dump(ledger, f, indent=2)
print(f"Successfully wrote ledger to {out_ledger_path}")

