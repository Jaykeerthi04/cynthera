"""Comprehensive deterministic regression tests for ClinicalTrials.gov safe fixes.

Covers:
- Study truncation removal (surviving index 37+, e.g. AIM-HIGH NCT00120289)
- Placebo matching safety (Nivolumab Placebo != Nivolumab)
- Attribution differentiating component logic (background subtraction across arms)
- whyStopped negation handling (no safety concerns != safety termination)
- Results section interpretation invariants
- Full evidence lineage trace
- Hard-negative safeguards
"""
import pytest
from unittest.mock import MagicMock
from typing import Any

from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.claim import Claim
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.enums.trial_attribution import TrialDrugRole, AttributionTextEvidence
from backend.core.enums.predicate_type import PredicateType
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    matches_drug,
    is_placebo_component,
    analyze_trial_drug_role,
    evaluate_trial_attribution,
    matches_disease_condition,
    trial_to_negative_claim,
    TherapeuticOppositionAssessor,
)
from backend.engineering.retrieval.disease_relation import (
    classify_disease_relation,
    matches_for_trial_attribution,
    matches_for_approval_anchor,
    DiseaseRelation,
)


def make_test_trial(**kwargs) -> ClinicalTrial:
    """Helper to construct ClinicalTrial with required phase and provenance fields."""
    nct = kwargs.get("nct_id", "NCT00000000")
    defaults = {
        "phase": "Phase III",
        "provenance": ProvenanceReference(
            source_name="ClinicalTrials.gov",
            source_version="2024",
            record_id=nct,
            url=f"https://clinicaltrials.gov/study/{nct}",
        ),
        "drug_chembl_id": "CHEMBL123",
        "disease_identifier": "MESH:D001",
    }
    defaults.update(kwargs)
    return ClinicalTrial(**defaults)


def make_mock_drug_disease(drug_name: str, disease_name: str) -> tuple[Any, Any]:
    """Create lightweight mock objects with string chembl_id and mesh_id."""
    drug = MagicMock(spec=Drug)
    drug.name = drug_name
    drug.chembl_id = "CHEMBL_TEST"
    disease = MagicMock(spec=Disease)
    disease.name = disease_name
    disease.mesh_id = "MESH_TEST"
    return drug, disease


# ─────────────────────────────────────────────────────────────
# 1. RETRIEVAL & TRUNCATION TESTS (§10 & §17 Item 9)
# ─────────────────────────────────────────────────────────────

def test_truncation_removal_index_37_survives():
    """50 returned studies; target study at index 37 (AIM-HIGH NCT00120289) survives parsing."""
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    studies = []
    for i in range(50):
        nct_id = f"NCT001202{i:02d}" if i != 37 else "NCT00120289"
        study = {
            "protocolSection": {
                "identificationModule": {"nctId": nct_id, "briefTitle": f"Study {i}"},
                "statusModule": {
                    "overallStatus": "TERMINATED" if i == 37 else "COMPLETED",
                    "whyStopped": "Lack of efficacy" if i == 37 else "",
                },
                "designModule": {"designInfo": {}},
                "conditionsModule": {"conditions": ["Atherosclerosis" if i == 37 else "Other"]},
            }
        }
        studies.append(study)

    drug, disease = make_mock_drug_disease("Niacin", "cardiovascular disease")

    trials = pipeline._parse_trials_data({"studies": studies}, drug, disease)
    assert len(trials) == 50, f"Expected 50 parsed trials, got {len(trials)}"
    ncts = [t.nct_id for t in trials]
    assert "NCT00120289" in ncts
    aim_high = next(t for t in trials if t.nct_id == "NCT00120289")
    assert aim_high.status == TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY


# ─────────────────────────────────────────────────────────────
# 2. PLACEBO MATCHING TESTS (§11 & §17 Items 10-12)
# ─────────────────────────────────────────────────────────────

def test_placebo_arm_not_matched_as_candidate():
    """'Nivolumab Placebo' vs 'Nivolumab' => NOT actual drug match."""
    assert matches_drug("Nivolumab Placebo", "Nivolumab") is False
    assert matches_drug("Placebo (Nivolumab)", "Nivolumab") is False
    assert matches_drug("Nivolumab-matched placebo", "Nivolumab") is False
    assert is_placebo_component("Nivolumab Placebo") is True


