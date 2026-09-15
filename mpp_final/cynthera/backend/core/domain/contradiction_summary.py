"""ContradictionSummary domain model (Phase 5.6).

Captures structured conflict and uncertainty propagation across targets and evidence groups.
Distinguishes unilateral alignment from genuine multi-source conflict without using
arbitrary numerical multiplier thresholds.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ContradictionSummary(BaseModel):
    """Structured summary of directional conflict and epistemic uncertainty.

    Attributes:
        has_conflict: True if both supporting and opposing evidence exists.
        support_groups: Number of independent evidence groups supporting the hypothesis.
        opposition_groups: Number of independent evidence groups opposing the hypothesis.
        support_weight: Cumulative weight of supporting evidence groups.
        opposition_weight: Cumulative weight of opposing evidence groups.
        strong_conflict: True if both support and opposition have meaningful grounded evidence.
        resolution: Consensus outcome: 'SUPPORTS' | 'OPPOSES' | 'INSUFFICIENT' | 'UNRESOLVED_CONFLICT'.
        conflict_sources: Target names, pathway IDs, or citations generating contradictory claims.
        explanation: Human-readable narrative detailing the conflict status and resolution rationale.
    """

    model_config = {"frozen": True}

    has_conflict: bool = Field(
        default=False,
        description="True if both supporting and opposing directional evidence exists.",
    )
    support_groups: int = Field(
        default=0,
        ge=0,
        description="Number of independent evidence groups supporting therapeutic hypothesis.",
    )
    opposition_groups: int = Field(
        default=0,
        ge=0,
        description="Number of independent evidence groups opposing therapeutic hypothesis.",
    )
    support_weight: float = Field(
        default=0.0,
        ge=0.0,
        description="Cumulative weight of supporting evidence groups.",
    )
    opposition_weight: float = Field(
        default=0.0,
        ge=0.0,
        description="Cumulative weight of opposing evidence groups.",
    )
    strong_conflict: bool = Field(
        default=False,
        description="True if both support and opposition possess meaningful grounded evidence.",
    )
    resolution: str = Field(
        default="INSUFFICIENT",
        description="Consensus conflict resolution: SUPPORTS | OPPOSES | INSUFFICIENT | UNRESOLVED_CONFLICT",
    )
    conflict_sources: list[str] = Field(
        default_factory=list,
        description="Sources, target IDs, or citations contributing to the conflict.",
    )
    explanation: str = Field(
        default="",
        description="Human-readable explanation of conflict status and resolution.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_conflict": self.has_conflict,
            "support_groups": self.support_groups,
            "opposition_groups": self.opposition_groups,
            "support_weight": self.support_weight,
            "opposition_weight": self.opposition_weight,
            "strong_conflict": self.strong_conflict,
            "resolution": self.resolution,
            "conflict_sources": list(self.conflict_sources),
            "explanation": self.explanation,
        }
