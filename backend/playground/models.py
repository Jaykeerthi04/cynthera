"""Playground view models — presentation DTOs for the interactive Playground.

These are NOT new domain entities. They are structured JSON-serializable
views over existing CYNTHERA domain objects (RetrievalPackage, ReasoningResult,
EvidenceGraph).

Post-audit revision: removed PlaygroundClaim (claim content not stored),
simplified ScenarioResult (only MS honestly recomputable), removed
InvestigationState complexity (deferred post-MVP).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Graph view models
# ─────────────────────────────────────────────

class PlaygroundNode(BaseModel):
    """A node in the Playground graph view."""

    id: str = Field(..., description="Unique node identifier (e.g., 'DRUG:Sildenafil').")
    label: str = Field(..., description="Node type: DRUG | TARGET | GENE | PATHWAY | DISEASE.")
    name: str = Field(..., description="Human-readable node name.")
    meta: dict[str, Any] = Field(default_factory=dict, description="Node metadata.")
    evidence_count: int = Field(default=0, description="Evidence records linked to this node.")
    links: list[dict[str, str]] = Field(default_factory=list, description="Clickable source URLs.")


class PlaygroundEdge(BaseModel):
    """An edge in the Playground graph view."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique edge identifier.")
    source_id: str = Field(..., description="Source node ID.")
    target_id: str = Field(..., description="Target node ID.")
    predicate: str = Field(..., description="Relationship predicate.")
    direction: str = Field(default="structural", description="supporting | opposing | structural.")
    evidence_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    source_database: str = Field(default="")
    provenance: str = Field(default="")
    data_quality: str = Field(default="EVIDENCE_BACKED")
    links: list[dict[str, str]] = Field(default_factory=list)
    is_disabled: bool = Field(default=False)

    # "Why is this relationship here?" data
    path_count: int = Field(default=0, description="Number of mechanistic paths using this edge.")
    evidence_count: int = Field(default=0, description="Number of evidence records for this relationship.")
    hop_claims: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Claims from candidate_mechanisms hops referencing this edge.",
    )


class PlaygroundEvidence(BaseModel):
    """Evidence record for detail panels."""

    id: str = Field(...)
    evidence_type: str = Field(...)
    erw: float = Field(default=0.5)
    citation_key: str = Field(default="")
    title: str | None = Field(None)
    abstract: str | None = Field(None)
    source_name: str = Field(default="")
    source_url: str | None = Field(None)
    retrieved_at: str | None = Field(None)
    links: list[dict[str, str]] = Field(default_factory=list)


class PlaygroundClinicalTrial(BaseModel):
    """Clinical trial record."""

    id: str = Field(...)
    nct_id: str = Field(...)
    title: str = Field(...)
    phase: str = Field(...)
    status: str = Field(...)
    primary_outcome: str | None = Field(None)
    enrollment: int | None = Field(None)
    url: str | None = Field(None)


