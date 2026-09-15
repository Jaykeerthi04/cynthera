import json
from pathlib import Path

path = Path("scratch/selected_100_cases.json")
if not path.exists():
    print("File does not exist:", path)
    exit(1)

with open(path, "r", encoding="utf-8") as f:
    cases = json.load(f)

target_ids = {
    "CYN-003", "CYN-013", "CYN-251", "CYN-260", "CYN-261",
    "CYN-179", "CYN-186", "CYN-200", "CYN-109", "CYN-103"
}
selected = [c for c in cases if c["case_id"] in target_ids]
# Sort by target_ids order:
order = ["CYN-003", "CYN-013", "CYN-251", "CYN-260", "CYN-261", "CYN-179", "CYN-186", "CYN-200", "CYN-109", "CYN-103"]
selected.sort(key=lambda x: order.index(x["case_id"]) if x["case_id"] in order else 99)

for c in selected:
    print(f"{c['case_id']}: {c['drug']} -> {c['disease']} | 3class: {c.get('expected_3class')} | epistemic: {c.get('epistemic_expected_class')}")
