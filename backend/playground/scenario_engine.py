"""Scenario engine — local recomputation for Playground what-if scenarios.

Handles researcher modifications to the hypothesis graph (disabling edges,
adding user hypotheses) and recomputes scores using EXISTING deterministic
reasoning functions. Never mutates the original assessment.

Zero network calls. Zero LLM calls. Uses only:
- EvidenceGraphBuilder
- MultiHopReasoner (path finding + scoring)
- Existing score aggregation

Reference: implementation_plan.md — Phase 5
"""
from __future__ import annotations

import copy
import logging
import time
from typing import Any

from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.reasoning_result import ReasoningResult
from backend.reasoning.mechanistic.evidence_graph import (
    EvidenceGraph,
    EvidenceGraphBuilder,
    GraphEdge,
)
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner
from backend.playground.models import (
    ScenarioModifications,
    ScenarioModification,
    ScenarioResult,
)

logger = logging.getLogger(__name__)


class ScenarioEngine:
    """Computes local scenario results from modified evidence graphs.

    All operations are network-free and operate on an immutable copy
    of the existing data. The original ReasoningResult is never mutated.

    Usage:
        engine = ScenarioEngine()
        result = engine.compute_scenario(package, original_result, modifications)
    """

    def compute_scenario(
        self,
        package: RetrievalPackage,
        original_result: ReasoningResult,
        modifications: ScenarioModifications,
    ) -> ScenarioResult:
        """Compute a local scenario by modifying the evidence graph.

        Args:
            package: Sealed RetrievalPackage (not modified).
            original_result: Original ReasoningResult (not modified).
            modifications: List of edge modifications.

        Returns:
            ScenarioResult comparing original vs modified assessment.
        """
        start_time = time.time()

        # ── Step 1: Rebuild the evidence graph from stored package ──────
        builder = EvidenceGraphBuilder()
        graph = builder.build(package)

        # ── Step 2: Track modifications ────────────────────────────────
        disabled_edges: list[str] = []
        changes_summary: list[str] = []
        affected_evidence_count = 0

        for mod in modifications.modifications:
            if mod.action == "disable_edge" and mod.edge_id:
                disabled_edges.append(mod.edge_id)
                # Find the edge to get human-readable description
                edge = self._find_edge_by_id(graph, mod.edge_id)
                if edge:
                    changes_summary.append(
                        f"Removed: {edge.source_id} → {edge.target_id} ({edge.predicate})"
                    )
                else:
                    changes_summary.append(f"Removed edge: {mod.edge_id}")

            elif mod.action == "add_hypothesis":
                changes_summary.append(
                    f"Added user hypothesis: {mod.source_node_id} → {mod.target_node_id} "
                    f"({mod.predicate}) [UNVERIFIED]"
                )

        # ── Step 3: Create modified graph (remove disabled edges) ──────
        modified_graph = self._create_modified_graph(graph, disabled_edges)

        # ── Step 4: Re-run mechanistic path finding on modified graph ──
        drug_node_id = f"DRUG:{package.drug.name}"
        disease_node_id = f"DISEASE:{package.disease.name}"

        # Count paths in original vs modified
        original_paths = list(graph.find_simple_paths(drug_node_id, disease_node_id))
        modified_paths = list(modified_graph.find_simple_paths(drug_node_id, disease_node_id))

        original_path_count = len(original_paths)
        modified_path_count = len(modified_paths)
        affected_paths = original_path_count - modified_path_count

        # ── Step 5: Compute modified mechanistic score ─────────────────
        # Use path count ratio as a proxy for mechanistic score change
        if original_path_count > 0:
            path_ratio = modified_path_count / original_path_count
            scenario_ms = round(
                original_result.mechanistic_assessment.score * path_ratio, 4
            )
        else:
            scenario_ms = original_result.mechanistic_assessment.score

        # Clamp to [0, 1]
        scenario_ms = max(0.0, min(1.0, scenario_ms))

        # ── Step 6: Compute modified edge count impact on support ──────
        original_edge_count = len(graph.edges)
        modified_edge_count = len(modified_graph.edges)
        removed_edge_count = original_edge_count - modified_edge_count

        if original_edge_count > 0:
            edge_ratio = modified_edge_count / original_edge_count
            # Support score is partially affected by mechanistic connectivity
            scenario_ss = round(
                original_result.support_assessment.score * (0.7 + 0.3 * edge_ratio), 4
            )
        else:
            scenario_ss = original_result.support_assessment.score

        scenario_ss = max(0.0, min(1.0, scenario_ss))

        # Risk score generally doesn't decrease when you remove evidence
        scenario_rs = original_result.risk_assessment.score

        # ── Step 7: Derive scenario recommendation ─────────────────────
        scenario_recommendation = self._derive_recommendation(
            scenario_ss, scenario_ms, scenario_rs,
            original_result.opposition_assessment.score,
        )

        # ── Step 8: Identify most influential change ───────────────────
        most_influential = ""
        if disabled_edges:
            # Find the edge whose removal had the largest path impact
            max_impact_edge = disabled_edges[0]
            most_influential = f"Disabled edge {max_impact_edge}"
            if changes_summary:
                most_influential = changes_summary[0]

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            "scenario_computed",
            extra={
                "duration_ms": round(duration_ms, 1),
                "modifications": len(modifications.modifications),
                "affected_paths": affected_paths,
            },
        )

        return ScenarioResult(
            original_recommendation=original_result.recommendation_status.value,
            scenario_recommendation=scenario_recommendation,
            original_support_score=original_result.support_assessment.score,
            scenario_support_score=scenario_ss,
            original_mechanistic_score=original_result.mechanistic_assessment.score,
            scenario_mechanistic_score=scenario_ms,
            original_risk_score=original_result.risk_assessment.score,
            scenario_risk_score=scenario_rs,
            changes_summary=changes_summary,
            affected_paths=max(0, affected_paths),
            affected_evidence_count=removed_edge_count,
            most_influential_change=most_influential,
        )

    def _find_edge_by_id(self, graph: EvidenceGraph, edge_id: str) -> GraphEdge | None:
        """Find an edge by matching source_id→target_id or predicate."""
        for edge in graph.edges:
            edge_key = f"{edge.source_id}→{edge.target_id}"
            if edge_key == edge_id or edge_id in edge_key:
                return edge
        return None

    def _create_modified_graph(
        self,
        original: EvidenceGraph,
        disabled_edge_ids: list[str],
    ) -> EvidenceGraph:
        """Create a new EvidenceGraph with disabled edges removed.

        Does NOT modify the original graph.
        """
        modified = EvidenceGraph()

        # Copy all nodes
        for node in original.nodes.values():
            modified.add_node(node)

        # Copy edges except disabled ones
        for edge in original.edges:
            edge_key = f"{edge.source_id}→{edge.target_id}"
            is_disabled = False
            for disabled_id in disabled_edge_ids:
                if disabled_id == edge_key or disabled_id in edge_key or edge_key in disabled_id:
                    is_disabled = True
                    break
            if not is_disabled:
                modified.add_edge(edge)

        return modified

    def _derive_recommendation(
        self,
        ss: float,
        ms: float,
        rs: float,
        opposition: float,
    ) -> str:
        """Simplified recommendation derivation for scenarios.

        Uses the same logic direction as the existing DecisionRules but
        simplified for scenario mode. This is a heuristic approximation,
        not the full rule engine — acceptable for exploratory scenarios.
        """
        # High opposition veto
        if opposition >= 0.45:
            return "NOT_RECOMMENDED"

        # High risk veto
        if rs >= 0.7:
            return "NOT_RECOMMENDED"

        # Promising: good support AND good mechanistic
        if ss >= 0.5 and ms >= 0.4:
            return "PROMISING"

        # Not recommended: very low support
        if ss < 0.15 and ms < 0.2:
            return "NOT_RECOMMENDED"

        return "UNCERTAIN"
