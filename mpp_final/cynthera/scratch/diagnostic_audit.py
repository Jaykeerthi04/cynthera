import asyncio
import os
import sys
import json
from dotenv import load_dotenv

# Ensure backend can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy

async def test_case(drug: str, disease: str, bypass_cache: bool):
    orchestrator = MasterOrchestrator(
        llm_api_key=os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY"),
        ncbi_api_key=os.environ.get("NCBI_API_KEY"),
        disgenet_api_key=os.environ.get("DISGENET_API_KEY"),
    )
    hypothesis, pkg, result = await orchestrator.evaluate(
        drug, disease, policy=RetrievalPolicy.STANDARD, bypass_cache=bypass_cache
    )
    return hypothesis, pkg, result

def analyze_result(drug, disease, hypothesis, pkg, result, mode):
    ma = result.mechanistic_assessment
    audit = result.audit_report
    cands = getattr(audit, "candidate_mechanisms", []) or getattr(ma, "candidate_mechanisms", []) or []
    
    rxn_evidence = getattr(pkg, "reactome_reaction_evidence", []) or []
    unique_rxn_ids = set(r.reaction_id for r in rxn_evidence if hasattr(r, "reaction_id"))
    
    enriched_cand_count = sum(
        1 for c in cands if any(
            "REACTION" in str(h.get("from_node", "")).upper() or "REACTION" in str(h.get("to_node", "")).upper()
            for h in c.get("hops", [])
        )
    )
    
    print(f"\n==================================================")
    print(f"DIAGNOSTIC: {drug} -> {disease} [{mode}]")
    print(f"==================================================")
    print(f"Drug: {hypothesis.drug_name} (ChEMBL: {hypothesis.drug_chembl_id})")
    print(f"Disease: {hypothesis.disease_name} (MeSH: {hypothesis.disease_mesh_id})")
    print(f"Recommendation: {result.recommendation_status.value}")
    print(f"Mechanistic Score: {ma.score}")
    print(f"Mechanistic Level: {ma.level}")
    print(f"Pathway Count: {ma.pathway_count}")
    print(f"Mechanistic Chain: {ma.mechanistic_chain}")
    print(f"Candidate Count: {len(cands)}")
    print(f"Reaction Evidence Count: {len(rxn_evidence)} (unique rxn IDs: {len(unique_rxn_ids)})")
    print(f"Reaction Enriched Candidate Count: {enriched_cand_count}")
    print(f"Evidence Status: {ma.evidence_status}")
    print(f"Literature Grounding: {ma.literature_grounding_level}")
    
    # Directional mechanism info
    print("\n--- Directional Mechanism Summary ---")
    for i, c in enumerate(cands):
        print(f"  Candidate {i+1}: {c.get('name')}")
        print(f"    support_level: {c.get('support_level')}")
        print(f"    confidence_score: {c.get('confidence_score')}")
        print(f"    directional_mechanism_status: {c.get('directional_mechanism_status')}")
        print(f"    directional_consistency: {c.get('directional_consistency')}")
        print(f"    directional_contradiction_count: {c.get('directional_contradiction_count')}")
        d_assess = c.get("directional_assessment")
        print(f"    directional_assessment: {d_assess}")
        
    return {
        "drug": drug,
        "disease": disease,
        "mode": mode,
        "ms": ma.score,
        "ms_level": ma.level,
        "candidate_count": len(cands),
        "reaction_count": len(rxn_evidence),
        "unique_rxn_count": len(unique_rxn_ids),
        "reaction_enriched_count": enriched_cand_count,
        "cands": cands,
    }

async def main():
    cases = [
        ("Doxycycline", "Heart failure"),
        ("Aspirin", "Colorectal Cancer"),
        ("Oseltamivir", "Influenza"),
        ("Aspirin", "Pancreatic Cancer"),
    ]
    
    summary = []
    for drug, disease in cases:
        # 1. Fresh run (bypass_cache=True)
        try:
            hyp_fresh, pkg_fresh, res_fresh = await test_case(drug, disease, bypass_cache=True)
            s_fresh = analyze_result(drug, disease, hyp_fresh, pkg_fresh, res_fresh, "FRESH (bypass_cache=True)")
            
            # 2. Cached run (bypass_cache=False)
            hyp_cached, pkg_cached, res_cached = await test_case(drug, disease, bypass_cache=False)
            s_cached = analyze_result(drug, disease, hyp_cached, pkg_cached, res_cached, "CACHED (bypass_cache=False)")
            
            summary.append((s_fresh, s_cached))
        except Exception as e:
            print(f"Error testing {drug} -> {disease}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
