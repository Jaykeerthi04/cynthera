"""Adversarial Audit Script for ClinicalTrials.gov + Shared Disease Relation Fixes.
Executes Sections 2 through 16.
AUDIT ONLY - NO CODE CHANGES.
"""
import asyncio
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from backend.engineering.retrieval.disease_relation import (
    DiseaseRelation,
    classify_disease_relation,
    matches_for_approval_anchor,
    matches_for_trial_attribution,
    normalize_disease_term,
    _PARENT_CHILD,
    _SIBLING_EXCLUSIONS,
    _CANONICAL_SYNONYMS,
)
from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.enums.trial_attribution import TrialDrugRole, AttributionTextEvidence
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    matches_drug,
    is_placebo_component,
    _extract_arm_components,
    analyze_trial_drug_role,
    analyze_failure_attribution_text,
    evaluate_trial_attribution,
    matches_disease_condition,
    trial_to_negative_claim,
    TherapeuticOppositionAssessor,
)
from backend.infrastructure.cache.evaluation_cache import EvaluationCache

def run_section_2_disease_relation_tests():
    print("=" * 80)
    print("SECTION 2: DISEASE RELATION ADVERSARIAL TEST")
    print("=" * 80)
    pairs = [
        ("stroke", "hemorrhagic stroke"),
        ("hemorrhagic stroke", "stroke"),
        ("stroke", "ischemic stroke"),
        ("ischemic stroke", "stroke"),
        ("ischemic stroke", "hemorrhagic stroke"),
        ("hemorrhagic stroke", "ischemic stroke"),
        ("traumatic brain injury", "subdural hematoma"),
        ("traumatic brain injury", "epidural hematoma"),
        ("traumatic brain injury", "concussion"),
        ("cardiovascular disease", "myocardial infarction"),
        ("cardiovascular disease", "heart failure"),
        ("cardiovascular disease", "hypertension"),
        ("alzheimer's disease", "dementia"),
        ("glioblastoma", "brain neoplasms"),
        ("glioblastoma", "lung cancer"),
    ]
    for term_a, term_b in pairs:
        rel = classify_disease_relation(term_a, term_b)
        appr = matches_for_approval_anchor(term_a, term_b)
        trial = matches_for_trial_attribution(term_a, term_b)
        print(f"Pair: '{term_a}' <-> '{term_b}' => Relation: {rel.value:16} | Approval: {str(appr):5} | Trial: {str(trial):5}")

def run_section_3_rule_minus_one_tests():
    print("\n" + "=" * 80)
    print("SECTION 3: RULE -1 SAFETY AUDIT")
    print("=" * 80)
    test_cases = [
        ("stroke", "hemorrhagic stroke"),
        ("stroke", "ischemic stroke"),
        ("cardiovascular disease", "myocardial infarction"),
        ("traumatic brain injury", "subdural hematoma"),
        ("type 2 diabetes", "type 2 diabetes"),
        ("glioblastoma", "glioblastoma multiforme"),
    ]
    for q, cand in test_cases:
        rel = classify_disease_relation(q, cand)
        appr = matches_for_approval_anchor(q, cand)
        print(f"Query: '{q}' | Indication: '{cand}' => Rel: {rel.value} | Rule -1 Approval Granted: {appr}")

