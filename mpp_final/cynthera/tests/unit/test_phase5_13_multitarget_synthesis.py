"""Unit tests for Phase 5.13 — Multi-Target Synthesis.

Verifies:
1. Single-target support
2. Single-target opposition
3. Support + opposition (mixed targets)
4. Support + unknown target
5. Multiple supporting targets
6. Multiple opposing targets
7. Strong primary target + weak off-target opposition (off-target does not overpower primary)
8. Two equally strong conflicting targets
9. Target with no directional evidence (marked unresolved/insufficient)
10. Target provenance preservation
11. No secondary target silently discarded
12. Existing single-target cases remain unchanged
"""
from __future__ import annotations

import uuid
import pytest

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.candidate_mechanism import CandidateMechanism
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.value_objects.therapeutic_direction_evidence import (
    TherapeuticDirectionEvidence,
    TherapeuticAction,
    EvidenceFamily,
)
from backend.core.enums.causal_grounding import CausalGrounding
from backend.reasoning.directional.multitarget_synthesizer import MultiTargetSynthesizer


def _make_target(uniprot: str, mech: str, affinity: float = 10.0) -> Target:
    return Target(
        drug_chembl_id="CHEMBL1",
        protein_uniprot=uniprot,
        affinity_nm=affinity,
        affinity_type="IC50",
        mechanism=mech,
        erw=ERW(value=0.9, rationale="Bioactivity"),
        provenance=ProvenanceReference(source_name="ChEMBL", source_version="34", record_id=f"act_{uniprot}"),
    )


def _make_dir_ev(
    target: str,
    req_action: str,
    grounding: CausalGrounding = CausalGrounding.DIRECT,
    ref: str = "pmid:11111",
) -> TherapeuticDirectionEvidence:
    return TherapeuticDirectionEvidence(
        target_canonical_id=target,
        disease_canonical_id="Disease1",
        source="OpenTargets",
        required_action=req_action,
        evidence_family=EvidenceFamily.GENETIC,
        causal_grounding=grounding,
        underlying_reference=ref,
        provenance={"reference": ref},
    )


def _make_pkg(targets: list[Target], dir_ev: list[TherapeuticDirectionEvidence]) -> RetrievalPackage:
    proteins = [
        Protein(uniprot_accession=t.protein_uniprot, gene_symbol=f"GENE_{t.protein_uniprot}", name=f"Protein {t.protein_uniprot}")
        for t in targets
    ]
    return RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=Drug(name="TestDrug", chembl_id="CHEMBL1", identifiers={"chembl": "CHEMBL1"}),
        disease=Disease(name="TestDisease", mesh_id="D1", identifiers={"mesh": "D1"}),
        targets=targets,
        proteins=proteins,
        therapeutic_direction_evidence=dir_ev,
    )


# ── 1. Single-target support ──────────────────────────────────────────────────
def test_1_single_target_support():
    targets = [_make_target("P55011", "INHIBITOR", 10.0)]
    ev = [_make_dir_ev("GENE_P55011", "INHIBITION", CausalGrounding.DIRECT)]
    pkg = _make_pkg(targets, ev)

    synth = MultiTargetSynthesizer().synthesize(pkg)
    assert synth.synthesis_state == "SUPPORTS"
    assert synth.supporting_targets == ["GENE_P55011"]
    assert len(synth.opposing_targets) == 0
    assert synth.conflict_detected is False


# ── 2. Single-target opposition ───────────────────────────────────────────────
def test_2_single_target_opposition():
    targets = [_make_target("P55017", "AGONIST", 10.0)]
    ev = [_make_dir_ev("GENE_P55017", "INHIBITION", CausalGrounding.DIRECT)]
    pkg = _make_pkg(targets, ev)

    synth = MultiTargetSynthesizer().synthesize(pkg)
    assert synth.synthesis_state == "OPPOSES"
    assert synth.opposing_targets == ["GENE_P55017"]
    assert len(synth.supporting_targets) == 0


# ── 3. Support + opposition ───────────────────────────────────────────────────
def test_3_support_and_opposition():
    targets = [
        _make_target("P55011", "INHIBITOR", 10.0),
        _make_target("P55017", "INHIBITOR", 10.0),
    ]
    ev = [
        _make_dir_ev("GENE_P55011", "INHIBITION", CausalGrounding.DIRECT, "pmid:1"),
        _make_dir_ev("GENE_P55017", "ACTIVATION", CausalGrounding.DIRECT, "pmid:2"),
    ]
    pkg = _make_pkg(targets, ev)

    synth = MultiTargetSynthesizer().synthesize(pkg)
    assert synth.conflict_detected is True
    assert "GENE_P55011" in synth.supporting_targets
    assert "GENE_P55017" in synth.opposing_targets


# ── 4. Support + unknown ──────────────────────────────────────────────────────
def test_4_support_and_unknown():
    targets = [
        _make_target("P55011", "INHIBITOR", 10.0),
        _make_target("P55017", "UNKNOWN", 100.0),
    ]
    ev = [_make_dir_ev("GENE_P55011", "INHIBITION", CausalGrounding.DIRECT)]
    pkg = _make_pkg(targets, ev)

    synth = MultiTargetSynthesizer().synthesize(pkg)
    assert synth.synthesis_state == "SUPPORTS"
    assert "GENE_P55011" in synth.supporting_targets
    assert "GENE_P55017" in synth.unresolved_targets


