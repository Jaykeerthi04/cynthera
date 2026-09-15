"""Execute hypothesis evaluation for Apixaban -> Atrial fibrillation."""
import asyncio
import os
import sys
import json
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy


def run_apixaban_eval():
    drug = "Apixaban"
    disease = "Atrial fibrillation"

    print("=" * 80)
    print(f"RUNNING CYNTHERA EVALUATION: {drug} -> {disease}")
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
    print(f"  Directional Mechanism State: {sc.get('directional_mechanism_state', 'N/A')}")
    print(f"  Validated Mechanism Count:   {sc.get('validated_mechanism_count', 'N/A')}")
    print(f"  Total Candidates:            {sc.get('candidate_mechanism_count', 'N/A')}")

    # 4. Target & Therapeutic Direction Evidence
    print("\n[4] RETRIEVED TARGETS & DIRECTIONAL EVIDENCE")
    print(f"  Target Count:                {len(package.targets)}")
    for t in package.targets[:5]:
        print(f"    - UniProt: {t.protein_uniprot} | Mechanism: {t.mechanism} | Affinity: {t.affinity_nm} nM ({t.affinity_type})")
    print(f"  Therapeutic Direction Recs:  {len(package.therapeutic_direction_evidence)}")
    for ev in package.therapeutic_direction_evidence[:5]:
        print(f"    - Target: {ev.target_canonical_id} | Req Action: {ev.required_action} | Grounding: {ev.causal_grounding.value} | Family: {ev.evidence_family.value} | Ref: {ev.underlying_reference}")

    # 5. Contradiction & Uncertainty Summary
    print("\n[5] CONTRADICTION & UNCERTAINTY PROFILE")
    if result.contradiction_summary:
        cs = result.contradiction_summary
        print(f"  Conflict Detected:           {cs.has_conflict}")
        print(f"  Strong Conflict:             {cs.strong_conflict}")
        print(f"  Supporting Weight:           {cs.support_weight:.2f}")
        print(f"  Opposing Weight:             {cs.opposition_weight:.2f}")
        print(f"  Resolution:                  {cs.resolution}")
        print(f"  Explanation:                 {cs.explanation}")
    else:
        print("  No contradiction summary recorded.")

    # 6. Safety Profile
    print("\n[6] SAFETY & ADVERSE EVENTS")
    ra = result.risk_assessment
    print(f"  Risk Score:                  {ra.score:.3f} ({ra.level})")
    print(f"  Failed Trials:               {ra.failed_trial_count}")
    print(f"  Contradiction Count:         {ra.contradiction_count}")
    print(f"  Rationale:                   {ra.rationale}")

    print("\n" + "=" * 80)
    print("EVALUATION COMPLETED SUCCESSFULLY.")
    print("=" * 80)


if __name__ == "__main__":
    run_apixaban_eval()
