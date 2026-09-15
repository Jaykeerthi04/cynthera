import json
from pathlib import Path

path = Path("evaluation_outputs/25_case_freeze_v3_2/results.jsonl")
if not path.exists():
    print("File does not exist yet.")
    exit(0)

with open(path, "r", encoding="utf-8") as f:
    lines = [l.strip() for l in f if l.strip()]

print(f"Progress: {len(lines)}/25 completed")
for l in lines:
    r = json.loads(l)
    cid = r.get("case_id")
    drug = r.get("drug")
    disease = r.get("disease")
    pred = r.get("prediction")
    exp = r.get("expected_3class")
    opp = r.get("opposition_score")
    ss = r.get("support_score")
    ms = r.get("mechanistic_score")
    rt = r.get("runtime_seconds")
    print(f"[{cid}] {drug} -> {disease}: pred={pred} (exp={exp}) [SS={ss}, MS={ms}, Opp={opp}] ({rt}s)")
