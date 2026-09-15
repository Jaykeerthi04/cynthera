"""Unit tests for Phase 5.15 — Production Evidence Weighting.

Verifies:
1. Structural evidence receives strictly 0.0 directional weight
2. Curated evidence receives appropriate weight
3. Causal evidence outweights curated evidence
4. Literature-grounded evidence receives high weight
5. Independently validated evidence receives full weight
6. Multiple duplicate records receive diminishing returns (not linear scaling)
7. Direct target mechanism outweights indirect target association
8. Primary target outweights secondary off-target
9. Missing provenance incurs conservative discount without becoming opposition
10. UNKNOWN evidence does not create opposing weight
11. Decisive support outranking opposition yields SUPPORTS verdict
12. Decisive opposition outranking support yields OPPOSES verdict
13. Balanced strong evidence yields CONFLICT verdict
14. Sub-threshold directional weight yields INSUFFICIENT verdict
15. ProductionWeightConfig parameters are labeled INITIAL_HEURISTIC and fully configurable
16. Every weight decision is traceable to target, family, quality, provenance, and direction
"""
from __future__ import annotations

import pytest

from backend.core.domain.contradiction_state import ContradictionLevel
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.therapeutic_direction_evidence import (
    DirectionalEvidenceGroup,
    EvidenceFamily,
    TherapeuticAction,
)
from backend.reasoning.evidence_weighting import (
    DEFAULT_PRODUCTION_WEIGHT_CONFIG,
    EvidenceWeight,
    EvidenceWeightingEngine,
    ProductionWeightConfig,
)


def _make_group(
    group_id: str,
    grounding: CausalGrounding,
    desired: TherapeuticAction,
    recs: list[str] | None = None,
    ref: str = "pmid:12345",
) -> DirectionalEvidenceGroup:
    record_ids = recs or [f"{group_id}_rec1"]
    return DirectionalEvidenceGroup(
        group_id=group_id,
        target_id="T1",
        disease_id="D1",
        evidence_family=EvidenceFamily.GENETIC,
        causal_grounding=grounding,
        desired_action=desired,
        references=[ref],
        member_record_count=len(record_ids),
        sources=["OpenTargets"],
    )


# ── 1. Structural evidence has 0.0 directional weight ─────────────────────────
def test_1_structural_evidence_zero_weight():
    engine = EvidenceWeightingEngine()
    g = _make_group("g1", CausalGrounding.STRUCTURAL, TherapeuticAction.INHIBITION)
    w = engine.compute_group_weight(g, "T1", TherapeuticAction.INHIBITION, mechanism_quality="STRUCTURAL")
    assert w.final_weight == 0.0
    assert w.base_weight == 0.0


# ── 2. Curated evidence receives appropriate weight ───────────────────────────
def test_2_curated_evidence_weight():
    engine = EvidenceWeightingEngine()
    g = _make_group("g1", CausalGrounding.CURATED, TherapeuticAction.INHIBITION)
    w = engine.compute_group_weight(g, "T1", TherapeuticAction.INHIBITION, mechanism_quality="CURATED")
    assert w.final_weight > 0.50
    assert w.base_weight == DEFAULT_PRODUCTION_WEIGHT_CONFIG.grounding_curated


# ── 3. Causal outweights curated ──────────────────────────────────────────────
def test_3_causal_outweighs_curated():
    engine = EvidenceWeightingEngine()
    g_cur = _make_group("g1", CausalGrounding.CURATED, TherapeuticAction.INHIBITION)
    g_cau = _make_group("g2", CausalGrounding.DIRECT, TherapeuticAction.INHIBITION)

    w_cur = engine.compute_group_weight(g_cur, "T1", TherapeuticAction.INHIBITION, mechanism_quality="CURATED")
    w_cau = engine.compute_group_weight(g_cau, "T1", TherapeuticAction.INHIBITION, mechanism_quality="CAUSAL")
    assert w_cau.final_weight > w_cur.final_weight


# ── 4. Literature grounded receives high weight ───────────────────────────────
def test_4_literature_grounded_weight():
    engine = EvidenceWeightingEngine()
    g = _make_group("g1", CausalGrounding.DIRECT, TherapeuticAction.INHIBITION)
    w = engine.compute_group_weight(g, "T1", TherapeuticAction.INHIBITION, mechanism_quality="LITERATURE_GROUNDED")
    assert w.final_weight >= 0.90


