import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, ".")

# Load 25-case dataset
from backend.evaluation.run_25_case_evaluation import EVALUATION_CASES
# Load 30-case holdout dataset
from backend.evaluation.holdout_30_case_dataset import HOLDOUT_CASES

print(f"25-case count: {len(EVALUATION_CASES)}")
print(f"30-case holdout count: {len(HOLDOUT_CASES)}")

con = sqlite3.connect("data/cynthera.db")
cur = con.cursor()

def get_latest_package(drug: str, disease: str):
    cur.execute("""
        SELECT rp.data_json
        FROM hypotheses h
        JOIN retrieval_packages rp ON h.id = rp.hypothesis_id
        WHERE LOWER(h.drug_name) = LOWER(?) AND LOWER(h.disease_name) = LOWER(?)
        ORDER BY rp.sealed_at DESC
        LIMIT 1;
    """, (drug, disease))
    row = cur.fetchone()
    if row:
        return json.loads(row[0])
    return None

all_benchmark_cases = []
for c in EVALUATION_CASES:
    all_benchmark_cases.append({
        "dataset": "25_case_regression",
        "case_id": c["case_id"],
        "drug": c["drug"],
        "disease": c["disease"],
        "expected_label": c.get("expected_label")
    })

for c in HOLDOUT_CASES:
    all_benchmark_cases.append({
        "dataset": "30_case_holdout",
        "case_id": c.case_id,
        "drug": c.drug,
        "disease": c.disease,
        "expected_label": c.expected_label
    })

print(f"Total benchmark cases to scan: {len(all_benchmark_cases)}")

terminated_trials_found = []
missing_packages = []

for case in all_benchmark_cases:
    pkg = get_latest_package(case["drug"], case["disease"])
    if not pkg:
        missing_packages.append(f"{case['drug']} -> {case['disease']}")
        continue
    trials = pkg.get("clinical_trials", [])
    for t in trials:
        status = t.get("status")
        # In domain, status can be string enum value or int
        why_stopped = t.get("why_stopped")
        if status in ("TERMINATED_LACK_OF_EFFICACY", "TERMINATED_SAFETY") or (why_stopped and any(w in str(why_stopped).lower() for w in ("efficacy", "futility", "safety", "harm", "benefit"))):
            terminated_trials_found.append({
                "dataset": case["dataset"],
                "case_id": case["case_id"],
                "drug": case["drug"],
                "disease": case["disease"],
                "nct_id": t.get("nct_id"),
                "title": t.get("title"),
                "phase": t.get("phase"),
                "status": status,
                "why_stopped": why_stopped,
                "intervention_names": t.get("intervention_names", []),
                "comparator_names": t.get("comparator_names", [])
            })

print(f"Missing packages: {len(missing_packages)}: {missing_packages}")
print(f"Total terminated/futility trials found across both datasets: {len(terminated_trials_found)}")

with open("scratch/corpus_negative_trials.json", "w", encoding="utf-8") as f:
    json.dump(terminated_trials_found, f, indent=2)

for item in terminated_trials_found:
    print(f"[{item['dataset']}] {item['case_id']} | {item['drug']} -> {item['disease']} | {item['nct_id']} ({item['phase']}) | status={item['status']}")
    print(f"   Title: {item['title']}")
    print(f"   Interventions: {item['intervention_names']}")
    print(f"   Comparators: {item['comparator_names']}")
    print(f"   Why Stopped: {item['why_stopped']}")
    print("-" * 60)

con.close()