def test_actual_drug_matches():
    """'Nivolumab' vs 'Nivolumab' => actual match."""
    assert matches_drug("Nivolumab", "Nivolumab") is True
    assert matches_drug("Nivolumab 3 mg/kg", "Nivolumab") is True


def test_combination_with_actual_drug_matches():
    """'Nivolumab + Radiation' => Nivolumab recognized."""
    assert matches_drug("Nivolumab + Radiation", "Nivolumab") is True
    assert matches_drug("Temozolomide + Nivolumab Placebo", "Temozolomide") is True
    assert matches_drug("Temozolomide + Nivolumab Placebo", "Nivolumab") is False


# ─────────────────────────────────────────────────────────────
# 3. ATTRIBUTION & BACKGROUND SUBTRACTION TESTS (§12 & §17 Items 13-15)
# ─────────────────────────────────────────────────────────────

def test_constant_background_subtraction_drug_a_metformin():
    """Drug A + Metformin vs Placebo + Metformin: Drug A differentiating, Metformin background."""
    trial_a = make_test_trial(
        nct_id="NCT09990001",
        title="Study of Drug A in T2D",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        why_stopped="Lack of efficacy",
        intervention_names=["Drug A", "Metformin"],
        comparator_names=["Placebo", "Metformin"],
        condition_names=["Type 2 Diabetes"],
    )
    # Evaluating Drug A
    attr_a = evaluate_trial_attribution(trial_a, "Drug A")
    assert attr_a.drug_role in (TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION, TrialDrugRole.EVALUATED_COMBINATION_COMPONENT)
    assert attr_a.is_differentiating_intervention is True
    assert attr_a.final_attribution_decision is True

    # Evaluating Metformin (constant background)
    attr_met = evaluate_trial_attribution(trial_a, "Metformin")
    assert attr_met.drug_role == TrialDrugRole.BACKGROUND_CONSTANT_THERAPY
    assert attr_met.is_differentiating_intervention is False
    assert attr_met.final_attribution_decision is False


def test_constant_background_subtraction_nivolumab_radiation():
    """Nivolumab + Radiation vs Temozolomide + Radiation: Nivolumab differentiating, Radiation background."""
    trial = make_test_trial(
        nct_id="NCT02617589",
        title="Study of Nivolumab in Glioblastoma",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        why_stopped="Did not meet primary endpoint of overall survival",
        intervention_names=["Nivolumab", "Radiation"],
        comparator_names=["Temozolomide", "Radiation"],
        condition_names=["Glioblastoma"],
        is_negative_efficacy=True,
    )
    attr_nivo = evaluate_trial_attribution(trial, "Nivolumab")
    assert attr_nivo.drug_role in (TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION, TrialDrugRole.EVALUATED_COMBINATION_COMPONENT)
    assert attr_nivo.is_differentiating_intervention is True
    assert attr_nivo.final_attribution_decision is True

    attr_tmz = evaluate_trial_attribution(trial, "Temozolomide")
    assert attr_tmz.drug_role == TrialDrugRole.COMPARATOR_ONLY
    assert attr_tmz.final_attribution_decision is False


def test_placebo_control_contrast_nivolumab():
    """Nivolumab vs Nivolumab Placebo: Nivolumab is evaluated intervention, Placebo not actual Nivolumab."""
    trial = make_test_trial(
        nct_id="NCT02667587",
        title="CheckMate 498: Nivolumab vs TMZ in GBM",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        why_stopped="Primary endpoint of OS was not met",
        intervention_names=["Nivolumab", "Radiation"],
        comparator_names=["Temozolomide", "Nivolumab Placebo", "Radiation"],
        condition_names=["Glioblastoma"],
        is_negative_efficacy=True,
    )
    attr = evaluate_trial_attribution(trial, "Nivolumab")
    assert attr.drug_role in (TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION, TrialDrugRole.EVALUATED_COMBINATION_COMPONENT)
    assert attr.is_differentiating_intervention is True
    assert attr.final_attribution_decision is True


# ─────────────────────────────────────────────────────────────
# 4. WHYSTOPPED NEGATION TESTS (§13 & §17 Items 16-18)
# ─────────────────────────────────────────────────────────────

