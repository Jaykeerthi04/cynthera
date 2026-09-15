"""Tests for Phase 5.6: Contradiction and uncertainty propagation."""
from __future__ import annotations

import pytest

from backend.core.domain.contradiction import Contradiction
from backend.core.domain.contradiction_summary import ContradictionSummary
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.therapeutic_direction_evidence import (
    DirectionalEvidenceGroup,
    EvidenceFamily,
    TargetTherapeuticAlignment,
    TherapeuticAction,
    TherapeuticAlignment,
    TherapeuticAlignmentReport,
)
from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator


def _make_group(
    group_id: str,
    target_id: str = "T1",
    desired_action: TherapeuticAction = TherapeuticAction.INHIBITION,
    grounding: CausalGrounding = CausalGrounding.CURATED,
) -> DirectionalEvidenceGroup:
    return DirectionalEvidenceGroup(
        group_id=group_id,
        target_id=target_id,
        disease_id="DIS1",
        desired_action=desired_action,
        evidence_family=EvidenceFamily.GENETIC,
        causal_grounding=grounding,
        summary=f"Group {group_id} -> desired {desired_action.value} ({grounding.value})",
    )


def _make_ta_report(
    supp_groups: list[DirectionalEvidenceGroup],
    opp_groups: list[DirectionalEvidenceGroup],
) -> TherapeuticAlignmentReport:
    target_id = "T1"
    all_groups = supp_groups + opp_groups
    supp_ids = [g.group_id for g in supp_groups]
    opp_ids = [g.group_id for g in opp_groups]

    ta = TargetTherapeuticAlignment(
        target_id=target_id,
        drug_action=TherapeuticAction.INHIBITION,
        desired_target_action=TherapeuticAction.INHIBITION if supp_groups else TherapeuticAction.ACTIVATION,
        alignment=TherapeuticAlignment.SUPPORTS if (supp_groups and not opp_groups) else (
            TherapeuticAlignment.OPPOSES if (opp_groups and not supp_groups) else TherapeuticAlignment.INSUFFICIENT
        ),
        evidence_groups=all_groups,
        supporting_groups=supp_ids,
        opposing_groups=opp_ids,
    )

    return TherapeuticAlignmentReport(
        drug_name="TestDrug",
        disease_name="TestDisease",
        overall_alignment=ta.alignment,
        target_alignments=[ta],
        primary_target_alignments=[ta],
        total_independent_groups=len(all_groups),
        supporting_groups_count=len(supp_groups),
        opposing_groups_count=len(opp_groups),
    )


