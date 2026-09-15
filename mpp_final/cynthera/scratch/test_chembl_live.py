import asyncio
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        url = "https://www.ebi.ac.uk/chembl/api/data/drug_indication.json?molecule_chembl_id=CHEMBL419213"
        print("Querying:", url)
        resp = await client.get(url, timeout=10.0)
        print("Status:", resp.status_code)
        inds = resp.json().get("drug_indications", [])
        print("Indications count for Lisinopril (CHEMBL419213):", len(inds))
        for ind in inds[:5]:
            print("  ", ind.get("efo_term"), "|", ind.get("mesh_heading"), "| max_phase:", ind.get("max_phase_for_ind"))

asyncio.run(main())
