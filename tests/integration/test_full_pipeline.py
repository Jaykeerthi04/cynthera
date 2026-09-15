"""Integration tests — full pipeline with mocked external connectors.

Tests the complete CYNTHERA pipeline using mocked HTTP connectors
to avoid external API calls during CI/CD.

Scientific validation cases:
- Sildenafil → Pulmonary Arterial Hypertension (should be PROMISING)
- Metformin → Type 2 Diabetes (should be PROMISING or UNCERTAIN)
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.evidence import Evidence
from backend.core.domain.target import Target
from backend.core.domain.pathway import Pathway
from backend.core.domain.protein import Protein
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.enums.evidence_type import EvidenceType
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.enums.recommendation import RecommendationStatus
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
from datetime import datetime


# ─────────────────────────────────────────────
# Test Package Builders
# ─────────────────────────────────────────────

def _make_provenance(source: str) -> ProvenanceReference:
    return ProvenanceReference(
        source_name=source,
        source_version="v1.0",
        record_id=f"raw_{source}_001",
        url=f"https://{source}.example.com",
    )


def _build_sildenafil_pah_package() -> RetrievalPackage:
    """Build a realistic mock RetrievalPackage for Sildenafil → PAH."""
    hypothesis_id = uuid.uuid4()
    drug = Drug(name="Sildenafil", identifiers={"chembl_id": "CHEMBL192"})
    disease = Disease(name="Pulmonary Arterial Hypertension", identifiers={"mesh_id": "D000081029"})

    prov = _make_provenance("ChEMBL")
    erw = ERW.from_base(base_weight=0.85)
    targets = [
        Target(
            drug_chembl_id="CHEMBL192",
            protein_uniprot="O76074",
            affinity_nm=1.0,
            affinity_type="IC50",
            mechanism="INHIBITOR",
            erw=erw,
            provenance=prov,
        )
    ]

    proteins = [
        Protein(
            uniprot_accession="O76074",
            gene_symbol="PDE5A",
            name="cGMP-specific 3',5'-cyclic phosphodiesterase",
            organism="Homo sapiens",
        )
    ]

    pathways = [
        Pathway(
            reactome_id="R-HSA-418457",
            name="cGMP/PKG signalling",
            gene_count=12,
        ),
        Pathway(
            reactome_id="R-HSA-390522",
            name="Pulmonary vascular smooth muscle contraction",
            gene_count=8,
        ),
    ]

    evidence_records = [
        Evidence(
            hypothesis_id=hypothesis_id,
            title="Sildenafil in Pulmonary Arterial Hypertension: A Systematic Review",
            abstract=(
                "Sildenafil activates PDE5A inhibition, leading to cGMP elevation "
                "and pulmonary vasodilation, improving PAH outcomes."
            ),
            evidence_type=EvidenceType.META_ANALYSIS,
            erw=ERW(value=0.92),
            source="pubmed",
            provenance=_make_provenance("pubmed"),
        ),
        Evidence(
            hypothesis_id=hypothesis_id,
            title="RCT: Sildenafil vs Placebo in PAH",
            abstract="Sildenafil prevents pulmonary vasoconstriction in PAH patients.",
            evidence_type=EvidenceType.RCT,
            erw=ERW(value=0.85),
            source="pubmed",
            provenance=_make_provenance("pubmed"),
        ),
        Evidence(
            hypothesis_id=hypothesis_id,
            title="PDE5 inhibition in vascular smooth muscle",
            abstract="Sildenafil binds PDE5A and inhibits cGMP degradation.",
            evidence_type=EvidenceType.IN_VITRO,
            erw=ERW(value=0.70),
            source="pubmed",
            provenance=_make_provenance("pubmed"),
        ),
    ]

    clinical_trials = [
        ClinicalTrial(
            nct_id="NCT00407485",
            title="Sildenafil in Pulmonary Arterial Hypertension",
            drug_name="Sildenafil",
            disease_name="Pulmonary Arterial Hypertension",
            status=TrialOutcomeStatus.COMPLETED_SUCCESS,
            phase="Phase III",
            provenance=prov,
        )
    ]

    return RetrievalPackage(
        hypothesis_id=hypothesis_id,
        drug=drug,
        disease=disease,
        targets=targets,
        proteins=proteins,
        pathways=pathways,
        evidence_records=evidence_records,
        clinical_trials=clinical_trials,
        retrieval_confidence="HIGH",
        sources_queried=["chembl", "uniprot", "pubmed", "reactome", "clinicaltrials"],
        sources_failed=[],
        sealed_at=datetime.utcnow(),
    )


def _build_metformin_t2d_package() -> RetrievalPackage:
    """Build a mock RetrievalPackage for Metformin → Type 2 Diabetes."""
    hypothesis_id = uuid.uuid4()
    drug = Drug(name="Metformin", identifiers={"chembl_id": "CHEMBL1431"})
    disease = Disease(name="Type 2 Diabetes", identifiers={"mesh_id": "D003924"})

    prov = _make_provenance("ChEMBL")
    erw = ERW.from_base(base_weight=0.85)

    targets = [
        Target(
            drug_chembl_id="CHEMBL1431",
            protein_uniprot="Q13131",
            affinity_nm=10.0,
            affinity_type="IC50",
            mechanism="ACTIVATOR",
            erw=erw,
            provenance=prov,
        )
    ]

    pathways = [
        Pathway(
            reactome_id="R-HSA-380972",
            name="Energy sensing",
            gene_count=6,
        ),
    ]

    evidence_records = [
        Evidence(
            hypothesis_id=hypothesis_id,
            title="Metformin activates AMPK and reduces hepatic gluconeogenesis",
            abstract="AMPK activation prevents insulin resistance in T2D.",
            evidence_type=EvidenceType.RCT,
            erw=ERW(value=0.88),
            source="pubmed",
            provenance=_make_provenance("pubmed"),
        ),
        Evidence(
            hypothesis_id=hypothesis_id,
            title="Long-term glycemic control with Metformin",
            abstract="Metformin causes weight loss and prevents T2D complications.",
            evidence_type=EvidenceType.META_ANALYSIS,
            erw=ERW(value=0.90),
            source="pubmed",
            provenance=_make_provenance("pubmed"),
        ),
    ]

    clinical_trials = [
        ClinicalTrial(
            nct_id="NCT00004608",
            title="Metformin in Type 2 Diabetes",
            drug_name="Metformin",
            disease_name="Type 2 Diabetes",
            status=TrialOutcomeStatus.COMPLETED_SUCCESS,
            phase="Phase III",
            provenance=prov,
        )
    ]

    return RetrievalPackage(
        hypothesis_id=hypothesis_id,
        drug=drug,
        disease=disease,
        targets=targets,
        proteins=[],
        pathways=pathways,
        evidence_records=evidence_records,
        clinical_trials=clinical_trials,
        retrieval_confidence="MEDIUM",
        sources_queried=["chembl", "pubmed", "reactome", "clinicaltrials"],
        sources_failed=["uniprot"],
        sealed_at=datetime.utcnow(),
    )


# ─────────────────────────────────────────────
# Integration Tests
# ─────────────────────────────────────────────

def _build_minimal_context_pkg() -> RetrievalPackage:
    """Minimal, model-valid Sildenafil/PAH package used by context regressions.

    Independent of the (stale) _build_sildenafil_pah_package helper so that the
    ScientificContext / Rule -1 assertions do not depend on unrelated test
    builders that reference a non-existent EvidenceType member.
    """
    return _build_minimal_context_package(approved=False, disease_name="Pulmonary Arterial Hypertension")


def _build_minimal_context_package(
    approved: bool = False,
    drug_name: str = "Sildenafil",
    disease_name: str = "Pulmonary Arterial Hypertension",
) -> RetrievalPackage:
    hypothesis_id = uuid.uuid4()
    drug = Drug(name=drug_name, identifiers={"chembl_id": "CHEMBL192"})
    disease = Disease(name=disease_name, identifiers={"mesh_id": "D000081029"})

    evidence = [
        Evidence(
            hypothesis_id=hypothesis_id,
            title="Sildenafil in PAH: systematic review",
            abstract="Sildenafil PDE5A inhibition improves PAH outcomes.",
            evidence_type=EvidenceType.META_ANALYSIS,
            erw=ERW(value=0.9),
            source="pubmed",
            provenance=_make_provenance("pubmed"),
        ),
        Evidence(
            hypothesis_id=hypothesis_id,
            title="PDE5 inhibition in vascular smooth muscle",
            abstract="Sildenafil binds PDE5A in vitro.",
            evidence_type=EvidenceType.IN_VITRO,
            erw=ERW(value=0.6),
            source="pubmed",
            provenance=_make_provenance("pubmed"),
        ),
    ]

    trials = [
        ClinicalTrial(
            nct_id="NCT00412446",
            title="Sildenafil in Pulmonary Arterial Hypertension",
            phase="Phase III",
            status=TrialOutcomeStatus.COMPLETED_SUCCESS,
            provenance=_make_provenance("ClinicalTrials.gov"),
        )
    ]

    approval_signal = None
    if approved:
        from backend.core.domain.approval_signal import ApprovalSignal
        approval_signal = ApprovalSignal.from_chembl_indication_match(
            max_phase=4,
            matched_term="Pulmonary Arterial Hypertension",
            match_confidence=0.95,
            approved_count=3,
        )

    return RetrievalPackage(
        hypothesis_id=hypothesis_id,
        drug=drug,
        disease=disease,
        evidence_records=evidence,
        clinical_trials=trials,
        approval_signal=approval_signal,
        retrieval_confidence="HIGH",
        sources_queried=["chembl", "uniprot", "pubmed", "reactome", "clinicaltrials"],
        sources_failed=[],
        sealed_at=datetime.utcnow(),
    )


class TestFullReasoningPipeline:
    """Integration tests for the full reasoning pipeline."""

    @pytest.fixture
    def orchestrator(self, tmp_path):
        db_path = str(tmp_path / "test_integration.db")
        return ReasoningOrchestrator(
            llm_api_key=None,
            llm_model="gemini-1.5-flash",
            db_path=db_path,
        )

    @pytest.mark.asyncio
    async def test_sildenafil_pah_promising(self, orchestrator):
        """Sildenafil/PAH canonical case: should produce PROMISING or UNCERTAIN.

        With strong evidence (meta-analysis, RCT), high mechanistic data (PDE5A,
        cGMP pathway), and successful trial — expect PROMISING or at least UNCERTAIN.
        """
        package = _build_sildenafil_pah_package()

        # Mock the claim extraction to return realistic claims
        with patch.object(orchestrator._extraction_agent, "extract_claims") as mock_extract:
            from backend.core.domain.claim import Claim

            def make_claim(predicate, subject="Sildenafil", obj="PDE5A", erw_val=0.8):
                c = MagicMock(spec=Claim)
                c.id = uuid.uuid4()
                c.subject = subject
                c.object = obj
                c.predicate = predicate
                c.erw = MagicMock()
                c.erw.value = erw_val
                c.statement = f"{subject} {predicate} {obj}"
                c.raw_text = ""
                c.evidence_ids = []
                c.provenance = None
                return c

            from backend.core.enums.predicate_type import PredicateType
            mock_claims = [
                make_claim(PredicateType.INHIBITS, erw_val=0.9),
                make_claim(PredicateType.ACTIVATES, erw_val=0.85),
                make_claim(PredicateType.PREVENTS, "Sildenafil", "vasoconstriction", 0.8),
            ]
            mock_extract.return_value = mock_claims

            result = await orchestrator.reason(package)

        # Assertions
        assert result is not None
        assert result.recommendation_status in (
            RecommendationStatus.PROMISING,
            RecommendationStatus.UNCERTAIN,
        )
        assert 0.0 <= result.support_assessment.score <= 1.0
        assert 0.0 <= result.mechanistic_assessment.score <= 1.0
        assert 0.0 <= result.risk_assessment.score <= 1.0
        assert result.audit_report.summary != ""
        assert len(result.recommendation_reasons) > 0

    @pytest.mark.asyncio
    async def test_metformin_t2d_pipeline(self, orchestrator):
        """Metformin/T2D: should run full pipeline without errors."""
        package = _build_metformin_t2d_package()

        with patch.object(orchestrator._extraction_agent, "extract_claims") as mock_extract:
            mock_extract.return_value = []  # No claims extracted
            result = await orchestrator.reason(package)

        assert result is not None
        assert result.recommendation_status in RecommendationStatus
        assert result.rule_set_version == "3.2"  # Current rule set version

    @pytest.mark.asyncio
    async def test_result_has_required_fields(self, orchestrator):
        """ReasoningResult should have all required fields populated."""
        package = _build_sildenafil_pah_package()

        with patch.object(orchestrator._extraction_agent, "extract_claims") as mock_extract:
            mock_extract.return_value = []
            result = await orchestrator.reason(package)

        assert result.hypothesis_id == package.hypothesis_id
        assert result.support_assessment is not None
        assert result.mechanistic_assessment is not None
        assert result.risk_assessment is not None
        assert result.audit_report is not None
        assert result.reasoning_duration_ms >= 0
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_high_risk_yields_not_recommended(self, orchestrator):
        """Package with multiple failed safety trials should yield NOT_RECOMMENDED."""
        package = _build_sildenafil_pah_package()

        # Add safety-terminated trials
        failed_trials = []
        for i in range(3):
            t = ClinicalTrial(
                nct_id=f"NCT9999000{i}",
                title=f"Trial {i} terminated for fatal adverse events black box",
                phase="Phase III",
                status=TrialOutcomeStatus.TERMINATED_SAFETY,
                primary_outcome="Life-threatening toxicity observed",
                provenance=ProvenanceReference(
                    source_name="clinicaltrials.gov",
                    source_version="v1.0",
                    record_id=f"NCT9999000{i}",
                ),
            )
            failed_trials.append(t)

        # Replace trials in package
        package = package.model_copy(update={"clinical_trials": failed_trials})

        with patch.object(orchestrator._extraction_agent, "extract_claims") as mock_extract:
            mock_extract.return_value = []
            result = await orchestrator.reason(package)

        # With safety terminations, risk should be elevated
        assert result.risk_assessment.score > 0.3

    @pytest.mark.asyncio
    async def test_prior_knowledge_enriches_result(self, orchestrator):
        """Prior knowledge context should contribute to the audit report."""
        package = _build_sildenafil_pah_package()

        with patch.object(orchestrator._extraction_agent, "extract_claims") as mock_extract:
            mock_extract.return_value = []
            result = await orchestrator.reason(package)

        # The audit report summary should contain Phase 2 context
        assert "Prior knowledge" in result.audit_report.summary

    @pytest.mark.asyncio
    async def test_score_in_unit_range(self, orchestrator):
        """All scores must be in [0.0, 1.0]."""
        package = _build_sildenafil_pah_package()

        with patch.object(orchestrator._extraction_agent, "extract_claims") as mock_extract:
            mock_extract.return_value = []
            result = await orchestrator.reason(package)

        assert 0.0 <= result.support_assessment.score <= 1.0
        assert 0.0 <= result.mechanistic_assessment.score <= 1.0
        assert 0.0 <= result.risk_assessment.score <= 1.0

    @pytest.mark.asyncio
    async def test_scientific_context_surfaces_in_audit(self, orchestrator):
        """Audit report should contain the five-dimensional ScientificContext."""
        package = _build_minimal_context_pkg()
        with patch.object(orchestrator._extraction_agent, "extract_claims") as mock_extract:
            mock_extract.return_value = []
            result = await orchestrator.reason(package)

        sc = result.audit_report.scientific_context
        assert set(sc) == {"regulatory", "repurposing", "mechanistic",
                           "clinical", "knowledge_maturity", "related_pairs"}
        for dim in ("regulatory", "repurposing", "mechanistic", "clinical", "knowledge_maturity"):
            assert "status" in sc[dim]
            assert "confidence" in sc[dim]
            assert "evidence" in sc[dim]

    @pytest.mark.asyncio
    async def test_rule_minus1_only_for_live_approval(self, orchestrator):
        """Rule -1 must fire ONLY on a live ChEMBL APPROVED signal.

        Regression: the cache-only route previously promoted an established,
        high-similarity seed pair (Sildenafil/PAH) to APPROVED and could grant
        the Rule -1 bypass without live ChEMBL data. It must no longer do so.
        """
        # No approval signal → cache seed alone must not fire Rule -1.
        pkg_no_signal = _build_minimal_context_package(approved=False)
        with patch.object(orchestrator._extraction_agent, "extract_claims") as mock_extract:
            mock_extract.return_value = []
            result_no_signal = await orchestrator.reason(pkg_no_signal)

        assert not any(r.startswith("Rule -1") for r in result_no_signal.recommendation_reasons)
        assert result_no_signal.audit_report.scientific_context["regulatory"]["status"] == "NONE"

        # Live approval present → Rule -1 fires.
        pkg_approved = _build_minimal_context_package(approved=True)
        with patch.object(orchestrator._extraction_agent, "extract_claims") as mock_extract:
            mock_extract.return_value = []
            result_approved = await orchestrator.reason(pkg_approved)

        assert any(r.startswith("Rule -1") for r in result_approved.recommendation_reasons)
        assert result_approved.audit_report.scientific_context["regulatory"]["status"] == "APPROVED"
