import json
from backend.evaluation.run_25_case_evaluation import EVALUATION_CASES
from backend.evaluation.holdout_30_case_dataset import HOLDOUT_CASES

print(f"=== 25-CASE REGRESSION BENCHMARK ({len(EVALUATION_CASES)} cases) ===")
for c in EVALUATION_CASES:
    print(f"  {c['case_id']}: {c['drug']} -> {c['disease']} | {c['category']} | expected: {c['expected_label']}")

print(f"\n=== 30-CASE HOLDOUT BENCHMARK ({len(HOLDOUT_CASES)} cases) ===")
for c in HOLDOUT_CASES:
    print(f"  {c.case_id}: {c.drug} -> {c.disease} | {c.category} | expected: {c.expected_label}")
