"""Safe path-level molecular polarity propagation over GraphEdge chains.

Reference: Phase 4B — Directional Evidence Infrastructure

This module computes the net molecular polarity of a multi-hop graph path,
considering ONLY edges that carry explicit curated directional evidence.

CRITICAL design constraints:
    1. Unknown edge ≠ negative edge. Unknown edge ≠ positive edge.
    2. STRUCTURAL edges (CATALYST, INPUT, OUTPUT, PARTICIPANT, ...) do NOT
       contribute a sign to path polarity computation.
    3. Only edges with causal_grounding in {DIRECT, CURATED} and
       polarity != UNKNOWN may contribute to path polarity.
    4. If no qualifying edges exist, path polarity is UNKNOWN.
    5. Phase 4B does NOT compute therapeutic_direction — that is Phase 4C.

This module cannot and does not produce a SUPPORTS/CONTRADICTS judgment.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.enums.causal_grounding import CausalGrounding

# Grounding tiers that may contribute a signed polarity to path computation.
_CAUSAL_GROUNDINGS: frozenset[CausalGrounding] = frozenset({
    CausalGrounding.DIRECT,
    CausalGrounding.CURATED,
})


@dataclass
class PathPolarity:
    """Polarity assessment for a single multi-hop mechanistic path.

    Attributes:
        polarity:        Net path polarity derived from qualifying edges.
                         UNKNOWN if no qualifying directional edges were found.
        grounded_edges:  Number of edges with explicit curated/direct polarity.
        unknown_edges:   Number of edges with UNKNOWN or STRUCTURAL polarity.
        has_conflict:    True if qualifying edges carry conflicting signs
                         (some POSITIVE, some NEGATIVE) — indicates ambiguous path.
    """
    polarity: MolecularPolarity
    grounded_edges: int
    unknown_edges: int
    has_conflict: bool


def propagate_path_polarity(edges: list) -> PathPolarity:
    """Compute path-level molecular polarity from a sequence of GraphEdge objects.

    Only edges satisfying BOTH:
        edge.causal_grounding in {DIRECT, CURATED}
        edge.polarity != UNKNOWN
    contribute to the polarity product.

    All other edges (STRUCTURAL, NONE grounding, or UNKNOWN polarity) are counted
    as unknown_edges but do NOT contribute a sign.

    If no qualifying edges exist: PathPolarity(UNKNOWN, 0, total, False).
    If qualifying edges all agree: PathPolarity(POSITIVE|NEGATIVE, count, ..., False).
    If qualifying edges conflict:  PathPolarity(UNKNOWN, count, ..., True).

    Args:
        edges: List of GraphEdge objects (must have .polarity: MolecularPolarity
               and .causal_grounding: CausalGrounding attributes).

    Returns:
        PathPolarity summarizing the directional quality of the path.
    """
    total_edges = len(edges)
    grounded_edges: list[MolecularPolarity] = []
    unknown_count = 0

    for edge in edges:
        # Read polarity — may be MolecularPolarity enum or string
        raw_polarity = getattr(edge, "polarity", MolecularPolarity.UNKNOWN)
        if isinstance(raw_polarity, str):
            try:
                edge_polarity = MolecularPolarity(raw_polarity)
            except ValueError:
                edge_polarity = MolecularPolarity.UNKNOWN
        else:
            edge_polarity = raw_polarity

        # Read causal_grounding — may be CausalGrounding enum or string
        raw_grounding = getattr(edge, "causal_grounding", CausalGrounding.NONE)
        if isinstance(raw_grounding, str):
            try:
                edge_grounding = CausalGrounding(raw_grounding)
            except ValueError:
                edge_grounding = CausalGrounding.NONE
        else:
            edge_grounding = raw_grounding

        # Only count edge as grounded if grounding tier is causal AND polarity is known
        if edge_grounding in _CAUSAL_GROUNDINGS and edge_polarity != MolecularPolarity.UNKNOWN:
            grounded_edges.append(edge_polarity)
        else:
            unknown_count += 1

    # No qualifying edges → UNKNOWN path polarity
    if not grounded_edges:
        return PathPolarity(
            polarity=MolecularPolarity.UNKNOWN,
            grounded_edges=0,
            unknown_edges=total_edges,
            has_conflict=False,
        )

    positives = grounded_edges.count(MolecularPolarity.POSITIVE)
    negatives = grounded_edges.count(MolecularPolarity.NEGATIVE)

    # Conflicting signs → UNKNOWN (ambiguous, not resolvable in Phase 4B)
    if positives > 0 and negatives > 0:
        return PathPolarity(
            polarity=MolecularPolarity.UNKNOWN,
            grounded_edges=len(grounded_edges),
            unknown_edges=unknown_count,
            has_conflict=True,
        )

    # Unanimous sign
    net = MolecularPolarity.POSITIVE if positives > 0 else MolecularPolarity.NEGATIVE
    return PathPolarity(
        polarity=net,
        grounded_edges=len(grounded_edges),
        unknown_edges=unknown_count,
        has_conflict=False,
    )
