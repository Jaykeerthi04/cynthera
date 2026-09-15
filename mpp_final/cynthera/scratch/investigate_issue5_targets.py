"""Forensic investigation of ClinicalTrials.gov for the 4 Issue 5 target cases.

Target Cases:
1. Ivermectin -> COVID-19
2. Celecoxib -> Alzheimer's disease
3. Simvastatin -> Sepsis
4. Interferon beta-1a -> COVID-19
"""

import asyncio
import json
import urllib.request
import urllib.parse
from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector

CASES = [
    ("Ivermectin", "COVID-19"),
    ("Celecoxib", "Alzheimer's disease"),
    ("Simvastatin", "Sepsis"),
    ("Interferon beta-1a", "COVID-19"),
]


async def investigate():
    async with ClinicalTrialsConnector() as conn:
        for drug, disease in CASES:
            print(f"\n{'='*70}\nINVESTIGATING: {drug} -> {disease}\n{'='*70}")
            try:
                data = await conn.fetch(drug, disease, max_results=20)
            except Exception as e:
                print(f"Error fetching from ClinicalTrialsConnector: {e}")
                continue
                
            studies = data.get("studies", [])
            print(f"Total studies returned: {len(studies)}")
            
            with_results = 0
            completed = 0
            terminated = 0
            
            for s in studies:
                protocol = s.get("protocolSection", {})
                ident = protocol.get("identificationModule", {})
                nct_id = ident.get("nctId", "UNKNOWN")
                status_mod = protocol.get("statusModule", {})
                overall_status = status_mod.get("overallStatus", "UNKNOWN")
                why_stopped = status_mod.get("whyStopped", "")
                has_results = s.get("hasResults", False)
                results_sec = s.get("resultsSection", {})
                
                if overall_status == "COMPLETED":
                    completed += 1
                elif overall_status in ("TERMINATED", "SUSPENDED", "WITHDRAWN"):
                    terminated += 1
                if has_results or results_sec:
                    with_results += 1
                    print(f"\n  [HAS RESULTS] {nct_id} | Status: {overall_status} | Why Stopped: {why_stopped}")
                    outcome_mod = results_sec.get("outcomeMeasuresModule", {})
                    outcomes = outcome_mod.get("outcomeMeasures", [])
                    print(f"    Outcome measures count: {len(outcomes)}")
                    for om in outcomes[:3]:
                        print(f"      - {om.get('type')}: {om.get('title')}")
                        for ana in om.get("analyses", [])[:2]:
                            print(f"        Analysis: p-value={ana.get('pValue')}, stat_method={ana.get('statisticalMethod')}, nonInferiority={ana.get('nonInferiorityType')}")
                else:
                    if overall_status in ("TERMINATED", "SUSPENDED", "WITHDRAWN"):
                        print(f"  [TERMINATED NO RESULTS] {nct_id} | Status: {overall_status} | Why Stopped: {why_stopped}")
                        
            print(f"\nSummary for {drug} -> {disease}: Total={len(studies)}, Completed={completed}, Terminated={terminated}, WithResults={with_results}")


if __name__ == "__main__":
    asyncio.run(investigate())
