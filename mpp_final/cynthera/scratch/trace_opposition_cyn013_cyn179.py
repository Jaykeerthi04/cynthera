import asyncio
import json
import sys
import os
sys.path.insert(0, os.path.abspath("."))
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    trial_to_negative_claim,
    NEGATIVE_PREDICATES,
    NEGATIVE_PREDICATE_NAMES,
    cluster_into_evidence_groups,
    group_weight,
)

async def trace_case(drug_name, disease_name, case_id):
    print(f"\n=======================================================")
    print(f"TRACING OPPOSITION COMPUTATION FOR {case_id}: {drug_name} -> {disease_name}")
    print(f"=======================================================")
    
    orch = MasterOrchestrator()
    hyp, pkg, res = await orch.evaluate(
        drug_name=drug_name,
        disease_name=disease_name,
        policy=RetrievalPolicy.STANDARD,
        bypass_cache=False,
    )
    
    # 1. Extracted literature claims
    all_lit_claims = await orch._reasoning._extract_all_claims(pkg)
    print(f"1. Total literature claims extracted: {len(all_lit_claims)}")
    for i, c in enumerate(all_lit_claims):
        print(f"   Lit Claim {i+1}: id={c.id} | subj='{c.subject}' pred='{c.predicate}' obj='{c.object}' type='{c.evidence_type}'")
        
    # 2. Classified clinical trials
    trial_cls = orch._reasoning._classify_clinical_trials(pkg)
    print(f"\n2. Classified clinical trials:")
    print(f"   Safety terminated: {len(trial_cls.safety_terminated)}")
    print(f"   Efficacy terminated: {len(trial_cls.efficacy_terminated)}")
    print(f"   Administrative: {len(trial_cls.administrative_terminated)}")
    print(f"   Covid terminated: {len(trial_cls.covid_terminated)}")
    print(f"   Other failed: {len(trial_cls.other_failed)}")
    
    trial_claims = []
    for t in trial_cls.efficacy_terminated + trial_cls.safety_terminated:
        c = trial_to_negative_claim(t, pkg.drug.name, pkg.disease.name)
        if c is not None:
            trial_claims.append(c)
            print(f"   Converted trial claim: {c}")
        else:
            print(f"   Trial {t.nct_id} REJECTED by attribution gate (is comparator/control or unrelated)")

    opp_input_claims = all_lit_claims + trial_claims
    print(f"\n3. Total claims entering TherapeuticOppositionAssessor: {len(opp_input_claims)}")
    
    assessor = TherapeuticOppositionAssessor()
    
    # Stage 1: Negative predicate filter
    negative_claims = []
    for c in opp_input_claims:
        pred = c.predicate
        if pred in NEGATIVE_PREDICATES or (hasattr(pred, "value") and pred.value in NEGATIVE_PREDICATE_NAMES) or str(pred) in NEGATIVE_PREDICATE_NAMES:
            negative_claims.append(c)
    print(f"\n4. Stage 1 (Negative predicate filter): {len(negative_claims)} claims passed")
    for c in negative_claims:
        print(f"   {c.subject} {c.predicate} {c.object}")
        
    # Stage 2 & 3: Relevance gate
    drug_lower = drug_name.lower().strip()
    disease_lower = disease_name.lower().strip()
    qualified = []
    excluded = []
    for claim in negative_claims:
        raw = (claim.raw_text or "").lower()
        subject_lower = claim.subject.lower()
        object_lower = claim.object.lower()
        drug_relevant = drug_lower in subject_lower or (len(drug_lower) >= 4 and drug_lower in raw)
        disease_relevant = disease_lower in object_lower or (len(disease_lower) >= 4 and disease_lower in raw)
        if drug_relevant and disease_relevant:
            qualified.append(claim)
        else:
            excluded.append((claim, f"drug_rel={drug_relevant}, dis_rel={disease_relevant}"))
            
    print(f"\n5. Stage 2 & 3 (Relevance gates):")
    print(f"   Qualified: {len(qualified)}")
    print(f"   Excluded: {len(excluded)}")
    for c, r in excluded:
        print(f"   - Excluded: {c.subject} {c.predicate} {c.object} -> {r}")
        
    # Full assessor run
    opp_assessment = assessor.assess(opp_input_claims, drug_name, disease_name)
    print(f"\n6. Assessor assessment result:")
    print(f"   score: {opp_assessment.score}")
    print(f"   level: {opp_assessment.level}")
    print(f"   qualified_negative_claim_count: {opp_assessment.qualified_negative_claim_count}")
    print(f"   excluded_negative_claim_count: {opp_assessment.excluded_negative_claim_count}")
    print(f"   independent_group_count: {opp_assessment.independent_group_count}")
    print(f"   rationale: {opp_assessment.rationale}")
    
    print(f"\n7. Compare against result object fields:")
    print(f"   result.opposition_assessment.score = {res.opposition_assessment.score}")
    print(f"   result.opposition_assessment.qualified_negative_claim_count = {res.opposition_assessment.qualified_negative_claim_count}")
    print(f"   result.risk_assessment.score = {res.risk_assessment.score}")
    print(f"   result.risk_assessment.level = {res.risk_assessment.level}")
    print(f"   result.risk_assessment.rationale = {res.risk_assessment.rationale}")

async def main():
    await trace_case("Aspirin", "Secondary prevention of cardiovascular disease", "CYN-013")
    await trace_case("Propranolol", "Depression", "CYN-179")

asyncio.run(main())
