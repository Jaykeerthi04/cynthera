"""Script to analyze and print the 25-case benchmark evaluation metrics.

Calculates:
1. Complete 25-case table with all required columns:
   - case_id
   - drug
   - disease
   - expected_3class
   - epistemic_expected_class
   - prediction
   - recommendation
   - therapeutic_anchor
   - mechanistic_score
   - support_score
   - opposition_score
   - opposition_level
   - qualified_negative_claim_count
   - contradiction_state
   - rule_fired

2. Standard Metrics:
   - accuracy, macro precision, macro recall, macro F1, weighted F1, MCC

3. Epistemic Metrics:
   - accuracy, macro F1, weighted F1, MCC

4. Safety / Diagnostic Metrics:
   - empirically verified negative recall
   - false-PROMISING rate

5. Comparison against previous baseline:
   - Standard accuracy = 44% (11/25)
   - Epistemic accuracy = 68% (17/25)
"""
import json
import math
from pathlib import Path


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
    return num / den if den > 0 else 0.0


def compute_metrics(y_true: list[str], y_pred: list[str]) -> dict:
    labels = ["SUPPORT", "OPPOSE", "UNCERTAIN"]
    cm = {t: {p: 0 for p in labels} for t in labels}
    for t, p in zip(y_true, y_pred):
        if t in cm and p in cm[t]:
            cm[t][p] += 1

    total = len(y_true)
    correct = sum(cm[k][k] for k in labels)
    accuracy = correct / total if total > 0 else 0.0

    precisions = {}
    recalls = {}
    f1s = {}

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

    macro_p = sum(precisions.values()) / 3.0
    macro_r = sum(recalls.values()) / 3.0
    macro_f1 = sum(f1s.values()) / 3.0

    support_counts = {k: sum(cm[k][p] for p in labels) for k in labels}
    weighted_f1 = sum(f1s[k] * support_counts[k] for k in labels) / total if total > 0 else 0.0
    mcc = compute_mcc_3x3(cm, labels)

    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "macro_precision": macro_p,
        "macro_recall": macro_r,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "mcc": mcc,
        "per_class": {
            k: {
                "precision": precisions[k],
                "recall": recalls[k],
                "f1": f1s[k],
                "support": support_counts[k],
            }
            for k in labels
        },
        "cm": cm,
    }


