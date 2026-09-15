"""MultiHopReasoner — traces mechanistic paths through a typed EvidenceGraph.

REWRITE (post-audit): previously this module enumerated three fixed path
templates (DIRECT / 2-HOP / 3-HOP) via nested loops over flat
``package.targets`` / ``package.pathways`` / ``package.proteins`` lists. That
is not graph reasoning — see MECHANISTIC_PLAUSIBILITY_AUDIT.md §1.1.

This version builds an ``EvidenceGraph`` (backend/reasoning/mechanistic/
evidence_graph.py) once per call and performs real path-finding (DFS over
simple paths) from the Drug node to the Disease node. Every edge in that
graph was already validated against retrieved source data at construction
time (fail-closed: no source data → no edge), so every path returned here
is hop-by-hop valid by construction — there is no separate "is this edge
real" check needed at traversal time.

Fixes carried by this rewrite (see audit for detail):
  1.1  Real graph traversal, not template enumeration. The old "3-HOP
       Effector" template (arbitrary secondary proteins sharing pathway
       membership) is removed — pathway co-membership was never evidence of
       a regulatory relationship between two proteins.
  1.2  Drug→Target hop predicate comes from ``target.mechanism``.
  1.3  Target→Gene / Gene→Disease strength uses the real association-score
       magnitude, not binary membership + flat 0.5 penalty.
  1.4  Pathway relevance/membership compares gene symbols to gene symbols
       (UniProt accessions are mapped through the retrieved Protein records
       first), instead of silently comparing accessions to symbols.

Public interface (``MultiHopReasoner.trace_paths``,
``MultiHopReasoner.compute_mechanistic_score``, ``MechanisticPath``,
``MechanisticHop``) is unchanged, so ``reasoning_orchestrator.py`` does not
need to change how it calls this module. ``MechanisticHop`` gains additional
optional fields (``predicate``, ``source``, ``evidence_strength``, ``status``)
that the orchestrator may inspect for richer audit output.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from backend.core.domain.retrieval_package import RetrievalPackage
from backend.reasoning.mechanistic.evidence_graph import (
    EvidenceGraph,
    EvidenceGraphBuilder,
    GraphEdge,
    _MAX_HOPS,
    _HOP_DECAY,
)
from backend.reasoning.directional.path_polarity import propagate_path_polarity

logger = logging.getLogger(__name__)

# Minimum confidence to include a path in the result set (calibrated for up to 5-hop decay)
_MIN_CONFIDENCE: float = 0.0001

_PATH_TYPE_BY_HOP_COUNT: dict[int, str] = {
    1: "DIRECT",
    2: "2-HOP",
    3: "3-HOP",
    4: "4-HOP",
    5: "5-HOP",
}


from backend.core.domain.candidate_mechanism import CandidateMechanism, MechanismHop
from backend.core.value_objects.source_url_builder import EvidenceLink


@dataclass
class MechanisticHop:
    """A single node in a mechanistic path.

    Attributes:
        label:            Node type: "Drug" | "Target" | "Pathway" | "Gene" | "Disease"
        name:             Human-readable entity name.
        hop_index:        Position in the path (0 = start, n = final node).
        predicate:        Edge predicate arriving at this node, e.g. "INHIBITOR".
        source:           Data source for the incoming edge, e.g. "ChEMBL".
        evidence_strength: Evidence strength of the incoming edge [0, 1].
        status:           Always "VALID" — edges are only created when data supports them.
        links:            Clickable URL links backing this hop.
    """

    label: str
    name: str
    hop_index: int
    predicate: str | None = None
    source: str | None = None
    evidence_strength: float | None = None
    status: str = "VALID"   # every hop here is valid by construction (see module docstring)
    links: list[EvidenceLink] = field(default_factory=list)
    direction: str = "UNKNOWN"
    relationship_type: str | None = None
    # Phase 4B: typed directional fields from the incoming GraphEdge
    polarity: str = "UNKNOWN"         # MolecularPolarity.value
    causal_grounding: str = "STRUCTURAL"  # CausalGrounding.value


@dataclass
class MechanisticPath:
    """A complete multi-hop mechanistic path from Drug to Disease.

    Attributes:
        hops:       Ordered list of MechanisticHop nodes.
        hop_count:  Number of intermediate steps (= len(hops) - 2).
        confidence: Confidence score [0.0, 1.0] — product of edge strengths × decay.
        path_type:  "DIRECT" | "2-HOP" | "3-HOP" | "4-HOP" | "INDIRECT"
        description: Human-readable chain string.
    """

    hops: list[MechanisticHop] = field(default_factory=list)
    hop_count: int = 0
    confidence: float = 0.0
    path_type: str = "DIRECT"
    description: str = ""

    def to_chain(self) -> list[str]:
        """Return the path as a list of 'Label: Name' strings."""
        return [f"{h.label}: {h.name}" for h in self.hops]

    def to_dict(self) -> dict[str, Any]:
        return {
            "hops": [
                {
                    "label": h.label,
                    "name": h.name,
                    "predicate": h.predicate,
                    "source": h.source,
                    "evidence_strength": h.evidence_strength,
                    "status": h.status,
                    "links": [l.to_dict() for l in h.links],
                    "direction": h.direction,
                    "relationship_type": h.relationship_type,
                }
                for h in self.hops
            ],
            "hop_count": self.hop_count,
            "confidence": self.confidence,
            "path_type": self.path_type,
            "description": self.description,
        }



# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

def _label_for_node_type(node_label: str) -> str:
    return {
        "DRUG": "Drug",
        "TARGET": "Target",
        "REACTION": "Reaction",
        "PATHWAY": "Pathway",
        "GENE": "Gene",
        "DISEASE": "Disease",
    }.get(node_label, node_label.title())


def _describe_edge(edge: GraphEdge) -> str:
    pred = edge.predicate.replace("_", " ").lower()
    return f"{pred} ({edge.source})"


# ─────────────────────────────────────────────
# PathFinder
# ─────────────────────────────────────────────

class PathFinder:
    """Real graph traversal from Drug to Disease over an EvidenceGraph."""

    def find(
        self,
        graph: EvidenceGraph,
        drug_id: str,
        disease_id: str,
    ) -> list[MechanisticPath]:
        """Enumerate all simple paths up to _MAX_HOPS from drug_id to disease_id.

        Args:
            graph:      Populated EvidenceGraph.
            drug_id:    ID of the Drug node.
            disease_id: ID of the Disease node.

        Returns:
            Unsorted list of MechanisticPath objects (confidence filled in by PathScorer).
        """
        paths: list[MechanisticPath] = []
        for edge_chain in graph.find_simple_paths(drug_id, disease_id, max_hops=_MAX_HOPS):
            paths.append(self._to_mechanistic_path(graph, edge_chain))
        return paths

    def _to_mechanistic_path(
        self, graph: EvidenceGraph, edges: list[GraphEdge]
    ) -> MechanisticPath:
        """Convert a raw edge chain from the DFS into a MechanisticPath."""
        node_ids = [edges[0].source_id] + [e.target_id for e in edges]
        hops: list[MechanisticHop] = []

        for i, node_id in enumerate(node_ids):
            node = graph.nodes[node_id]
            edge_in = edges[i - 1] if i > 0 else None
            hops.append(MechanisticHop(
                label=_label_for_node_type(node.label),
                name=node.name,
                hop_index=i,
                predicate=edge_in.predicate if edge_in else None,
                source=edge_in.source if edge_in else None,
                evidence_strength=edge_in.evidence_strength if edge_in else None,
                status=edge_in.data_quality if edge_in else "VALID",
                links=list(edge_in.links) if edge_in and hasattr(edge_in, "links") else [],
                direction=getattr(edge_in, "direction", "UNKNOWN") if edge_in else "UNKNOWN",
                relationship_type=getattr(edge_in, "relationship_type", None) or (edge_in.predicate if edge_in else None),
                # Phase 4B: populate typed directional fields from the GraphEdge
                polarity=getattr(edge_in, "polarity", "UNKNOWN").value if edge_in and hasattr(getattr(edge_in, "polarity", None), "value") else (getattr(edge_in, "polarity", "UNKNOWN") if edge_in else "UNKNOWN"),
                causal_grounding=getattr(edge_in, "causal_grounding", "STRUCTURAL").value if edge_in and hasattr(getattr(edge_in, "causal_grounding", None), "value") else (getattr(edge_in, "causal_grounding", "STRUCTURAL") if edge_in else "STRUCTURAL"),
            ))

        # hop_count = number of intermediate nodes (not counting Drug and Disease)
        hop_count = max(0, len(node_ids) - 2)
        path_type = _PATH_TYPE_BY_HOP_COUNT.get(hop_count, "INDIRECT")

        # Human-readable description of the full chain
        parts: list[str] = []
        for i, h in enumerate(hops):
            if i == 0:
                parts.append(h.name)
            else:
                edge = edges[i - 1]
                parts.append(
                    f"→ {h.name} [{_describe_edge(edge)}]"
                )
        description = " ".join(parts)

        return MechanisticPath(
            hops=hops,
            hop_count=hop_count,
            confidence=0.0,   # filled in by PathScorer
            path_type=path_type,
            description=description,
        )


# ─────────────────────────────────────────────
# PathScorer
# ─────────────────────────────────────────────

class PathScorer:
    """Scores a MechanisticPath using the real per-edge evidence strengths."""

    def score(self, path: MechanisticPath) -> float:
        """Compute a confidence score for a path.

        Returns 0.0 immediately if ANY hop carries an UNVALIDATED status.
        An UNVALIDATED hop means there was no Open Targets/DisGeNET association
        score for the gene — missing data is not evidence and cannot support a
        mechanistic claim.

        Formula for valid paths: product of all edge evidence_strength values,
        with a per-hop decay factor applied for each additional hop beyond the first.
        """
        # Hard gate: reject any path with an UNVALIDATED hop
        for h in path.hops:
            if h.status == "UNVALIDATED":
                return 0.0

        strengths = [
            h.evidence_strength
            for h in path.hops
            if h.evidence_strength is not None
        ]
        if not strengths:
            return 0.0
        base = 1.0
        for s in strengths:
            base *= max(0.0, min(1.0, s))
        decay = _HOP_DECAY ** max(0, len(strengths) - 1)
        return round(min(1.0, base * decay), 4)


# ─────────────────────────────────────────────
# MultiHopReasoner (public interface)
# ─────────────────────────────────────────────

class MultiHopReasoner:
    """Traces and evaluates candidate biological mechanisms connecting Drug to Disease."""

    def __init__(self) -> None:
        self._graph_builder = EvidenceGraphBuilder()
        self._path_finder = PathFinder()
        self._path_scorer = PathScorer()
        logger.info("MultiHopReasoner initialized (graph-based mechanism discovery)")

    def trace_paths(self, package: RetrievalPackage) -> list[MechanisticPath]:
        """Trace all plausible mechanistic paths in the RetrievalPackage."""
        logger.info(
            "multi_hop_reasoning_start",
            extra={
                "hypothesis_id": str(package.hypothesis_id),
                "targets": len(package.targets),
                "pathways": len(package.pathways),
                "proteins": len(package.proteins),
            },
        )

        if not package.targets:
            return []

        graph, _resolver = self._graph_builder.build(package)
        drug_id = f"DRUG:{package.drug.name}"
        disease_id = f"DISEASE:{package.disease.name}"

        if drug_id not in graph.nodes or disease_id not in graph.nodes:
            return []

        raw_paths = self._path_finder.find(graph, drug_id, disease_id)

        # Score and filter
        scored: list[MechanisticPath] = []
        for path in raw_paths:
            confidence = self._path_scorer.score(path)
            if confidence < _MIN_CONFIDENCE:
                continue
            path.confidence = confidence
            scored.append(path)

        # Sort by confidence descending
        scored.sort(key=lambda p: p.confidence, reverse=True)

        # Deduplicate
        seen: set[str] = set()
        unique_paths: list[MechanisticPath] = []
        for path in scored:
            key = path.description[:120]
            if key not in seen:
                seen.add(key)
                unique_paths.append(path)

        result = unique_paths[:20]

        logger.info(
            "multi_hop_reasoning_complete",
            extra={
                "hypothesis_id": str(package.hypothesis_id),
                "graph_nodes": len(graph.nodes),
                "graph_edges": len(graph.edges),
                "paths_found": len(result),
                "max_confidence": result[0].confidence if result else 0.0,
            },
        )

        return result

    def discover_candidate_mechanisms(
        self, package: RetrievalPackage, paths: list[MechanisticPath]
    ) -> list[CandidateMechanism]:
        """Transform traced graph paths into distinct, evidence-evaluated CandidateMechanism objects."""
        if not paths:
            return []

        candidates: list[CandidateMechanism] = []
        for idx, path in enumerate(paths[:5], start=1):
            # Hop breakdown
            mechanism_hops: list[MechanismHop] = []

            # Collect GraphEdge objects for this path from path.hops
            # path.hops carries edge info via MechanisticHop attributes
            for i in range(1, len(path.hops)):
                h_prev = path.hops[i - 1]
                h_curr = path.hops[i]
                # A traversable graph edge is a discovery fact, not causal
                # validation. MechanismValidator may upgrade it later.
                status = (
                    "DATABASE_SUPPORTED"
                    if i == 1 and (h_curr.predicate or "").upper() not in ("", "MODULATES")
                    else "CANDIDATE_STRUCTURAL"
                )
                mechanism_hops.append(MechanismHop(
                    from_node=f"{h_prev.label}: {h_prev.name}",
                    to_node=f"{h_curr.label}: {h_curr.name}",
                    predicate=h_curr.predicate or "MODULATES",
                    status=status,
                    evidence_strength=h_curr.evidence_strength or 0.5,
                    source_database=h_curr.source or "Structured Data",
                    provenance_note=(
                        f"Discovered graph relationship: {h_prev.name} "
                        f"{h_curr.predicate or 'interacts with'} {h_curr.name}. "
                        "This is not causal validation."
                    ),
                    links=getattr(h_curr, "links", []),
                    # Phase 4B: populate polarity/grounding from the incoming edge
                    polarity=getattr(h_curr, "polarity", "UNKNOWN"),
                    causal_grounding=getattr(h_curr, "causal_grounding", "STRUCTURAL"),
                ))

            # Phase 4B: compute path-level polarity from per-hop GraphEdge data
            # MechanisticHop objects carry polarity/causal_grounding from the edge
            # We reconstruct a lightweight proxy for propagate_path_polarity
            from backend.core.enums.molecular_polarity import MolecularPolarity
            from backend.core.enums.causal_grounding import CausalGrounding

            class _HopEdgeProxy:
                """Minimal proxy to feed hop polarity data into propagate_path_polarity."""
                def __init__(self, hop: MechanismHop):
                    raw_p = getattr(hop, "polarity", "UNKNOWN")
                    self.polarity = MolecularPolarity(raw_p) if isinstance(raw_p, str) else raw_p
                    raw_g = getattr(hop, "causal_grounding", "STRUCTURAL")
                    try:
                        self.causal_grounding = CausalGrounding(raw_g) if isinstance(raw_g, str) else raw_g
                    except ValueError:
                        self.causal_grounding = CausalGrounding.STRUCTURAL

            hop_proxies = [_HopEdgeProxy(h) for h in mechanism_hops]
            path_pol = propagate_path_polarity(hop_proxies)

            # Classify support level
            conf = path.confidence
            has_unverified = False  # retained for backwards-compatible branch below
            if has_unverified:
                level = "UNSUPPORTED"   # not speculative — actual unverified data absence
            elif conf < 0.15:
                level = "WEAK_SPECULATIVE"
            elif conf >= 0.60:
                level = "STRONGLY_SUPPORTED"
            elif conf >= 0.25:
                level = "MODERATELY_SUPPORTED"
            else:
                level = "WEAK_SPECULATIVE"

            # The numerical graph confidence ranks discovery candidates only;
            # it must not be presented as validated mechanistic support.
            level = "WEAK_SPECULATIVE"
            target_name = path.hops[1].name if len(path.hops) > 1 else "Unknown Target"
            pathway_name = next((h.name for h in path.hops if h.label == "Pathway"), "")
            cand_name = f"Mechanism {idx}: {target_name}"
            if pathway_name:
                cand_name += f" via {pathway_name}"

            rationale = (
                f"Structural candidate traced with graph confidence {conf:.1%}. "
                "Independent validation of the biological bridge is required."
            )

            # Phase 4B: best causal grounding level across hops
            grounding_priority = ["DIRECT", "CURATED", "INFERRED", "STRUCTURAL", "NONE"]
            hop_groundings = [getattr(h, "causal_grounding", "STRUCTURAL") for h in mechanism_hops]
            best_grounding = "NONE"
            for tier in grounding_priority:
                if tier in hop_groundings:
                    best_grounding = tier
                    break

            candidates.append(CandidateMechanism(
                candidate_index=idx,
                name=cand_name,
                support_level=level,
                confidence_score=conf,
                summary_chain=path.to_chain(),
                hops=mechanism_hops,
                literature_citations=[],
                rationale=rationale,
                discovery_status="CANDIDATE_STRUCTURAL",
                # Phase 4B directional fields
                directional_polarity=path_pol.polarity.value,
                causal_grounding_level=best_grounding,
                grounded_edge_count=path_pol.grounded_edges,
                therapeutic_direction="UNKNOWN",  # Phase 4C will fill this
            ))

        return candidates

    def compute_mechanistic_score(self, paths: list[MechanisticPath]) -> float:
        """Compute a conservative Mechanistic Score from traced paths.

        NOTE: When candidates are available, prefer `compute_mechanistic_score_from_candidates()`
        which derives the score from validated candidate mechanism quality, ensuring
        MS level is always consistent with candidate support levels.

        This method is retained for backward compat and as a fallback.
        """
        if not paths:
            return 0.0

        best_path = paths[0]
        best_conf = best_path.confidence

        corroboration_bonus = 0.0
        for path in paths[1:4]:
            shared_intermediates = set(h.name for h in best_path.hops[1:-1]) & set(h.name for h in path.hops[1:-1])
            independence_weight = 0.3 if shared_intermediates else 1.0
            corroboration_bonus += (path.confidence * independence_weight) / 3.0

        score = round(min(1.0, best_conf + min(0.15, corroboration_bonus)), 4)
        return min(1.0, score)

    def compute_mechanistic_score_from_candidates(
        self,
        candidates: list["CandidateMechanism"],
    ) -> tuple[float, str]:
        """Derive MS score AND level directly from validated CandidateMechanism quality.

        This is the primary scoring method (Fix 3). Score and level come from the
        same source, so they can NEVER be logically inconsistent.

        Support level weights map the biological evidence quality to a numeric score:
          STRONGLY_SUPPORTED  -> base confidence * 1.0
          MODERATELY_SUPPORTED -> base confidence * 0.75
          WEAK_SPECULATIVE    -> base confidence * 0.40
          CONTRADICTED        -> base confidence * 0.10
          UNSUPPORTED         -> 0.0

        Corroboration from additional INDEPENDENT candidates adds up to +0.10 bonus.

        Returns:
            (score: float, level: str) — always consistent with each other.
        """
        _SUPPORT_WEIGHTS: dict[str, float] = {
            "STRONGLY_SUPPORTED": 1.0,
            "MODERATELY_SUPPORTED": 0.75,
            "WEAK_SPECULATIVE": 0.40,
            "CONTRADICTED": 0.10,
            "UNSUPPORTED": 0.0,
        }

        if not candidates:
            return 0.0, "NONE"

        # Candidate confidence is already the validator's transparent,
        # evidence-dimensional score. Do not add graph-path-count or related
        # candidate bonuses: such paths commonly share the same records and do
        # not represent independent corroboration.
        usable = [c for c in candidates if c.support_level not in ("UNSUPPORTED", "CONTRADICTED")]
        if not usable:
            return 0.0, "NONE"
        best_validated = max(usable, key=lambda c: c.confidence_score)
        score = round(best_validated.confidence_score, 4)
        if best_validated.support_level == "STRONGLY_SUPPORTED":
            return score, "HIGH"
        if best_validated.support_level == "MODERATELY_SUPPORTED":
            return score, "MEDIUM"
        return score, "LOW" if score > 0.0 else "NONE"

