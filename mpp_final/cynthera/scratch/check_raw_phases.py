import asyncio
from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector

async def check():
    cases = [
        ("Atorvastatin", "CHEMBL1487", "alzheimer"),
        ("Fluvoxamine", "CHEMBL814", "covid"),
        ("Imatinib", "CHEMBL941", "covid"),
        ("Pregabalin", "CHEMBL1059", "breast"),
        ("Azithromycin", "CHEMBL529", "covid"),
    ]
    async with ChEMBLConnector() as conn:
        for drug_name, cid, search_w in cases:
            ind_data = await conn.fetch_indications(cid)
            inds = ind_data.get("indications", [])
            print(f"\n{drug_name} ({cid}) matching '{search_w}':")
            for ind in inds:
                term = f"{ind.get('efo_term')} | {ind.get('mesh_heading')}"
                if search_w in term.lower():
                    print(f"  term: {term}, max_phase_for_ind: {ind.get('max_phase_for_ind')}")

asyncio.run(check())
