import json
from pathlib import Path

target_ids = [
    "CYN-013", "CYN-026", "CYN-041", "CYN-003", "CYN-023", "CYN-036", "CYN-044",
    "CYN-125", "CYN-109", "CYN-299", "CYN-277",
    "CYN-251", "CYN-284",
    "CYN-186", "CYN-200",
    "CYN-103"
]

cases = {}
results_file = Path("evaluation_outputs/25_case/results.jsonl")
with open(results_file, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        cases[rec["case_id"]] = rec

baseline = {}
for cid in target_ids:
    if cid in cases:
        r = cases[cid]
        sig = r.get("approval_signal") or {}
        baseline[cid] = {
            "case_id": cid,
            "drug": r.get("drug"),
            "disease": r.get("disease"),
            "approval_signal": sig,
            "matched_indication_term": sig.get("matched_indication_term"),
            "match_confidence": sig.get("match_confidence"),
            "max_phase": sig.get("max_phase"),
            "evaluation_pathway": sig.get("evaluation_pathway"),
            "has_high_quality_therapeutic": r.get("has_high_quality_therapeutic"),
            "therapeutic_evidence_audit": r.get("therapeutic_evidence_audit"),
            "opposition_score": r.get("opposition_score"),
            "opposition_level": r.get("opposition_level"),
            "qualified_negative_claim_count": r.get("qualified_negative_claim_count"),
            "prediction": r.get("prediction"),
            "recommendation": r.get("recommendation"),
            "decision_gate": r.get("decision_gate")
        }

out_file = Path("scratch/phase0_baseline.json")
with open(out_file, "w", encoding="utf-8") as out:
    json.dump(baseline, out, indent=2)

print(f"Captured {len(baseline)} cases to {out_file}")
