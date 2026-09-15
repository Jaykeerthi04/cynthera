"""CandidateMechanism domain entity — represents a discovered, candidate biological mechanism.

Models the candidate biological mechanisms connecting Drug → Target → Biological Process / Pathway → Disease.
Each candidate mechanism contains detailed hop-by-hop evidence, status ratings, and direct source links.
"""
from __future__ import annotations

import uuid
from typing import Any
from pydantic import BaseModel, Field

from backend.core.value_objects.source_url_builder import EvidenceLink


class MechanismHop(BaseModel):
    """One relationship in a candidate mechanism chain.

    ``status`` deliberately describes the *kind* of support, not whether a
    graph edge happened to be traversable.  In particular, Reactome
    participation is ``STRUCTURAL_EVIDENCE`` until an independent mechanistic
    source or a mapped literature claim supports the biological bridge.
    """

    model_config = {"frozen": True}

    from_node: str = Field(..., description="Source node name and label (e.g., 'Drug: Dapagliflozin').")
    to_node: str = Field(..., description="Target node name and label (e.g., 'Target: SLC5A2').")
    predicate: str = Field(..., description="Biological interaction predicate (e.g., 'INHIBITOR', 'PARTICIPATES_IN').")
    status: str = Field(
        default="CANDIDATE_STRUCTURAL",
        description=(
            "CANDIDATE_STRUCTURAL | DATABASE_SUPPORTED | LITERATURE_SUPPORTED | "
            "DIRECTION_UNCERTAIN | INSUFFICIENT_EVIDENCE | CONTRADICTED"
        ),
    )
    evidence_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    source_database: str = Field(..., description="Database source (e.g., 'ChEMBL', 'Reactome', 'Open Targets').")
    provenance_note: str = Field(default="", description="Detailed rationale or measurement note.")
    links: list[EvidenceLink] = Field(default_factory=list, description="Clickable URL links for this hop.")
    canonical_from_id: str | None = Field(default=None, description="Resolved canonical identifier for from_node.")
    canonical_to_id: str | None = Field(default=None, description="Resolved canonical identifier for to_node.")
    directionality: str = Field(default="DIRECTION_UNCERTAIN", description="SUPPORTED | DIRECTION_UNCERTAIN | NOT_APPLICABLE")
    evidence_type: str = Field(default="STRUCTURAL", description="DIRECT | CURATED | STRUCTURAL | LITERATURE")
    supporting_claims: list[dict[str, Any]] = Field(default_factory=list)
    contradicting_claims: list[dict[str, Any]] = Field(default_factory=list)
    # Phase 4B: typed directional fields for this hop's incoming edge
    polarity: str = Field(
        default="UNKNOWN",
        description="Phase 4B molecular polarity: POSITIVE | NEGATIVE | UNKNOWN",
    )
    causal_grounding: str = Field(
        default="STRUCTURAL",
        description="Phase 4B causal grounding: DIRECT | CURATED | INFERRED | STRUCTURAL | NONE",
    )


