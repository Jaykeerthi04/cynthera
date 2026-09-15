import sys
sys.path.insert(0, ".")
import asyncio
from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector

async def main():
    async with ChEMBLConnector() as conn:
        res = await conn.fetch_indications('CHEMBL1201825')
        for i, ind in enumerate(res.get('indications', [])):
            print(f"{i}: efo='{ind.get('efo_term')}' | mesh='{ind.get('mesh_heading')}' | phase={ind.get('max_phase_for_ind')}")

asyncio.run(main())
