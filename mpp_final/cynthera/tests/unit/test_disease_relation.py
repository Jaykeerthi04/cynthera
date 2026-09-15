"""Unit tests for shared disease relation classification and matching policies."""
import pytest

from backend.engineering.retrieval.disease_relation import (
    DiseaseRelation,
    classify_disease_relation,
    matches_for_trial_attribution,
    matches_for_approval_anchor,
    evaluate_approval_anchor_match,
    evaluate_trial_attribution_match,
    normalize_disease_term,
)


def test_1_same_relation():
    """hypertension / hypertension => SAME"""
    assert classify_disease_relation("hypertension", "hypertension") == DiseaseRelation.SAME


def test_2_tbi_parent_child():
    """traumatic brain injury / subdural hematoma => PARENT_CHILD"""
    assert classify_disease_relation("traumatic brain injury", "subdural hematoma") == DiseaseRelation.PARENT_CHILD
    assert classify_disease_relation("subdural hematoma", "traumatic brain injury") == DiseaseRelation.PARENT_CHILD


def test_3_trial_matcher_tbi_subdural():
    """TBI / subdural hematoma => True in trial matcher"""
    assert matches_for_trial_attribution("TBI", "subdural hematoma") is True
    assert matches_for_trial_attribution("traumatic brain injury", "Hematoma, Subdural, Chronic") is True


def test_4_approval_matcher_tbi_subdural():
    """TBI / subdural hematoma => False in approval matcher (strict SAME only)"""
    assert matches_for_approval_anchor("TBI", "subdural hematoma") is False
    assert matches_for_approval_anchor("traumatic brain injury", "subdural hematoma") is False


def test_5_sibling_ischemic_hemorrhagic():
    """ischemic stroke / hemorrhagic stroke => SIBLING_EXCLUDED"""
    assert classify_disease_relation("ischemic stroke", "hemorrhagic stroke") == DiseaseRelation.SIBLING_EXCLUDED
    assert classify_disease_relation("hemorrhagic stroke", "ischemic stroke") == DiseaseRelation.SIBLING_EXCLUDED


def test_6_approval_stroke_hemorrhagic():
    """stroke / hemorrhagic stroke => False for approval anchor"""
    assert matches_for_approval_anchor("stroke", "hemorrhagic stroke") is False
    assert matches_for_approval_anchor("hemorrhagic stroke", "stroke") is False
    assert matches_for_approval_anchor("hemorrhagic stroke", "ischemic stroke") is False


def test_7_trial_matcher_stroke_hemorrhagic():
    """stroke / hemorrhagic stroke => False for trial matcher (sibling excluded)"""
    assert matches_for_trial_attribution("stroke", "hemorrhagic stroke") is False
    assert matches_for_trial_attribution("hemorrhagic stroke", "stroke") is False
    assert matches_for_trial_attribution("ischemic stroke", "hemorrhagic stroke") is False


def test_8_unrelated_diseases():
    """hypertension / glioblastoma => UNRELATED"""
    assert classify_disease_relation("hypertension", "glioblastoma") == DiseaseRelation.UNRELATED
    assert matches_for_trial_attribution("hypertension", "glioblastoma") is False
    assert matches_for_approval_anchor("hypertension", "glioblastoma") is False


def test_telemetry_generation():
    """Telemetry provides full audit traceability with policy and relation."""
    matched, tel = evaluate_approval_anchor_match("hemorrhagic stroke", "stroke")
    assert matched is False
    assert tel.relation == "SIBLING_EXCLUDED"
    assert tel.policy == "APPROVAL_ANCHOR"
    assert tel.to_dict() == {
        "query_disease": "hemorrhagic stroke",
        "candidate_term": "stroke",
        "relation": "SIBLING_EXCLUDED",
        "policy": "APPROVAL_ANCHOR",
        "matched": False,
    }

    matched_tr, tel_tr = evaluate_trial_attribution_match("traumatic brain injury", "hematoma, subdural, chronic")
    assert matched_tr is True
    assert tel_tr.relation == "PARENT_CHILD"
    assert tel_tr.policy == "TRIAL_ATTRIBUTION"
    assert tel_tr.matched is True
