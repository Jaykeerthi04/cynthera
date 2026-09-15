"""DirectionalEvidence — value object for a single directional biological evidence record.

Reference: Phase 4B — Directional Evidence Infrastructure

Every directional claim must preserve its provenance. No direction without source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.enums.causal_grounding import CausalGrounding


@dataclass(frozen=True)
class DirectionalEvidence:
    """A single directional evidence record linking two biological entities.

    Attributes:
        subject_id:       Canonical identifier for the acting entity (e.g. drug ChEMBL ID,
                          UniProt accession, or gene symbol).
        object_id:        Canonical identifier for the receiving entity.
        polarity:         Molecular polarity of the interaction (POSITIVE/NEGATIVE/UNKNOWN).
        causal_grounding: Reliability of the directional claim (CURATED/STRUCTURAL/NONE/...).
        source:           Name of the originating data source (e.g. "ChEMBL", "Reactome").
        source_id:        Specific record ID within the source (e.g. ChEMBL mechanism ID,
                          Reactome reaction stId). May be None if not available.
        evidence_type:    Evidence category (e.g. "IN_VITRO", "CURATED_REACTION",
                          "PATHWAY_MEMBERSHIP", "DATABASE_ASSOCIATION").
        context:          Arbitrary source-specific metadata (action_type, target_role, etc.).
        confidence:       Optional confidence or association score [0.0, 1.0].

    Usage notes:
        - Used as an immutable audit record: do NOT mutate after creation.
        - polarity=UNKNOWN + causal_grounding=STRUCTURAL means "connected, direction unknown".
        - polarity=NEGATIVE + causal_grounding=CURATED means "ChEMBL says INHIBITOR".
        - therapeutic_direction is NOT a field here — that belongs to Phase 4C.
    """

    subject_id: str
    object_id: str
    polarity: MolecularPolarity
    causal_grounding: CausalGrounding
    source: str
    source_id: str | None
    evidence_type: str
    context: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.subject_id:
            raise ValueError("DirectionalEvidence.subject_id must not be empty.")
        if not self.object_id:
            raise ValueError("DirectionalEvidence.object_id must not be empty.")
        if not self.source:
            raise ValueError("DirectionalEvidence.source must not be empty.")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"DirectionalEvidence.confidence must be in [0.0, 1.0], got {self.confidence}."
            )