def test_whystopped_lack_of_efficacy_no_safety_concern():
    """'Lack of efficacy; no safety concern' => TERMINATED_LACK_OF_EFFICACY."""
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT02284906", "briefTitle": "Pioglitazone in AD"},
            "statusModule": {
                "overallStatus": "TERMINATED",
                "whyStopped": "Lack of efficacy; no safety concern",
            },
            "designModule": {},
            "conditionsModule": {"conditions": ["Alzheimer's Disease"]},
        }
    }
    drug, disease = make_mock_drug_disease("Pioglitazone", "Alzheimer's Disease")

    trials = pipeline._parse_trials_data({"studies": [study]}, drug, disease)
    assert len(trials) == 1
    assert trials[0].status == TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY
    assert trials[0].is_negative_efficacy is True


def test_whystopped_safety_concern():
    """'Stopped due to safety concerns' => TERMINATED_SAFETY."""
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT02362321", "briefTitle": "Dexamethasone in TBI"},
            "statusModule": {
                "overallStatus": "TERMINATED",
                "whyStopped": "Stopped due to safety concerns and increased mortality",
            },
            "designModule": {},
            "conditionsModule": {"conditions": ["Subdural Hematoma, Chronic"]},
        }
    }
    drug, disease = make_mock_drug_disease("Dexamethasone", "Traumatic Brain Injury")

    trials = pipeline._parse_trials_data({"studies": [study]}, drug, disease)
    assert len(trials) == 1
    assert trials[0].status == TrialOutcomeStatus.TERMINATED_SAFETY


def test_whystopped_administrative():
    """'Unable to obtain product' => administrative."""
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT04303065", "briefTitle": "Admin Stop"},
            "statusModule": {
                "overallStatus": "TERMINATED",
                "whyStopped": "Unable to obtain product / lack of funding",
            },
            "designModule": {},
            "conditionsModule": {"conditions": ["Traumatic Brain Injury"]},
        }
    }
    drug, disease = make_mock_drug_disease("Dexamethasone", "Traumatic Brain Injury")

    trials = pipeline._parse_trials_data({"studies": [study]}, drug, disease)
    assert len(trials) == 1
    assert trials[0].status == TrialOutcomeStatus.TERMINATED_ADMINISTRATIVE
    assert trials[0].is_negative_efficacy is False


# ─────────────────────────────────────────────────────────────
# 5. RESULTS INTERPRETATION INVARIANTS (§14 & §17 Items 19-23)
# ─────────────────────────────────────────────────────────────

def test_completed_hasresults_false_remains_unknown():
    """COMPLETED + hasResults=False => UNKNOWN status."""
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00053599", "briefTitle": "Completed no results"},
            "statusModule": {"overallStatus": "COMPLETED"},
            "designModule": {},
            "conditionsModule": {"conditions": ["Alzheimer's Disease"]},
        },
        "hasResults": False,
    }
    drug, disease = make_mock_drug_disease("Simvastatin", "Alzheimer's Disease")

    trials = pipeline._parse_trials_data({"studies": [study]}, drug, disease)
    assert len(trials) == 1
    assert trials[0].status == TrialOutcomeStatus.UNKNOWN
    assert trials[0].is_negative_efficacy is False


def test_completed_counts_only_remains_unknown():
    """COMPLETED + measurements but no analyses => UNKNOWN direction."""
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT03426891", "briefTitle": "Counts only"},
            "statusModule": {"overallStatus": "COMPLETED"},
            "designModule": {},
            "conditionsModule": {"conditions": ["Glioblastoma"]},
        },
        "hasResults": True,
        "resultsSection": {
            "outcomeMeasuresModule": {
                "outcomeMeasures": [
                    {
                        "type": "PRIMARY",
                        "title": "Overall Survival",
                        "description": "OS at 12 months",
                        "classes": [{"categories": [{"measurements": [{"value": "10"}]}]}],
                        # analyses array is absent!
                    }
                ]
            }
        },
    }
    drug, disease = make_mock_drug_disease("Pembrolizumab", "Glioblastoma")

    trials = pipeline._parse_trials_data({"studies": [study]}, drug, disease)
    assert len(trials) == 1
    assert trials[0].status == TrialOutcomeStatus.UNKNOWN
    assert trials[0].is_negative_efficacy is False


