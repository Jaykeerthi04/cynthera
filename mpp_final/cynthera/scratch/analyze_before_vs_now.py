import json
import math
import sys
from collections import Counter
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

cids = [c["case_id"] for c in resolved_50]
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

print("=== STANDARD 3-CLASS METRICS ===")
print("Metric | BEFORE | NOW | Delta")
for k in ["accuracy", "balanced_accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1", "mcc"]:
    vb = m_before_std[k]
    vn = m_now_std[k]
    d = vn - vb
    print(f"{k:20s} | {vb:.4f} | {vn:.4f} | {d:+.4f}")

print("\n=== EPISTEMIC 3-CLASS METRICS ===")
print("Metric | BEFORE | NOW | Delta")
for k in ["accuracy", "balanced_accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1", "mcc"]:
    vb = m_before_epi[k]
    vn = m_now_epi[k]
    d = vn - vb
    print(f"{k:20s} | {vb:.4f} | {vn:.4f} | {d:+.4f}")

# Transitions
print("\n=== PREDICTION TRANSITIONS ===")
transitions = []
for cid in cids:
    b_p = before_cases[cid]["prediction"]
    n_p = now_cases[cid]["prediction"]
    std_g = before_cases[cid]["standard_gold"]
    epi_g = before_cases[cid]["epistemic_gold"]
    drug = before_cases[cid]["drug"]
    dis = before_cases[cid]["disease"]

    c_b = (b_p == std_g)
    c_n = (n_p == std_g)

    if c_b and c_n:
        trans_type = "UNCHANGED_CORRECT"
    elif (not c_b) and (not c_n):
        trans_type = "UNCHANGED_INCORRECT"
    elif (not c_b) and c_n:
        trans_type = "IMPROVED"
    else:
        trans_type = "REGRESSED"

    if b_p != n_p:
        transitions.append({
            "case_id": cid,
            "drug": drug,
            "disease": dis,
            "gold": std_g,
            "before": b_p,
            "now": n_p,
            "correct_before": c_b,
            "correct_now": c_n,
            "transition": trans_type,
            "b_opp": before_cases[cid]["opposition_score"],
            "n_opp": now_cases[cid]["opposition_score"],
            "b_rule": before_cases[cid]["decision_rule"][:40],
            "n_rule": now_cases[cid]["decision_rule"][:40],
        })

print(f"Total transitioned cases (BEFORE != NOW): {len(transitions)}")
for t in transitions:
    print(f"  {t['case_id']} {t['drug']} -> {t['disease']}: Gold={t['gold']} | Before={t['before']} -> Now={t['now']} | {t['transition']}")

# Safety diagnostics
def calc_diagnostics(preds, golds):
    fp_cnt = sum(1 for p, g in zip(preds, golds) if p == "SUPPORT" and g == "OPPOSE")
    fo_cnt = sum(1 for p, g in zip(preds, golds) if p == "OPPOSE" and g == "SUPPORT")
    opp_corr = sum(1 for p, g in zip(preds, golds) if p == "OPPOSE" and g == "OPPOSE")
    supp_corr = sum(1 for p, g in zip(preds, golds) if p == "SUPPORT" and g == "SUPPORT")
    unc_cnt = sum(1 for p in preds if p == "UNCERTAIN")
    unc_corr = sum(1 for p, g in zip(preds, golds) if p == "UNCERTAIN" and g == "UNCERTAIN")

    hard_negs = [p for p, g in zip(preds, golds) if g == "OPPOSE"]
    hn_total = len(hard_negs)
    hn_unc = sum(1 for p in hard_negs if p == "UNCERTAIN")
    hn_fp = sum(1 for p in hard_negs if p == "SUPPORT")
    hn_fo = 0 # Cannot falsely oppose an OPPOSE gold

    return {
        "false_promising_count": fp_cnt,
        "false_promising_rate": round(fp_cnt / len(preds), 4),
        "false_oppose_count": fo_cnt,
        "false_oppose_rate": round(fo_cnt / len(preds), 4),
        "correct_oppose_count": opp_corr,
        "oppose_recall": round(opp_corr / hn_total, 4) if hn_total > 0 else 0.0,
        "correct_support_count": supp_corr,
        "support_recall": round(supp_corr / 26, 4),
        "uncertain_count": unc_cnt,
        "uncertain_correctness": round(unc_corr / unc_cnt, 4) if unc_cnt > 0 else 0.0,
        "hard_neg_uncertainty": round(hn_unc / hn_total, 4) if hn_total > 0 else 0.0,
        "hard_neg_fp": round(hn_fp / hn_total, 4) if hn_total > 0 else 0.0,
    }

diag_b = calc_diagnostics(before_std_preds, std_golds)
diag_n = calc_diagnostics(now_std_preds, std_golds)

print("\n=== SAFETY-CRITICAL DIAGNOSTICS ===")
print("Diagnostic | BEFORE | NOW | Delta")
for k in diag_b:
    vb = diag_b[k]
    vn = diag_n[k]
    d = vn - vb
    print(f"{k:25s} | {vb} | {vn} | {d:+.4f}" if isinstance(vb, float) else f"{k:25s} | {vb} | {vn} | {d:+d}")