class TestContradictionPropagation:
    def test_support_only_yields_supports(self):
        """Unilateral support yields SUPPORTS with has_conflict=False."""
        orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
        g1 = _make_group("g1", grounding=CausalGrounding.CURATED)
        report = _make_ta_report([g1], [])

        summary = orch._build_contradiction_summary(report, [])
        assert summary.resolution == "SUPPORTS"
        assert summary.has_conflict is False
        assert summary.strong_conflict is False
        assert summary.support_groups == 1
        assert summary.opposition_groups == 0

    def test_opposition_only_yields_opposes(self):
        """Unilateral opposition yields OPPOSES with has_conflict=False."""
        orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
        g1 = _make_group("g1", desired_action=TherapeuticAction.ACTIVATION, grounding=CausalGrounding.CURATED)
        report = _make_ta_report([], [g1])

        summary = orch._build_contradiction_summary(report, [])
        assert summary.resolution == "OPPOSES"
        assert summary.has_conflict is False
        assert summary.strong_conflict is False
        assert summary.support_groups == 0
        assert summary.opposition_groups == 1

    def test_unknown_only_yields_insufficient(self):
        """Zero directional groups yields INSUFFICIENT with has_conflict=False."""
        orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
        report = _make_ta_report([], [])

        summary = orch._build_contradiction_summary(report, [])
        assert summary.resolution == "INSUFFICIENT"
        assert summary.has_conflict is False
        assert summary.strong_conflict is False

    def test_equal_strong_support_opposition_yields_unresolved_conflict(self):
        """Both curated/direct support and opposition yields UNRESOLVED_CONFLICT with strong_conflict=True."""
        orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
        g_supp = _make_group("g_supp", desired_action=TherapeuticAction.INHIBITION, grounding=CausalGrounding.DIRECT)
        g_opp = _make_group("g_opp", desired_action=TherapeuticAction.ACTIVATION, grounding=CausalGrounding.CURATED)
        report = _make_ta_report([g_supp], [g_opp])

        summary = orch._build_contradiction_summary(report, [])
        assert summary.resolution == "UNRESOLVED_CONFLICT"
        assert summary.has_conflict is True
        assert summary.strong_conflict is True
        assert len(summary.conflict_sources) > 0

    def test_weak_opposition_vs_strong_support_yields_supports_with_conflict_noted(self):
        """Curated support outweighs inferred opposition, but conflict is preserved in audit."""
        orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
        g_supp = _make_group("g_supp", desired_action=TherapeuticAction.INHIBITION, grounding=CausalGrounding.CURATED)
        g_opp = _make_group("g_opp", desired_action=TherapeuticAction.ACTIVATION, grounding=CausalGrounding.INFERRED)
        report = _make_ta_report([g_supp], [g_opp])

        summary = orch._build_contradiction_summary(report, [])
        assert summary.resolution == "SUPPORTS"
        assert summary.has_conflict is True
        assert summary.strong_conflict is False
        assert "noted" in summary.explanation.lower()

    def test_strong_opposition_vs_weak_support_yields_opposes_with_conflict_noted(self):
        """Curated opposition outweighs inferred support, but conflict is preserved in audit."""
        orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
        g_supp = _make_group("g_supp", desired_action=TherapeuticAction.INHIBITION, grounding=CausalGrounding.INFERRED)
        g_opp = _make_group("g_opp", desired_action=TherapeuticAction.ACTIVATION, grounding=CausalGrounding.DIRECT)
        report = _make_ta_report([g_supp], [g_opp])

        summary = orch._build_contradiction_summary(report, [])
        assert summary.resolution == "OPPOSES"
        assert summary.has_conflict is True
        assert summary.strong_conflict is False
        assert "noted" in summary.explanation.lower()

    def test_inferred_vs_inferred_conflict_preserved(self):
        """Conflicting inferred evidence without curated consensus yields UNRESOLVED_CONFLICT."""
        orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
        g_supp = _make_group("g_supp", desired_action=TherapeuticAction.INHIBITION, grounding=CausalGrounding.INFERRED)
        g_opp = _make_group("g_opp", desired_action=TherapeuticAction.ACTIVATION, grounding=CausalGrounding.INFERRED)
        report = _make_ta_report([g_supp], [g_opp])

        summary = orch._build_contradiction_summary(report, [])
        assert summary.resolution == "UNRESOLVED_CONFLICT"
        assert summary.has_conflict is True
        assert summary.strong_conflict is True

    def test_contradiction_summary_serialization(self):
        """ContradictionSummary serializes to dictionary cleanly."""
        summary = ContradictionSummary(
            has_conflict=True,
            support_groups=2,
            opposition_groups=1,
            support_weight=2.0,
            opposition_weight=1.0,
            strong_conflict=False,
            resolution="SUPPORTS",
            conflict_sources=["Target T1: conflict"],
            explanation="Test explanation",
        )
        data = summary.to_dict()
        assert data["has_conflict"] is True
        assert data["support_groups"] == 2
        assert data["resolution"] == "SUPPORTS"
        assert data["conflict_sources"] == ["Target T1: conflict"]

    def test_unknown_plus_support_does_not_become_opposes(self):
        """UNKNOWN desired action plus support evidence must NOT become OPPOSES."""
        orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
        g_supp = _make_group("g_supp", desired_action=TherapeuticAction.INHIBITION, grounding=CausalGrounding.CURATED)
        # Group with UNKNOWN desired action
        g_unk = _make_group("g_unk", desired_action=TherapeuticAction.UNKNOWN, grounding=CausalGrounding.NONE)

        report = _make_ta_report([g_supp], [])
        # Append unk to evidence groups
        report.target_alignments[0].evidence_groups.append(g_unk)

        summary = orch._build_contradiction_summary(report, [])
        assert summary.resolution == "SUPPORTS"
        assert summary.resolution != "OPPOSES"
        assert summary.opposition_groups == 0

    def test_unknown_plus_opposition_does_not_become_supports(self):
        """UNKNOWN desired action plus opposition evidence must NOT become SUPPORTS."""
        orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
        g_opp = _make_group("g_opp", desired_action=TherapeuticAction.ACTIVATION, grounding=CausalGrounding.CURATED)
        g_unk = _make_group("g_unk", desired_action=TherapeuticAction.UNKNOWN, grounding=CausalGrounding.NONE)

        report = _make_ta_report([], [g_opp])
        report.target_alignments[0].evidence_groups.append(g_unk)

        summary = orch._build_contradiction_summary(report, [])
        assert summary.resolution == "OPPOSES"
        assert summary.resolution != "SUPPORTS"
        assert summary.support_groups == 0

