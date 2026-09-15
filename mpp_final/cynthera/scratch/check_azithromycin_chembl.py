import asyncio
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        url = "https://www.ebi.ac.uk/chembl/api/data/drug_indication.json?molecule_chembl_id=CHEMBL682"
        print("Querying Azithromycin:", url)
        resp = await client.get(url, timeout=10.0)
        print("Status:", resp.status_code)
        inds = resp.json().get("drug_indications", [])
        print("Indications count for Azithromycin (CHEMBL682):", len(inds))
        for ind in inds:
            term = f"{ind.get('efo_term')} | {ind.get('mesh_heading')}"
            phase = ind.get("max_phase_for_ind")
            if any(w in term.lower() for w in ["covid", "sars", "corona"]):
                print("  COVID Indication:", term, "phase:", phase)

asyncio.run(main())
