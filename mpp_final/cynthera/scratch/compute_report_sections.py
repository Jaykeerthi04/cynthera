import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, ".")

with open("backend/evaluation/before_vs_now_50_end_to_end_ledger.json", "r", encoding="utf-8") as f:
    ledger = json.load(f)

cases = ledger["cases"]
m_std_b = ledger["metrics"]["standard_3class"]["before"]
m_std_n = ledger["metrics"]["standard_3class"]["now"]
m_epi_b = ledger["metrics"]["epistemic_3class"]["before"]
m_epi_n = ledger["metrics"]["epistemic_3class"]["now"]

print("=== 1. SCORE DISTRIBUTIONS (BEFORE vs NOW) ===")
for name in ["support_score", "mechanistic_score", "risk_score", "opposition_score"]:
    b_vals = [c["before"][name] for c in cases]
    n_vals = [c["now"][name] for c in cases]
    print(f"--- {name} ---")
    print(f"  BEFORE: min={min(b_vals):.4f}, max={max(b_vals):.4f}, median={statistics.median(b_vals):.4f}, mean={statistics.mean(b_vals):.4f}")
    print(f"  NOW:    min={min(n_vals):.4f}, max={max(n_vals):.4f}, median={statistics.median(n_vals):.4f}, mean={statistics.mean(n_vals):.4f}")

ss_now = [c["now"]["support_score"] for c in cases]
print(f"SS > 0.90 count: {sum(1 for s in ss_now if s > 0.90)} / 50")
print(f"SS > 0.95 count: {sum(1 for s in ss_now if s > 0.95)} / 50")
print(f"SS > 0.98 count: {sum(1 for s in ss_now if s > 0.98)} / 50")

print("\n=== 2. EPISTEMIC QUALITY / CONDITIONAL MATRICES ===")
# Gold SUPPORT
for label, cm in [("BEFORE", m_std_b["confusion_matrix"]), ("NOW", m_std_n["confusion_matrix"])]:
    print(f"{label} Gold SUPPORT: SUPPORT={cm['SUPPORT']['SUPPORT']}, UNCERTAIN={cm['SUPPORT']['UNCERTAIN']}, OPPOSE={cm['SUPPORT']['OPPOSE']}")
    print(f"{label} Gold OPPOSE:  OPPOSE={cm['OPPOSE']['OPPOSE']}, UNCERTAIN={cm['OPPOSE']['UNCERTAIN']}, SUPPORT={cm['OPPOSE']['SUPPORT']}")
    print(f"{label} Gold UNCERTAIN: UNCERTAIN={cm['UNCERTAIN']['UNCERTAIN']}, SUPPORT={cm['UNCERTAIN']['SUPPORT']}, OPPOSE={cm['UNCERTAIN']['OPPOSE']}")

# Uncertainty metrics
unc_p_b = m_std_b["per_class"]["UNCERTAIN"]["precision"]
unc_r_b = m_std_b["per_class"]["UNCERTAIN"]["recall"]
unc_f1_b = m_std_b["per_class"]["UNCERTAIN"]["f1"]
unc_p_n = m_std_n["per_class"]["UNCERTAIN"]["precision"]
unc_r_n = m_std_n["per_class"]["UNCERTAIN"]["recall"]
unc_f1_n = m_std_n["per_class"]["UNCERTAIN"]["f1"]

print(f"Uncertainty precision: BEFORE={unc_p_b:.4f}, NOW={unc_p_n:.4f}")
print(f"Uncertainty recall:    BEFORE={unc_r_b:.4f}, NOW={unc_r_n:.4f}")
print(f"Uncertainty F1:        BEFORE={unc_f1_b:.4f}, NOW={unc_f1_n:.4f}")

print("\n=== 3. ROOT CAUSE SUMMARY FOR NOW ERRORS ===")
from collections import Counter
rc_p_counter = Counter()
rc_s_counter = Counter()
err_cases = []
for c in cases:
    if not c["change_analysis"]["correct_now"]:
        err_cases.append(c)
        rc_p_counter[c["root_cause_analysis"]["primary_root_cause"]] += 1
        rc_s_counter[c["root_cause_analysis"]["secondary_root_cause"]] += 1

print(f"Total NOW Errors: {len(err_cases)} / 50")
print("Primary Root Causes:")
for k, v in rc_p_counter.most_common():
    print(f"  {k}: {v}")
print("Secondary Root Causes:")
for k, v in rc_s_counter.most_common():
    print(f"  {k}: {v}")

print("\n=== 4. KEY CASES REVIEW ===")
key_cids = [
    "TC-019", "TC-023", "TC-025", "TC-026", "TC-030", "TC-043", "TC-053", "TC-056",
    "TC-058", "TC-062", "TC-072", "TC-079", "TC-081", "TC-082", "TC-085", "TC-088"
]
for c in cases:
    if c["case_id"] in key_cids:
        print(f"{c['case_id']} {c['drug']} -> {c['disease']}: Gold={c['standard_gold']} | Before={c['before']['prediction']} | Now={c['now']['prediction']} | Trans={c['change_analysis']['transition']} | Driver={c['change_analysis']['primary_change_driver']} | PRoot={c['root_cause_analysis']['primary_root_cause']}")

