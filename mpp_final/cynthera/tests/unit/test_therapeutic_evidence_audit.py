"""Regression tests for therapeutic-evidence provenance gates."""
from __future__ import annotations

import uuid

from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.disease import Disease
from backend.core.domain.drug import Drug
from backend.core.domain.evidence import Evidence
from backend.core.domain.reasoning_result import (
    MechanisticAssessment,
    RiskAssessment,
    SupportAssessment,
)
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.contradiction_summary import ContradictionSummary
from backend.core.enums.recommendation import RecommendationStatus
from backend.core.enums.evidence_type import EvidenceType
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.identifier import CanonicalIdentifier, ResolvedIdentifierSet
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.agents.clinical_safety_agent import SafetyProfile
from backend.reasoning.agents.prior_knowledge_agent import PriorKnowledgeContext
from backend.reasoning.context.scientific_context_builder import (
    DimensionalAssessment,
    ScientificContext,
)
from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
from backend.reasoning.therapeutic_evidence_audit import (
    has_high_quality_therapeutic_evidence,
)


def _package(*, evidence_records=None, clinical_trials=None) -> RetrievalPackage:
    drug = Drug(
        name="TestDrug",
        identifiers=ResolvedIdentifierSet(
            entity_name="TestDrug",
            entity_type="drug",
            identifiers=[CanonicalIdentifier(namespace="chembl", value="CHEMBL1")],
        ),
    )
    disease = Disease(
        name="Test Disease",
        identifiers=ResolvedIdentifierSet(
            entity_name="Test Disease",
            entity_type="disease",
            identifiers=[CanonicalIdentifier(namespace="mesh", value="D000001")],
        ),
    )
    return RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        evidence_records=evidence_records or [],
        clinical_trials=clinical_trials or [],
    )


def _clinical_record(citation_key: str) -> Evidence:
    return Evidence(
        evidence_type=EvidenceType.RCT,
        erw=ERW(value=0.85, rationale="study type"),
        citation_key=citation_key,
        provenance=ProvenanceReference(
            source_name="PubMed", source_version="test", record_id=citation_key
        ),
        drug_chembl_id="CHEMBL1",
        disease_identifier="D000001",
    )


def test_generic_clinical_record_volume_does_not_certify_therapy():
    """Study type + pair tags lack a structured efficacy direction/outcome."""
    approved, audit = has_high_quality_therapeutic_evidence(
        _package(evidence_records=[_clinical_record("PMID:1"), _clinical_record("PMID:2")])
    )

    assert approved is False
    assert len(audit) == 2
    assert all(not item.allowed_for_high_quality_therapeutic for item in audit)
    assert all(item.direction == "UNKNOWN" for item in audit)


def test_explicit_successful_pair_scoped_trial_can_certify_therapy():
    trial = ClinicalTrial(
        nct_id="NCT00000001",
        title="Successful TestDrug trial in Test Disease",
        phase="Phase III",
        status=TrialOutcomeStatus.COMPLETED_SUCCESS,
        drug_chembl_id="CHEMBL1",
        disease_identifier="D000001",
        provenance=ProvenanceReference(
            source_name="ClinicalTrials.gov", source_version="test", record_id="NCT00000001"
        ),
    )

    approved, audit = has_high_quality_therapeutic_evidence(_package(clinical_trials=[trial]))

    assert approved is True
    assert audit[0].allowed_for_high_quality_therapeutic is True
    assert audit[0].direction == "SUPPORTS"


def test_completed_registry_status_is_not_normalized_as_success():
    """ClinicalTrials.gov completion says nothing about the primary endpoint."""
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    trials = pipeline._parse_trials_data(
        {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {"nctId": "NCT00000002", "briefTitle": "Completed study"},
                        "statusModule": {"overallStatus": "COMPLETED"},
                        "designModule": {"phases": ["PHASE3"]},
                    }
                }
            ]
        },
        _package().drug,
        _package().disease,
    )

    assert trials[0].status == TrialOutcomeStatus.UNKNOWN


def test_directional_opposition_is_not_bypassed_by_approval_pathway():
    """An approval signal cannot override pair-specific evidence of opposition."""
    context = ScientificContext(
        DimensionalAssessment("regulatory", "APPROVED", 1.0, []),
        DimensionalAssessment("repurposing", "ESTABLISHED", 1.0, []),
        DimensionalAssessment("mechanistic", "MECHANISTIC_WEAK", 0.0, []),
        DimensionalAssessment("clinical", "CLINICAL_HUMAN", 0.9, []),
        DimensionalAssessment("maturity", "HIGH", 0.9, []),
    )
    status, _ = ReasoningOrchestrator()._apply_rules(
        support=SupportAssessment(score=0.9, level="HIGH", has_high_quality_therapeutic=True),
        mechanistic=MechanisticAssessment(score=0.0, level="NONE"),
        risk=RiskAssessment(score=0.1, level="LOW"),
        contradictions=[],
        package=_package(),
        safety_profile=SafetyProfile(overall_safety_grade="A"),
        prior_ctx=PriorKnowledgeContext(),
        scientific_context=context,
        contradiction_summary=ContradictionSummary(resolution="OPPOSES"),
    )

    assert status == RecommendationStatus.NOT_RECOMMENDED
