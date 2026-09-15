"""Tests for Phase 5.5: Multi-target reasoning and synthesis."""
from __future__ import annotations

import uuid
import pytest

from backend.core.domain.candidate_mechanism import CandidateMechanism, MechanismHop
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.value_objects.therapeutic_direction_evidence import DrugMechDBEvidence
from backend.reasoning.mechanistic.target_synthesizer import (
    extract_target_identifier,
    rank_targets_and_synthesize_candidates,
)
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner


def _make_target_hop(target_id: str, predicate: str = "INHIBITOR") -> MechanismHop:
    return MechanismHop(
        from_node="Drug: TestDrug",
        to_node=f"Target: {target_id}",
        predicate=predicate,
        canonical_to_id=target_id,
        status="VALID",
        source_database="ChEMBL",
    )


def _make_candidate(
    target_id: str,
    confidence: float,
    support_level: str = "WEAK_SPECULATIVE",
    candidate_index: int = 1,
) -> CandidateMechanism:
    hop0 = _make_target_hop(target_id)
    return CandidateMechanism(
        candidate_index=candidate_index,
        name=f"Mechanism for {target_id}",
        support_level=support_level,
        confidence_score=confidence,
        summary_chain=["Drug: TestDrug", f"Target: {target_id}", "Disease: TestDisease"],
        hops=[hop0],
    )


def _make_pkg(targets: list[Target], drugmech: list[DrugMechDBEvidence] | None = None) -> RetrievalPackage:
    return RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=Drug(name="TestDrug", identifiers={"chembl": "CHEMBL1"}),
        disease=Disease(name="TestDisease", identifiers={"mesh": "D001"}),
        targets=targets,
        drugmechdb_evidence=drugmech or [],
    )


def _make_target_obj(uniprot: str, mechanism: str = "INHIBITOR", affinity: float = 10.0) -> Target:
    return Target(
        drug_chembl_id="CHEMBL1",
        protein_uniprot=uniprot,
        affinity_nm=affinity,
        affinity_type="IC50",
        mechanism=mechanism,
        erw=ERW.from_base(0.9),
        provenance=ProvenanceReference(source_name="ChEMBL", source_version="33", record_id="r1", url=""),
    )