class PlaygroundContradiction(BaseModel):
    """Contradiction for the contradiction panel."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim_a_id: str = Field(default="")
    claim_b_id: str = Field(default="")
    conflict_type: str = Field(default="directional")
    contradiction_score: float = Field(default=0.5, ge=0.0, le=1.0)
    shared_subject: str = Field(default="")
    explanation: str = Field(default="")


# ─────────────────────────────────────────────
# Evidence landscape
# ─────────────────────────────────────────────

class EvidenceLandscape(BaseModel):
    """Compact evidence summary for the status panel."""

    supporting_count: int = Field(default=0)
    opposing_count: int = Field(default=0)
    uncertain_count: int = Field(default=0)
    mechanistic_count: int = Field(default=0)
    literature_count: int = Field(default=0)
    clinical_count: int = Field(default=0)
    support_score: float = Field(default=0.0)
    mechanistic_score: float = Field(default=0.0)
    risk_score: float = Field(default=0.0)
    opposition_score: float = Field(default=0.0)
    support_level: str = Field(default="NONE")
    mechanistic_level: str = Field(default="NONE")
    risk_level: str = Field(default="NONE")
    opposition_level: str = Field(default="NONE")
    recommendation_status: str = Field(default="UNCERTAIN")
    recommendation_reasons: list[str] = Field(default_factory=list)


class EvidenceGap(BaseModel):
    """An identified evidence gap. Explicitly labeled as UI heuristic."""

    category: str = Field(...)
    status: str = Field(..., description="FOUND | MISSING | CONFLICTED | LIMITED.")
    label: str = Field(...)
    is_heuristic: bool = Field(default=True)


# ─────────────────────────────────────────────
# Composite graph data
# ─────────────────────────────────────────────

class PlaygroundGraphData(BaseModel):
    """Complete data package for the Playground.

    Primary response model for GET /api/v1/playground/{hypothesis_id}.
    """

    hypothesis_id: str = Field(...)
    drug_name: str = Field(...)
    disease_name: str = Field(...)

    nodes: list[PlaygroundNode] = Field(default_factory=list)
    edges: list[PlaygroundEdge] = Field(default_factory=list)
    evidence: list[PlaygroundEvidence] = Field(default_factory=list)
    clinical_trials: list[PlaygroundClinicalTrial] = Field(default_factory=list)
    contradictions: list[PlaygroundContradiction] = Field(default_factory=list)
    landscape: EvidenceLandscape = Field(default_factory=EvidenceLandscape)
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)

    # From ReasoningResult
    candidate_mechanisms: list[dict[str, Any]] = Field(default_factory=list)
    claim_citations: dict[str, list[str]] = Field(default_factory=dict)

    # Metadata
    retrieval_confidence: str = Field(default="MEDIUM")
    sources_queried: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)
    sealed_at: str | None = Field(None)
    data_source_failures: list[str] = Field(default_factory=list)
    claim_extraction_method: str = Field(default="unknown")


# ─────────────────────────────────────────────
# Scenario models (MS-only recomputation)
# ─────────────────────────────────────────────

class ScenarioModification(BaseModel):
    """A single edge modification in a scenario."""

    action: str = Field(..., description="disable_edge | enable_edge.")
    edge_id: str = Field(..., description="Edge key: source_id|target_id.")
    note: str | None = Field(None)


class ScenarioModifications(BaseModel):
    """Collection of modifications defining a scenario."""

    modifications: list[ScenarioModification] = Field(default_factory=list)


class ScenarioResult(BaseModel):
    """Result of a local scenario recomputation.

    ONLY Mechanistic Score is recomputed. Support Score, Risk Score,
    and Opposition Score are kept from the original result because
    they depend on LLM-extracted claims that cannot be recomputed
    locally.

    The original assessment is never mutated.
    """

    # Original scores (all four)
    original_recommendation: str = Field(...)
    original_support_score: float = Field(...)
    original_mechanistic_score: float = Field(...)
    original_risk_score: float = Field(...)
    original_opposition_score: float = Field(...)

    # Scenario scores
    scenario_recommendation: str = Field(...)
    scenario_mechanistic_score: float = Field(...)

    # What changed
    original_path_count: int = Field(default=0)
    scenario_path_count: int = Field(default=0)
    affected_paths: int = Field(default=0)
    disabled_edge_count: int = Field(default=0)
    changes_summary: list[str] = Field(default_factory=list)

    # Honesty labels
    scores_recomputed: list[str] = Field(
        default_factory=lambda: ["mechanistic_score"],
        description="Which scores were actually recomputed.",
    )
    scores_kept_original: list[str] = Field(
        default_factory=lambda: ["support_score", "risk_score", "opposition_score"],
        description="Which scores are kept from the original (cannot be locally recomputed).",
    )
    disclaimer: str = Field(
        default=(
            "Only Mechanistic Score was recomputed from the modified graph. "
            "Support, Risk, and Opposition scores require full re-evaluation "
            "(including LLM claim extraction) and are kept from the original assessment. "
            "This is an exploratory scenario, not a scientific conclusion."
        ),
    )


# ─────────────────────────────────────────────
# Researcher notes (MVP-only persistence)
# ─────────────────────────────────────────────

class ResearcherNote(BaseModel):
    """A researcher annotation. NOT machine-generated evidence."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hypothesis_id: str = Field(...)
    target_type: str = Field(..., description="hypothesis | node | edge | evidence.")
    target_id: str | None = Field(None)
    text: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
