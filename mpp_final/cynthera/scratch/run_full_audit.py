import asyncio
import os
import sys
import json
import sqlite3
import hashlib
from dotenv import load_dotenv

# Ensure backend can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.infrastructure.cache.evaluation_cache import EvaluationCache
from backend.reporting.pdf_exporter import PDFReporter

def get_cache_info(drug: str, disease: str, policy: str = "STANDARD", db_path: str = "data/cynthera.db"):
    key = EvaluationCache._make_key(drug, disease, policy)
    version = EvaluationCache._CACHE_VERSION
    if not os.path.exists(db_path):
        return {"cache_key": key, "cache_version": version, "exists": False, "hit_count": 0}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT created_at, expires_at, hit_count, result_json FROM evaluation_cache WHERE cache_key = ?", (key,)).fetchone()
    conn.close()
    if row:
        return {
            "cache_key": key,
            "cache_version": version,
            "exists": True,
            "hit_count": row["hit_count"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "result_json_len": len(row["result_json"]),
        }
    return {"cache_key": key, "cache_version": version, "exists": False, "hit_count": 0}

async def run_single_audit(drug: str, disease: str):
    orchestrator = MasterOrchestrator(
        llm_api_key=os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY"),
        ncbi_api_key=os.environ.get("NCBI_API_KEY"),
        disgenet_api_key=os.environ.get("DISGENET_API_KEY"),
    )
    
    print(f"\n=======================================================", flush=True)
    print(f"AUDITING: {drug} -> {disease}", flush=True)
    print(f"=======================================================", flush=True)
    
    # 1. FRESH RUN (bypass_cache=True)
    print(f"--> Running FRESH (bypass_cache=True)...", flush=True)
    hyp_fresh, pkg_fresh, res_fresh = await orchestrator.evaluate(
        drug, disease, policy=RetrievalPolicy.STANDARD, bypass_cache=True
    )
    
    # 2. CACHED RUN (bypass_cache=False)
    print(f"--> Running CACHED (bypass_cache=False)...", flush=True)
    cache_before = get_cache_info(drug, disease)
    hyp_cached, pkg_cached, res_cached = await orchestrator.evaluate(
        drug, disease, policy=RetrievalPolicy.STANDARD, bypass_cache=False
    )
    cache_after = get_cache_info(drug, disease)
    
    # 3. PDF GENERATION
    print(f"--> Testing PDF generation...", flush=True)
    pdf_gen = PDFReporter(drug, disease)
    pdf_path = f"scratch/test_report_{drug.replace(' ', '_')}.pdf"
    pdf_bytes = pdf_gen.generate(res_fresh)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    
    return {
        "drug": drug,
        "disease": disease,
        "fresh": {
            "hypothesis": hyp_fresh,
            "package": pkg_fresh,
            "result": res_fresh,
        },
        "cached": {
            "hypothesis": hyp_cached,
            "package": pkg_cached,
            "result": res_cached,
        },
        "cache_before": cache_before,
        "cache_after": cache_after,
        "pdf_path": pdf_path,
        "pdf_size": len(pdf_bytes) if pdf_bytes else 0,
    }

async def main():
    test_cases = [
        ("Doxycycline", "Heart failure"),
        ("Aspirin", "Colorectal Cancer"),
        ("Oseltamivir", "Influenza"),
        ("Aspirin", "Pancreatic Cancer"),
    ]
    
    all_data = []
    for drug, disease in test_cases:
        try:
            res = await run_single_audit(drug, disease)
            all_data.append(res)
        except Exception as e:
            print(f"FAILED {drug} -> {disease}: {e}", flush=True)
            import traceback
            traceback.print_exc()
            
    # Process and print full report
    print("\n\n" + "="*80, flush=True)
    print("ALL AUDITS COMPLETED. PROCESSING DETAILED AUDIT DATA...", flush=True)
    print("="*80, flush=True)
    
    out_records = []
    for item in all_data:
        drug = item["drug"]
        disease = item["disease"]
        rf = item["fresh"]["result"]
        pf = item["fresh"]["package"]
        rc = item["cached"]["result"]
        pc = item["cached"]["package"]
        
        cands_fresh = getattr(rf.audit_report, "candidate_mechanisms", []) or getattr(rf.mechanistic_assessment, "candidate_mechanisms", []) or []
        cands_cached = getattr(rc.audit_report, "candidate_mechanisms", []) or getattr(rc.mechanistic_assessment, "candidate_mechanisms", []) or []
        
        rxn_fresh = getattr(pf, "reactome_reaction_evidence", []) or []
        rxn_cached = getattr(pc, "reactome_reaction_evidence", []) or []
        
        enriched_fresh = sum(
            1 for c in cands_fresh if any(
                "REACTION" in str(h.get("from_node", "")).upper() or "REACTION" in str(h.get("to_node", "")).upper()
                for h in c.get("hops", [])
            )
        )
        enriched_cached = sum(
            1 for c in cands_cached if any(
                "REACTION" in str(h.get("from_node", "")).upper() or "REACTION" in str(h.get("to_node", "")).upper()
                for h in c.get("hops", [])
            )
        )
        
        record = {
            "drug": drug,
            "disease": disease,
            "fresh_ms": rf.mechanistic_assessment.score,
            "fresh_ms_level": rf.mechanistic_assessment.level,
            "fresh_cands_count": len(cands_fresh),
            "fresh_cands": cands_fresh,
            "fresh_rxn_count": len(rxn_fresh),
            "fresh_enriched_rxn_count": enriched_fresh,
            "fresh_chain": rf.mechanistic_assessment.mechanistic_chain,
            "fresh_evidence_status": rf.mechanistic_assessment.evidence_status,
            "cached_ms": rc.mechanistic_assessment.score,
            "cached_ms_level": rc.mechanistic_assessment.level,
            "cached_cands_count": len(cands_cached),
            "cached_rxn_count": len(rxn_cached),
            "cached_enriched_rxn_count": enriched_cached,
            "cache_before": item["cache_before"],
            "cache_after": item["cache_after"],
            "pdf_path": item["pdf_path"],
            "pdf_size": item["pdf_size"],
        }
        out_records.append(record)
        
        print(f"\n--- CASE: {drug} -> {disease} ---", flush=True)
        print(f"Fresh MS: {rf.mechanistic_assessment.score} ({rf.mechanistic_assessment.level})", flush=True)
        print(f"Cached MS: {rc.mechanistic_assessment.score} ({rc.mechanistic_assessment.level})", flush=True)
        print(f"Fresh Candidate Count: {len(cands_fresh)}, Cached Candidate Count: {len(cands_cached)}", flush=True)
        print(f"Fresh Reaction Count: {len(rxn_fresh)}, Cached Reaction Count: {len(rxn_cached)}", flush=True)
        print(f"Fresh Enriched Reactions: {enriched_fresh}, Cached Enriched: {enriched_cached}", flush=True)
        print(f"Mechanistic Chain: {rf.mechanistic_assessment.mechanistic_chain}", flush=True)
        print(f"Cache key: {item['cache_after']['cache_key']} (Hit count: {item['cache_after']['hit_count']})", flush=True)
        
        for i, c in enumerate(cands_fresh):
            print(f"  Cand {i+1}: {c.get('name')}", flush=True)
            print(f"    support_level: {c.get('support_level')}, score: {c.get('confidence_score')}", flush=True)
            print(f"    directional_mechanism_status: {c.get('directional_mechanism_status')}", flush=True)
            print(f"    directional_consistency: {c.get('directional_consistency')}", flush=True)
            print(f"    directional_contradiction_count: {c.get('directional_contradiction_count')}", flush=True)
            da = c.get('directional_assessment')
            if da:
                print(f"    DA status: {da.get('path_direction_status')}, supporting: {len(da.get('supporting_edges', []))}, opposing: {len(da.get('opposing_edges', []))}", flush=True)
    
    # Save full JSON to scratch
    with open("scratch/full_audit_data.json", "w") as f:
        json.dump(out_records, f, indent=2, default=str)
    print("\nSaved full audit data to scratch/full_audit_data.json", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
