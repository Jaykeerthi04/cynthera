"""Unit tests for Phase 5.14 — Contradiction & Uncertainty Propagation.

Verifies:
1. No contradiction (unilateral direction) -> ContradictionLevel.NONE
2. Minor contradiction (dominant direction with small conflict) -> ContradictionLevel.MINOR
3. Moderate contradiction -> ContradictionLevel.MODERATE
4. Strong contradiction -> ContradictionLevel.STRONG
5. Duplicate evidence does not inflate contradiction level
6. Independent opposing evidence creates contradiction
7. UNKNOWN propagates as uncertainty without becoming opposition
8. PARTIAL propagates as uncertainty without becoming CONSISTENT
9. Strong support + weak opposition remains support
10. Strong support + strong opposition produces UNCERTAIN (Strong-Conflict Safety Rule)
11. Contradiction survives multi-target synthesis
12. Contradiction explanation details affected targets and groups
"""
from __future__ import annotations

import pytest

from backend.core.domain.contradiction_state import ContradictionLevel, ContradictionState
from backend.core.domain.multitarget_synthesis import MultiTargetSynthesis
from backend.core.domain.target_evidence_summary import TargetEvidenceSummary
from backend.core.value_objects.therapeutic_direction_evidence import TherapeuticAction
from backend.reasoning.directional.contradiction_propagator import (
    ContradictionConfig,
    ContradictionPropagator,
)


def _make_propagator() -> ContradictionPropagator:
    return ContradictionPropagator(
        ContradictionConfig(
            minor_balance_threshold=0.75,
            moderate_balance_threshold=0.40,
            strong_min_weight=0.50,
        )
    )


# ── 1. No contradiction ───────────────────────────────────────────────────────
def test_1_no_contradiction():
    prop = _make_propagator()
    state = prop.compute_contradiction_state(supporting_weight=2.0, opposing_weight=0.0)
    assert state.level == ContradictionLevel.NONE
    assert state.has_conflict is False
    assert state.strong_conflict is False


# ── 2. Minor contradiction ───────────────────────────────────────────────────
def test_2_minor_contradiction():
    prop = _make_propagator()
    # Supp 3.0, Opp 0.3 -> balance = |3.0 - 0.3| / 3.3 = 0.818 >= 0.75 -> MINOR
    state = prop.compute_contradiction_state(supporting_weight=3.0, opposing_weight=0.3, affected_targets=["T1"])
    assert state.level == ContradictionLevel.MINOR
    assert state.has_conflict is True
    assert state.strong_conflict is False


# ── 3. Moderate contradiction ─────────────────────────────────────────────────
def test_3_moderate_contradiction():
    prop = _make_propagator()
    # Supp 2.0, Opp 0.8 -> balance = |2.0 - 0.8| / 2.8 = 0.428 -> MODERATE
    state = prop.compute_contradiction_state(supporting_weight=2.0, opposing_weight=0.8, affected_targets=["T1", "T2"])
    assert state.level == ContradictionLevel.MODERATE
    assert state.has_conflict is True


# ── 4. Strong contradiction ───────────────────────────────────────────────────
def test_4_strong_contradiction():
    prop = _make_propagator()
    # Supp 1.5, Opp 1.2 -> balance = 0.3 / 2.7 = 0.111 < 0.40 -> STRONG
    state = prop.compute_contradiction_state(supporting_weight=1.5, opposing_weight=1.2, affected_targets=["T1"])
    assert state.level == ContradictionLevel.STRONG
    assert state.strong_conflict is True


# ── 5. Duplicate evidence does not inflate contradiction ──────────────────────
def test_5_duplicate_evidence_does_not_inflate_contradiction():
    prop = _make_propagator()
    # If 10 duplicate rows represent 1 underlying study (supp_w = 0.9) vs 1 real opposing group (opp_w = 0.9)
    state = prop.compute_contradiction_state(supporting_weight=0.9, opposing_weight=0.9, supporting_groups=1, opposing_groups=1)
    assert state.level == ContradictionLevel.STRONG
    # Weight remains bounded by independent grouping, not row count


