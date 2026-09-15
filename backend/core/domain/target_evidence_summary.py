"""TargetEvidenceSummary domain model (Phase 5.13).

Captures target-specific evidence synthesis including molecular drug action,
disease therapeutic requirements, independent directional groups, mechanism quality,
and explicit target relevance attributes.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from backend.core.value_objects.therapeutic_direction_evidence import TherapeuticAction


class TargetEvidenceSummary(BaseModel):
    """Summary of all therapeutic, mechanistic, and directional evidence for an individual target.

    Attributes:
        target_id: Canonical target identifier (e.g. UniProt accession or canonical gene symbol).
        target_symbol: Human-readable gene symbol (e.g. 'SLC12A1').
        drug_action: Drug's action on target (INHIBITION, ACTIVATION, TARGETING, UNKNOWN).
        required_action: Disease-specific requirement on target (INHIBITION, ACTIVATION, UNKNOWN).
        alignment: Directional alignment verdict (SUPPORTS, OPPOSES, INSUFFICIENT, MIXED).
        mechanistic_score: Best mechanistic score through this target.
        mechanism_quality: Quality tier for mechanisms involving this target (STRUCTURAL, CURATED, CAUSAL, etc.).
        supporting_evidence_groups: Number of independent evidence groups supporting alignment.
        opposing_evidence_groups: Number of independent evidence groups opposing alignment.
        independent_evidence_groups: Total distinct independent evidence groups for this target.
        directional_state: Directional mechanism state (CONSISTENT, CONTRADICTORY, PARTIAL, UNKNOWN).
        confidence: Normalized confidence in this target's evaluation [0.0, 1.0].
        is_primary: True if primary binding target from bioactivity data, False for secondary/off-target.
        target_relevance: Structured components determining relative target influence.
    """

    model_config = {"frozen": True}

    target_id: str = Field(..., description="Canonical target identifier.")
    target_symbol: str | None = Field(default=None, description="Human-readable gene symbol.")
    drug_action: TherapeuticAction = Field(default=TherapeuticAction.UNKNOWN, description="Drug molecular action.")
    required_action: TherapeuticAction = Field(default=TherapeuticAction.UNKNOWN, description="Desired action in disease.")
    alignment: str = Field(default="INSUFFICIENT", description="Alignment verdict: SUPPORTS | OPPOSES | INSUFFICIENT | MIXED.")
    mechanistic_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Mechanistic path score.")
    mechanism_quality: str = Field(default="STRUCTURAL", description="Quality tier: STRUCTURAL | CURATED | CAUSAL | LITERATURE_GROUNDED | INDEPENDENTLY_VALIDATED.")
    supporting_evidence_groups: int = Field(default=0, ge=0, description="Independent supporting groups.")
    opposing_evidence_groups: int = Field(default=0, ge=0, description="Independent opposing groups.")
    independent_evidence_groups: int = Field(default=0, ge=0, description="Total independent groups.")
    directional_state: str = Field(default="UNKNOWN", description="CONSISTENT | CONTRADICTORY | PARTIAL | UNKNOWN.")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Target evaluation confidence.")
    is_primary: bool = Field(default=True, description="True if primary target, False if secondary/off-target.")
    target_relevance: dict[str, Any] = Field(default_factory=dict, description="Relevance components breakdown.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_symbol": self.target_symbol,
            "drug_action": self.drug_action.value if hasattr(self.drug_action, "value") else str(self.drug_action),
            "required_action": self.required_action.value if hasattr(self.required_action, "value") else str(self.required_action),
            "alignment": self.alignment,
            "mechanistic_score": self.mechanistic_score,
            "mechanism_quality": self.mechanism_quality,
            "supporting_evidence_groups": self.supporting_evidence_groups,
            "opposing_evidence_groups": self.opposing_evidence_groups,
            "independent_evidence_groups": self.independent_evidence_groups,
            "directional_state": self.directional_state,
            "confidence": self.confidence,
            "is_primary": self.is_primary,
            "target_relevance": dict(self.target_relevance),
        }
