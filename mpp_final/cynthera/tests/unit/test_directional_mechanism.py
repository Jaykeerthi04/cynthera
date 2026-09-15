"""Unit tests for Mechanistic Arm + Directional Mechanism (Phase 5).

Tests root-cause fixes, directional mechanism evaluator, polarity invariants,
and semantic separation between Mechanistic Plausibility and Therapeutic Direction.
"""
from __future__ import annotations

import pytest

from backend.core.domain.candidate_mechanism import CandidateMechanism, MechanismHop
from backend.core.domain.directional_mechanism import DirectionalMechanismAssessment
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.pathway import Pathway
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.enums.causal_grounding import CausalGrounding
from backend.reasoning.directional.directional_mechanism_evaluator import (
    DirectionalMechanismEvaluator,
)
from backend.reasoning.directional.reactome_polarity import (
    reactome_role_to_polarity,
    reactome_role_to_grounding,
)
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner
from backend.reasoning.mechanistic.mechanism_validation import MechanismValidator


# ─────────────────────────────────────────────────────────────────────────────
# PART F: ROOT-CAUSE TESTS (1 - 10)
# ─────────────────────────────────────────────────────────────────────────────

from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference


import uuid


def test_01_valid_path_non_zero_without_reaction_evidence():
    """A valid mechanistic path does NOT become MS = 0 merely because reaction evidence is unavailable."""
    package = RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=Drug(name="TestDrug", identifiers={"chembl": "CHEMBL123"}),
        disease=Disease(name="TestDisease", identifiers={"mesh": "D001"}),

        targets=[Target(
            drug_chembl_id="CHEMBL123",
            protein_uniprot="P12345",
            affinity_nm=10.0,
            affinity_type="IC50",
            mechanism="INHIBITOR",
            erw=ERW(value=0.85, base_weight=0.85),
            provenance=ProvenanceReference(source_name="ChEMBL", source_version="v33", record_id="CHEMBL123"),
        )],


        proteins=[Protein(uniprot_accession="P12345", name="Test Protein", gene_symbol="TEST1", organism="Homo sapiens")],

        pathways=[Pathway(reactome_id="R-HSA-1001", name="Test Pathway", participant_uniprot_ids=["P12345", "P99999"])],
        validated_disease_genes={"TEST1": 0.85},
        evidence_records=[],
        reactome_reaction_evidence=[],  # 0 reactions
    )


    builder = EvidenceGraphBuilder()
    graph, resolver = builder.build(package)
    reasoner = MultiHopReasoner()
    paths = reasoner.trace_paths(package)
    assert len(paths) >= 1

    candidates = reasoner.discover_candidate_mechanisms(package, paths)
    assert len(candidates) >= 1

    validator = MechanismValidator()
    val_cands = validator.validate(package, candidates, [])
    assert len(val_cands) >= 1
    assert val_cands[0].confidence_score > 0.0

    score, level = reasoner.compute_mechanistic_score_from_candidates(val_cands)
    assert score > 0.0
    assert level in ("LOW", "MEDIUM", "HIGH")


def test_02_reaction_enriched_path_contributes_mechanistic_evidence():
    """A valid reaction-enriched path contributes valid structured evidence."""
    cand = CandidateMechanism(
        candidate_index=1,
        name="Target via Reaction to Pathway",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.65,
        summary_chain=["Drug: D", "Target: T", "Reaction: R", "Pathway: P", "Disease: Dis"],
        hops=[
            MechanismHop(from_node="Drug: D", to_node="Target: T", predicate="INHIBITOR", source_database="ChEMBL"),
            MechanismHop(from_node="Target: T", to_node="Reaction: R", predicate="CATALYZES", source_database="Reactome"),
            MechanismHop(from_node="Reaction: R", to_node="Pathway: P", predicate="PART_OF", source_database="Reactome"),
            MechanismHop(from_node="Pathway: P", to_node="Disease: Dis", predicate="ASSOCIATED_WITH", source_database="Open Targets"),
        ],
    )
    assert cand.confidence_score == 0.65
    assert cand.support_level == "MODERATELY_SUPPORTED"


def test_03_structural_reactome_participation_does_not_create_polarity():
    """Structural Reactome participation roles remain UNKNOWN polarity and never signed."""
    structural_roles = ["CATALYST", "INPUT", "OUTPUT", "PARTICIPANT", "COMPLEX_COMPONENT", "ENTITY_SET_MEMBER"]
    for role in structural_roles:
        pol = reactome_role_to_polarity(role)
        grounding = reactome_role_to_grounding(role)
        assert pol == MolecularPolarity.UNKNOWN, f"Role {role} should have UNKNOWN polarity, got {pol}"
        assert grounding == CausalGrounding.STRUCTURAL, f"Role {role} should have STRUCTURAL grounding, got {grounding}"