class CandidateMechanism(BaseModel):
    """A discovered biological route plus its independent validation record."""

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_index: int = Field(default=1, description="Index of this candidate mechanism (1-based).")
    name: str = Field(..., description="Human-readable title (e.g., 'SLC5A2 inhibition → Renal Glucose Reabsorption').")
    support_level: str = Field(
        ...,
        description="Rating: 'STRONGLY_SUPPORTED' | 'MODERATELY_SUPPORTED' | 'WEAK_SPECULATIVE' | 'CONTRADICTED' | 'UNSUPPORTED'",
    )
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    summary_chain: list[str] = Field(default_factory=list, description="Ordered chain strings (Drug → ... → Disease).")
    hops: list[MechanismHop] = Field(default_factory=list, description="Detailed hop-by-hop evidence breakdown.")
    literature_citations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Citations supporting this specific candidate mechanism with links.",
    )
    rationale: str = Field(default="", description="Scientific justification explaining why this mechanism is supported/rejected.")
    discovery_status: str = Field(
        default="CANDIDATE_STRUCTURAL",
        description="CANDIDATE_STRUCTURAL | VALIDATED | INSUFFICIENT_EVIDENCE | CONTRADICTED",
    )
    validation_dimensions: dict[str, float] = Field(default_factory=dict)
    score_explanation: list[str] = Field(default_factory=list)
    missing_critical_evidence: list[str] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    # Phase 4B: path-level directional evidence fields
    directional_polarity: str = Field(
        default="UNKNOWN",
        description="Phase 4B net path polarity: POSITIVE | NEGATIVE | UNKNOWN",
    )
    causal_grounding_level: str = Field(
        default="NONE",
        description="Phase 4B causal grounding of best-grounded edge: DIRECT | CURATED | STRUCTURAL | NONE",
    )
    grounded_edge_count: int = Field(
        default=0,
        ge=0,
        description="Phase 4B number of edges with curated/direct directional evidence.",
    )
    therapeutic_direction: str = Field(
        default="UNKNOWN",
        description=(
            "Phase 4B placeholder: always UNKNOWN. "
            "Therapeutic direction (SUPPORTS/CONTRADICTS) requires Phase 4C disease-state evidence."
        ),
    )
    # Phase 5.1: Mechanistic quality audit components
    structural_edge_count: int = Field(
        default=0,
        ge=0,
        description="Phase 5.1 number of structural (non-causal) edges along the path.",
    )
    independent_evidence_groups: int = Field(
        default=0,
        ge=0,
        description="Phase 5.1 number of independent literature source groups supporting this candidate.",
    )
    # Phase 5: Directional Mechanism Assessment Layer
    directional_mechanism_status: str = Field(
        default="UNKNOWN",
        description="Phase 5 directional mechanism status: CONSISTENT | CONTRADICTORY | PARTIAL | UNKNOWN",
    )
    directional_consistency: bool | None = Field(
        default=None,
        description="Phase 5 directional consistency with therapeutic hypothesis: True | False | None",
    )
    directional_contradiction_count: int = Field(
        default=0,
        ge=0,
        description="Phase 5 number of explicit signed contradictions along the mechanistic path.",
    )
    directional_assessment: dict[str, Any] | None = Field(
        default=None,
        description="Phase 5 detailed DirectionalMechanismAssessment serialized dictionary.",
    )
    # Phase 5.11: Mechanistic Evidence Quality Components
    quality_tier: str = Field(
        default="STRUCTURAL",
        description="Phase 5.11 internal quality tier: STRUCTURAL | CURATED | CAUSAL | LITERATURE_GROUNDED | INDEPENDENTLY_VALIDATED",
    )
    quality_components: dict[str, Any] = Field(
        default_factory=dict,
        description="Phase 5.11 detailed evidence quality components matrix.",
    )
    # Phase 5.12: Reaction Evidence Aggregation Components
    reaction_evidence_count: int = Field(
        default=0,
        ge=0,
        description="Total raw reaction records contributing to candidate hops.",
    )
    unique_reaction_count: int = Field(
        default=0,
        ge=0,
        description="Unique canonical reactions contributing to candidate hops.",
    )
    reaction_independent_groups: int = Field(
        default=0,
        ge=0,
        description="Distinct independent study groups supporting reaction hops.",
    )
    reaction_enriched: bool = Field(
        default=False,
        description="True if candidate mechanism is backed by canonical reaction evidence.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "candidate_index": self.candidate_index,
            "name": self.name,
            "support_level": self.support_level,
            "confidence_score": self.confidence_score,
            "summary_chain": self.summary_chain,
            "hops": [
                {
                    "from_node": h.from_node,
                    "to_node": h.to_node,
                    "predicate": h.predicate,
                    "status": h.status,
                    "evidence_strength": h.evidence_strength,
                    "source_database": h.source_database,
                    "provenance_note": h.provenance_note,
                    "links": [l.to_dict() for l in h.links],
                    "canonical_from_id": h.canonical_from_id,
                    "canonical_to_id": h.canonical_to_id,
                    "directionality": h.directionality,
                    "evidence_type": h.evidence_type,
                    "supporting_claims": h.supporting_claims,
                    "contradicting_claims": h.contradicting_claims,
                    # Phase 4B fields
                    "polarity": h.polarity,
                    "causal_grounding": h.causal_grounding,
                }
                for h in self.hops
            ],
            "literature_citations": self.literature_citations,
            "rationale": self.rationale,
            "discovery_status": self.discovery_status,
            "validation_dimensions": self.validation_dimensions,
            "score_explanation": self.score_explanation,
            "missing_critical_evidence": self.missing_critical_evidence,
            "contradictions": self.contradictions,
            # Phase 4B fields
            "directional_polarity": self.directional_polarity,
            "causal_grounding_level": self.causal_grounding_level,
            "grounded_edge_count": self.grounded_edge_count,
            "therapeutic_direction": self.therapeutic_direction,
            # Phase 5.1 fields
            "structural_edge_count": self.structural_edge_count,
            "independent_evidence_groups": self.independent_evidence_groups,
            # Phase 5 fields
            "directional_mechanism_status": self.directional_mechanism_status,
            "directional_consistency": self.directional_consistency,
            "directional_contradiction_count": self.directional_contradiction_count,
            "directional_assessment": self.directional_assessment,
            # Phase 5.11 fields
            "quality_tier": self.quality_tier,
            "quality_components": self.quality_components,
            # Phase 5.12 fields
            "reaction_evidence_count": self.reaction_evidence_count,
            "unique_reaction_count": self.unique_reaction_count,
            "reaction_independent_groups": self.reaction_independent_groups,
            "reaction_enriched": self.reaction_enriched,
        }

