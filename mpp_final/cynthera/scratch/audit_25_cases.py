import json
import math
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

with open("evaluation_outputs/25_case_repaired/results.json") as f:
    cases = json.load(f)

# Also load our newly run 10-case diagnostic to see how Phase 5.16 updated predictions
try:
    with open("phase_5_16_10_case_diagnostic.json") as f:
        diag10 = {c["case_id"]: c for c in json.load(f)}
except Exception:
    diag10 = {}

print(f"Loaded {len(cases)} cases from 25_case_repaired.")
print(f"Loaded {len(diag10)} cases from phase_5_16_10_case_diagnostic.json.")

def compute_metrics_table(y_true, y_pred, labels=["SUPPORT", "OPPOSE", "UNCERTAIN"]):
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
    supports = {}

    for k in labels:
        tp = cm[k][k]
        fp = sum(cm[t][k] for t in labels if t != k)
        fn = sum(cm[k][p] for p in labels if p != k)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        precisions[k] = prec
        recalls[k] = rec
        f1s[k] = f1
        supports[k] = sum(cm[k][p] for p in labels)

    macro_prec = sum(precisions.values()) / len(labels)
    macro_rec = sum(recalls.values()) / len(labels)
    macro_f1 = sum(f1s.values()) / len(labels)

    weighted_f1 = sum(f1s[k] * supports[k] for k in labels) / total if total > 0 else 0.0

    # MCC 3x3
    n = total
    c = sum(cm[k][k] for k in labels)
    p_k = {k: sum(cm[t][k] for t in labels) for k in labels}
    t_k = {k: sum(cm[k][p] for p in labels) for k in labels}

    num = c * n - sum(p_k[k] * t_k[k] for k in labels)
    den1 = n**2 - sum(p_k[k] ** 2 for k in labels)
    den2 = n**2 - sum(t_k[k] ** 2 for k in labels)
    den = math.sqrt(den1 * den2)
    mcc = num / den if den > 0 else 0.0

    return {
        "accuracy": accuracy,
        "macro_precision": macro_prec,
        "macro_recall": macro_rec,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "mcc": mcc,
        "cm": cm,
        "per_class": {
            k: {"precision": precisions[k], "recall": recalls[k], "f1": f1s[k], "support": supports[k]}
            for k in labels
        }
    }

print("\n" + "=" * 110)
print("CASE LISTING (Baseline 25 cases):")
print(f"{'Case ID':<8} | {'Drug':<14} | {'Disease':<35} | {'Category':<20} | {'Exp':<8} | {'Epist':<8} | {'Pred':<8} | {'Rec':<15}")
print("-" * 110)

y_true_3class = []
y_true_epistemic = []
y_pred_baseline = []
y_pred_phase516 = []

for c in cases:
    cid = c["case_id"]
    drug = c["drug"]
    disease = c["disease"]
    cat = c["category"]
    exp3 = c["expected_3class"]
    epist = c.get("epistemic_expected_class", exp3)
    if epist == "UNVERIFIED":
        epist = "UNCERTAIN"
    
    pred_base = c["prediction"]
    
    # Check if we have updated Phase 5.16 result for this case
    if cid in diag10:
        pred_p516 = diag10[cid]["prediction"]
    else:
        pred_p516 = pred_base
        
    y_true_3class.append(exp3)
    y_true_epistemic.append(epist)
    y_pred_baseline.append(pred_base)
    y_pred_phase516.append(pred_p516)
    
    print(f"{cid:<8} | {drug:<14} | {disease[:35]:<35} | {cat:<20} | {exp3:<8} | {epist:<8} | {pred_base:<8} | {c['recommendation']:<15}")