def test_completed_neutral_analysis_remains_unknown():
    """COMPLETED + statistical non-significance (p >= 0.05) on superiority endpoint is NEUTRAL (status=UNKNOWN)."""
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT01142336", "briefTitle": "Simvastatin in AD"},
            "statusModule": {"overallStatus": "COMPLETED"},
            "designModule": {},
            "conditionsModule": {"conditions": ["Alzheimer's Disease"]},
        },
        "hasResults": True,
        "resultsSection": {
            "outcomeMeasuresModule": {
                "outcomeMeasures": [
                    {
                        "type": "PRIMARY",
                        "title": "ADAS-Cog Score Change",
                        "description": "Cognitive assessment",
                        "analyses": [
                            {"pValue": "0.53", "statisticalMethod": "ANCOVA"}
                        ],
                    }
                ]
            }
        },
    }
    drug, disease = make_mock_drug_disease("Simvastatin", "Alzheimer's Disease")

    trials = pipeline._parse_trials_data({"studies": [study]}, drug, disease)
    assert len(trials) == 1
    assert trials[0].status == TrialOutcomeStatus.UNKNOWN
    assert trials[0].is_negative_efficacy is False


def test_completed_genuine_negative_analysis_becomes_failure():
    """COMPLETED + explicit lack of efficacy or futility => COMPLETED_FAILURE."""
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT01142337", "briefTitle": "Simvastatin Failure in AD"},
            "statusModule": {"overallStatus": "COMPLETED"},
            "designModule": {},
            "conditionsModule": {"conditions": ["Alzheimer's Disease"]},
        },
        "hasResults": True,
        "resultsSection": {
            "outcomeMeasuresModule": {
                "outcomeMeasures": [
                    {
                        "type": "PRIMARY",
                        "title": "ADAS-Cog Score Change",
                        "description": "Trial failed to meet primary endpoint: lack of efficacy.",
                        "analyses": [],
                    }
                ]
            }
        },
    }
    drug, disease = make_mock_drug_disease("Simvastatin", "Alzheimer's Disease")

    trials = pipeline._parse_trials_data({"studies": [study]}, drug, disease)
    assert len(trials) == 1
    assert trials[0].status == TrialOutcomeStatus.COMPLETED_FAILURE
    assert trials[0].is_negative_efficacy is True


def test_hasresults_alone_does_not_create_opposition():
    """hasResults=True alone without negative outcome or termination MUST NOT create opposition."""
    trial = make_test_trial(
        nct_id="NCT01234567",
        title="Observational registry",
        status=TrialOutcomeStatus.COMPLETED_SUCCESS,
        intervention_names=["Metformin"],
        condition_names=["Type 2 Diabetes"],
        is_negative_efficacy=False,
    )
    claim = trial_to_negative_claim(trial, "Metformin", "type 2 diabetes")
    assert claim is None


# ─────────────────────────────────────────────────────────────
# 6. REAL REGRESSION CASES (§17 Items 24-28)
# ─────────────────────────────────────────────────────────────

def test_real_case_aim_high_nct00120289():
    """AIM-HIGH NCT00120289: Niacin in CVD survives, attributes, and produces negative claim."""
    trial = make_test_trial(
        nct_id="NCT00120289",
        title="AIM-HIGH: Niacin Extended Release in High Risk CVD",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        why_stopped="Stopped early due to lack of efficacy / futility",
        intervention_names=["Niacin Extended-Release", "Simvastatin"],
        comparator_names=["Simvastatin", "Placebo"],
        condition_names=["Atherosclerosis", "Cardiovascular Disease"],
        is_negative_efficacy=True,
    )
    # 1. Disease relation: CVD -> Atherosclerosis is PARENT_CHILD
    assert matches_disease_condition(trial, "cardiovascular disease") is True
    # 2. Drug attribution: Niacin is differentiating
    attr = evaluate_trial_attribution(trial, "Niacin")
    assert attr.final_attribution_decision is True
    # 3. Negative claim produced
    claim = trial_to_negative_claim(trial, "Niacin", "cardiovascular disease")
    assert claim is not None
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE


