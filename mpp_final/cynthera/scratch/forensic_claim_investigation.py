import asyncio
import json
import sys
import os

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, r"c:\Users\win10\Documents\cynthera\mpp_final\cynthera")

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    NEGATIVE_PREDICATE_NAMES,
    NEGATIVE_PREDICATES,
    trial_to_negative_claim,
    is_trial_comparator,
    determine_trial_evidence_type
)
from backend.reasoning.conflict.evidence_weighting import (
    compute_claim_weight,
    evidence_group_key,
    cluster_into_evidence_groups,
    group_weight,
    EVIDENCE_TYPE_WEIGHTS
)

async def inspect_case(drug: str, disease: str):
    print(f"\n=======================================================")
    print(f"INSPECTING: {drug} -> {disease}")
    print(f"=======================================================")
    
    orch = MasterOrchestrator()
    hypothesis, package, result = await orch.evaluate(
        drug_name=drug,
        disease_name=disease,
        policy=RetrievalPolicy.STANDARD,
        bypass_cache=False
    )
    
    # 1. Inspect ClinicalTrials in package
    print(f"\n--- 1. Clinical Trials in Package ({len(package.clinical_trials)}) ---")
    neg_trial_claims = []
    for t in package.clinical_trials:
        status_val = t.status.value if hasattr(t.status, 'value') else str(t.status)
        is_comp = is_trial_comparator(t, drug)
        ev_type = determine_trial_evidence_type(t)
        claim = trial_to_negative_claim(t, drug, disease)
        if claim or status_val not in ("UNKNOWN", "COMPLETED_SUCCESS"):
            print(f"  NCT: {t.nct_id} | Status: {status_val} | Phase: {t.phase} | EvType: {ev_type} | Comparator: {is_comp}")
            print(f"    Title: {t.title}")
            print(f"    Why stopped: {getattr(t, 'why_stopped', None)}")
            if claim:
                print(f"    -> Converted to negative claim: {claim.predicate.value} erw={claim.erw.value}")
                neg_trial_claims.append((t, claim))

    # 2. Get the actual opposition input claims that the orchestrator used
    # 2. Extract claims as the pipeline does
    all_claims = await orch._reasoning._extract_all_claims(package)
    trial_cls = orch._reasoning._classify_clinical_trials(package)
    trial_claims = []
    for t in trial_cls.efficacy_terminated + trial_cls.safety_terminated:
        c = trial_to_negative_claim(t, package.drug.name, package.disease.name)
        if c is not None:
            trial_claims.append(c)
    opp_input_claims = all_claims + trial_claims
    print(f"\n--- 2. Claims passed to Opposition Assessor ({len(opp_input_claims)}) ---")
    print(f"Literature claims: {len(all_claims)}, Trial claims: {len(trial_claims)}")
    
    neg_claims = []
    for c in opp_input_claims:
        pred = c.predicate
        if pred in NEGATIVE_PREDICATES or (hasattr(pred, "value") and pred.value in NEGATIVE_PREDICATE_NAMES) or str(pred) in NEGATIVE_PREDICATE_NAMES:
            neg_claims.append(c)
            
    print(f"Negative-predicate claims: {len(neg_claims)}")
    for nc in neg_claims:
        print(f"\n  CLAIM ID: {nc.id}")
        print(f"  Subject: {nc.subject!r}")
        print(f"  Predicate: {nc.predicate.value if hasattr(nc.predicate, 'value') else str(nc.predicate)}")
        print(f"  Object: {nc.object!r}")
        print(f"  Confidence: {nc.confidence}")
        print(f"  ERW: {nc.erw.value if nc.erw else None} (base_weight: {getattr(nc.erw, 'base_weight', None)})")
        print(f"  Evidence Type: {getattr(nc, 'evidence_type', 'NOT_AVAILABLE_IN_MODEL')}")
        print(f"  Publication Year: {getattr(nc, 'publication_year', 'NOT_AVAILABLE_IN_MODEL')}")
        print(f"  Raw Text: {nc.raw_text}")
        print(f"  Provenance: source={getattr(nc.provenance, 'source_name', None)}, record_id={getattr(nc.provenance, 'record_id', None)}, url={getattr(nc.provenance, 'url', None)}")
        
        # Check relevance
        drug_lower = drug.lower().strip()
        disease_lower = disease.lower().strip()
        raw = (nc.raw_text or "").lower()
        sub_lower = nc.subject.lower()
        obj_lower = nc.object.lower()
        drug_rel = (drug_lower in sub_lower or (len(drug_lower) >= 4 and drug_lower in raw))
        dis_rel = (disease_lower in obj_lower or (len(disease_lower) >= 4 and disease_lower in raw))
        print(f"  Relevance: drug_rel={drug_rel}, dis_rel={dis_rel} -> Qualified: {drug_rel and dis_rel}")
        
        # Check weight
        w = compute_claim_weight(nc)
        g_key = evidence_group_key(nc)
        print(f"  Group Key: {g_key}")
        print(f"  Claim Weight: {w}")
        
    # 3. Assessment breakdown
    opp = result.opposition_assessment
    print(f"\n--- 3. Opposition Assessment Result ---")
    print(f"Score: {opp.score} | Level: {opp.level} | n_groups: {opp.independent_group_count} | qualified_count: {opp.qualified_negative_claim_count}")
    print(f"Rationale: {opp.rationale}")
    print(f"Strongest group weight: {opp.strongest_group_weight}")
    print(f"Key claim IDs: {opp.key_claim_ids}")
    
    # 4. Check contradiction summary
    print(f"\n--- 4. Contradiction Summary ---")
    report = getattr(result.audit_report, "therapeutic_alignment", None)
    contradictions = result.contradictions
    if report:
        c_summary = orch._reasoning._build_contradiction_summary(report, contradictions)
        print(f"ContradictionSummary resolution: {c_summary.resolution}")
        print(f"ContradictionSummary strong_conflict: {c_summary.strong_conflict}")
        print(f"ContradictionSummary explanation: {c_summary.explanation}")
        print(f"ContradictionSummary sources: {c_summary.conflict_sources}")
        print(f"Support groups: {c_summary.support_groups}, Opposition groups: {c_summary.opposition_groups}")
        print(f"Support weight: {c_summary.support_weight}, Opposition weight: {c_summary.opposition_weight}")
    else:
        print("No therapeutic_alignment report in audit_report!")
        
    # Also dump the raw claim as json-serializable dict
    raw_claims_dump = []
    for nc in neg_claims:
        raw_claims_dump.append({
            "id": str(nc.id),
            "subject": nc.subject,
            "predicate": nc.predicate.value if hasattr(nc.predicate, 'value') else str(nc.predicate),
            "object": nc.object,
            "confidence": nc.confidence,
            "erw": {
                "value": nc.erw.value if nc.erw else None,
                "base_weight": getattr(nc.erw, "base_weight", None),
            },
            "evidence_type": getattr(nc, "evidence_type", "NOT_AVAILABLE_IN_MODEL"),
            "publication_year": getattr(nc, "publication_year", "NOT_AVAILABLE_IN_MODEL"),
            "raw_text": nc.raw_text,
            "provenance": {
                "source_name": getattr(nc.provenance, "source_name", None),
                "record_id": getattr(nc.provenance, "record_id", None),
                "source_version": getattr(nc.provenance, "source_version", None),
                "url": getattr(nc.provenance, "url", None),
            } if nc.provenance else None,
            "is_validated": nc.is_validated,
            "statement": getattr(nc, "statement", None),
        })

    return {
        "drug": drug,
        "disease": disease,
        "opp": {
            "score": opp.score,
            "level": opp.level,
            "independent_group_count": opp.independent_group_count,
            "qualified_negative_claim_count": opp.qualified_negative_claim_count,
            "strongest_group_weight": opp.strongest_group_weight,
            "rationale": opp.rationale,
            "key_claim_ids": opp.key_claim_ids,
        },
        "raw_claims": raw_claims_dump,
        "recommendation": result.recommendation_status.value,
        "reasons": result.recommendation_reasons,
    }

async def main():
    res_niacin = await inspect_case("Niacin", "Cardiovascular disease")
    res_metformin = await inspect_case("Metformin", "Type 2 diabetes mellitus")
    
    with open(r'C:\Users\win10\.gemini\antigravity-ide\brain\338359ef-11f5-4696-8f5a-aa4b94f640c7\scratch\forensic_claims_data.json', 'w', encoding='utf-8') as f:
        json.dump({"niacin": res_niacin, "metformin": res_metformin}, f, indent=2)
    print("\nSaved raw data to scratch/forensic_claims_data.json")

if __name__ == "__main__":
    asyncio.run(main())
