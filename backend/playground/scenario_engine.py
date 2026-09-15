"""Scenario engine — local recomputation for Playground what-if scenarios.

Handles researcher modifications to the hypothesis graph (disabling edges)
and recomputes Mechanistic Score using deterministic path finding.
Support Score, Risk Score, and Opposition Score are kept from the original
evaluation with explicit 'KEPT_ORIGINAL' labeling.

Never mutates the original assessment. Zero network calls. Zero LLM calls.

Reference: implementation_plan.md (v2) — Honest scenario recomputation
"""
from __future__ import annotations

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
from backend.reasoning.orchestrator.decision_rules import apply_decision_rules
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
        built = builder.build(package)
        graph = built[0] if isinstance(built, tuple) else built

        # ── Step 2: Track modifications ────────────────────────────────
        disabled_edges: list[str] = []
        changes_summary: list[str] = []

        for mod in modifications.modifications:
            if mod.action == "disable_edge" and mod.edge_id:
                disabled_edges.append(mod.edge_id)
                edge = self._find_edge_by_id(graph, mod.edge_id)
                if edge:
                    changes_summary.append(
                        f"Disabled relationship: {edge.source_id} ➔ {edge.predicate} ➔ {edge.target_id}"
                    )
                else:
                    changes_summary.append(f"Disabled edge: {mod.edge_id}")

        # ── Step 3: Create modified graph (remove disabled edges) ──────
        modified_graph = self._create_modified_graph(graph, disabled_edges)

        # ── Step 4: Re-run mechanistic path finding on modified graph ──
        drug_node_id = f"DRUG:{package.drug.name}"
        disease_node_id = f"DISEASE:{package.disease.name}"

        original_paths = list(graph.find_simple_paths(drug_node_id, disease_node_id))
        modified_paths = list(modified_graph.find_simple_paths(drug_node_id, disease_node_id))

        original_path_count = len(original_paths)
        modified_path_count = len(modified_paths)
        affected_paths = max(0, original_path_count - modified_path_count)

        # ── Step 5: Honestly recompute mechanistic score ───────────────
        if original_path_count > 0:
            path_ratio = modified_path_count / original_path_count
            scenario_ms = round(
                original_result.mechanistic_assessment.score * path_ratio, 4
            )
        else:
            scenario_ms = 0.0

        scenario_ms = max(0.0, min(1.0, scenario_ms))

        # ── Step 6: SS, RS, Opposition kept from original ──────────────
        # No fake approximations. Support and Risk depend on LLM-extracted claims.
        orig_ss = original_result.support_assessment.score
        orig_rs = original_result.risk_assessment.score
        orig_opp = (
            getattr(original_result.opposition_assessment, "score", 0.0)
            if original_result.opposition_assessment
            else 0.0
        )

        # ── Step 7: Derive scenario recommendation via DecisionRules ───
        try:
            decision = apply_decision_rules(
                support=original_result.support_assessment,
                mechanistic=original_result.mechanistic_assessment,
                risk=original_result.risk_assessment,
                opposition=original_result.opposition_assessment,
                contradictions=original_result.contradictions,
                package=package,
                mechanistic_score=scenario_ms,
                pathway_count=modified_path_count,
            )
            scenario_recommendation = decision.status.value
        except Exception as exc:
            logger.warning(
                "decision_rules_scenario_error",
                extra={"error": str(exc)},
                exc_info=True,
            )
            if orig_opp >= 0.45 or orig_rs >= 0.7:
                scenario_recommendation = "NOT_RECOMMENDED"
            elif orig_ss >= 0.4 and scenario_ms >= 0.4 and orig_rs <= 0.39:
                scenario_recommendation = "PROMISING"
            else:
                scenario_recommendation = "UNCERTAIN"

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            "scenario_computed",
            extra={
                "duration_ms": round(duration_ms, 1),
                "disabled_edges": len(disabled_edges),
                "affected_paths": affected_paths,
                "original_ms": original_result.mechanistic_assessment.score,
                "scenario_ms": scenario_ms,
                "scenario_recommendation": scenario_recommendation,
            },
        )

        return ScenarioResult(
            original_recommendation=original_result.recommendation_status.value,
            original_support_score=orig_ss,
            original_mechanistic_score=original_result.mechanistic_assessment.score,
            original_risk_score=orig_rs,
            original_opposition_score=orig_opp,
            scenario_recommendation=scenario_recommendation,
            scenario_mechanistic_score=scenario_ms,
            original_path_count=original_path_count,
            scenario_path_count=modified_path_count,
            affected_paths=affected_paths,
            disabled_edge_count=len(disabled_edges),
            changes_summary=changes_summary,
            scores_recomputed=["mechanistic_score"],
            scores_kept_original=["support_score", "risk_score", "opposition_score"],
            disclaimer=(
                "Only Mechanistic Score was recomputed from the modified graph. "
                "Support, Risk, and Opposition scores require full re-evaluation "
                "(including LLM claim extraction) and are kept from the original assessment. "
                "This is an exploratory scenario, not a scientific conclusion."
            ),
        )

    def _find_edge_by_id(self, graph: EvidenceGraph, edge_id: str) -> GraphEdge | None:
        """Find an edge matching an edge key."""
        clean_id = edge_id.replace("EDGE:", "")
        for edge in graph.edges:
            candidates = [
                f"{edge.source_id}->{edge.target_id}",
                f"{edge.source_id}→{edge.target_id}",
                f"{edge.source_id}|{edge.target_id}",
                f"{edge.source_id}->{edge.target_id}:{edge.predicate}",
            ]
            if any(c in clean_id or clean_id in c for c in candidates):
                return edge
        return None

    def _create_modified_graph(
        self,
        original: EvidenceGraph,
        disabled_edge_ids: list[str],
    ) -> EvidenceGraph:
        """Create a new EvidenceGraph with disabled edges removed."""
        modified = EvidenceGraph()

        # Copy all nodes
        for node in original.nodes.values():
            modified.add_node(node)

        # Copy edges except disabled ones
        for edge in original.edges:
            is_disabled = False
            for dis in disabled_edge_ids:
                clean = dis.replace("EDGE:", "")
                candidates = [
                    f"{edge.source_id}->{edge.target_id}",
                    f"{edge.source_id}→{edge.target_id}",
                    f"{edge.source_id}|{edge.target_id}",
                    f"{edge.source_id}->{edge.target_id}:{edge.predicate}",
                ]
                if any(c == clean or c in clean or clean in c for c in candidates):
                    is_disabled = True
                    break
            if not is_disabled:
                modified.add_edge(edge)

        return modified
