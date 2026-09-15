import sys
sys.path.insert(0, ".")
import asyncio
import re
from pathlib import Path
from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector
from backend.engineering.retrieval.disease_relation import (
    classify_disease_relation,
    matches_for_approval_anchor,
    DiseaseRelation,
)
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.approval_signal import ApprovalSignal
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.hypothesis import Hypothesis
from backend.reasoning.context.scientific_context_builder import ScientificContextBuilder
from backend.reasoning.agents.prior_knowledge_agent import PriorKnowledgeContext
from backend.reasoning.agents.clinical_safety_agent import SafetyProfile
from backend.core.domain.reasoning_result import (
    SupportAssessment,
    MechanisticAssessment,
    RiskAssessment,
    OppositionAssessment,
)
from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
from backend.reasoning.orchestrator.decision_rules import apply_decision_rules
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    trial_to_negative_claim,
)

async def test_full_pipeline():
    drug = "Ranibizumab"
    disease = "Age-related macular degeneration"

    # Simulate updated _parse_indication_data:
    sig = ApprovalSignal.from_chembl_indication_match(
        max_phase=4,
        matched_term="wet macular degeneration",
        match_confidence=0.40,
        approved_count=10,
        source="chembl",
        global_approval_phase=4,
        requested_disease=disease,
        matching_rationale="Direct disease match between requested 'Age-related macular degeneration' and indication term 'wet macular degeneration' (confidence 0.40, phase 4).",
        disease_relation="SAME",
        disease_relation_policy="APPROVAL_ANCHOR",
    )

    hyp = Hypothesis(drug_name=drug, disease_name=disease)
    pkg = RetrievalPackage(
        hypothesis_id=hyp.id,
        drug=Drug(name=drug, identifiers={"chembl": "CHEMBL1201825"}),
        disease=Disease(name=disease, identifiers={"mesh": "D008268"}),
        approval_signal=sig,
        sources_failed=[],
    )

    prior_ctx = PriorKnowledgeContext(
        is_approved_indication=True,
        evaluation_pathway="APPROVED_INDICATION",
        matched_indication_term="wet macular degeneration",
    )
    support = SupportAssessment(score=0.9942, level="HIGH", evidence_count=68, has_high_quality_therapeutic=False)
    mechanistic = MechanisticAssessment(score=0.490, level="LOW", pathway_count=0)
    risk = RiskAssessment(score=0.0, level="LOW", failed_trial_count=0, contradiction_count=0)
    safety = SafetyProfile(overall_safety_grade="A", has_boxed_warning=False)

    sci_ctx = ScientificContextBuilder.build(prior_ctx, support, mechanistic, [], pkg)

    # Negative trials from cache
    cache_path = Path("data/ct_raw_cache/Ranibizumab_Age_related_macular_degeneration.json")
    import json
    raw_ct = json.loads(cache_path.read_text(encoding="utf-8"))
    pipe = RetrievalPipeline()
    parsed_trials = pipe._parse_trials_data(raw_ct, pkg.drug, pkg.disease)
    assessor = TherapeuticOppositionAssessor()
    claims = [trial_to_negative_claim(t, drug, disease) for t in parsed_trials if trial_to_negative_claim(t, drug, disease)]
    opp_assessment = assessor.assess(claims, drug, disease)

    orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    rec, reasons = orch._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=pkg,
        safety_profile=safety,
        prior_ctx=prior_ctx,
        scientific_context=sci_ctx,
        opposition=opp_assessment,
    )

    print("FULL PRODUCTION REASONING PIPELINE RESULT:")
    print("  Status:", rec)
    print("  Deciding Rule:", reasons[1] if len(reasons) > 1 else reasons[0])
    print("  Trace:", orch._last_rule_minus_one_trace)

asyncio.run(test_full_pipeline())