def run_section_4_trial_matching_tests():
    print("\n" + "=" * 80)
    print("SECTION 4: TRIAL MATCHING & TITLE FALLBACK AUDIT")
    print("=" * 80)
    
    # Test conditions
    pairs = [
        ("traumatic brain injury", "subdural hematoma, chronic"),
        ("stroke", "hemorrhagic stroke"),
        ("ischemic stroke", "hemorrhagic stroke"),
    ]
    for q, cond in pairs:
        rel = classify_disease_relation(q, cond)
        match = matches_for_trial_attribution(q, cond)
        print(f"Query: '{q}' | Condition: '{cond}' => Rel: {rel.value} | Trial Match: {match}")

    # Test title fallback with sibling exclusion when condition is unpopulated vs populated
    trial_sib_empty = ClinicalTrial(
        nct_id="NCT00000001",
        title="Study of Intervention in Acute Hemorrhagic Stroke Patients",
        condition_names=[], # empty condition
        phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_SUCCESS,
        provenance=ProvenanceReference(source_name="CT", source_version="1", record_id="1", url=""),
        drug_chembl_id="CHEMBL1",
        disease_identifier="MESH1",
    )
    match_sib_empty = matches_disease_condition(trial_sib_empty, "stroke")
    print(f"Title Sibling Exclusion (empty conditions): Query='stroke' vs Title='{trial_sib_empty.title}' => matched: {match_sib_empty}")

    trial_sib_unspec = ClinicalTrial(
        nct_id="NCT00000002",
        title="Study of Intervention in Acute Hemorrhagic Stroke Patients",
        condition_names=["Clinical Trial"], # populated non-matching condition
        phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_SUCCESS,
        provenance=ProvenanceReference(source_name="CT", source_version="1", record_id="2", url=""),
        drug_chembl_id="CHEMBL1",
        disease_identifier="MESH1",
    )
    match_sib_unspec = matches_disease_condition(trial_sib_unspec, "stroke")
    print(f"Title Sibling Exclusion (populated condition): Query='stroke' vs Title='{trial_sib_unspec.title}' => matched: {match_sib_unspec} (Expected: False)")

    trial_valid = ClinicalTrial(
        nct_id="NCT00000003",
        title="Study in Patients with Newly Diagnosed Glioblastoma (GBM)",
        condition_names=["Clinical Trial"],
        phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_SUCCESS,
        provenance=ProvenanceReference(source_name="CT", source_version="1", record_id="3", url=""),
        drug_chembl_id="CHEMBL1",
        disease_identifier="MESH1",
    )
    match_valid = matches_disease_condition(trial_valid, "glioblastoma")
    print(f"Title with Valid Term: Query='glioblastoma' vs Title='{trial_valid.title}' => matches_disease_condition: {match_valid} (Expected: True)")

def run_section_5_placebo_tests():
    print("\n" + "=" * 80)
    print("SECTION 5: PLACEBO ADVERSARIAL AUDIT")
    print("=" * 80)
    items = [
        "Nivolumab",
        "Nivolumab Placebo",
        "Nivolumab-matched placebo",
        "Placebo (Nivolumab)",
        "Placebo",
        "Vehicle",
        "Sham",
        "Temozolomide + Nivolumab Placebo",
        "Nivolumab + Radiation",
    ]
    for item in items:
        is_plac = is_placebo_component(item)
        matches_nivo = matches_drug(item, "Nivolumab")
        comps = _extract_arm_components([item])
        print(f"Arm: '{item:<32}' => is_placebo: {str(is_plac):5} | matches 'Nivolumab': {str(matches_nivo):5} | extracted components: {comps}")

def run_section_6_arm_contrast_tests():
    print("\n" + "=" * 80)
    print("SECTION 6: ARM CONTRAST ADVERSARIAL AUDIT")
    print("=" * 80)
    scenarios = [
        ("A + B vs B", ["Drug A", "Drug B"], ["Drug B"], "Drug A"),
        ("A + C vs B + C", ["Drug A", "Drug C"], ["Drug B", "Drug C"], "Drug A"),
        ("A + B vs C + B", ["Drug A", "Drug B"], ["Drug C", "Drug B"], "Drug A"),
        ("A vs Placebo", ["Drug A"], ["Placebo"], "Drug A"),
        ("A vs B", ["Drug A"], ["Drug B"], "Drug A"),
        ("A + B vs C + D", ["Drug A", "Drug B"], ["Drug C", "Drug D"], "Drug A"),
    ]
    for label, exp_arms, comp_arms, target_drug in scenarios:
        t = ClinicalTrial(
            nct_id="NCT12345678",
            title=f"Trial testing {label}",
            intervention_names=exp_arms,
            comparator_names=comp_arms,
            phase="Phase III",
            status=TrialOutcomeStatus.COMPLETED_SUCCESS,
            provenance=ProvenanceReference(source_name="CT", source_version="1", record_id="1", url=""),
            drug_chembl_id="CHEMBL1",
            disease_identifier="MESH1",
        )
        role, intr_m, comp_m, is_diff, reason = analyze_trial_drug_role(t, target_drug)
        print(f"Scenario: {label:<16} | Drug: '{target_drug}' => Role: {role.value:<32} | is_diff: {str(is_diff):5}")
        print(f"   Reason: {reason}")

