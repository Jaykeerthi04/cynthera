import json
import os

filepath = "evaluation_outputs/25_case_freeze_v3_2/results.jsonl"
if not os.path.exists(filepath):
    print("File not found.")
    exit(0)

with open(filepath, "r", encoding="utf-8") as f:
    lines = [line.strip() for line in f if line.strip()]

print(f"Total cases completed so far: {len(lines)}/25")
for i, line in enumerate(lines, 1):
    data = json.loads(line)
    case_id = str(data.get("case_id"))
    drug = str(data.get("drug"))
    disease = str(data.get("disease"))
    pred = str(data.get("prediction"))
    exp = str(data.get("expected_label") or data.get("expected"))
    rec = str(data.get("recommendation"))
    rule = str(data.get("rule_fired"))
    opp = str(data.get("opposition_score"))
    print(f"[{i:02d}] {case_id:8s} | {drug:15s} -> {disease:25s} | pred: {pred:10s} (exp: {exp:10s}) | rec: {rec} | rule: {rule}")