# ── 5. Multiple supporting targets ────────────────────────────────────────────
def test_5_multiple_supporting_targets():
    targets = [
        _make_target("P55011", "INHIBITOR", 10.0),
        _make_target("P55017", "INHIBITOR", 20.0),
    ]
    ev = [
        _make_dir_ev("GENE_P55011", "INHIBITION", CausalGrounding.DIRECT, "pmid:1"),
        _make_dir_ev("GENE_P55017", "INHIBITION", CausalGrounding.CURATED, "pmid:2"),
    ]
    pkg = _make_pkg(targets, ev)

    synth = MultiTargetSynthesizer().synthesize(pkg)
    assert synth.synthesis_state == "SUPPORTS"
    assert len(synth.supporting_targets) == 2
    assert synth.supporting_weight > 1.0


# ── 6. Multiple opposing targets ──────────────────────────────────────────────
def test_6_multiple_opposing_targets():
    targets = [
        _make_target("P55011", "AGONIST", 10.0),
        _make_target("P55017", "AGONIST", 15.0),
    ]
    ev = [
        _make_dir_ev("GENE_P55011", "INHIBITION", CausalGrounding.DIRECT, "pmid:1"),
        _make_dir_ev("GENE_P55017", "INHIBITION", CausalGrounding.CURATED, "pmid:2"),
    ]
    pkg = _make_pkg(targets, ev)

    synth = MultiTargetSynthesizer().synthesize(pkg)
    assert synth.synthesis_state == "OPPOSES"
    assert len(synth.opposing_targets) == 2
    assert synth.opposing_weight > 1.0


# ── 7. Strong primary + weak off-target opposition ────────────────────────────
def test_7_strong_primary_vs_weak_off_target():
    targets = [
        _make_target("P55011", "INHIBITOR", 1.0),
        _make_target("P55017", "INHIBITOR", 5000.0),  # Weak off-target affinity
    ]
    ev = [
        _make_dir_ev("GENE_P55011", "INHIBITION", CausalGrounding.DIRECT, "pmid:1"),
        _make_dir_ev("GENE_P55017", "ACTIVATION", CausalGrounding.INFERRED, "pmid:2"),
    ]
    pkg = _make_pkg(targets, ev)

    synth = MultiTargetSynthesizer().synthesize(pkg)
    assert synth.supporting_weight > synth.opposing_weight
    assert synth.synthesis_state == "SUPPORTS"


# ── 8. Two equally strong conflicting targets ─────────────────────────────────
def test_8_equally_strong_conflicting_targets():
    targets = [
        _make_target("P55011", "INHIBITOR", 5.0),
        _make_target("P55017", "INHIBITOR", 5.0),
    ]
    ev = [
        _make_dir_ev("GENE_P55011", "INHIBITION", CausalGrounding.DIRECT, "pmid:1"),
        _make_dir_ev("GENE_P55017", "ACTIVATION", CausalGrounding.DIRECT, "pmid:2"),
    ]
    pkg = _make_pkg(targets, ev)

    synth = MultiTargetSynthesizer().synthesize(pkg)
    assert synth.conflict_detected is True
    assert synth.strong_conflict is True
    assert synth.synthesis_state == "MIXED"


# ── 9. Target with no directional evidence ────────────────────────────────────
def test_9_target_with_no_directional_evidence():
    targets = [_make_target("P55011", "INHIBITOR", 10.0)]
    pkg = _make_pkg(targets, [])

    synth = MultiTargetSynthesizer().synthesize(pkg)
    assert synth.synthesis_state == "INSUFFICIENT"
    assert "GENE_P55011" in synth.unresolved_targets
    assert len(synth.target_summaries) == 1
    assert synth.target_summaries[0].alignment == "INSUFFICIENT"


# ── 10. Target provenance preservation ────────────────────────────────────────
def test_10_target_provenance_preservation():
    targets = [_make_target("P55011", "INHIBITOR", 10.0)]
    ev = [_make_dir_ev("GENE_P55011", "INHIBITION", CausalGrounding.DIRECT, "pmid:98765")]
    pkg = _make_pkg(targets, ev)

    synth = MultiTargetSynthesizer().synthesize(pkg)
    summary = synth.target_summaries[0]
    assert summary.target_id == "GENE_P55011"
    assert summary.target_symbol == "GENE_P55011"
    assert summary.target_relevance["affinity_nm"] == 10.0
    assert summary.target_relevance["direct_drug_target"] is True


# ── 11. No secondary target silently discarded ────────────────────────────────
def test_11_no_secondary_target_discarded():
    targets = [
        _make_target("P55011", "INHIBITOR", 10.0),
        _make_target("P55017", "INHIBITOR", 200.0),
        _make_target("P00918", "INHIBITOR", 800.0),
    ]
    pkg = _make_pkg(targets, [])

    synth = MultiTargetSynthesizer().synthesize(pkg)
    # All 3 targets must be present in target_summaries
    assert len(synth.target_summaries) == 3
    summaries_ids = {s.target_id for s in synth.target_summaries}
    assert summaries_ids == {"GENE_P55011", "GENE_P55017", "GENE_P00918"}


# ── 12. Existing single-target cases remain unchanged ─────────────────────────
def test_12_single_target_backward_compatibility():
    targets = [_make_target("P55011", "INHIBITOR", 10.0)]
    ev = [_make_dir_ev("GENE_P55011", "INHIBITION", CausalGrounding.DIRECT, "pmid:1")]
    pkg = _make_pkg(targets, ev)

    synth = MultiTargetSynthesizer().synthesize(pkg)
    assert synth.synthesis_state == "SUPPORTS"
    d = synth.to_dict()
    assert "target_summaries" in d
    assert "supporting_weight" in d
    assert d["synthesis_state"] == "SUPPORTS"
