"""Tests for OppositionAssessment and ReasoningResult integration (Phase 5.16).

Verifies strict type identity, real-model instantiation (no MagicMock for required
ReasoningResult fields), and JSON serialization / validation round-trips.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from backend.core.domain.claim import Claim
from backend.core.domain.reasoning_result import (
    MechanisticAssessment,
    OppositionAssessment,
    ReasoningResult,
    RiskAssessment,
    ScientificAuditReport,
    SupportAssessment,
)
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.recommendation import RecommendationStatus
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
)


def _make_sample_negative_claim() -> Claim:
    return Claim(
        subject="Fluvoxamine",
        predicate=PredicateType.FAILED_TO_IMPROVE,
        object="COVID-19",
        confidence=0.85,
        erw=ERW(
            value=0.85,
            base_weight=0.85,
        ),
        provenance=ProvenanceReference(
            source_name="clinicaltrials",
            source_version="2024",
            record_id="NCT04727424",
            url="https://clinicaltrials.gov/study/NCT04727424",
        ),
        raw_text="Fluvoxamine failed to improve clinical recovery in COVID-19 patients.",
    )


def _make_real_reasoning_result(
    opposition: OppositionAssessment | None = None,
) -> ReasoningResult:
    """Build a real ReasoningResult instance with real sub-models and no MagicMocks."""
    opp = opposition if opposition is not None else OppositionAssessment.empty()
    return ReasoningResult(
        hypothesis_id=uuid.uuid4(),
        support_assessment=SupportAssessment(
            score=0.45,
            level="MEDIUM",
            rationale="Sample support rationale.",
            key_claim_ids=[],
        ),
        mechanistic_assessment=MechanisticAssessment(
            score=0.50,
            level="MEDIUM",
            rationale="Sample mechanistic rationale.",
            pathway_ids=[],
        ),
        risk_assessment=RiskAssessment(
            score=0.20,
            level="LOW",
            rationale="Sample risk rationale.",
            risk_claim_ids=[],
        ),
        opposition_assessment=opp,
        recommendation_status=RecommendationStatus.UNCERTAIN,
        recommendation_reasons=["Test rule triggered"],
        audit_report=ScientificAuditReport(
            summary="Test scientific audit summary",
            confidence_narrative="Confidence narrative test",
            recommendation_rationale="Recommendation rationale test",
            data_gaps=[],
        ),
        rule_set_version="3.2",
        reasoning_duration_ms=120.0,
        completed_at=datetime.utcnow(),
    )


def test_a_assessor_returns_exact_annotated_type():
    """A. TherapeuticOppositionAssessor.assess(...) returns exactly the class expected by ReasoningResult."""
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([], "Fluvoxamine", "COVID-19")

    expected_annotation = ReasoningResult.model_fields["opposition_assessment"].annotation

    assert type(assessment) is expected_annotation, (
        f"Type mismatch: returned {type(assessment)} ({type(assessment).__module__}) "
        f"vs expected {expected_annotation} ({expected_annotation.__module__})"
    )
    assert type(assessment) is OppositionAssessment


def test_b_real_reasoning_result_accepts_assessor_output():
    """B. A real ReasoningResult accepts assessor output without ValidationError."""
    claim = _make_sample_negative_claim()
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "Fluvoxamine", "COVID-19")

    assert assessment.score > 0.0
    assert assessment.level != "NONE"

    rr = _make_real_reasoning_result(opposition=assessment)
    assert rr.opposition_assessment.score == assessment.score
    assert rr.opposition_assessment.level == assessment.level
    assert rr.opposition_assessment.independent_group_count == assessment.independent_group_count


def test_c_empty_opposition_assessment_accepted():
    """C. OppositionAssessment.empty() is accepted by ReasoningResult."""
    empty_opp = OppositionAssessment.empty()
    assert empty_opp.score == 0.0
    assert empty_opp.level == "NONE"

    rr = _make_real_reasoning_result(opposition=empty_opp)
    assert rr.opposition_assessment.score == 0.0
    assert rr.opposition_assessment.level == "NONE"


def test_d_e_model_dump_json_preserves_nested_opposition():
    """D & E. model_dump(mode='json') preserves opposition_assessment and nested values."""
    claim = _make_sample_negative_claim()
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "Fluvoxamine", "COVID-19")

    rr = _make_real_reasoning_result(opposition=assessment)
    dumped = rr.model_dump(mode="json")

    assert "opposition_assessment" in dumped
    opp_dict = dumped["opposition_assessment"]
    assert isinstance(opp_dict, dict)
    assert opp_dict["score"] == assessment.score
    assert opp_dict["level"] == assessment.level
    assert opp_dict["independent_group_count"] == assessment.independent_group_count
    assert opp_dict["qualified_negative_claim_count"] == assessment.qualified_negative_claim_count
    assert opp_dict["strongest_group_weight"] == assessment.strongest_group_weight


def test_f_model_validate_json_round_trip():
    """F. model_dump_json() and model_validate_json() round-trip preserves OppositionAssessment."""
    claim = _make_sample_negative_claim()
    assessor = TherapeuticOppositionAssessor()
    assessment = assessor.assess([claim], "Fluvoxamine", "COVID-19")

    rr = _make_real_reasoning_result(opposition=assessment)
    json_str = rr.model_dump_json()

    restored = ReasoningResult.model_validate_json(json_str)
    assert isinstance(restored.opposition_assessment, OppositionAssessment)
    assert restored.opposition_assessment.score == assessment.score
    assert restored.opposition_assessment.level == assessment.level
    assert restored.opposition_assessment.independent_group_count == assessment.independent_group_count
    assert restored.opposition_assessment.qualified_negative_claim_count == assessment.qualified_negative_claim_count
    assert restored.opposition_assessment.strongest_group_weight == assessment.strongest_group_weight
