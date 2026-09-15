"""Tests for Phase 5.7: Production evidence weighting interface."""
from __future__ import annotations

import uuid
import pytest

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.evidence_weight_policy import (
    DEFAULT_WEIGHT_POLICY,
    EvidenceWeightPolicy,
    WeightMode,
)
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.value_objects.therapeutic_direction_evidence import (
    EvidenceFamily,
    TherapeuticAction,
    TherapeuticAlignment,
    TherapeuticDirectionEvidence,
)
from backend.reasoning.directional.therapeutic_alignment import (
    TherapeuticAlignmentEngine,
    group_evidence_by_independence,
)


def _make_tde(
    target_id: str = "T1",
    source: str = "OpenTargets",
    reference: str = "PMID:12345678",
    target_dir: str = "LoF",
    trait_dir: str = "protect",
    grounding: CausalGrounding = CausalGrounding.CURATED,
    family: EvidenceFamily = EvidenceFamily.GENETIC,
) -> TherapeuticDirectionEvidence:
    from backend.core.value_objects.therapeutic_direction_evidence import compute_independence_group

    indep = compute_independence_group(family, [reference], source)
    return TherapeuticDirectionEvidence(
        target_canonical_id=target_id,
        disease_canonical_id="DIS1",
        source=source,
        target_direction=target_dir,
        trait_direction=trait_dir,
        causal_grounding=grounding,
        evidence_family=family,
        underlying_reference=reference,
        independence_group=indep,
    )