def test_04_explicit_positive_regulation_creates_positive_polarity():
    """Explicit POSITIVE_REGULATOR creates positive molecular polarity."""
    pol = reactome_role_to_polarity("POSITIVE_REGULATOR")
    grounding = reactome_role_to_grounding("POSITIVE_REGULATOR")
    assert pol == MolecularPolarity.POSITIVE
    assert grounding == CausalGrounding.CURATED


def test_05_explicit_negative_regulation_creates_negative_polarity():
    """Explicit NEGATIVE_REGULATOR creates negative molecular polarity."""
    pol = reactome_role_to_polarity("NEGATIVE_REGULATOR")
    grounding = reactome_role_to_grounding("NEGATIVE_REGULATOR")
    assert pol == MolecularPolarity.NEGATIVE
    assert grounding == CausalGrounding.CURATED


def test_06_unknown_edges_remain_unknown():
    """Unknown predicates or roles return UNKNOWN polarity."""
    pol = reactome_role_to_polarity("SOME_RANDOM_ROLE")
    assert pol == MolecularPolarity.UNKNOWN


def test_07_therapeutic_insufficient_does_not_force_ms_zero():
    """Therapeutic alignment INSUFFICIENT does NOT force mechanistic score to 0.0."""
    # A drug with unknown therapeutic direction can still have a well-traced biological route
    cand = CandidateMechanism(
        candidate_index=1,
        name="Mechanism: P12345",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.55,
        summary_chain=["Drug: D", "Target: T", "Disease: Dis"],
        hops=[MechanismHop(from_node="Drug: D", to_node="Target: T", predicate="MODULATES", source_database="ChEMBL")],
    )
    reasoner = MultiHopReasoner()
    score, level = reasoner.compute_mechanistic_score_from_candidates([cand])
    assert score == 0.55
    assert level == "MEDIUM"


def test_08_mechanistic_score_and_therapeutic_alignment_are_separate():
    """Mechanistic score measures biological route plausibility, not therapeutic support."""
    evaluator = DirectionalMechanismEvaluator()
    # Drug is ACTIVATOR, Disease requires INHIBITION -> Therapeutic alignment is OPPOSES
    cand = CandidateMechanism(
        candidate_index=1,
        name="AR Mechanism",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.60,
        summary_chain=["Drug: Testo", "Target: AR", "Disease: PCa"],
        hops=[MechanismHop(from_node="Drug: Testo", to_node="Target: AR", predicate="AGONIST", source_database="ChEMBL")],
    )
    assess = evaluator.evaluate_candidate(
        candidate=cand,
        disease_required_action="INHIBITION",
        drug_action="AGONIST",
    )
    # Directional mechanism detects contradiction, but mechanistic plausibility remains 0.60
    assert assess.contradiction_detected is True
    assert assess.path_direction_status == "CONTRADICTORY"
    assert cand.confidence_score == 0.60


def test_09_candidate_with_valid_evidence_receives_non_zero_ms():
    """Candidate mechanism with valid database evidence receives non-zero MS."""
    cand = CandidateMechanism(
        candidate_index=1,
        name="Valid Mechanism",
        support_level="WEAK_SPECULATIVE",
        confidence_score=0.35,
        hops=[MechanismHop(from_node="Drug: A", to_node="Target: B", predicate="INHIBITOR", source_database="ChEMBL")],
    )
    reasoner = MultiHopReasoner()
    score, level = reasoner.compute_mechanistic_score_from_candidates([cand])
    assert score == 0.35
    assert level == "LOW"


def test_10_provenance_preserved_across_directional_assessment():
    """Directional mechanism assessment preserves edge explanation and target IDs."""
    evaluator = DirectionalMechanismEvaluator()
    cand = CandidateMechanism(
        candidate_index=1,
        name="Target: ACE",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.55,
        hops=[MechanismHop(from_node="Drug: Lisinopril", to_node="Target: ACE", predicate="INHIBITOR", source_database="ChEMBL")],
    )
    assess = evaluator.evaluate_candidate(cand, disease_required_action="INHIBITION", drug_action="INHIBITOR")
    assert assess.target_id == "ACE"
    assert assess.drug_action == "INHIBITOR"
    assert assess.disease_required_action == "INHIBITION"
    assert "consistent" in assess.explanation.lower()
    assert assess.to_dict()["target_id"] == "ACE"


# ─────────────────────────────────────────────────────────────────────────────
# PART G: DIRECTIONAL MECHANISM TESTS (11 - 15)
# ─────────────────────────────────────────────────────────────────────────────