def test_real_case_checkmate_498_nct02667587():
    """CheckMate 498 NCT02667587: Nivolumab in GBM attributes cleanly despite Nivolumab Placebo."""
    trial = make_test_trial(
        nct_id="NCT02667587",
        title="CheckMate 498: Nivolumab vs TMZ in Glioblastoma",
        status=TrialOutcomeStatus.COMPLETED_FAILURE,
        why_stopped="Primary endpoint of OS was not met",
        intervention_names=["Nivolumab", "Radiation"],
        comparator_names=["Temozolomide", "Nivolumab Placebo", "Radiation"],
        condition_names=["Glioblastoma"],
        is_negative_efficacy=True,
    )
    assert matches_disease_condition(trial, "glioblastoma") is True
    attr = evaluate_trial_attribution(trial, "Nivolumab")
    assert attr.is_differentiating_intervention is True
    assert attr.final_attribution_decision is True
    claim = trial_to_negative_claim(trial, "Nivolumab", "glioblastoma")
    assert claim is not None
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE


def test_real_case_dexamethasone_tbi_nct02362321():
    """Dexamethasone in TBI NCT02362321: Subdural Hematoma matches TBI query."""
    trial = make_test_trial(
        nct_id="NCT02362321",
        title="Dexamethasone for Chronic Subdural Hematoma",
        status=TrialOutcomeStatus.TERMINATED_SAFETY,
        why_stopped="Stopped early due to serious adverse events and increased mortality",
        intervention_names=["Dexamethasone"],
        comparator_names=["Placebo"],
        condition_names=["Hematoma, Subdural, Chronic"],
    )
    assert matches_disease_condition(trial, "traumatic brain injury") is True
    claim = trial_to_negative_claim(trial, "Dexamethasone", "traumatic brain injury")
    assert claim is not None
    assert claim.predicate == PredicateType.TERMINATED_FOR_SAFETY


# ─────────────────────────────────────────────────────────────
# 7. FULL EVIDENCE-LINEAGE TEST (§18)
# ─────────────────────────────────────────────────────────────

def test_full_evidence_lineage():
    """Deterministic end-to-end evidence lineage from raw JSON to OppositionAssessment."""
    raw_study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00120289", "briefTitle": "AIM-HIGH Trial"},
            "statusModule": {
                "overallStatus": "TERMINATED",
                "whyStopped": "Stopped early due to lack of efficacy at interim analysis",
            },
            "designModule": {"designInfo": {"allocation": "RANDOMIZED"}},
            "armsInterventionsModule": {
                "armGroups": [
                    {"type": "EXPERIMENTAL", "interventionNames": ["Niacin", "Simvastatin"]},
                    {"type": "ACTIVE_COMPARATOR", "interventionNames": ["Simvastatin", "Placebo"]},
                ]
            },
            "conditionsModule": {"conditions": ["Atherosclerosis"]},
        }
    }
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    drug, disease = make_mock_drug_disease("Niacin", "cardiovascular disease")

    # Stage 1: Raw -> Parsed ClinicalTrial
    trials = pipeline._parse_trials_data({"studies": [raw_study]}, drug, disease)
    assert len(trials) == 1
    trial = trials[0]
    raw_signal = trial.status
    assert raw_signal == TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY

    # Stage 2: Disease Relation
    disease_match = matches_disease_condition(trial, "cardiovascular disease")
    assert disease_match is True

    # Stage 3: Attribution
    attr = evaluate_trial_attribution(trial, "Niacin")
    attribution_signal = attr.final_attribution_decision
    assert attribution_signal is True
    assert attr.is_differentiating_intervention is True

    # Stage 4: Claim Creation
    claim = trial_to_negative_claim(trial, "Niacin", "cardiovascular disease")
    assert claim is not None
    claim_signal = claim.predicate
    assert claim_signal == PredicateType.FAILED_TO_IMPROVE

    # Stage 5: Opposition Assessment
    assessor = TherapeuticOppositionAssessor()
    opp = assessor.assess([claim], "Niacin", "cardiovascular disease")
    opposition_signal = opp.score
    assert opposition_signal > 0.0
    assert opp.level in ("MODERATE", "HIGH")


# ─────────────────────────────────────────────────────────────
# 8. PRE-BENCHMARK HARDENING ADVERSARIAL TESTS (§5)
# ─────────────────────────────────────────────────────────────

