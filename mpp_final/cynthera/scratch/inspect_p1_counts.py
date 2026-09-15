import json
from pathlib import Path

results_100_path = Path("evaluation_outputs/100_case_final/results.jsonl")
cases_to_check = ["TC-019", "TC-047", "TC-053", "TC-062"]

with open(results_100_path, "r", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        cid = d.get("case_id")
        if cid in cases_to_check:
            print(f"Case: {cid}")
            print(f"  support_score: {d.get('support_score')}")
            print(f"  literature_claims_count: {d.get('literature_claims_count')}")
            print(f"  evidence_record_count: {d.get('evidence_record_count')}")
            print(f"  decision_rule: {d.get('decision_rule')}")
