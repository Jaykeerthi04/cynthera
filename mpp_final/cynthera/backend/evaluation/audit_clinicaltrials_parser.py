"""Audit script for ClinicalTrials.gov parsing, raw JSON structure, and evidence flow.

AUDIT ONLY - DOES NOT MODIFY PRODUCTION LOGIC.
"""
import asyncio
import json
import logging
import os
import re
import sys
from typing import Any

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))
logging.basicConfig(level=logging.WARNING)

from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    trial_to_negative_claim,
    evaluate_trial_attribution,
    TrialDrugRole,
    matches_disease_condition,
    determine_trial_evidence_type,
    TherapeuticOppositionAssessor,
)

CASES_17 = [
    ("Ivermectin", "COVID-19"),
    ("Fluvoxamine", "COVID-19"),
    ("Azithromycin", "COVID-19"),
    ("Hydroxychloroquine", "COVID-19"),
    ("Interferon beta-1a", "COVID-19"),
    ("Niacin", "Cardiovascular disease"),
    ("Dexamethasone", "Traumatic brain injury"),
    ("Aspirin", "Alzheimer's disease"),
    ("Simvastatin", "Alzheimer's disease"),
    ("Pioglitazone", "Alzheimer's disease"),
    ("Rofecoxib", "Cardiovascular disease"),
    ("Nivolumab", "Glioblastoma"),
    ("Pembrolizumab", "Glioblastoma"),
    ("Semaglutide", "Alzheimer's disease"),
    ("Furosemide", "Depression"),
    ("Warfarin", "Leishmaniasis"),
    ("Metformin", "Type 2 diabetes"),
]

async def audit_17_cases():
    pipeline = RetrievalPipeline()
    assessor = TherapeuticOppositionAssessor()
    
    print("\n" + "="*120, flush=True)
    print("SECTION 17: FORENSIC AUDIT OF 17 REAL CASES", flush=True)
    print("="*120, flush=True)
    
    headers = [
        "Case", "Retrieved", "HasResults", "Parsed", "EffEndpoints",
        "StatAnalyses", "NegSignals", "Attributed", "NegClaims", "OppScore", "Decision"
    ]
    row_format = "| {:<32} | {:>9} | {:>10} | {:>6} | {:>12} | {:>12} | {:>10} | {:>10} | {:>9} | {:>8} | {:<12} |"
    print(row_format.format(*headers), flush=True)
    print("|" + "|".join(["-"*(len(h)+2) for h in [
        "Case                            ", "Retrieved", "HasResults", "Parsed", "EffEndpoints",
        "StatAnalyses", "NegSignals", "Attributed", "NegClaims", "OppScore", "Decision    "
    ]]) + "|", flush=True)

    case_details = []

    for drug_name, disease_name in CASES_17:
        case_str = f"{drug_name} -> {disease_name}"
        try:
            async with ClinicalTrialsConnector() as conn:
                data = await conn.fetch(drug_name, disease_name, max_results=20)
            studies = data.get("studies", [])
            retrieved_count = len(studies)

            has_results_count = sum(1 for s in studies if s.get("hasResults") or "resultsSection" in s)

            drug_obj = Drug(name=drug_name, identifiers={"chembl": "CHEMBL_TEST"})
            disease_obj = Disease(name=disease_name, identifiers={"mesh": "MESH_TEST"})
            parsed_trials = pipeline._parse_trials_data(data, drug_obj, disease_obj)
            parsed_count = len(parsed_trials)

            eff_endpoints = 0
            stat_analyses = 0
            neg_signals = 0
            attributed_count = 0
            claims = []

            for t in parsed_trials:
                for om in t.outcome_measures:
                    if not om.get("is_safety") and not om.get("is_non_efficacy"):
                        eff_endpoints += 1
                        if om.get("direction") in ("NEGATIVE", "POSITIVE"):
                            stat_analyses += 1
                        if om.get("direction") == "NEGATIVE":
                            neg_signals += 1

                if t.is_negative_efficacy or t.status in (
                    TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
                    TrialOutcomeStatus.TERMINATED_SAFETY,
                    TrialOutcomeStatus.COMPLETED_FAILURE,
                ):
                    attr = evaluate_trial_attribution(t, drug_name)
                    if attr.final_attribution_decision:
                        attributed_count += 1

                c = trial_to_negative_claim(t, drug_name, disease_name)
                if c:
                    claims.append(c)

            opp_assessment = assessor.assess(claims=claims, drug_name=drug_name, disease_name=disease_name)
            opp_score = opp_assessment.score
            opp_level = opp_assessment.level

            if opp_score >= 0.45:
                mock_decision = "OPPOSE"
            elif opp_score > 0:
                mock_decision = "MIXED/LOW"
            else:
                mock_decision = "UNCERTAIN"

            print(row_format.format(
                case_str[:32],
                retrieved_count,
                has_results_count,
                parsed_count,
                eff_endpoints,
                stat_analyses,
                neg_signals,
                attributed_count,
                len(claims),
                f"{opp_score:.3f}",
                mock_decision
            ), flush=True)

            case_details.append({
                "case": case_str,
                "drug": drug_name,
                "disease": disease_name,
                "retrieved": retrieved_count,
                "has_results": has_results_count,
                "parsed": parsed_count,
                "eff_endpoints": eff_endpoints,
                "stat_analyses": stat_analyses,
                "neg_signals": neg_signals,
                "attributed": attributed_count,
                "neg_claims": len(claims),
                "opp_score": opp_score,
                "opp_level": opp_level,
                "decision": mock_decision,
                "trials": [
                    {
                        "nct_id": t.nct_id,
                        "status": str(t.status),
                        "neg_efficacy": t.is_negative_efficacy,
                        "neg_reason": t.negative_efficacy_reason,
                        "attr_decision": evaluate_trial_attribution(t, drug_name).final_attribution_decision,
                        "attr_role": evaluate_trial_attribution(t, drug_name).drug_role.value,
                        "claim": trial_to_negative_claim(t, drug_name, disease_name) is not None,
                    }
                    for t in parsed_trials if t.is_negative_efficacy or t.status != TrialOutcomeStatus.UNKNOWN
                ]
            })

        except Exception as e:
            print(f"Error on {case_str}: {e}", flush=True)

    print("\n" + "="*120, flush=True)
    print("DETAILED CASE DIAGNOSTICS FOR NEGATIVE-EVALUATION CANDIDATES", flush=True)
    print("="*120, flush=True)
    for cd in case_details:
        if cd["neg_claims"] > 0 or cd["neg_signals"] > 0 or cd["has_results"] > 0:
            print(f"\n--- {cd['case']} ---", flush=True)
            print(f"  Retrieved: {cd['retrieved']}, HasResults: {cd['has_results']}, Parsed: {cd['parsed']}", flush=True)
            print(f"  EffEndpoints: {cd['eff_endpoints']}, NegSignals: {cd['neg_signals']}, Attributed: {cd['attributed']}, Claims: {cd['neg_claims']}", flush=True)
            for tr in cd["trials"]:
                print(f"    [{tr['nct_id']}] Status: {tr['status']} | NegEff: {tr['neg_efficacy']} | Role: {tr['attr_role']} | Attr: {tr['attr_decision']} | Claim: {tr['claim']}", flush=True)
                if tr["neg_reason"]:
                    print(f"      Reason: {tr['neg_reason']}", flush=True)

if __name__ == "__main__":
    asyncio.run(audit_17_cases())
