"""Unit tests for CYNTHERA Analyze API & DTOs."""
import uuid
import pytest

from backend.api.dtos import AnalysisResultDTO, ReportModelDTO
from backend.api.dto_builder import build_analysis_result_dto, build_report_model_dto
from backend.core.domain.hypothesis import Hypothesis
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.approval_signal import ApprovalSignal
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.reasoning_result import (
    ReasoningResult,
    SupportAssessment,
    MechanisticAssessment,
    RiskAssessment,
    OppositionAssessment,
    ScientificAuditReport,
)
from backend.core.enums.recommendation import RecommendationStatus
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.core.value_objects.identifier import CanonicalIdentifier, ResolvedIdentifierSet


def _make_drug(name: str, chembl_id: str = "CHEMBL644") -> Drug:
    ids = ResolvedIdentifierSet(
        entity_name=name,
        entity_type="drug",
        identifiers=[CanonicalIdentifier(namespace="chembl", value=chembl_id)],
    )
    return Drug(name=name, identifiers=ids)


def _make_disease(name: str, mesh_id: str = "D000086382") -> Disease:
    ids = ResolvedIdentifierSet(
        entity_name=name,
        entity_type="disease",
        identifiers=[CanonicalIdentifier(namespace="mesh", value=mesh_id)],
    )
    return Disease(name=name, identifiers=ids)


@pytest.fixture
def sample_data():
    hypo_id = uuid.uuid4()
    hypo = Hypothesis(
        id=hypo_id,
        drug_name="Azithromycin",
        disease_name="COVID-19",
        retrieval_policy=RetrievalPolicy.STANDARD,
    )
    drug = _make_drug("Azithromycin", "CHEMBL644")
    disease = _make_disease("COVID-19", "D000086382")
    signal = ApprovalSignal(
        is_approved=False,
        max_phase=3,
        matched_indication_term="COVID-19",
        match_confidence=0.98,
        approved_indications_count=12,
        global_approval_phase=4,
        matched_indication_phase=3,
    )
    package = RetrievalPackage(
        id=uuid.uuid4(),
        hypothesis_id=hypo_id,
        drug=drug,
        disease=disease,
        approval_signal=signal,
        sources_queried=["ChEMBL", "PubMed", "ClinicalTrials.gov"],
        sources_failed=["Semantic Scholar"],
    )
    result = ReasoningResult(
        hypothesis_id=hypo_id,
        recommendation_status=RecommendationStatus.NOT_RECOMMENDED,
        recommendation_reasons=["Pair-specific negative clinical evidence contradicts efficacy."],
        support_assessment=SupportAssessment(
            score=0.2,
            level="LOW",
            rationale="Weak supportive claims.",
        ),
        mechanistic_assessment=MechanisticAssessment(
            score=0.3,
            level="LOW",
            rationale="Indirect mechanistic plausibility only.",
        ),
        risk_assessment=RiskAssessment(
            score=0.7,
            level="HIGH",
            failed_trial_count=2,
            rationale="High trial failure rate.",
        ),
        opposition_assessment=OppositionAssessment(
            score=0.85,
            level="HIGH",
            independent_group_count=2,
            qualified_negative_claim_count=2,
            rationale="Two pair-specific RCTs demonstrated no benefit.",
        ),
        audit_report=ScientificAuditReport(
            summary="Azithromycin demonstrated no clinical benefit for COVID-19 in dedicated trials.",
            recommendation_rationale="Opposition veto applied.",
        ),
        data_source_failures=["Semantic Scholar unavailable during retrieval."],
    )
    return hypo, package, result


def test_build_analysis_result_dto_azithromycin(sample_data):
    hypo, package, result = sample_data
    dto = build_analysis_result_dto(hypo, package, result)

    assert isinstance(dto, AnalysisResultDTO)
    assert dto.decision.verdict == "OPPOSE"
    assert dto.decision.recommendation == "NOT_RECOMMENDED"
    assert dto.decision.opposition == "HIGH"
    assert dto.drug.name == "Azithromycin"
    assert dto.disease.name == "COVID-19"
    assert "Semantic Scholar" in dto.sources["failed"]
    assert dto.status == "partial"
    assert any("Semantic Scholar" in lim for lim in dto.limitations)


def test_build_report_model_dto(sample_data):
    hypo, package, result = sample_data
    report = build_report_model_dto(hypo, package, result)

    assert isinstance(report, ReportModelDTO)
    assert report.decision.verdict == "OPPOSE"
    assert report.decision.recommendation == "NOT_RECOMMENDED"
    assert "Azithromycin" in report.evaluated_hypothesis
    assert "COVID-19" in report.evaluated_hypothesis
    assert report.safety_analysis.risk_level == "HIGH"
