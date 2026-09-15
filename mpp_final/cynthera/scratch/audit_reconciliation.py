import json
import math
from collections import Counter
from pathlib import Path

ledger_path = Path("backend/evaluation/post_clinicaltrials_50_fast_ledger.json")
with open(ledger_path, "r", encoding="utf-8") as f:
    ledger = json.load(f)

cases = ledger["cases"]
controls = ledger["controls"]
target_trials = ledger["target_trials"]
reported_metrics = ledger["metrics"]

print(f"Loaded {len(cases)} cases, {len(controls)} controls, {len(target_trials)} target trials.")

# 1. Recompute 3-class confusion matrix and metrics
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

def calc_metrics(y_true: list[str], y_pred: list[str]):
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
        "total": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "balanced_accuracy": round(balanced_acc, 4),
        "macro_precision": round(macro_p, 4),
        "macro_recall": round(macro_r, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "mcc": round(mcc, 4),
        "confusion_matrix": cm,
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
        }
    }

std_golds = [c["standard_gold"] for c in cases]
epi_golds = [c["epistemic_gold"] for c in cases]
base_preds = [c["baseline_prediction"] for c in cases]
post_preds = [c["prediction"] for c in cases]

recomp_b_std = calc_metrics(std_golds, base_preds)
recomp_p_std = calc_metrics(std_golds, post_preds)
recomp_b_epi = calc_metrics(epi_golds, base_preds)
recomp_p_epi = calc_metrics(epi_golds, post_preds)

print("\n--- STANDARD METRICS RECOMPUTATION ---")
print("Baseline Standard:", recomp_b_std["accuracy"], recomp_b_std["balanced_accuracy"], recomp_b_std["macro_f1"], recomp_b_std["mcc"])
print("Post-Fix Standard:", recomp_p_std["accuracy"], recomp_p_std["balanced_accuracy"], recomp_p_std["macro_f1"], recomp_p_std["mcc"])

print("\n--- EPISTEMIC METRICS RECOMPUTATION ---")
print("Baseline Epistemic:", recomp_b_epi["accuracy"], recomp_b_epi["balanced_accuracy"], recomp_b_epi["macro_f1"], recomp_b_epi["mcc"])
print("Post-Fix Epistemic:", recomp_p_epi["accuracy"], recomp_p_epi["balanced_accuracy"], recomp_p_epi["macro_f1"], recomp_p_epi["mcc"])

print("\nConfusion Matrix Baseline Standard:", recomp_b_std["confusion_matrix"])
print("Confusion Matrix Post-Fix Standard:", recomp_p_std["confusion_matrix"])