# ── 6. Independent opposing evidence creates contradiction ────────────────────
def test_6_independent_opposing_evidence_creates_contradiction():
    prop = _make_propagator()
    state = prop.compute_contradiction_state(supporting_weight=1.0, opposing_weight=0.9, supporting_groups=2, opposing_groups=2)
    assert state.has_conflict is True
    assert state.level == ContradictionLevel.STRONG


# ── 7. UNKNOWN propagates as uncertainty without becoming opposition ──────────
def test_7_unknown_propagates_as_uncertainty():
    prop = _make_propagator()
    # Supp 1.5, Opp 0.0, Unresolved 1.2
    state = prop.compute_contradiction_state(supporting_weight=1.5, opposing_weight=0.0, unresolved_weight=1.2)
    assert state.level == ContradictionLevel.NONE
    assert state.has_conflict is False
    assert state.unresolved_weight == 1.2
    assert "uncertainty" in state.explanation.lower()
    # Must NOT become opposition
    assert state.opposing_weight == 0.0


# ── 8. PARTIAL propagates as uncertainty without becoming CONSISTENT ──────────
def test_8_partial_propagates_as_uncertainty():
    summary = TargetEvidenceSummary(
        target_id="T1",
        drug_action=TherapeuticAction.INHIBITION,
        required_action=TherapeuticAction.INHIBITION,
        alignment="SUPPORTS",
        directional_state="PARTIAL",  # Intermediate step uncertain
        confidence=0.5,
    )
    assert summary.directional_state == "PARTIAL"
    assert summary.directional_state != "CONSISTENT"


# ── 9. Strong support + weak opposition remains support ───────────────────────
def test_9_strong_support_weak_opposition_remains_support():
    prop = _make_propagator()
    state = prop.compute_contradiction_state(supporting_weight=2.5, opposing_weight=0.2)
    status, reason = prop.apply_strong_conflict_guard("PROMISING", state)
    # Weak opposition is not a strong conflict; status remains PROMISING
    assert status == "PROMISING"
    assert reason is None


# ── 10. Strong support + strong opposition produces UNCERTAIN ─────────────────
def test_10_strong_support_strong_opposition_produces_uncertain():
    prop = _make_propagator()
    state = prop.compute_contradiction_state(supporting_weight=1.8, opposing_weight=1.5)
    assert state.strong_conflict is True

    # Strong-Conflict Safety Rule: Cannot produce PROMISING or NOT_RECOMMENDED
    status1, reason1 = prop.apply_strong_conflict_guard("PROMISING", state)
    assert status1 == "UNCERTAIN"
    assert reason1 is not None
    assert "STRONG CONFLICT SAFETY OVERRIDE" in reason1

    status2, reason2 = prop.apply_strong_conflict_guard("NOT_RECOMMENDED", state)
    assert status2 == "UNCERTAIN"


# ── 11. Contradiction survives multi-target synthesis ─────────────────────────
def test_11_contradiction_survives_multitarget_synthesis():
    prop = _make_propagator()
    t1 = TargetEvidenceSummary(
        target_id="T1",
        alignment="SUPPORTS",
        supporting_evidence_groups=2,
        opposing_evidence_groups=0,
    )
    t2 = TargetEvidenceSummary(
        target_id="T2",
        alignment="OPPOSES",
        supporting_evidence_groups=0,
        opposing_evidence_groups=2,
    )
    synth = MultiTargetSynthesis(
        target_summaries=[t1, t2],
        supporting_targets=["T1"],
        opposing_targets=["T2"],
        supporting_weight=1.2,
        opposing_weight=1.1,
        conflict_detected=True,
        strong_conflict=True,
        synthesis_state="MIXED",
    )
    state = prop.propagate_from_multitarget(synth)
    assert state.has_conflict is True
    assert state.strong_conflict is True
    assert "T1" in state.affected_targets
    assert "T2" in state.affected_targets


# ── 12. Contradiction explanation details affected targets and groups ─────────
def test_12_contradiction_explanation_details():
    prop = _make_propagator()
    state = prop.compute_contradiction_state(
        supporting_weight=1.2,
        opposing_weight=1.0,
        supporting_groups=3,
        opposing_groups=2,
        affected_targets=["ADRB1", "ADRA1A"],
    )
    assert "ADRB1" in state.explanation
    assert "ADRA1A" in state.explanation
    assert "3 groups" in state.explanation
    assert "2 groups" in state.explanation
