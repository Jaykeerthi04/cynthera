"""Unit tests for Phase 5.12 — Reaction Evidence Aggregation & Deduplication.

Verifies:
1. Exact duplicate reaction records collapse to one canonical record
2. Same reaction from multiple API responses deduplicated
3. Same PMID across multiple records collapsed into one independent group
4. Same DOI across records collapsed into one independent group
5. Different PMIDs remain distinct independent groups
6. Missing citation provenance is marked UNKNOWN (no artificial independence)
7. Structural Reactome roles (CATALYST, INPUT, OUTPUT, PARTICIPANT) retain UNKNOWN direction
8. Duplicate evidence does not inflate independent group count
9. Raw records remain accessible via AggregatedReactionEvidence.raw_records
10. Candidate mechanism serialization remains fully backward compatible and preserves reaction metadata
"""
from __future__ import annotations

import uuid
import pytest

from backend.core.domain.candidate_mechanism import CandidateMechanism, MechanismHop
from backend.core.domain.disease import Disease
from backend.core.domain.drug import Drug
from backend.core.domain.reactome_reaction_evidence import ReactomeReactionEvidence
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.reasoning.mechanistic.reaction_aggregator import (
    aggregate_reaction_evidence,
    AggregatedReactionEvidence,
    extract_reaction_independence_group,
)
from backend.reasoning.mechanistic.mechanism_validation import MechanismValidator


def _make_rec(
    reaction_id: str = "R-HSA-100",
    target: str = "BRAF",
    role: str = "CATALYST",
    pathway: str = "R-HSA-1000",
    source_id: str = "src_1",
    provenance: dict | None = None,
) -> ReactomeReactionEvidence:
    return ReactomeReactionEvidence(
        target_canonical_id=target,
        target_original_id="P15056",
        reaction_id=reaction_id,
        reaction_name="Test Reaction",
        target_role=role,
        pathway_id=pathway,
        source_id=source_id,
        provenance=provenance or {},
    )


# ── 1. Exact duplicate reaction records ───────────────────────────────────────
def test_1_exact_duplicate_reaction_records():
    r1 = _make_rec("R-HSA-101", source_id="rec_a")
    r2 = _make_rec("R-HSA-101", source_id="rec_b")
    agg = aggregate_reaction_evidence([r1, r2])
    assert len(agg) == 1
    record = agg[0]
    assert record.evidence_count == 2
    assert record.duplicate_count == 1
    assert record.reaction_id == "R-HSA-101"


# ── 2. Same reaction from multiple API responses ──────────────────────────────
def test_2_same_reaction_multiple_api_responses():
    r1 = _make_rec("R-HSA-102", role="CATALYST", source_id="api_call_1")
    r2 = _make_rec("R-HSA-102", role="INPUT", source_id="api_call_2")
    agg = aggregate_reaction_evidence([r1, r2])
    assert len(agg) == 1
    record = agg[0]
    assert len(record.roles) == 2
    assert "CATALYST" in record.roles
    assert "INPUT" in record.roles
    assert record.has_structural_role is True


# ── 3. Same PMID across multiple records ──────────────────────────────────────
def test_3_same_pmid_across_multiple_records():
    r1 = _make_rec("R-HSA-103", source_id="s1", provenance={"pmid": "99988877"})
    r2 = _make_rec("R-HSA-103", source_id="s2", provenance={"pmid": "99988877"})
    r3 = _make_rec("R-HSA-103", source_id="s3", provenance={"pmid": "99988877"})
    agg = aggregate_reaction_evidence([r1, r2, r3])
    assert len(agg) == 1
    record = agg[0]
    assert record.independence_group == "PMID:99988877"
    assert record.independence_groups == ("PMID:99988877",)
    assert record.duplicate_count == 2


# ── 4. Same DOI across records ────────────────────────────────────────────────
def test_4_same_doi_across_records():
    doi = "10.1038/s41586-020-0001-x"
    r1 = _make_rec("R-HSA-104", source_id="s1", provenance={"doi": doi})
    r2 = _make_rec("R-HSA-104", source_id="s2", provenance={"doi": doi})
    agg = aggregate_reaction_evidence([r1, r2])
    assert len(agg) == 1
    assert agg[0].independence_group == f"DOI:{doi}"


