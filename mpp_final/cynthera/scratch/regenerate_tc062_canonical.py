import sys
sys.path.insert(0, ".")
import asyncio
import json
from pathlib import Path
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.evaluation.run_100_case_evaluation import evaluate_case

async def main():
    with open("scratch/manifest_100_cases.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)

    tc062_case = None
    for c in manifest:
        if c["case_id"] == "TC-062":
            tc062_case = c
            break

    print(f"Found case: {tc062_case}")
    orchestrator = MasterOrchestrator(use_cache=True)
    print("Running canonical evaluate_case for TC-062 through MasterOrchestrator...")
    res = await evaluate_case(tc062_case, orchestrator, timeout_seconds=120)

    print("\nCanonical evaluation result for TC-062:")
    for k in sorted(res.keys()):
        print(f"  {k}: {repr(res[k])}")

    # Now let's see: how does this record integrate cleanly into results.jsonl?
    # By replacing the old TC-062 line in results.jsonl with this exact generated record!
    jsonl_path = Path("evaluation_outputs/100_case_final/results.jsonl")
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    replaced = False
    for line in lines:
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("case_id") == "TC-062":
            new_lines.append(json.dumps(res))
            replaced = True
        else:
            new_lines.append(line)
    
    if not replaced:
        new_lines.append(json.dumps(res))
    
    jsonl_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"\nSuccessfully regenerated TC-062 record in {jsonl_path}")

asyncio.run(main())
