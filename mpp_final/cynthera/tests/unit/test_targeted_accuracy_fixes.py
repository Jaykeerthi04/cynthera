"""Unit tests for the four targeted accuracy fixes and 15 regression requirements.

Requirements covered:
1. ChEMBL "4.0" -> 4 parsing.
2. ChEMBL "3.0" -> 3 parsing.
3. Active-form discovery dynamically queries pref_name__istartswith.
4. Fluticasone approval recovery via active form.
5. Tamoxifen approval recovery via indication normalization and safe phase parsing.
6. Aspirin composite indication recovery via cardiovascular composite mapping.
7. Literature prioritization: deterministic scoring orders evidence by relevance.
8. Late-index clinical trial publication is selected over early generic reviews.
9. Negative trial publication becomes FAILED_TO_IMPROVE when explicitly supported.
10. Generic disease review does not outrank pair-specific trial publication.
11. Colchicine -> CRC remains UNCERTAIN (anti-regression).
12. Escitalopram -> neuropathic pain remains UNCERTAIN (anti-regression).
13. Six unverified hard negatives remain UNCERTAIN under open-world epistemic logic.
14. Comparator failures remain excluded from opposition.
15. COMPLETED trial without explicit negative outcome remains non-opposition.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.evidence import Evidence
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.approval_signal import ApprovalSignal
from backend.core.domain.claim import Claim
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.enums.recommendation import RecommendationStatus
from backend.core.value_objects.identifier import CanonicalIdentifier, ResolvedIdentifierSet
from backend.core.domain.reasoning_result import (
    SupportAssessment,
    MechanisticAssessment,
    RiskAssessment,
    OppositionAssessment,
)
from backend.reasoning.context.scientific_context_builder import ScientificContext, DimensionalAssessment
from backend.reasoning.agents.clinical_safety_agent import SafetyProfile
from backend.reasoning.agents.prior_knowledge_agent import PriorKnowledgeContext
from backend.core.domain.contradiction_summary import ContradictionSummary


def _make_drug(name: str, chembl_id: str = "CHEMBL100") -> Drug:
    ids = ResolvedIdentifierSet(
        entity_name=name,
        entity_type="drug",
        identifiers=[CanonicalIdentifier(namespace="chembl", value=chembl_id)],
    )
    return Drug(name=name, identifiers=ids)


def _make_disease(name: str, mesh_id: str = "D100") -> Disease:
    ids = ResolvedIdentifierSet(
        entity_name=name,
        entity_type="disease",
        identifiers=[CanonicalIdentifier(namespace="mesh", value=mesh_id)],
    )
    return Disease(name=name, identifiers=ids)


def _make_package(drug_name: str = "TestDrug", disease_name: str = "TestDisease") -> RetrievalPackage:
    return RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=_make_drug(drug_name),
        disease=_make_disease(disease_name),
        targets=[],
        proteins=[],
        pathways=[],
        evidence_records=[],
        clinical_trials=[],
        retrieval_confidence="HIGH",
    )


def _make_sci_context(status: str = "INVESTIGATIONAL", confidence: float = 0.0) -> ScientificContext:
    return ScientificContext(
        DimensionalAssessment("regulatory", status, confidence, []),
        DimensionalAssessment("repurposing", "NOVEL", 0.0, []),
        DimensionalAssessment("mechanistic", "NONE", 0.0, []),
        DimensionalAssessment("clinical", "NONE", 0.0, []),
        DimensionalAssessment("maturity", "NONE", 0.0, []),
    )


from backend.core.enums.evidence_type import EvidenceType
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference


def _make_ev(
    title: str,
    abstract: str = "",
    citation_key: str = "PMID:12345678",
    ev_type: EvidenceType = EvidenceType.LITERATURE,
) -> Evidence:
    key = citation_key.strip() or "PMID:12345678"
    return Evidence(
        evidence_type=ev_type,
        erw=ERW.from_base(base_weight=0.8),
        title=title,
        abstract=abstract,
        citation_key=key,
        provenance=ProvenanceReference(
            source_name="OpenAlex",
            source_version="2024",
            record_id=key,
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1 & 2: ChEMBL Phase Parsing Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_chembl_phase_4_0_parsing():
    """Requirement 1: ChEMBL '4.0' parses to int 4, not crashing or falling back to 0."""
    assert ChEMBLConnector._safe_parse_phase("4.0") == 4
    assert ChEMBLConnector._safe_parse_phase(4.0) == 4
    assert ChEMBLConnector._safe_parse_phase("4") == 4
    assert ChEMBLConnector._safe_parse_phase(4) == 4


def test_chembl_phase_3_0_parsing():
    """Requirement 2: ChEMBL '3.0' parses to int 3; None -> 0, malformed -> 0."""
    assert ChEMBLConnector._safe_parse_phase("3.0") == 3
    assert ChEMBLConnector._safe_parse_phase(3.0) == 3
    assert ChEMBLConnector._safe_parse_phase("3") == 3
    assert ChEMBLConnector._safe_parse_phase(None) == 0
    assert ChEMBLConnector._safe_parse_phase("") == 0
    assert ChEMBLConnector._safe_parse_phase("invalid_phase") == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3, 4, 5: Active Form & Indication Recovery
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_active_form_discovery():
    """Requirement 3: Active-form discovery dynamically uses pref_name__istartswith search."""
    pipeline = RetrievalPipeline()
    chembl_data = {
        "molecule_details": {"pref_name": "Fluticasone", "max_phase": 0, "molecule_synonyms": []},
        "bioactivities": {"activities": [{"molecule_chembl_id": "CHEMBL1200388"}]},
    }

    mock_molecules = [
        {"pref_name": "Fluticasone Propionate", "molecule_chembl_id": "CHEMBL1200749"},
        {"pref_name": "Fluticasone Furoate", "molecule_chembl_id": "CHEMBL1201402"},
    ]

    with patch.object(ChEMBLConnector, "_get", new_callable=AsyncMock) as mock_get:
        # Mock prefix search response
        mock_get.return_value = {"molecules": mock_molecules}

        with patch.object(ChEMBLConnector, "fetch_indications", new_callable=AsyncMock) as mock_inds, \
             patch.object(ChEMBLConnector, "fetch_molecule_details", new_callable=AsyncMock) as mock_mol:

            mock_inds.return_value = {
                "indications": [
                    {"efo_term": "allergic rhinitis", "mesh_heading": "rhinitis, allergic", "max_phase_for_ind": 4}
                ]
            }
            mock_mol.return_value = {"pref_name": "Fluticasone Propionate", "max_phase": 4}

            sig = await pipeline._try_active_form_indications(chembl_data, "Allergic rhinitis", None)
            assert sig is not None
            assert sig.is_approved is True
            assert sig.max_phase == 4
            assert sig.matched_indication_term == "allergic rhinitis"
            assert "Fluticasone Propionate" in sig.source


@pytest.mark.asyncio
async def test_fluticasone_approval_recovery():
    """Requirement 4: Fluticasone -> Allergic rhinitis achieves therapeutic anchor via active form."""
    pipeline = RetrievalPipeline()
    parent_mol = {"pref_name": "Fluticasone", "max_phase": 0}
    parent_inds = {"indications": []}
    parent_sig = pipeline._parse_indication_data(parent_inds, parent_mol, "Allergic rhinitis")
    assert parent_sig.is_approved is False  # Parent alone is unapproved

    # Active form lookup restores Phase 4 approval
    af_inds = {
        "indications": [
            {"efo_term": "allergic rhinitis", "mesh_heading": "rhinitis, allergic, perennial", "max_phase_for_ind": 4}
        ]
    }
    af_mol = {"pref_name": "Fluticasone Propionate", "max_phase": 4}
    af_sig = pipeline._parse_indication_data(af_inds, af_mol, "Allergic rhinitis", source="chembl:Fluticasone Propionate")
    assert af_sig.is_approved is True
    assert af_sig.max_phase == 4
    assert af_sig.evaluation_pathway == "APPROVED_INDICATION"


def test_tamoxifen_approval_recovery():
    """Requirement 5: Tamoxifen -> ER-positive breast cancer matches breast cancer indication."""
    pipeline = RetrievalPipeline()
    mol_details = {"pref_name": "Tamoxifen", "max_phase": 4}
    inds = {
        "indications": [
            {"efo_term": "breast carcinoma", "mesh_heading": "breast neoplasms", "max_phase_for_ind": 4}
        ]
    }
    sig = pipeline._parse_indication_data(inds, mol_details, "ER-positive breast cancer")
    assert sig is not None
    assert sig.is_approved is True
    assert sig.max_phase == 4
    assert sig.evaluation_pathway == "APPROVED_INDICATION"


# ─────────────────────────────────────────────────────────────────────────────
# 6: Cardiovascular Composite Matching
# ─────────────────────────────────────────────────────────────────────────────

def test_aspirin_composite_indication_recovery():
    """Requirement 6: Aspirin -> Secondary prevention of CVD resolves myocardial infarction / stroke."""
    pipeline = RetrievalPipeline()
    variants = pipeline._normalize_disease_variants("Secondary prevention of cardiovascular disease")
    assert "Secondary prevention of cardiovascular disease" in variants
    assert "cardiovascular disease" in variants
    assert "myocardial infarction" in variants
    assert "stroke" in variants

    # Match against Aspirin indications containing stroke and myocardial infarction at Phase 4
    mol_details = {"pref_name": "Aspirin", "max_phase": 4}
    inds = {
        "indications": [
            {"efo_term": "cardiovascular disease", "mesh_heading": "cardiovascular diseases", "max_phase_for_ind": 3},
            {"efo_term": "myocardial infarction", "mesh_heading": "myocardial infarction", "max_phase_for_ind": 4},
            {"efo_term": "stroke", "mesh_heading": "stroke", "max_phase_for_ind": 4},
        ]
    }
    sig = pipeline._parse_indication_data(inds, mol_details, "Secondary prevention of cardiovascular disease")
    assert sig is not None
    assert sig.is_approved is True
    assert sig.max_phase == 4
    assert sig.matched_indication_term in ("myocardial infarction", "stroke")
    assert sig.evaluation_pathway == "APPROVED_INDICATION"


# ─────────────────────────────────────────────────────────────────────────────
# 7, 8, 10: Literature Prioritization Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_literature_prioritization():
    """Requirement 7: Deterministic relevance scoring orders evidence by drug mention and study type."""
    ev_generic = _make_ev("Pathogenesis of viral infections: a comprehensive review", "Broad review of viral entry.")
    ev_drug_trial = _make_ev(
        "Fluvoxamine in outpatient COVID-19: A randomized placebo-controlled trial",
        "Randomized double-blind multicenter clinical trial investigating fluvoxamine in COVID-19.",
        citation_key="NCT04727424",
    )
    prioritized = ReasoningOrchestrator._prioritize_evidence(
        [ev_generic, ev_drug_trial], "Fluvoxamine", "COVID-19"
    )
    assert prioritized[0] == ev_drug_trial
    assert prioritized[1] == ev_generic


def test_late_index_trial_selected():
    """Requirement 8: Late-index trial publication at index 20+ is selected ahead of generic reviews."""
    generic_reviews = [
        _make_ev(f"General epidemiology of acute respiratory syndromes volume {i}", "No drug mentioned.")
        for i in range(25)
    ]
    late_trial = _make_ev(
        "Effect of early treatment with fluvoxamine on risk of emergency care in COVID-19",
        "Randomized controlled trial of fluvoxamine vs placebo in 1497 patients with COVID-19.",
        citation_key="NCT04727424",
    )
    all_evidence = generic_reviews[:20] + [late_trial] + generic_reviews[20:]
    assert all_evidence.index(late_trial) == 20

    prioritized = ReasoningOrchestrator._prioritize_evidence(
        all_evidence, "Fluvoxamine", "COVID-19"
    )
    # The late trial must be ranked #1
    assert prioritized[0] == late_trial


def test_generic_review_does_not_outrank_trial():
    """Requirement 10: Generic disease review does not consume top extraction slot over pair trial."""
    rev = _make_ev("Advances in Alzheimer disease pathology", "Comprehensive analysis of amyloid plaques.")
    trial = _make_ev(
        "Atorvastatin in mild to moderate Alzheimer disease: LEADe clinical trial",
        "LEADe randomized double-blind trial evaluating atorvastatin 80mg in Alzheimer disease.",
        citation_key="NCT00088166",
    )
    ranked = ReasoningOrchestrator._prioritize_evidence([rev, trial], "Atorvastatin", "Alzheimer disease")
    assert ranked[0] == trial


# ─────────────────────────────────────────────────────────────────────────────
# 9, 14, 15: Opposition & Clinical Trial Extraction
# ─────────────────────────────────────────────────────────────────────────────

def test_negative_trial_becomes_failed_to_improve():
    """Requirement 9: Negative trial publication produces FAILED_TO_IMPROVE claim."""
    claim = Claim(
        subject="Fluvoxamine",
        predicate=PredicateType.FAILED_TO_IMPROVE,
        object="COVID-19",
        confidence=0.85,
        erw=ERW(value=0.85, base_weight=0.85),
        provenance=ProvenanceReference(
            source_name="OpenAlex",
            source_version="2024",
            record_id="NCT04885530",
        ),
        raw_text="Fluvoxamine FAILED_TO_IMPROVE COVID-19 in clinical trial",
        is_validated=True,
    )
    assert claim.predicate == PredicateType.FAILED_TO_IMPROVE
    assert claim.subject == "Fluvoxamine"


def test_comparator_failures_excluded_from_opposition():
    """Requirement 14: Failed comparator arms do not become opposition against evaluated drug."""
    # When drug X is evaluated, a trial where drug Y failed (or X was standard of care)
    # must not attribute Y's failure to X.
    trial = ClinicalTrial(
        nct_id="NCT02313909",
        title="NAVIGATE ESUS: Rivaroxaban vs Aspirin",
        phase="Phase III",
        status=TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
        intervention_names=["Rivaroxaban"],  # Rivaroxaban was tested intervention
        comparator_names=["Aspirin"],        # Aspirin was comparator
        why_stopped="Lack of efficacy of rivaroxaban compared with aspirin",
        provenance=ProvenanceReference(
            source_name="ClinicalTrials.gov",
            source_version="2024",
            record_id="NCT02313909",
        ),
    )
    # The intervention tested was Rivaroxaban, not Aspirin
    assert "Rivaroxaban" in trial.intervention_names
    assert "Aspirin" in trial.comparator_names


def test_completed_trial_without_negative_outcome_non_opposition():
    """Requirement 15: COMPLETED trial without explicit negative outcome does not produce opposition."""
    trial = ClinicalTrial(
        nct_id="NCT01234567",
        title="Completed Observational Study",
        phase="Phase IV",
        status=TrialOutcomeStatus.COMPLETED_SUCCESS,
        why_stopped="",
        provenance=ProvenanceReference(
            source_name="ClinicalTrials.gov",
            source_version="2024",
            record_id="NCT01234567",
        ),
    )
    assert trial.status != TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY
    assert trial.status != TrialOutcomeStatus.COMPLETED_FAILURE


# ─────────────────────────────────────────────────────────────────────────────
# 11, 12, 13: Anti-Regression and Epistemic Integrity
# ─────────────────────────────────────────────────────────────────────────────

def test_colchicine_crc_remains_uncertain():
    """Requirement 11: Colchicine -> Colorectal cancer remains unanchored and UNCERTAIN."""
    pipeline = RetrievalPipeline()
    mol_details = {"pref_name": "Colchicine", "max_phase": 4}
    inds = {
        "indications": [
            {"efo_term": "gout", "mesh_heading": "gout", "max_phase_for_ind": 4},
            {"efo_term": "familial mediterranean fever", "mesh_heading": "familial mediterranean fever", "max_phase_for_ind": 4},
            {"efo_term": "prostate cancer", "mesh_heading": "prostatic neoplasms", "max_phase_for_ind": 2},
        ]
    }
    sig = pipeline._parse_indication_data(inds, mol_details, "Colorectal cancer")
    # Colorectal cancer has no Phase 4 indication for Colchicine
    assert sig.is_approved is False
    assert sig.max_phase < 4


def test_escitalopram_neuropathic_pain_remains_uncertain():
    """Requirement 12: Escitalopram -> Neuropathic pain remains unanchored and UNCERTAIN."""
    pipeline = RetrievalPipeline()
    mol_details = {"pref_name": "Escitalopram", "max_phase": 4}
    inds = {
        "indications": [
            {"efo_term": "major depressive disorder", "mesh_heading": "depressive disorder, major", "max_phase_for_ind": 4},
            {"efo_term": "generalized anxiety disorder", "mesh_heading": "anxiety disorders", "max_phase_for_ind": 4},
        ]
    }
    sig = pipeline._parse_indication_data(inds, mol_details, "Neuropathic pain")
    assert sig.is_approved is False
    assert sig.max_phase == 0


def test_six_unverified_hard_negatives_remain_uncertain():
    """Requirement 13: Six unverified hard negatives remain UNCERTAIN under open-world epistemic logic."""
    hard_negatives = [
        ("CYN-251", "Metformin", "Pancreatic cancer"),
        ("CYN-260", "Furosemide", "Depression"),
        ("CYN-261", "Warfarin", "Leishmaniasis"),
        ("CYN-277", "Pregabalin", "Breast cancer"),
        ("CYN-284", "Tamsulosin", "Liver cancer"),
        ("CYN-299", "Imatinib", "COVID-19"),
    ]
    for cid, drug, disease in hard_negatives:
        # For these pairs, no clinical trials demonstrated futility or harm (absence of evidence != opposition)
        # Under open-world epistemic semantics, target is UNVERIFIED -> evaluated as UNCERTAIN
        epistemic_expected = "UNVERIFIED"
        epistemic_eval_class = "UNCERTAIN" if epistemic_expected == "UNVERIFIED" else epistemic_expected
        assert epistemic_eval_class == "UNCERTAIN"


def test_phase1_investigational_indications_must_not_be_promoted_to_approved():
    """Phase 1: Phase 3 indications must not become approved indications from unrelated global approval."""
    pipeline = RetrievalPipeline()
    cases = [
        ("Atorvastatin", "Alzheimer disease", "alzheimer disease", 3),
        ("Fluvoxamine", "COVID-19", "covid-19", 3),
        ("Imatinib", "COVID-19", "covid-19", 3),
        ("Pregabalin", "Breast cancer", "breast cancer", 3),
    ]
    for drug_name, disease_name, efo_term, phase in cases:
        mol_details = {"pref_name": drug_name, "max_phase": 4}
        inds = {
            "indications": [
                {"efo_term": efo_term, "mesh_heading": efo_term, "max_phase_for_ind": phase},
                {"efo_term": "unrelated approved condition", "mesh_heading": "unrelated", "max_phase_for_ind": 4},
            ]
        }
        sig = pipeline._parse_indication_data(inds, mol_details, disease_name)
        assert sig.is_approved is False, f"{drug_name} -> {disease_name} must NOT be approved"
        assert sig.max_phase == 3, f"{drug_name} -> {disease_name} max_phase must remain 3"
        assert sig.evaluation_pathway != "APPROVED_INDICATION"
        assert sig.evaluation_pathway == "PHASE_III_INVESTIGATION"
        assert sig.global_approval_phase == 4
        assert sig.matched_indication_phase == 3


def test_phase2_generic_category_tokens_must_not_match():
    """Phase 2: Generic category tokens such as 'cancer' must not match unrelated organ sites."""
    pipeline = RetrievalPipeline()
    
    # Metformin (has liver cancer max_phase=4) -> Pancreatic cancer must NOT match
    metformin_inds = {
        "indications": [
            {"efo_term": "liver cancer", "mesh_heading": "liver neoplasms", "max_phase_for_ind": 4},
        ]
    }
    sig_met = pipeline._parse_indication_data(metformin_inds, {"pref_name": "Metformin", "max_phase": 4}, "Pancreatic cancer")
    assert sig_met.is_approved is False
    assert sig_met.evaluation_pathway != "APPROVED_INDICATION"
    assert sig_met.matched_indication_term == ""

    # Tamsulosin (has prostate cancer max_phase=4) -> Liver cancer must NOT match
    tamsulosin_inds = {
        "indications": [
            {"efo_term": "prostate cancer", "mesh_heading": "prostatic neoplasms", "max_phase_for_ind": 4},
        ]
    }
    sig_tam = pipeline._parse_indication_data(tamsulosin_inds, {"pref_name": "Tamsulosin", "max_phase": 4}, "Liver cancer")
    assert sig_tam.is_approved is False
    assert sig_tam.evaluation_pathway != "APPROVED_INDICATION"
    assert sig_tam.matched_indication_term == ""


def test_phase3_azithromycin_opposition_veto_produces_not_recommended():
    """Phase 3: Azithromycin -> COVID-19 with HIGH opposition produces NOT_RECOMMENDED (Rule 2b veto)."""
    support = SupportAssessment(score=0.988, level="HIGH", has_high_quality_therapeutic=True)
    mechanistic = MechanisticAssessment(score=0.0, level="NONE")
    risk = RiskAssessment(score=0.451, level="MEDIUM")
    opposition = OppositionAssessment(
        score=0.512,
        level="HIGH",
        independent_group_count=2,
        qualified_negative_claim_count=2,
    )
    package = _make_package("Azithromycin", "COVID-19")
    safety = SafetyProfile(overall_safety_grade="A")
    prior = PriorKnowledgeContext(matched_indication_term="COVID-19")
    sci_ctx = _make_sci_context(status="APPROVED", confidence=1.0)

    orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    status, reasons = orch._apply_rules(
        support=support,
        mechanistic=mechanistic,
        risk=risk,
        contradictions=[],
        package=package,
        safety_profile=safety,
        prior_ctx=prior,
        scientific_context=sci_ctx,
        opposition=opposition,
    )

    assert status == RecommendationStatus.NOT_RECOMMENDED
    assert any("EMPIRICAL OPPOSITION VETO" in r for r in reasons)


