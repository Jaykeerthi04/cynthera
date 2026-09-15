import asyncio
import json
import sys
import os
sys.path.insert(0, os.path.abspath("."))
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator

async def inspect_phase4():
    orch = MasterOrchestrator()
    for name, chembl_id in [("Aspirin", "CHEMBL25"), ("Tamoxifen", "CHEMBL83"), ("Fluticasone Propionate", "CHEMBL1200749"), ("Fluticasone", "CHEMBL1201396")]:
        chembl_data = await orch._retrieval._fetch_chembl(chembl_id)
        ind_data = chembl_data.get("indications", {})
        indications = ind_data.get("indications", [])
        print(f"\n=== {name} ({chembl_id}) ===")
        print(f"Total indications: {len(indications)}")
        phase4 = [ind for ind in indications if int(ind.get("max_phase_for_ind") or 0) == 4]
        print(f"Phase 4 indications ({len(phase4)}):")
        for p in phase4:
            print(f"  efo_term='{p.get('efo_term')}' | mesh_heading='{p.get('mesh_heading')}'")

asyncio.run(inspect_phase4())