# ── 5. Different PMIDs remain independent ─────────────────────────────────────
def test_5_different_pmids_remain_independent():
    r1 = _make_rec("R-HSA-105", source_id="s1", provenance={"pmid": "11111"})
    r2 = _make_rec("R-HSA-106", source_id="s2", provenance={"pmid": "22222"})
    agg = aggregate_reaction_evidence([r1, r2])
    assert len(agg) == 2
    groups = {a.independence_group for a in agg}
    assert groups == {"PMID:11111", "PMID:22222"}


# ── 6. Missing provenance becomes UNKNOWN independence ────────────────────────
def test_6_missing_provenance_becomes_unknown_independence():
    r1 = _make_rec("R-HSA-107", provenance={})
    indep = extract_reaction_independence_group(r1)
    assert indep == "UNKNOWN"

    agg = aggregate_reaction_evidence([r1])
    assert len(agg) == 1
    assert agg[0].independence_group == "UNKNOWN"


# ── 7. Structural Reactome role remains UNKNOWN direction ─────────────────────
def test_7_structural_reactome_role_remains_unknown_direction():
    for role in ["CATALYST", "INPUT", "OUTPUT", "PARTICIPANT", "COMPLEX_COMPONENT"]:
        rec = _make_rec("R-HSA-108", role=role)
        agg = aggregate_reaction_evidence([rec])
        assert agg[0].polarity == MolecularPolarity.UNKNOWN
        assert agg[0].causal_grounding == CausalGrounding.STRUCTURAL


# ── 8. Duplicate evidence does not inflate independent group count ────────────
def test_8_duplicate_evidence_does_not_inflate_groups():
    # 5 duplicate rows referencing the same PMID
    rows = [_make_rec("R-HSA-109", source_id=f"dup_{i}", provenance={"pmid": "33333333"}) for i in range(5)]
    agg = aggregate_reaction_evidence(rows)
    assert len(agg) == 1
    # Only 1 unique independent evidence group
    assert len(agg[0].independence_groups) == 1
    assert agg[0].evidence_count == 5
    assert agg[0].duplicate_count == 4


# ── 9. Raw records remain accessible ──────────────────────────────────────────
def test_9_raw_records_remain_accessible():
    r1 = _make_rec("R-HSA-110", source_id="orig_1")
    r2 = _make_rec("R-HSA-110", source_id="orig_2")
    agg = aggregate_reaction_evidence([r1, r2])
    record = agg[0]
    assert len(record.raw_records) == 2
    assert record.raw_record_ids == ("orig_1", "orig_2")
    assert record.raw_records[0].source_id == "orig_1"
    assert record.raw_records[1].source_id == "orig_2"


# ── 10. Candidate serialization remains backward compatible ───────────────────
def test_10_candidate_serialization_backward_compatible():
    cand = CandidateMechanism(
        name="Reaction Validated Route",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.62,
        summary_chain=["Drug", "Target", "Disease"],
        hops=[
            MechanismHop(
                from_node="Drug: D",
                to_node="Target: T",
                predicate="INHIBITOR",
                source_database="ChEMBL",
            )
        ],
    )
    r1 = _make_rec("R-HSA-111", source_id="s1", provenance={"pmid": "44444444"})
    r2 = _make_rec("R-HSA-111", source_id="s2", provenance={"pmid": "44444444"})
    pkg = RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=Drug(name="D", chembl_id="CHEMBL1", identifiers={"chembl": "CHEMBL1"}),
        disease=Disease(name="Dis", mesh_id="D1", identifiers={"mesh": "D1"}),
        reactome_reaction_evidence=[r1, r2],
    )
    validator = MechanismValidator()
    validated = validator.validate(pkg, [cand], claims=[])[0]

    assert validated.reaction_evidence_count == 2
    assert validated.unique_reaction_count == 1
    assert validated.reaction_independent_groups == 1
    assert validated.reaction_enriched is True

    # Check to_dict() serialization
    serialized = validated.to_dict()
    assert "reaction_evidence_count" in serialized
    assert serialized["reaction_evidence_count"] == 2
    assert "unique_reaction_count" in serialized
    assert serialized["unique_reaction_count"] == 1
    assert "reaction_independent_groups" in serialized
    assert serialized["reaction_independent_groups"] == 1
    assert "reaction_enriched" in serialized
    assert serialized["reaction_enriched"] is True
    # Invariant check: independent_evidence_groups on candidate mechanism was NOT corrupted
    assert "independent_evidence_groups" in serialized