# ── 5. Independently validated receives full weight ───────────────────────────
def test_5_independently_validated_full_weight():
    engine = EvidenceWeightingEngine()
    g = _make_group("g1", CausalGrounding.DIRECT, TherapeuticAction.INHIBITION)
    w = engine.compute_group_weight(g, "T1", TherapeuticAction.INHIBITION, mechanism_quality="INDEPENDENTLY_VALIDATED")
    assert w.final_weight == 1.0


# ── 6. Duplicate records receive diminishing returns ──────────────────────────
def test_6_duplicate_records_diminishing_returns():
    engine = EvidenceWeightingEngine()
    g1 = _make_group("g1", CausalGrounding.DIRECT, TherapeuticAction.INHIBITION, recs=["rec1"])
    # Group with 10 duplicate rows pointing to same citation
    g10 = _make_group("g10", CausalGrounding.DIRECT, TherapeuticAction.INHIBITION, recs=[f"rec_{i}" for i in range(10)])

    w1 = engine.compute_group_weight(g1, "T1", TherapeuticAction.INHIBITION)
    w10 = engine.compute_group_weight(g10, "T1", TherapeuticAction.INHIBITION)

    # 10 records must NOT produce 10x the weight of 1 record
    assert w10.final_weight < 2.0 * w1.final_weight
    assert w10.independence_multiplier == 1.0 + (3 * 0.15)  # Capped at max 3 extra steps


# ── 7. Direct target outweights indirect ──────────────────────────────────────
def test_7_direct_target_outweighs_indirect():
    engine = EvidenceWeightingEngine()
    g = _make_group("g1", CausalGrounding.DIRECT, TherapeuticAction.INHIBITION)

    w_dir = engine.compute_group_weight(g, "T1", TherapeuticAction.INHIBITION, is_direct_target=True)
    w_ind = engine.compute_group_weight(g, "T1", TherapeuticAction.INHIBITION, is_direct_target=False)
    assert w_dir.final_weight > w_ind.final_weight


# ── 8. Primary target outweights secondary off-target ─────────────────────────
def test_8_primary_target_outweighs_secondary():
    engine = EvidenceWeightingEngine()
    g = _make_group("g1", CausalGrounding.DIRECT, TherapeuticAction.INHIBITION)

    w_pri = engine.compute_group_weight(g, "T1", TherapeuticAction.INHIBITION, is_primary_target=True)
    w_sec = engine.compute_group_weight(g, "T1", TherapeuticAction.INHIBITION, is_primary_target=False)
    assert w_pri.final_weight > w_sec.final_weight
    assert w_sec.final_weight == pytest.approx(w_pri.final_weight * 0.40)


# ── 9. Missing provenance incurs conservative discount (not opposition) ───────
def test_9_missing_provenance_conservative_discount():
    engine = EvidenceWeightingEngine()
    g_prov = _make_group("g1", CausalGrounding.DIRECT, TherapeuticAction.INHIBITION, ref="pmid:999")
    g_noprov = _make_group("g2", CausalGrounding.DIRECT, TherapeuticAction.INHIBITION, ref="unlinked")

    w_prov = engine.compute_group_weight(g_prov, "T1", TherapeuticAction.INHIBITION)
    w_noprov = engine.compute_group_weight(g_noprov, "T1", TherapeuticAction.INHIBITION)

    assert w_noprov.final_weight < w_prov.final_weight
    assert w_noprov.final_weight > 0.0  # Discounted, but NOT zero and NOT opposition
    assert w_noprov.direction == "SUPPORTS"


# ── 10. UNKNOWN evidence does not create opposition ───────────────────────────
def test_10_unknown_evidence_no_opposition():
    engine = EvidenceWeightingEngine()
    g_unk = _make_group("g1", CausalGrounding.DIRECT, TherapeuticAction.UNKNOWN)
    w_unk = engine.compute_group_weight(g_unk, "T1", TherapeuticAction.INHIBITION)

    assert w_unk.direction == "UNKNOWN"
    agg = engine.aggregate_weights([w_unk])
    assert agg.opposing_weight == 0.0
    assert agg.supporting_weight == 0.0
    assert agg.unresolved_weight > 0.0


