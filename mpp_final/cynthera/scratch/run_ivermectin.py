"""Clear Cynthera caches and execute hypothesis evaluation for Ivermectin -> Heart failure."""
import asyncio
import os
import sqlite3
import sys
from dotenv import load_dotenv

# Ensure root path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy

def clear_all_caches(db_path: str = "data/cynthera.db"):
    print("=" * 80)
    print("STEP 1: CLEARING CACHES")
    print("=" * 80)
    if not os.path.exists(db_path):
        print(f"No database found at {db_path}.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"Database: {db_path}")
    print(f"Existing tables: {tables}")

    cleared = []
    for t in tables:
        if "cache" in t.lower():
            cnt = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            cur.execute(f"DELETE FROM {t}")
            conn.commit()
            cleared.append((t, cnt))
            print(f"  [CLEARED] Table '{t}': deleted {cnt} cached entries.")

    conn.close()
    if not cleared:
        print("  No cache tables found.")
    print("All caches successfully cleared.\n")

def run_evaluation(drug: str, disease: str):
    print("=" * 80)
    print(f"STEP 2: RUNNING EVALUATION IN CLI: {drug} -> {disease}")
    print("=" * 80)

    orchestrator = MasterOrchestrator(
        llm_api_key=os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY"),
        ncbi_api_key=os.environ.get("NCBI_API_KEY"),
        disgenet_api_key=os.environ.get("DISGENET_API_KEY"),
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        hypothesis, package, result = loop.run_until_complete(
            orchestrator.evaluate(
                drug_name=drug,
                disease_name=disease,
                policy=RetrievalPolicy.STANDARD,
                bypass_cache=True,
            )
        )
    finally:
        loop.close()

    print("\n" + "=" * 80)
    print("CYNTHERA EVALUATION REPORT (CLI OUTPUT)")
    print("=" * 80)
    print(f"Drug:        {hypothesis.drug_name} (ChEMBL ID: {hypothesis.drug_chembl_id})")
    print(f"Disease:     {hypothesis.disease_name} (MeSH ID: {hypothesis.disease_mesh_id})")
    print(f"Status:      {result.recommendation_status.value}")
    print("-" * 80)

    # 1. Recommendation & Decision Trace
    print("\n[1] FINAL RECOMMENDATION & DECISION TRACE")
    print(f"  Final Decision: {result.recommendation_status.value}")
    if result.recommendation_reasons:
        print("  Rule Application Reasons:")
        for idx, r in enumerate(result.recommendation_reasons, 1):
            print(f"    {idx}. {r}")
    else:
        print("  No rule-specific reasons recorded.")

    # 2. Three-Dimensional Scores
    print("\n[2] THREE-DIMENSIONAL SCORES")
    print(f"  Support Score (SS):      {result.support_assessment.score:.3f} ({result.support_assessment.level})")
    print(f"  Mechanistic Score (MS):  {result.mechanistic_assessment.score:.3f} ({result.mechanistic_assessment.level})")
    print(f"  Risk Score (RS):         {result.risk_assessment.score:.3f} ({result.risk_assessment.level})")

    # 3. Mechanistic Semantics & Quality Gate
    ma = result.mechanistic_assessment
    sc = getattr(ma, "score_components", {}) or {}
    print("\n[3] MECHANISTIC EVIDENCE & QUALITY BREAKDOWN")
    print(f"  Mechanistic Score:           {ma.score:.3f}")
    print(f"  Confidence Level:            {ma.level}")
    print(f"  Mechanism Quality:           {sc.get('support_level', 'UNKNOWN')}")
    print(f"  Raw Confidence:              {sc.get('raw_confidence', 'N/A')}")
    print(f"  Structural Edge Count:       {sc.get('structural_edge_count', 'N/A')}")
    print(f"  Causal Edge Count:           {sc.get('causal_edge_count', 'N/A')}")
    print(f"  Grounded Edge Count:         {sc.get('grounded_edge_count', 'N/A')}")
    print(f"  Independent Evidence Groups: {sc.get('independent_evidence_groups', 'N/A')}")
    print(f"  Reaction Enriched:           {sc.get('reaction_enriched', False)}")
    print(f"  Discovered Candidate Paths:  {len(getattr(ma, 'candidate_mechanisms', []))}")
    if ma.mechanistic_chain:
        print(f"  Primary Chain:               {' -> '.join(ma.mechanistic_chain)}")

    # Quality Gate Check
    qual = sc.get("support_level", "")
    if qual == "WEAK_SPECULATIVE" and ma.score >= 0.40:
        print("  >>> QUALITY GATE APPLIED (Rule 1b): WEAK_SPECULATIVE blocked from PROMISING -> UNCERTAIN")

    # 4. Directional Mechanism
    print("\n[4] DIRECTIONAL MECHANISM")
    dir_state = sc.get("directional_mechanism_state", "UNKNOWN")
    cands = getattr(ma, "candidate_mechanisms", [])
    if cands and isinstance(cands[0], dict) and dir_state == "UNKNOWN":
        dir_state = cands[0].get("directional_mechanism_status", "UNKNOWN")
    print(f"  Directional Mechanism State: {dir_state}")

    # 5. Contradiction & Uncertainty
    print("\n[5] CONTRADICTION & UNCERTAINTY")
    cs = result.contradiction_summary
    if cs:
        print(f"  Conflict Detected:           {'YES' if cs.has_conflict else 'NO'}")
        print(f"  Strong Conflict:             {'YES' if cs.strong_conflict else 'NO'}")
        print(f"  Supporting Evidence Groups:  {cs.support_groups} (weight: {cs.support_weight:.1f})")
        print(f"  Opposing Evidence Groups:    {cs.opposition_groups} (weight: {cs.opposition_weight:.1f})")
        print(f"  Resolution Status:           {cs.resolution}")
        if cs.conflict_sources:
            print(f"  Conflict Sources:            {', '.join(cs.conflict_sources)}")
    else:
        ta = getattr(result.audit_report, "therapeutic_alignment", {}) or {}
        print(f"  Overall Direction:           {ta.get('overall_alignment', 'INSUFFICIENT')}")
        print(f"  Supporting Groups:           {ta.get('supporting_groups_count', 0)}")
        print(f"  Opposing Groups:             {ta.get('opposing_groups_count', 0)}")

    # 6. Target Trace
    print("\n[6] TARGET TRACE")
    ranked_tgt = sc.get("ranked_target")
    print(f"  Ranked Pipeline Target:      {ranked_tgt or 'None'}")
    tgt_summary = sc.get("target_ranking_summary", [])
    if tgt_summary:
        print(f"  Evaluated Targets ({len(tgt_summary)}):")
        for t in tgt_summary:
            print(f"    - Target: {t.get('target_id')}, Rank: {t.get('rank_score')}, Support: {t.get('support_level')}, Conf: {t.get('confidence')}")

    # 7. Retrieval / Data Sources
    print("\n[7] DATA SOURCES & RETRIEVAL")
    print(f"  Sources Queried:             {', '.join(package.sources_queried) or 'None'}")
    print(f"  Sources Failed:              {', '.join(package.sources_failed) or 'None'}")
    print(f"  Total Targets Retrieved:     {len(package.targets)}")
    print(f"  Total Pathways Retrieved:    {len(package.pathways)}")
    print(f"  Total Evidence Records:      {len(package.evidence_records)}")

    # 8. Executive Summary
    print("\n[8] EXECUTIVE SUMMARY")
    summary_clean = str(result.audit_report.summary).encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8')
    print(f"  {summary_clean}")
    print("=" * 80)

if __name__ == "__main__":
    clear_all_caches()
    run_evaluation("Ivermectin", "Heart failure")
