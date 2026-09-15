import asyncio
import sys
sys.path.insert(0, ".")

from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease

async def test_chembl_ranibizumab():
    conn = ChEMBLConnector()
    pipeline = RetrievalPipeline()
    print("Fetching molecule details and indications for CHEMBL1201825 (Ranibizumab)...")
    mol_details = await conn.fetch_molecule_details("CHEMBL1201825")
    ind_data = await conn.fetch_indications("CHEMBL1201825")
    print(f"Total indications returned: {len(ind_data.get('indications', []))}")
    for ind in ind_data.get("indications", []):
        print("  Indication:", ind.get("mesh_heading"), "| efo:", ind.get("efo_term"), "| max_phase:", ind.get("max_phase_for_ind"))
    
    # Test _parse_indications
    sig = pipeline._parse_indications(
        indication_data=ind_data,
        molecule_data=mol_details,
        disease_name="Age-related macular degeneration",
    )
    print("\nParsed ApprovalSignal for 'Age-related macular degeneration':")
    if sig:
        print("  is_approved:", sig.is_approved)
        print("  regulatory_status:", sig.regulatory_status)
        print("  confidence:", sig.confidence)
        print("  matched_term:", getattr(sig, "matched_term", None))
        print("  source:", getattr(sig, "source", None))
    else:
        print("  ApprovalSignal is None!")

asyncio.run(test_chembl_ranibizumab())