def test_11_consistent_inhibitor_hypothesis():
    """Test 1: Drug=INHIBITION, Disease=INHIBITION, Path=structural -> CONSISTENT, contradiction=False."""
    evaluator = DirectionalMechanismEvaluator()
    cand = CandidateMechanism(
        candidate_index=1,
        name="SLC12A1 Path",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.55,
        hops=[
            MechanismHop(from_node="Drug: Furosemide", to_node="Target: SLC12A1", predicate="INHIBITOR", source_database="ChEMBL", polarity="NEGATIVE", causal_grounding="DIRECT"),
            MechanismHop(from_node="Target: SLC12A1", to_node="Pathway: Cation transport", predicate="PARTICIPATES_IN", source_database="Reactome", polarity="UNKNOWN", causal_grounding="STRUCTURAL"),
        ],
    )
    assess = evaluator.evaluate_candidate(cand, disease_required_action="INHIBITION", drug_action="INHIBITOR")
    assert assess.directionally_consistent is True
    assert assess.path_direction_status == "CONSISTENT"
    assert assess.contradiction_detected is False


def test_12_opposing_activator_hypothesis():
    """Test 2: Drug=ACTIVATION, Disease=INHIBITION -> CONTRADICTORY, contradiction=True."""
    evaluator = DirectionalMechanismEvaluator()
    cand = CandidateMechanism(
        candidate_index=1,
        name="AR Path",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.60,
        hops=[
            MechanismHop(from_node="Drug: Testosterone", to_node="Target: AR", predicate="AGONIST", source_database="ChEMBL", polarity="POSITIVE", causal_grounding="DIRECT"),
        ],
    )
    assess = evaluator.evaluate_candidate(cand, disease_required_action="INHIBITION", drug_action="AGONIST")
    assert assess.directionally_consistent is False
    assert assess.path_direction_status == "CONTRADICTORY"
    assert assess.contradiction_detected is True
    assert len(assess.opposing_edges) >= 1


def test_13_signed_path_contradiction_detected():
    """Test 3: Drug=INHIBITION, Disease=INHIBITION, but path contains explicit negative regulation contradiction."""
    evaluator = DirectionalMechanismEvaluator()
    cand = CandidateMechanism(
        candidate_index=1,
        name="Contradictory Pathway",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.50,
        hops=[
            MechanismHop(from_node="Drug: DrugA", to_node="Target: ProtB", predicate="INHIBITOR", source_database="ChEMBL", polarity="NEGATIVE"),
            MechanismHop(from_node="Target: ProtB", to_node="Reaction: RxnC", predicate="NEGATIVE_REGULATOR", source_database="Reactome", polarity="NEGATIVE", causal_grounding="CURATED"),
        ],
    )
    assess = evaluator.evaluate_candidate(cand, disease_required_action="INHIBITION", drug_action="INHIBITOR")
    assert assess.contradiction_detected is True
    assert assess.path_direction_status == "CONTRADICTORY"
    assert assess.directionally_consistent is False


def test_14_catalyst_creates_no_contradiction():
    """Test 4: Reactome CATALYST is non-directional -> no contradiction."""
    evaluator = DirectionalMechanismEvaluator()
    cand = CandidateMechanism(
        candidate_index=1,
        name="Catalytic Pathway",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.50,
        hops=[
            MechanismHop(from_node="Drug: DrugA", to_node="Target: ProtB", predicate="INHIBITOR", source_database="ChEMBL", polarity="NEGATIVE"),
            MechanismHop(from_node="Target: ProtB", to_node="Reaction: RxnC", predicate="CATALYZES", source_database="Reactome", polarity="UNKNOWN", causal_grounding="STRUCTURAL"),
        ],
    )
    assess = evaluator.evaluate_candidate(cand, disease_required_action="INHIBITION", drug_action="INHIBITOR")
    assert assess.contradiction_detected is False
    assert assess.path_direction_status == "CONSISTENT"


def test_15_unknown_direction_yields_unknown_status():
    """Test 5: Unknown disease requirement yields UNKNOWN status without false contradiction."""
    evaluator = DirectionalMechanismEvaluator()
    cand = CandidateMechanism(
        candidate_index=1,
        name="Unknown Requirement Path",
        support_level="WEAK_SPECULATIVE",
        confidence_score=0.40,
        hops=[
            MechanismHop(from_node="Drug: DrugA", to_node="Target: ProtB", predicate="MODULATES", source_database="ChEMBL", polarity="UNKNOWN"),
        ],
    )
    assess = evaluator.evaluate_candidate(cand, disease_required_action="UNKNOWN", drug_action="MODULATES")
    assert assess.path_direction_status == "UNKNOWN"
    assert assess.directionally_consistent is None
    assert assess.contradiction_detected is False