print("\n" + "=" * 110)
print("EVALUATION A: Baseline Predictions vs Expected 3-Class (Standard Benchmark)")
m_a = compute_metrics_table(y_true_3class, y_pred_baseline)
print(f"Accuracy:        {m_a['accuracy']:.4f} ({int(m_a['accuracy']*25)}/25)")
print(f"Macro Precision: {m_a['macro_precision']:.4f}")
print(f"Macro Recall:    {m_a['macro_recall']:.4f}")
print(f"Macro F1:        {m_a['macro_f1']:.4f}")
print(f"Weighted F1:     {m_a['weighted_f1']:.4f}")
print(f"MCC:             {m_a['mcc']:.4f}")
print("Confusion Matrix (Rows = True, Cols = Pred):")
print("               SUPPORT  OPPOSE  UNCERTAIN")
for row in ["SUPPORT", "OPPOSE", "UNCERTAIN"]:
    print(f"  {row:<11} {m_a['cm'][row]['SUPPORT']:<8} {m_a['cm'][row]['OPPOSE']:<7} {m_a['cm'][row]['UNCERTAIN']:<9}")

print("\n" + "=" * 110)
print("EVALUATION B: Baseline Predictions vs Epistemic Expected Class (UNVERIFIED -> UNCERTAIN)")
m_b = compute_metrics_table(y_true_epistemic, y_pred_baseline)
print(f"Accuracy:        {m_b['accuracy']:.4f} ({int(m_b['accuracy']*25)}/25)")
print(f"Macro Precision: {m_b['macro_precision']:.4f}")
print(f"Macro Recall:    {m_b['macro_recall']:.4f}")
print(f"Macro F1:        {m_b['macro_f1']:.4f}")
print(f"Weighted F1:     {m_b['weighted_f1']:.4f}")
print(f"MCC:             {m_b['mcc']:.4f}")
print("Confusion Matrix (Rows = True, Cols = Pred):")
print("               SUPPORT  OPPOSE  UNCERTAIN")
for row in ["SUPPORT", "OPPOSE", "UNCERTAIN"]:
    print(f"  {row:<11} {m_b['cm'][row]['SUPPORT']:<8} {m_b['cm'][row]['OPPOSE']:<7} {m_b['cm'][row]['UNCERTAIN']:<9}")

print("\n" + "=" * 110)
print("EVALUATION C: Phase 5.16 Post-Diagnostic Predictions vs Expected 3-Class")
m_c = compute_metrics_table(y_true_3class, y_pred_phase516)
print(f"Accuracy:        {m_c['accuracy']:.4f} ({int(m_c['accuracy']*25)}/25)")
print(f"Macro Precision: {m_c['macro_precision']:.4f}")
print(f"Macro Recall:    {m_c['macro_recall']:.4f}")
print(f"Macro F1:        {m_c['macro_f1']:.4f}")
print(f"Weighted F1:     {m_c['weighted_f1']:.4f}")
print(f"MCC:             {m_c['mcc']:.4f}")
print("Confusion Matrix:")
for row in ["SUPPORT", "OPPOSE", "UNCERTAIN"]:
    print(f"  {row:<11} {m_c['cm'][row]['SUPPORT']:<8} {m_c['cm'][row]['OPPOSE']:<7} {m_c['cm'][row]['UNCERTAIN']:<9}")

print("\n" + "=" * 110)
print("EVALUATION D: Phase 5.16 Post-Diagnostic Predictions vs Epistemic Expected Class")
m_d = compute_metrics_table(y_true_epistemic, y_pred_phase516)
print(f"Accuracy:        {m_d['accuracy']:.4f} ({int(m_d['accuracy']*25)}/25)")
print(f"Macro Precision: {m_d['macro_precision']:.4f}")
print(f"Macro Recall:    {m_d['macro_recall']:.4f}")
print(f"Macro F1:        {m_d['macro_f1']:.4f}")
print(f"Weighted F1:     {m_d['weighted_f1']:.4f}")
print(f"MCC:             {m_d['mcc']:.4f}")
print("Confusion Matrix:")
for row in ["SUPPORT", "OPPOSE", "UNCERTAIN"]:
    print(f"  {row:<11} {m_d['cm'][row]['SUPPORT']:<8} {m_d['cm'][row]['OPPOSE']:<7} {m_d['cm'][row]['UNCERTAIN']:<9}")
