"""Audit script to compile Section 16 targeted real-case matrix.
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

CASES_10 = [
    ("Niacin", "Cardiovascular disease"),
    ("Dexamethasone", "Traumatic brain injury"),
    ("Nivolumab", "Glioblastoma"),
    ("Pioglitazone", "Alzheimer's disease"),
    ("Metformin", "Type 2 diabetes"),
    ("Ivermectin", "COVID-19"),
    ("Fluvoxamine", "COVID-19"),
    ("Simvastatin", "Alzheimer's disease"),
    ("Aspirin", "Hemorrhagic stroke"),
    ("Furosemide", "Depression"),
]

def load_old_results():
    path = "evaluation_outputs/100_case_final/results.jsonl"
    old_data = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                d = record.get("drug", "").lower().strip()
                dis = record.get("disease", "").lower().strip()
                old_data[(d, dis)] = record
    return old_data

old_map = load_old_results()
print("Found old records:", len(old_map))
for drug, disease in CASES_10:
    rec = old_map.get((drug.lower(), disease.lower()))
    if rec:
        print(f"{drug} -> {disease}: Old Pred={rec.get('prediction')} | Old OppScore={rec.get('opposition_score')} | Rule={rec.get('decision_rule')[:40]}...")
    else:
        print(f"{drug} -> {disease}: NOT FOUND in 100-case final results")