def test_hardening_a_empty_conditions_sibling_title_rejected():
    """A: conditions=[], title='Acute Hemorrhagic Stroke', query='Stroke' => NO MATCH."""
    trial = make_test_trial(
        nct_id="NCT08880001",
        title="Study of Intervention in Acute Hemorrhagic Stroke Patients",
        condition_names=[],
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
    )
    assert matches_disease_condition(trial, "Stroke") is False
    assert trial_to_negative_claim(trial, "DrugX", "Stroke") is None


def test_hardening_b_empty_conditions_parent_child_title_matched():
    """B: conditions=[], title='Chronic Subdural Hematoma', query='Traumatic Brain Injury' => MATCH via PARENT_CHILD."""
    trial = make_test_trial(
        nct_id="NCT08880002",
        title="Study in Chronic Subdural Hematoma Patients",
        condition_names=[],
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        why_stopped="Lack of efficacy",
        intervention_names=["DrugA"],
        comparator_names=["Placebo"],
    )
    assert matches_disease_condition(trial, "Traumatic Brain Injury") is True
    claim = trial_to_negative_claim(trial, "DrugA", "Traumatic Brain Injury")
    assert claim is not None
    assert claim.subject == "DrugA"
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE


def test_hardening_c_unresolved_combination_is_diff_false():
    """C: A+B vs C+D, candidate=A => is_diff=False."""
    trial = make_test_trial(
        nct_id="NCT08880003",
        title="Evaluation of Drug A and Drug B vs Drug C and Drug D",
        intervention_names=["Drug A", "Drug B"],
        comparator_names=["Drug C", "Drug D"],
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
    )
    role, intr_m, comp_m, is_diff, reason = analyze_trial_drug_role(trial, "Drug A")
    assert role == TrialDrugRole.EVALUATED_COMBINATION_COMPONENT
    assert is_diff is False


def test_hardening_d_unresolved_combination_whystopped_not_attributable():
    """D: A+B vs C+D with whyStopped='Drug A was ineffective' => still NOT attributable (design unresolved)."""
    trial = make_test_trial(
        nct_id="NCT08880004",
        title="Evaluation of Drug A and Drug B vs Drug C and Drug D",
        intervention_names=["Drug A", "Drug B"],
        comparator_names=["Drug C", "Drug D"],
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        why_stopped="Study stopped because Drug A was ineffective",
    )
    attr = evaluate_trial_attribution(trial, "Drug A")
    assert attr.is_differentiating_intervention is False
    assert attr.final_attribution_decision is False
    assert "unresolved combination contrast" in attr.attribution_reason
    assert trial_to_negative_claim(trial, "Drug A", "Some Disease") is None


def test_hardening_e_stroke_vs_hemorrhagic_stroke_strict_veto():
    """E: stroke vs hemorrhagic stroke => approval blocked, trial blocked."""
    rel = classify_disease_relation("stroke", "hemorrhagic stroke")
    assert rel == DiseaseRelation.SIBLING_EXCLUDED
    assert matches_for_approval_anchor("stroke", "hemorrhagic stroke") is False
    assert matches_for_approval_anchor("hemorrhagic stroke", "stroke") is False
    assert matches_for_trial_attribution("stroke", "hemorrhagic stroke") is False
    assert matches_for_trial_attribution("hemorrhagic stroke", "stroke") is False


def test_hardening_f_metformin_background_protection_preserved():
    """F: Metformin in NCT02020616 (LY3053102 + Metformin vs Placebo + Metformin) => NOT attributable."""
    trial = make_test_trial(
        nct_id="NCT02020616",
        title="A Study of LY3053102 in Participants With Type 2 Diabetes",
        intervention_names=["LY3053102", "Metformin"],
        comparator_names=["Placebo", "Metformin"],
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        why_stopped="Lack of Efficacy",
    )
    attr = evaluate_trial_attribution(trial, "Metformin")
    assert attr.final_attribution_decision is False
    assert attr.is_differentiating_intervention is False
    assert trial_to_negative_claim(trial, "Metformin", "Type 2 diabetes") is None


def test_hardening_g_nivolumab_placebo_remains_non_match():
    """G: Nivolumab Placebo remains non-match for candidate Nivolumab."""
    assert matches_drug("Nivolumab Placebo", "Nivolumab") is False
    assert is_placebo_component("Nivolumab Placebo") is True
    assert is_placebo_component("Placebo (Nivolumab)") is True
    assert is_placebo_component("Nivolumab-matched placebo") is True