class TestMultiTargetSynthesis:
    def test_strong_target_not_averaged_down_by_weak_target(self):
        """A strong primary target (0.70) is not averaged down by a weak secondary target (0.30)."""
        t_a = _make_target_obj("P001", mechanism="INHIBITOR", affinity=5.0)
        t_b = _make_target_obj("P002", mechanism="MODULATES", affinity=500.0)
        pkg = _make_pkg([t_a, t_b])

        cand_a = _make_candidate("P001", 0.70, support_level="STRONGLY_SUPPORTED", candidate_index=1)
        cand_b = _make_candidate("P002", 0.30, support_level="WEAK_SPECULATIVE", candidate_index=2)

        synthesized, summary = rank_targets_and_synthesize_candidates(pkg, [cand_b, cand_a])
        assert synthesized[0].name == cand_a.name
        assert summary["ranked_target"] == "P001"

        reasoner = MultiHopReasoner()
        score, level = reasoner.compute_mechanistic_score_from_candidates(synthesized)
        assert score == pytest.approx(0.70, abs=0.01)
        assert level == "HIGH"

    def test_secondary_target_row_count_cannot_dominate(self):
        """10 weak candidate rows for Target B cannot overwhelm 1 strong candidate for Target A."""
        t_a = _make_target_obj("P001", mechanism="INHIBITOR")
        t_b = _make_target_obj("P002", mechanism="MODULATES")
        pkg = _make_pkg([t_a, t_b])

        cand_a = _make_candidate("P001", 0.75, support_level="STRONGLY_SUPPORTED", candidate_index=1)
        cands_b = [
            _make_candidate("P002", 0.25, support_level="WEAK_SPECULATIVE", candidate_index=i + 2)
            for i in range(10)
        ]

        synthesized, summary = rank_targets_and_synthesize_candidates(pkg, cands_b + [cand_a])
        assert synthesized[0].name == cand_a.name
        assert summary["ranked_target"] == "P001"
        assert summary["target_count"] == 2

    def test_explicit_mechanism_outranks_unannotated(self):
        """Target with explicit actionable mechanism outranks target with unknown mechanism."""
        t_a = _make_target_obj("P001", mechanism="INHIBITOR")
        t_b = _make_target_obj("P002", mechanism="UNKNOWN")
        pkg = _make_pkg([t_a, t_b])

        cand_a = _make_candidate("P001", 0.40, support_level="WEAK_SPECULATIVE", candidate_index=1)
        cand_b = _make_candidate("P002", 0.40, support_level="WEAK_SPECULATIVE", candidate_index=2)

        synthesized, summary = rank_targets_and_synthesize_candidates(pkg, [cand_b, cand_a])
        assert summary["ranked_target"] == "P001"

    def test_drugmechdb_validated_target_prioritized(self):
        """Target with curated DrugMechDB validation receives rank priority."""
        t_a = _make_target_obj("P001", mechanism="INHIBITOR")
        t_b = _make_target_obj("P002", mechanism="INHIBITOR")
        dm = DrugMechDBEvidence(
            drug_name="TestDrug",
            disease_name="TestDisease",
            target_uniprot="P002",
            is_curated_path_available=True,
        )
        pkg = _make_pkg([t_a, t_b], drugmech=[dm])

        cand_a = _make_candidate("P001", 0.50, support_level="MODERATELY_SUPPORTED", candidate_index=1)
        cand_b = _make_candidate("P002", 0.50, support_level="MODERATELY_SUPPORTED", candidate_index=2)

        synthesized, summary = rank_targets_and_synthesize_candidates(pkg, [cand_a, cand_b])
        assert summary["ranked_target"] == "P002"

    def test_target_synthesis_summary_structure(self):
        """Summary contains ranked target metadata and full ranking list."""
        t_a = _make_target_obj("P001", mechanism="INHIBITOR")
        pkg = _make_pkg([t_a])
        cand_a = _make_candidate("P001", 0.65, support_level="MODERATELY_SUPPORTED")

        _, summary = rank_targets_and_synthesize_candidates(pkg, [cand_a])
        assert "ranked_target" in summary
        assert "target_count" in summary
        assert "target_ranking_summary" in summary
        assert len(summary["target_ranking_summary"]) == 1
        assert summary["target_ranking_summary"][0]["target_id"] == "P001"

    def test_empty_candidates_handled_gracefully(self):
        """Empty candidate list yields empty result and empty summary."""
        pkg = _make_pkg([])
        synthesized, summary = rank_targets_and_synthesize_candidates(pkg, [])
        assert synthesized == []
        assert summary["ranked_target"] == ""
        assert summary["target_count"] == 0

    def test_extract_target_identifier(self):
        """extract_target_identifier correctly extracts canonical target."""
        c = _make_candidate("MMP1", 0.40)
        assert extract_target_identifier(c) == "MMP1"

    def test_contradicted_secondary_target_does_not_affect_primary(self):
        """CONTRADICTED secondary target does not change primary target's MS."""
        t_a = _make_target_obj("P001", mechanism="INHIBITOR")
        t_b = _make_target_obj("P002", mechanism="MODULATES")
        pkg = _make_pkg([t_a, t_b])

        cand_a = _make_candidate("P001", 0.70, support_level="STRONGLY_SUPPORTED", candidate_index=1)
        cand_b = _make_candidate("P002", 0.60, support_level="CONTRADICTED", candidate_index=2)

        synthesized, summary = rank_targets_and_synthesize_candidates(pkg, [cand_a, cand_b])
        assert summary["ranked_target"] == "P001"
        reasoner = MultiHopReasoner()
        score, level = reasoner.compute_mechanistic_score_from_candidates(synthesized)
        assert score == pytest.approx(0.70, abs=0.01)
        assert level == "HIGH"

    def test_case_a_strong_primary_target_dominant(self):
        """Case A: Strong primary target remains dominant over weak secondary target."""
        t_pri = _make_target_obj("P100", mechanism="INHIBITOR", affinity=1.0)
        t_sec = _make_target_obj("P200", mechanism="MODULATOR", affinity=50.0)
        pkg = _make_pkg([t_pri, t_sec])

        cand_pri = _make_candidate("P100", 0.72, support_level="STRONGLY_SUPPORTED", candidate_index=1)
        cand_sec = _make_candidate("P200", 0.35, support_level="WEAK_SPECULATIVE", candidate_index=2)

        synthesized, summary = rank_targets_and_synthesize_candidates(pkg, [cand_sec, cand_pri])
        assert summary["ranked_target"] == "P100"
        assert synthesized[0].name == cand_pri.name

    def test_case_b_weak_primary_outranked_by_strong_secondary(self):
        """Case B: Weak target in input position 0 is outranked by a strong secondary target according to hierarchy."""
        # Input order has P_weak first with no mechanism annotation and weak support
        t_weak = _make_target_obj("P_WEAK", mechanism="UNKNOWN", affinity=500.0)
        # Target P_strong is second in input but has explicit INHIBITOR mechanism and strong support
        t_strong = _make_target_obj("P_STRONG", mechanism="INHIBITOR", affinity=10.0)
        pkg = _make_pkg([t_weak, t_strong])

        cand_weak = _make_candidate("P_WEAK", 0.25, support_level="WEAK_SPECULATIVE", candidate_index=1)
        cand_strong = _make_candidate("P_STRONG", 0.68, support_level="STRONGLY_SUPPORTED", candidate_index=2)

        # Pass candidates with weak first
        synthesized, summary = rank_targets_and_synthesize_candidates(pkg, [cand_weak, cand_strong])
        # P_STRONG must be ranked as preferred target, NOT blindly trusting input order
        assert summary["ranked_target"] == "P_STRONG"
        assert synthesized[0].name == cand_strong.name
        assert summary["target_ranking_summary"][0]["target_id"] == "P_STRONG"

    def test_case_c_comparable_evidence_deterministic_tie_breaking(self):
        """Case C: Multiple targets with identical evidence qualities achieve deterministic tie-breaking."""
        t_x = _make_target_obj("PX", mechanism="INHIBITOR", affinity=10.0)
        t_y = _make_target_obj("PY", mechanism="INHIBITOR", affinity=10.0)
        pkg = _make_pkg([t_x, t_y])

        cand_x = _make_candidate("PX", 0.50, support_level="MODERATELY_SUPPORTED", candidate_index=1)
        cand_y = _make_candidate("PY", 0.50, support_level="MODERATELY_SUPPORTED", candidate_index=2)

        # Run multiple times with different input permutations
        synth1, summ1 = rank_targets_and_synthesize_candidates(pkg, [cand_x, cand_y])
        synth2, summ2 = rank_targets_and_synthesize_candidates(pkg, [cand_y, cand_x])

        assert summ1["ranked_target"] == summ2["ranked_target"]
        assert synth1[0].name == synth2[0].name

