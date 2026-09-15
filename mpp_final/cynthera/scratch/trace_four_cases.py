import asyncio
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector

async def check():
    pipeline = RetrievalPipeline()
    cases = [
        ("Atorvastatin", "Alzheimer disease"),
        ("Fluvoxamine", "COVID-19"),
        ("Imatinib", "COVID-19"),
        ("Pregabalin", "Breast cancer"),
        ("Azithromycin", "COVID-19"),
    ]
    async with ChEMBLConnector() as conn:
        for drug_name, disease_name in cases:
            search_res = await conn.search_molecule(drug_name)
            mols = search_res.get("molecules", [])
            mol = mols[0]
            cid = mol.get("molecule_chembl_id")
            ind_data = await conn.fetch_indications(cid)
            mol_data = await conn.fetch_molecule_details(cid)
            sig = pipeline._parse_indication_data(ind_data, mol_data, disease_name)
            print(f"\n{drug_name} -> {disease_name}:")
            print(f"  Parent ChEMBL ID: {cid}")
            print(f"  Parent max_phase: {mol_data.get('max_phase')}")
            print(f"  Parsed Sig: is_approved={sig.is_approved}, max_phase={sig.max_phase}, term='{sig.matched_indication_term}', conf={sig.match_confidence}")
            
            # Now run _try_active_form_indications
            chembl_data = {
                "molecule_details": mol_data,
                "bioactivities": {"activities": [{"molecule_chembl_id": cid}]},
            }
            af_sig = await pipeline._try_active_form_indications(chembl_data, disease_name, sig)
            print(f"  After active forms: is_approved={af_sig.is_approved}, max_phase={af_sig.max_phase}, term='{af_sig.matched_indication_term}', source='{af_sig.source}'")

asyncio.run(check())
