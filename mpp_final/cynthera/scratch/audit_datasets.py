import json
import sys
from pathlib import Path

# 30-case holdout
p30 = Path("evaluation_outputs/30_case_holdout/results.json")
if p30.exists():
    with open(p30, "r", encoding="utf-8") as f:
        data30 = json.load(f)
    print(f"=== 30-Case Holdout Results (Total: {len(data30)}) ===")
    for c in data30:
        opp_score = c.get("opposition_score", 0.0)
        neg_count = c.get("qualified_negative_claim_count", 0)
        if opp_score > 0 or neg_count > 0:
            print(f"[{c['case_id']}] {c['drug']} -> {c['disease']}: opp_score={opp_score}, level={c.get('opposition_level')}, neg_claims={neg_count}")

# 25-case results.jsonl
p25 = Path("evaluation_outputs/25_case/results.jsonl")
if p25.exists():
    data25 = []
    with open(p25, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data25.append(json.loads(line.strip()))
    print(f"\n=== 25-Case Results (Total: {len(data25)}) ===")
    for c in data25:
        opp_score = c.get("opposition_score", 0.0)
        neg_count = c.get("qualified_negative_claim_count", 0)
        if opp_score > 0 or neg_count > 0:
            print(f"[{c.get('case_id')}] {c.get('drug')} -> {c.get('disease')}: opp_score={opp_score}, level={c.get('opposition_level')}, neg_claims={neg_count}")