# ── 11. Decisive support yields SUPPORTS ──────────────────────────────────────
def test_11_decisive_support_yields_supports():
    engine = EvidenceWeightingEngine()
    g1 = _make_group("g1", CausalGrounding.DIRECT, TherapeuticAction.INHIBITION)
    g2 = _make_group("g2", CausalGrounding.INFERRED, TherapeuticAction.ACTIVATION)  # Opposes

    w1 = engine.compute_group_weight(g1, "T1", TherapeuticAction.INHIBITION, is_primary_target=True)
    w2 = engine.compute_group_weight(g2, "T2", TherapeuticAction.INHIBITION, is_primary_target=False)  # Weak off-target

    agg = engine.aggregate_weights([w1, w2])
    assert agg.verdict == "SUPPORTS"
    assert agg.supporting_weight > agg.opposing_weight


# ── 12. Decisive opposition yields OPPOSES ────────────────────────────────────
def test_12_decisive_opposition_yields_opposes():
    engine = EvidenceWeightingEngine()
    g1 = _make_group("g1", CausalGrounding.DIRECT, TherapeuticAction.ACTIVATION)  # Opposes INHIBITION drug
    w1 = engine.compute_group_weight(g1, "T1", TherapeuticAction.INHIBITION, is_primary_target=True)

    agg = engine.aggregate_weights([w1])
    assert agg.verdict == "OPPOSES"
    assert agg.opposing_weight > 0.0
    assert agg.supporting_weight == 0.0


# ── 13. Balanced strong evidence yields CONFLICT ──────────────────────────────
def test_13_balanced_strong_evidence_yields_conflict():
    engine = EvidenceWeightingEngine()
    g_supp = _make_group("g1", CausalGrounding.DIRECT, TherapeuticAction.INHIBITION)
    g_opp = _make_group("g2", CausalGrounding.DIRECT, TherapeuticAction.ACTIVATION)

    w_supp = engine.compute_group_weight(g_supp, "T1", TherapeuticAction.INHIBITION, is_primary_target=True)
    w_opp = engine.compute_group_weight(g_opp, "T2", TherapeuticAction.INHIBITION, is_primary_target=True)

    agg = engine.aggregate_weights([w_supp, w_opp])
    assert agg.conflict_level == ContradictionLevel.STRONG
    assert agg.verdict == "CONFLICT"


# ── 14. Sub-threshold weight yields INSUFFICIENT ──────────────────────────────
def test_14_subthreshold_weight_yields_insufficient():
    engine = EvidenceWeightingEngine()
    # Structural group has 0.0 weight
    g_struct = _make_group("g1", CausalGrounding.STRUCTURAL, TherapeuticAction.INHIBITION)
    w_struct = engine.compute_group_weight(g_struct, "T1", TherapeuticAction.INHIBITION, mechanism_quality="STRUCTURAL")

    agg = engine.aggregate_weights([w_struct])
    assert agg.verdict == "INSUFFICIENT"
    assert agg.supporting_weight == 0.0


# ── 15. ProductionWeightConfig labeled INITIAL_HEURISTIC and configurable ─────
def test_15_config_labeled_initial_heuristic():
    cfg = DEFAULT_PRODUCTION_WEIGHT_CONFIG
    assert "INITIAL_HEURISTIC" in cfg.config_name

    # Check custom configuration overrides
    custom = ProductionWeightConfig(
        config_name="INITIAL_HEURISTIC_CUSTOM",
        quality_curated=0.70,
        decision_ratio_threshold=2.0,
    )
    assert custom.quality_curated == 0.70
    assert custom.decision_ratio_threshold == 2.0


# ── 16. Full traceability of each weight component ────────────────────────────
def test_16_full_weight_traceability():
    engine = EvidenceWeightingEngine()
    g = _make_group("g_trace", CausalGrounding.DIRECT, TherapeuticAction.INHIBITION, recs=["rec1", "rec2"], ref="pmid:77777")
    w = engine.compute_group_weight(g, "SLC12A1", TherapeuticAction.INHIBITION, is_primary_target=True, mechanism_quality="CAUSAL")

    d = w.to_dict()
    assert d["target_id"] == "SLC12A1"
    assert d["group_id"] == "g_trace"
    assert d["evidence_family"] == "GENETIC"
    assert d["direction"] == "SUPPORTS"
    assert d["base_weight"] == 1.0
    assert d["quality_multiplier"] == 0.90
    assert d["independence_multiplier"] == 1.15
    assert d["relevance_multiplier"] == 1.0
    assert d["provenance_multiplier"] == 1.0
    assert d["final_weight"] == round(1.0 * 0.90 * 1.15 * 1.0 * 1.0, 4)
    assert "Final weight=" in d["explanation"]