def run_section_9_whystopped_tests():
    print("\n" + "=" * 80)
    print("SECTION 9: WHY STOPPED ADVERSARIAL AUDIT")
    print("=" * 80)
    statements = [
        "lack of efficacy",
        "lack of efficacy; no safety concern",
        "no safety concern",
        "not safety related",
        "not due to safety",
        "stopped for safety",
        "serious adverse events",
        "lack of efficacy due to safety concerns",
        "futility analysis met criteria; acceptable safety profile",
    ]
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    drug = Drug(name="TestDrug", identifiers={"chembl": "CHEMBL1"})
    disease = Disease(name="TestDisease", identifiers={"mesh": "MESH1"})

    for stmt in statements:
        study = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT00000000", "briefTitle": "Test Trial"},
                "statusModule": {"overallStatus": "TERMINATED", "whyStopped": stmt},
                "designModule": {},
                "conditionsModule": {"conditions": ["TestDisease"]},
            }
        }
        parsed = pipeline._parse_trials_data({"studies": [study]}, drug, disease)
        status = parsed[0].status if parsed else "NOT_PARSED"
        print(f"Statement: '{stmt:<55}' => Parsed Status: {status}")

def run_section_10_completed_semantics():
    print("\n" + "=" * 80)
    print("SECTION 10: COMPLETED TRIAL SEMANTICS AUDIT")
    print("=" * 80)
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    drug = Drug(name="DrugX", identifiers={"chembl": "CHEMBL1"})
    disease = Disease(name="DiseaseY", identifiers={"mesh": "MESH1"})

    cases = [
        ("COMPLETED + no results", {}),
        ("COMPLETED + counts only", {"outcomeMeasures": [{"title": "Overall Survival", "type": "PRIMARY", "classes": []}]}),
        ("COMPLETED + p-value non-sig without failure", {"outcomeMeasures": [{"title": "Progression Free Survival", "type": "PRIMARY", "analyses": [{"pValue": "0.12"}]}]}),
        ("COMPLETED + primary efficacy failure", {"outcomeMeasures": [{"title": "Progression Free Survival", "type": "PRIMARY", "analyses": [{"pValue": "0.04", "paramValue": "-0.5"}]}]}),
        ("COMPLETED + safety endpoint only", {"outcomeMeasures": [{"title": "Adverse Events Incidence", "type": "PRIMARY", "analyses": [{"pValue": "0.01"}]}]}),
    ]

    for label, results_sec in cases:
        study = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT99999999", "briefTitle": "Study " + label},
                "statusModule": {"overallStatus": "COMPLETED"},
                "designModule": {},
                "conditionsModule": {"conditions": ["DiseaseY"]},
            },
            "resultsSection": {"outcomeMeasuresModule": results_sec} if results_sec else {},
            "hasResults": bool(results_sec),
        }
        parsed = pipeline._parse_trials_data({"studies": [study]}, drug, disease)
        t = parsed[0]
        claim = trial_to_negative_claim(t, "DrugX", "DiseaseY")
        print(f"Case: {label:<45} => Status: {t.status:<25} | neg_eff: {str(t.is_negative_efficacy):5} | Claim: {str(claim is not None):5}")

if __name__ == "__main__":
    run_section_2_disease_relation_tests()
    run_section_3_rule_minus_one_tests()
    run_section_4_trial_matching_tests()
    run_section_5_placebo_tests()
    run_section_6_arm_contrast_tests()
    run_section_9_whystopped_tests()
    run_section_10_completed_semantics()