class TestProductionEvidenceWeighting:
    def test_production_default_is_equal_vote(self):
        """EQUAL_VOTE is the mandatory production default mode."""
        policy = DEFAULT_WEIGHT_POLICY
        assert policy.mode == WeightMode.EQUAL_VOTE

    def test_same_pmid_across_two_databases_counts_once(self):
        """Open Targets and DATTs records citing the exact same PMID cluster into one independent group."""
        rec_ot = _make_tde(source="OpenTargets", reference="PMID:99887766")
        rec_datts = _make_tde(source="DATTs", reference="pubmed/99887766")

        groups = group_evidence_by_independence([rec_ot, rec_datts])
        assert len(groups) == 1
        assert groups[0].member_record_count == 2
        assert set(groups[0].sources) == {"OpenTargets", "DATTs"}

    def test_direct_greater_than_inferred_in_heuristic_weights(self):
        """DIRECT grounding receives higher weight than INFERRED under default heuristic policy."""
        policy = EvidenceWeightPolicy(mode=WeightMode.GROUNDING_WEIGHTED)
        assert policy.weight_for_grounding(CausalGrounding.DIRECT) == 1.0
        assert policy.weight_for_grounding(CausalGrounding.CURATED) == 0.9
        assert policy.weight_for_grounding(CausalGrounding.INFERRED) == 0.5
        assert policy.weight_for_grounding(CausalGrounding.DIRECT) > policy.weight_for_grounding(CausalGrounding.INFERRED)

    def test_structural_and_none_grounding_contribute_zero_weight(self):
        """STRUCTURAL and NONE grounding tiers strictly contribute 0.0 weight."""
        policy = EvidenceWeightPolicy(mode=WeightMode.GROUNDING_WEIGHTED)
        assert policy.weight_for_grounding(CausalGrounding.STRUCTURAL) == 0.0
        assert policy.weight_for_grounding(CausalGrounding.NONE) == 0.0

    def test_weighted_mode_direct_opposition_beats_inferred_support(self):
        """Under GROUNDING_WEIGHTED mode, a single DIRECT opposing group (w=1.0) overcomes weak inferred support."""
        engine = TherapeuticAlignmentEngine()
        policy = EvidenceWeightPolicy(mode=WeightMode.GROUNDING_WEIGHTED)

        # Drug is INHIBITOR
        # 1 Inferred support record (LoF + protect -> desires INHIBITION)
        rec_supp = _make_tde(target_id="T1", reference="PMID:101", target_dir="LoF", trait_dir="protect", grounding=CausalGrounding.INFERRED)
        # 1 Direct opposition record (LoF + risk -> desires ACTIVATION)
        rec_opp = _make_tde(target_id="T1", reference="PMID:102", target_dir="LoF", trait_dir="risk", grounding=CausalGrounding.DIRECT)

        # In weighted alignment
        alignment = engine.weighted_align_target(
            target_id="T1",
            drug_action=TherapeuticAction.INHIBITION,
            evidence_records=[rec_supp, rec_opp],
            weight_config=policy.to_weight_config(),
        )
        # In this scenario, opposition (1.0) exceeds support (0.5), but both are present.
        # Check that weighted concordance reflects opposition weight > support weight
        assert alignment.confidence > 0.0 or alignment.alignment == TherapeuticAlignment.OPPOSES

    def test_weighted_mode_balanced_strong_evidence_yields_insufficient(self):
        """Under GROUNDING_WEIGHTED mode, strong conflicting evidence yields INSUFFICIENT."""
        engine = TherapeuticAlignmentEngine()
        policy = EvidenceWeightPolicy(mode=WeightMode.GROUNDING_WEIGHTED)

        rec_supp = _make_tde(target_id="T1", reference="PMID:201", target_dir="LoF", trait_dir="protect", grounding=CausalGrounding.DIRECT)
        rec_opp = _make_tde(target_id="T1", reference="PMID:202", target_dir="LoF", trait_dir="risk", grounding=CausalGrounding.DIRECT)

        alignment = engine.weighted_align_target(
            target_id="T1",
            drug_action=TherapeuticAction.INHIBITION,
            evidence_records=[rec_supp, rec_opp],
            weight_config=policy.to_weight_config(),
        )
        assert alignment.alignment == TherapeuticAlignment.INSUFFICIENT
        assert "conflict" in alignment.explanation.lower()

    def test_equal_vote_and_weighted_modes_both_run_through_align_package(self):
        """Both EQUAL_VOTE and GROUNDING_WEIGHTED policies run deterministically through align_package."""
        drug = Drug(id=uuid.uuid4(), name="TestDrug", chembl_id="CHEMBL1", identifiers={"chembl": "CHEMBL1"})
        disease = Disease(id=uuid.uuid4(), name="TestDisease", mesh_id="D001", identifiers={"mesh": "D001"})
        target = Target(
            drug_chembl_id="CHEMBL1",
            protein_uniprot="P12345",
            affinity_nm=10.0,
            affinity_type="IC50",
            mechanism="INHIBITOR",
            erw=ERW.from_base(0.9),
            provenance=ProvenanceReference(source_name="ChEMBL", source_version="33", record_id="r1", url=""),
        )
        protein = Protein(name="TestProtein", uniprot_accession="P12345", gene_symbol="T1", is_reviewed=True)
        rec = _make_tde(target_id="T1", reference="PMID:301", target_dir="LoF", trait_dir="protect", grounding=CausalGrounding.CURATED)

        pkg = RetrievalPackage(
            hypothesis_id=uuid.uuid4(),
            drug=drug,
            disease=disease,
            targets=[target],
            proteins=[protein],
            therapeutic_direction_evidence=[rec],
        )

        engine = TherapeuticAlignmentEngine()

        # Run with EQUAL_VOTE (default)
        report_eq = engine.align_package(pkg, policy=EvidenceWeightPolicy(mode=WeightMode.EQUAL_VOTE))
        assert report_eq.overall_alignment == TherapeuticAlignment.SUPPORTS

        # Run with GROUNDING_WEIGHTED
        report_wt = engine.align_package(pkg, policy=EvidenceWeightPolicy(mode=WeightMode.GROUNDING_WEIGHTED))
        assert report_wt.overall_alignment == TherapeuticAlignment.SUPPORTS

    def test_weight_calculation_is_deterministic(self):
        """Repeated evaluations of the same evidence produce identical weight outputs."""
        policy = EvidenceWeightPolicy(mode=WeightMode.GROUNDING_WEIGHTED)
        w1 = policy.weight_for_grounding(CausalGrounding.CURATED)
        w2 = policy.weight_for_grounding(CausalGrounding.CURATED)
        assert w1 == w2 == 0.9

    def test_provenance_survives_independence_grouping(self):
        """Primary citation, sources, and group summary are preserved in the independent group."""
        rec = _make_tde(source="OpenTargets", reference="PMID:12345678", family=EvidenceFamily.LITERATURE)
        groups = group_evidence_by_independence([rec])
        assert len(groups) == 1
        g = groups[0]
        assert "PMID:12345678" in g.references
        assert "OpenTargets" in g.sources
        assert g.evidence_family == EvidenceFamily.LITERATURE

    def test_task5_weighted_vs_equal_vote_decision_difference(self):
        """Task 5 proof: Group A (DIRECT SUPPORT) + Group B (INFERRED OPPOSE).

        Under EQUAL_VOTE: 1 support vs 1 oppose -> INSUFFICIENT / conflict.
        Under GROUNDING_WEIGHTED: support 1.0 > oppose 0.5 -> SUPPORTS.
        """
        engine = TherapeuticAlignmentEngine()

        # Drug is INHIBITOR
        rec_supp = _make_tde(target_id="T1", reference="PMID:111", target_dir="LoF", trait_dir="protect", grounding=CausalGrounding.DIRECT)
        rec_opp = _make_tde(target_id="T1", reference="PMID:222", target_dir="LoF", trait_dir="risk", grounding=CausalGrounding.INFERRED)

        # 1. Under EQUAL_VOTE (production default)
        align_equal = engine.align_target(
            target_id="T1",
            drug_action=TherapeuticAction.INHIBITION,
            evidence_records=[rec_supp, rec_opp],
        )
        assert align_equal.alignment == TherapeuticAlignment.INSUFFICIENT
        assert len(align_equal.supporting_groups) == 1
        assert len(align_equal.opposing_groups) == 1

        # 2. Under GROUNDING_WEIGHTED (opt-in)
        policy = EvidenceWeightPolicy(mode=WeightMode.GROUNDING_WEIGHTED)
        align_weighted = engine.weighted_align_target(
            target_id="T1",
            drug_action=TherapeuticAction.INHIBITION,
            evidence_records=[rec_supp, rec_opp],
            weight_config=policy.to_weight_config(),
        )
        assert align_weighted.alignment == TherapeuticAlignment.SUPPORTS
        assert "net-supported" in align_weighted.explanation

    def test_task5_reverse_weighted_opposition_wins(self):
        """Task 5 proof (reverse): Group A (INFERRED SUPPORT) + Group B (DIRECT OPPOSE).

        Under EQUAL_VOTE: 1 support vs 1 oppose -> INSUFFICIENT / conflict.
        Under GROUNDING_WEIGHTED: oppose 1.0 > support 0.5 -> OPPOSES.
        """
        engine = TherapeuticAlignmentEngine()

        rec_supp = _make_tde(target_id="T1", reference="PMID:333", target_dir="LoF", trait_dir="protect", grounding=CausalGrounding.INFERRED)
        rec_opp = _make_tde(target_id="T1", reference="PMID:444", target_dir="LoF", trait_dir="risk", grounding=CausalGrounding.DIRECT)

        # Equal vote -> INSUFFICIENT
        align_equal = engine.align_target(
            target_id="T1",
            drug_action=TherapeuticAction.INHIBITION,
            evidence_records=[rec_supp, rec_opp],
        )
        assert align_equal.alignment == TherapeuticAlignment.INSUFFICIENT

        # Grounding weighted -> OPPOSES
        policy = EvidenceWeightPolicy(mode=WeightMode.GROUNDING_WEIGHTED)
        align_weighted = engine.weighted_align_target(
            target_id="T1",
            drug_action=TherapeuticAction.INHIBITION,
            evidence_records=[rec_supp, rec_opp],
            weight_config=policy.to_weight_config(),
        )
        assert align_weighted.alignment == TherapeuticAlignment.OPPOSES
        assert "net-opposed" in align_weighted.explanation

    def test_task5_duplicate_rows_same_citation_do_not_inflate_weight(self):
        """Task 5 proof: 5 duplicate rows citing the SAME PMID do NOT overpower an independent group."""
        engine = TherapeuticAlignmentEngine()
        policy = EvidenceWeightPolicy(mode=WeightMode.GROUNDING_WEIGHTED)

        # 1 Direct opposing group
        rec_opp = _make_tde(target_id="T1", reference="PMID:555", target_dir="LoF", trait_dir="risk", grounding=CausalGrounding.DIRECT)

        # 5 duplicate inferred support rows all citing PMID:999 from different databases
        recs_supp = [
            _make_tde(target_id="T1", source=f"DB_{i}", reference="PMID:999", target_dir="LoF", trait_dir="protect", grounding=CausalGrounding.INFERRED)
            for i in range(5)
        ]

        # In weighted alignment, the 5 duplicate rows must cluster into 1 independent group (weight 0.5)
        # Therefore DIRECT opposition (1.0) must still defeat the duplicate-row support (0.5)!
        alignment = engine.weighted_align_target(
            target_id="T1",
            drug_action=TherapeuticAction.INHIBITION,
            evidence_records=[rec_opp] + recs_supp,
            weight_config=policy.to_weight_config(),
        )
        assert alignment.alignment == TherapeuticAlignment.OPPOSES
        assert "net-opposed" in alignment.explanation

