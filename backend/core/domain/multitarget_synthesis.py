"""MultiTargetSynthesis domain model (Phase 5.13).

Captures drug-level synthesis across all evaluated targets with explicit
weighting, conflict detection, and target provenance preservation.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from backend.core.domain.target_evidence_summary import TargetEvidenceSummary


class MultiTargetSynthesis(BaseModel):
    """Synthesized conclusion across multiple drug targets.

    Attributes:
        target_summaries: List of individual TargetEvidenceSummary objects.
        supporting_targets: Canonical identifiers of targets supporting the hypothesis.
        opposing_targets: Canonical identifiers of targets opposing the hypothesis.
        unresolved_targets: Canonical identifiers of targets with insufficient or ambiguous data.
        supporting_weight: Cumulative evidence weight supporting hypothesis.
        opposing_weight: Cumulative evidence weight opposing hypothesis.
        unresolved_weight: Weight associated with unresolved or uncertain targets.
        conflict_detected: True if both supporting and opposing targets exist.
        strong_conflict: True if meaningful grounded evidence exists on both sides.
        synthesis_state: Overall multi-target state: 'SUPPORTS' | 'OPPOSES' | 'MIXED' | 'INSUFFICIENT'.
        effective_target_count: Number of targets with actionable directional evidence.
        rationale: Human-readable explanation of synthesis rationale.
    """

    model_config = {"frozen": True}

    target_summaries: list[TargetEvidenceSummary] = Field(
        default_factory=list,
        description="Detailed evidence summaries for each evaluated target.",
    )
    supporting_targets: list[str] = Field(
        default_factory=list,
        description="Targets whose directional evidence supports the hypothesis.",
    )
    opposing_targets: list[str] = Field(
        default_factory=list,
        description="Targets whose directional evidence opposes the hypothesis.",
    )
    unresolved_targets: list[str] = Field(
        default_factory=list,
        description="Targets lacking sufficient directional evidence to resolve alignment.",
    )
    supporting_weight: float = Field(
        default=0.0,
        ge=0.0,
        description="Aggregated support weight across all targets.",
    )
    opposing_weight: float = Field(
        default=0.0,
        ge=0.0,
        description="Aggregated opposition weight across all targets.",
    )
    unresolved_weight: float = Field(
        default=0.0,
        ge=0.0,
        description="Aggregated weight of unresolved target evidence.",
    )
    conflict_detected: bool = Field(
        default=False,
        description="True if discordant target directions are detected.",
    )
    strong_conflict: bool = Field(
        default=False,
        description="True if both supporting and opposing targets have substantial grounded evidence.",
    )
    synthesis_state: str = Field(
        default="INSUFFICIENT",
        description="Synthesized state: SUPPORTS | OPPOSES | MIXED | INSUFFICIENT.",
    )
    effective_target_count: int = Field(
        default=0,
        ge=0,
        description="Count of targets contributing actionable evidence.",
    )
    rationale: str = Field(
        default="",
        description="Explanation detailing multi-target synthesis decision.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_summaries": [t.to_dict() for t in self.target_summaries],
            "supporting_targets": list(self.supporting_targets),
            "opposing_targets": list(self.opposing_targets),
            "unresolved_targets": list(self.unresolved_targets),
            "supporting_weight": round(self.supporting_weight, 4),
            "opposing_weight": round(self.opposing_weight, 4),
            "unresolved_weight": round(self.unresolved_weight, 4),
            "conflict_detected": self.conflict_detected,
            "strong_conflict": self.strong_conflict,
            "synthesis_state": self.synthesis_state,
            "effective_target_count": self.effective_target_count,
            "rationale": self.rationale,
        }
