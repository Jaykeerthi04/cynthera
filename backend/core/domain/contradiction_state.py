"""ContradictionState domain model (Phase 5.14).

Formalizes contradiction levels and epistemic uncertainty across the reasoning hierarchy
(evidence -> target -> mechanism -> drug -> hypothesis).
"""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ContradictionLevel(str, Enum):
    """Categorical severity of directional contradiction."""
    NONE = "NONE"          # Unilateral support, unilateral opposition, or no directional data
    MINOR = "MINOR"        # Decisive majority direction with small secondary conflict
    MODERATE = "MODERATE"  # Noticeable discordance across targets or evidence sources
    STRONG = "STRONG"      # Substantial grounded evidence on both supporting and opposing sides


class ContradictionState(BaseModel):
    """Explicit state of directional contradiction and epistemic uncertainty.

    Attributes:
        level: Categorical contradiction severity (NONE, MINOR, MODERATE, STRONG).
        supporting_weight: Total grounded weight supporting the hypothesis.
        opposing_weight: Total grounded weight opposing the hypothesis.
        unresolved_weight: Weight associated with uncharacterized or ambiguous evidence.
        supporting_groups: Number of independent evidence groups supporting.
        opposing_groups: Number of independent evidence groups opposing.
        affected_targets: List of target identifiers contributing to discordance.
        has_conflict: True if both supporting and opposing evidence exist.
        strong_conflict: True if meaningful grounded evidence exists on both sides.
        explanation: Transparent narrative detailing conflict sources, citations, and resolution.
    """

    model_config = {"frozen": True}

    level: ContradictionLevel = Field(
        default=ContradictionLevel.NONE,
        description="Severity level of directional contradiction.",
    )
    supporting_weight: float = Field(
        default=0.0,
        ge=0.0,
        description="Cumulative grounded weight supporting hypothesis.",
    )
    opposing_weight: float = Field(
        default=0.0,
        ge=0.0,
        description="Cumulative grounded weight opposing hypothesis.",
    )
    unresolved_weight: float = Field(
        default=0.0,
        ge=0.0,
        description="Cumulative weight of unresolved or uncertain evidence.",
    )
    supporting_groups: int = Field(
        default=0,
        ge=0,
        description="Count of independent supporting groups.",
    )
    opposing_groups: int = Field(
        default=0,
        ge=0,
        description="Count of independent opposing groups.",
    )
    affected_targets: list[str] = Field(
        default_factory=list,
        description="Target canonical identifiers involved in the conflict.",
    )
    has_conflict: bool = Field(
        default=False,
        description="True if discordant evidence is present.",
    )
    strong_conflict: bool = Field(
        default=False,
        description="True if substantial grounded evidence exists on both sides.",
    )
    explanation: str = Field(
        default="",
        description="Human-readable explanation of contradiction state and causes.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "supporting_weight": round(self.supporting_weight, 4),
            "opposing_weight": round(self.opposing_weight, 4),
            "unresolved_weight": round(self.unresolved_weight, 4),
            "supporting_groups": self.supporting_groups,
            "opposing_groups": self.opposing_groups,
            "affected_targets": list(self.affected_targets),
            "has_conflict": self.has_conflict,
            "strong_conflict": self.strong_conflict,
            "explanation": self.explanation,
        }
