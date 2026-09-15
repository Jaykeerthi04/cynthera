import asyncio
import httpx

async def check():
    drugs = [
        ("Pregabalin", "CHEMBL1059"),
        ("Atorvastatin", "CHEMBL1487"),
        ("Fluvoxamine", "CHEMBL633"),
        ("Imatinib", "CHEMBL941"),
    ]
    async with httpx.AsyncClient() as client:
        for drug_name, chembl_id in drugs:
            url = f"https://www.ebi.ac.uk/chembl/api/data/drug_indication.json?molecule_chembl_id={chembl_id}"
            resp = await client.get(url, timeout=10.0)
            inds = resp.json().get("drug_indications", [])
            print(f"\n{drug_name} ({chembl_id}) - {len(inds)} indications:")
            for ind in inds:
                term = f"{ind.get('efo_term')} | {ind.get('mesh_heading')}"
                phase = ind.get("max_phase_for_ind")
                print(f"  {term} -> phase {phase}")

asyncio.run(check())
