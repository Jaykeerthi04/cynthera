"""Claim entity — structured semantic statement from literature.

Reference: 02_DOMAIN_MODEL.md §4.12
"""
from __future__ import annotations

import uuid
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator

from backend.core.enums.predicate_type import PredicateType
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference


class Claim(BaseModel):
    """A structured semantic statement extracted from text as a subject-predicate-object triple.

    Immutable. Created by the ClaimExtractionAgent.
    Predicate must map to a PredicateType enum.
    Confidence score must be float [0.0, 1.0].

    Attributes:
        id: Internal UUID.
        subject: Entity performing the action (e.g., drug name, gene symbol).
        predicate: Directional mechanism from PredicateType enum.
        object: Entity receiving the action (e.g., target name, disease name).
        confidence: Extraction confidence float [0.0, 1.0].
        erw: Evidence Reliability Weight inherited from parent evidence.
        evidence_ids: UUIDs of supporting Evidence records.
        provenance: Source citation.
        raw_text: Original sentence(s) from which the claim was extracted.
        is_validated: True once ClaimValidationAgent confirms this claim.
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Internal unique identifier.")
    subject: str = Field(..., min_length=1, description="Entity performing the action.")
    predicate: PredicateType = Field(..., description="Directional mechanism (PredicateType).")
    object: str = Field(..., min_length=1, description="Entity receiving the action.")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Extraction confidence score [0.0, 1.0].",
    )
    erw: ERW = Field(..., description="Evidence Reliability Weight inherited from parent evidence.")
    evidence_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="UUIDs of supporting Evidence records.",
    )
    provenance: ProvenanceReference = Field(..., description="Source citation.")
    raw_text: str | None = Field(None, description="Original sentence(s) from which this claim was extracted.")
    is_validated: bool = Field(default=False, description="True once ClaimValidationAgent confirms.")
    evidence_type: Optional[str] = Field(
        default=None,
        description=(
            "Study design classification for evidence quality weighting. "
            "Valid values match EVIDENCE_TYPE_WEIGHTS keys (e.g. 'RCT', 'META_ANALYSIS', "
            "'COHORT_STUDY'). None means UNKNOWN — applies 0.50 quality multiplier. "
            "Set by trial_to_negative_claim() for CT.gov-sourced claims."
        ),
    )
    attribution_trace: Optional[dict[str, Any]] = Field(
        default=None,
        description="Structured attribution diagnostic trace for CT.gov-sourced negative claims.",
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Validate confidence is within [0.0, 1.0]."""
        return round(v, 4)
