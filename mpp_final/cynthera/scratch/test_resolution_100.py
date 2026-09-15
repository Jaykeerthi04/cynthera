"""Test identifier resolution across all 100 cases using resolve_drug and resolve_disease.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))

from backend.engineering.identity.resolution_service import IdentifierResolutionService

async def main():
    with open("scratch/manifest_100_cases.json") as f:
        manifest = json.load(f)

    resolver = IdentifierResolutionService()
    resolved = []
    unresolved = []

    print(f"Testing resolution for {len(manifest)} cases...")
    for idx, item in enumerate(manifest, 1):
        drug = item["drug"]
        disease = item["disease"]
        cid = item["case_id"]
        try:
            d_ids, dis_ids = await asyncio.gather(
                resolver.resolve_drug(drug),
                resolver.resolve_disease(disease)
            )
            chembl = d_ids.chembl_id if hasattr(d_ids, 'chembl_id') else (d_ids.primary_id.identifier_value if d_ids.primary_id else 'UNKNOWN')
            mesh = dis_ids.mesh_id if hasattr(dis_ids, 'mesh_id') else (dis_ids.primary_id.identifier_value if dis_ids.primary_id else 'UNKNOWN')
            resolved.append({
                "case_id": cid,
                "drug": drug,
                "disease": disease,
                "drug_chembl": chembl,
                "disease_mesh": mesh,
            })
            print(f"[{idx}/100] OK: {cid} | {drug} ({chembl}) -> {disease} ({mesh})")
        except Exception as exc:
            unresolved.append({
                "case_id": cid,
                "drug": drug,
                "disease": disease,
                "error": f"{type(exc).__name__}: {exc}"
            })
            print(f"[{idx}/100] FAILED: {cid} | {drug} -> {disease} | {type(exc).__name__}: {exc}")

    print(f"\n==========================================")
    print(f"RESOLUTION SUMMARY:")
    print(f"Resolved: {len(resolved)}/100")
    print(f"Unresolved: {len(unresolved)}/100")
    if unresolved:
        print("Unresolved cases:")
        for u in unresolved:
            print(f"  {u['case_id']}: {u['drug']} -> {u['disease']} ({u['error']})")

if __name__ == "__main__":
    asyncio.run(main())