def main():
    p = Path("evaluation_outputs/25_case/results.jsonl")
    if not p.exists():
        print("evaluation_outputs/25_case/results.jsonl not found!")
        return

    cases = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))

    print(f"Loaded {len(cases)} cases from {p}")
    if len(cases) == 0:
        return

    # Extract fields
    rows = []
    for c in cases:
        cid = c["case_id"]
        drug = c["drug"]
        disease = c["disease"]
        exp_3 = c["expected_3class"]
        epist_exp = c["epistemic_expected_class"]
        pred = c["prediction"]
        rec = c["recommendation"]

        # Therapeutic anchor detection
        sig = c.get("approval_signal") or {}
        is_app = sig.get("is_approved", False)
        high_qual = c.get("has_high_quality_therapeutic", False)
        term = sig.get("matched_indication_term", "")
        anchor = f"YES ({term})" if is_app else ("YES (CLINICAL)" if high_qual else "NO")

        ms = c.get("mechanistic_score", 0.0)
        ss = c.get("support_score", 0.0)
        opp_score = c.get("opposition_score", 0.0)
        opp_level = c.get("opposition_level", "NONE")
        qual_neg = c.get("qualified_negative_claim_count", 0)
        contra = c.get("contradiction_state", "NONE")

        # Rule fired extraction
        reasons = c.get("recommendation_reasons", [])
        rule_fired = "Rule 5 (UNCERTAIN)"
        for r in reasons:
            if "Rule -1" in r or "RULE -1" in r or "RULE_-1" in r:
                rule_fired = "Rule -1 (Approved Indication)"
                break
            elif "Rule 0" in r or "RULE 0" in r:
                rule_fired = "Rule 0 (Strong Opposition)"
                break
            elif "Rule 1b" in r or "RULE 1B" in r:
                rule_fired = "Rule 1b (Conflict -> Uncertain)"
                break
            elif "Rule 1" in r or "RULE 1" in r:
                rule_fired = "Rule 1 (High Quality Support)"
                break
            elif "Rule 2" in r or "RULE 2" in r:
                rule_fired = "Rule 2 (Futility/Safety Opposition)"
                break
            elif "Rule 3" in r or "RULE 3" in r:
                rule_fired = "Rule 3 (Mechanistic Plausibility)"
                break
            elif "Rule 4" in r or "RULE 4" in r:
                rule_fired = "Rule 4 (Strong Direct Evidence)"
                break
            elif "Rule 5" in r or "RULE 5" in r:
                rule_fired = "Rule 5 (Inconclusive Evidence)"
                break

        rows.append({
            "case_id": cid,
            "drug": drug,
            "disease": disease,
            "expected_3class": exp_3,
            "epistemic_expected_class": epist_exp,
            "prediction": pred,
            "recommendation": rec,
            "therapeutic_anchor": anchor,
            "mechanistic_score": ms,
            "support_score": ss,
            "opposition_score": opp_score,
            "opposition_level": opp_level,
            "qualified_negative_claim_count": qual_neg,
            "contradiction_state": contra,
            "rule_fired": rule_fired,
        })

    # Print Table
    print("\n" + "=" * 160)
    print(f"{'Case ID':<9} | {'Drug':<14} | {'Disease':<35} | {'Exp':<8} | {'Epist':<8} | {'Pred':<8} | {'Rec':<15} | {'Anchor':<18} | {'MS':<6} | {'SS':<6} | {'Opp':<6} | {'OppLvl':<7} | {'QNeg':<5} | {'Contra':<12} | {'Rule Fired'}")
    print("-" * 160)
    for r in rows:
        print(f"{r['case_id']:<9} | {r['drug']:<14} | {r['disease'][:35]:<35} | {r['expected_3class']:<8} | {r['epistemic_expected_class']:<8} | {r['prediction']:<8} | {r['recommendation']:<15} | {r['therapeutic_anchor'][:18]:<18} | {r['mechanistic_score']:<6.3f} | {r['support_score']:<6.3f} | {r['opposition_score']:<6.3f} | {r['opposition_level']:<7} | {r['qualified_negative_claim_count']:<5} | {r['contradiction_state'][:12]:<12} | {r['rule_fired']}")
    print("=" * 160)

    # Standard Metrics
    y_true_std = [r["expected_3class"] for r in rows]
    y_pred = [r["prediction"] for r in rows]
    std_m = compute_metrics(y_true_std, y_pred)

    # Epistemic Metrics (UNVERIFIED maps to UNCERTAIN)
    y_true_epist = ["UNCERTAIN" if r["epistemic_expected_class"] == "UNVERIFIED" else r["epistemic_expected_class"] for r in rows]
    epist_m = compute_metrics(y_true_epist, y_pred)

    # Empirically Verified Negative Recall
    # Ground truth OPPOSE cases among Category C (Contradictory/Negative)
    cat_c = [r for r in rows if r["epistemic_expected_class"] == "OPPOSE"]
    neg_recall = sum(1 for r in cat_c if r["prediction"] == "OPPOSE") / len(cat_c) if cat_c else 0.0

    # False-PROMISING Rate
    # True negatives/unverified (OPPOSE or UNCERTAIN) predicted as SUPPORT
    neg_or_unc = [r for r in rows if r["epistemic_expected_class"] in ("OPPOSE", "UNVERIFIED", "UNCERTAIN")]
    false_promising = sum(1 for r in neg_or_unc if r["prediction"] == "SUPPORT") / len(neg_or_unc) if neg_or_unc else 0.0

    print("\nSTANDARD METRICS (Benchmark closed-world ground truth):")
    print(f"  Accuracy:         {std_m['accuracy'] * 100:.1f}% ({std_m['correct']}/{std_m['total']})")
    print(f"  Macro Precision:  {std_m['macro_precision']:.4f}")
    print(f"  Macro Recall:     {std_m['macro_recall']:.4f}")
    print(f"  Macro F1:         {std_m['macro_f1']:.4f}")
    print(f"  Weighted F1:      {std_m['weighted_f1']:.4f}")
    print(f"  MCC:              {std_m['mcc']:.4f}")

    print("\nEPISTEMIC METRICS (Open-world scientific ground truth):")
    print(f"  Accuracy:         {epist_m['accuracy'] * 100:.1f}% ({epist_m['correct']}/{epist_m['total']})")
    print(f"  Macro F1:         {epist_m['macro_f1']:.4f}")
    print(f"  Weighted F1:      {epist_m['weighted_f1']:.4f}")
    print(f"  MCC:              {epist_m['mcc']:.4f}")

    print("\nSAFETY & DIAGNOSTIC METRICS:")
    print(f"  Empirically Verified Negative Recall: {neg_recall * 100:.1f}% ({sum(1 for r in cat_c if r['prediction'] == 'OPPOSE')}/{len(cat_c)})")
    print(f"  False-PROMISING Rate:                 {false_promising * 100:.1f}% ({sum(1 for r in neg_or_unc if r['prediction'] == 'SUPPORT')}/{len(neg_or_unc)})")

    print("\nCOMPARISON AGAINST BASELINE:")
    print(f"  Standard Accuracy:   44% (11/25) -> {std_m['accuracy'] * 100:.1f}% ({std_m['correct']}/{std_m['total']})")
    print(f"  Epistemic Accuracy:  68% (17/25) -> {epist_m['accuracy'] * 100:.1f}% ({epist_m['correct']}/{epist_m['total']})")


if __name__ == "__main__":
    main()
