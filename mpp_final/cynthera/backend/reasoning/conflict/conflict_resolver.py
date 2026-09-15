"""AdvancedConflictResolver — weighted multi-factor conflict resolution.

Phase 2 enhancement: replaces simple directional conflict detection with
a weighted scoring system that considers:
  - Evidence quality (ERW values)
  - Study type (meta-analysis > RCT > case report)
  - Recency (date-weighted)
  - Source authority (journal tier proxy)

Produces a ConflictResolutionReport with resolution strategy and winner claim.

Reference: Phase 2 — Advanced conflict resolution
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from backend.core.domain.claim import Claim
from backend.core.domain.contradiction import Contradiction
from backend.core.enums.predicate_type import PredicateType
from backend.reasoning.conflict.evidence_weighting import compute_claim_weight

# Phase 4B: Canonical entity gating — only imported when resolver is provided
if TYPE_CHECKING:
    from backend.reasoning.normalization.biological_identifier_resolver import (
        BiologicalIdentifierResolver,
    )

logger = logging.getLogger(__name__)

# Conflict predicate pairs (A contradicts B and vice versa)
_CONFLICT_PAIRS: list[tuple[PredicateType, PredicateType]] = [
    (PredicateType.ACTIVATES, PredicateType.INHIBITS),
    (PredicateType.UPREGULATES, PredicateType.DOWNREGULATES),
    (PredicateType.CAUSES, PredicateType.PREVENTS),
    (PredicateType.BINDS, PredicateType.INHIBITS),
]


@dataclass
class ConflictResolution:
    """Resolution of a single conflict between two claims.

    Attributes:
        claim_id_a: First claim UUID.
        claim_id_b: Second claim UUID.
        subject: Shared subject entity.
        predicate_a: Predicate of claim A.
        predicate_b: Predicate of claim B.
        weight_a: Weighted score for claim A.
        weight_b: Weighted score for claim B.
        winner_claim_id: UUID of the stronger claim.
        resolution_strategy: How the conflict was resolved.
        confidence: Confidence in the resolution [0.0, 1.0].
        explanation: Human-readable explanation.
    """

    claim_id_a: str
    claim_id_b: str
    subject: str
    predicate_a: str
    predicate_b: str
    weight_a: float
    weight_b: float
    winner_claim_id: str | None
    resolution_strategy: str
    confidence: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id_a": self.claim_id_a,
            "claim_id_b": self.claim_id_b,
            "subject": self.subject,
            "predicate_a": self.predicate_a,
            "predicate_b": self.predicate_b,
            "weight_a": self.weight_a,
            "weight_b": self.weight_b,
            "winner_claim_id": self.winner_claim_id,
            "resolution_strategy": self.resolution_strategy,
            "confidence": self.confidence,
            "explanation": self.explanation,
        }


@dataclass
class ConflictResolutionReport:
    """Complete conflict resolution report for a reasoning session.

    Attributes:
        contradictions: Raw Contradiction objects (for compatibility).
        resolutions: Detailed ConflictResolution for each conflict.
        net_conflict_score: Aggregate conflict burden [0.0, 1.0].
        unresolved_count: Number of conflicts that could not be resolved.
        resolution_narrative: Human-readable summary.
    """

    contradictions: list[Contradiction] = field(default_factory=list)
    resolutions: list[ConflictResolution] = field(default_factory=list)
    net_conflict_score: float = 0.0
    unresolved_count: int = 0
    resolution_narrative: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "contradiction_count": len(self.contradictions),
            "resolutions": [r.to_dict() for r in self.resolutions],
            "net_conflict_score": self.net_conflict_score,
            "unresolved_count": self.unresolved_count,
            "resolution_narrative": self.resolution_narrative,
        }


class AdvancedConflictResolver:
    """Multi-factor weighted conflict resolution engine.

    Detects directional conflicts between claims and resolves them using
    a weighted scoring approach that prioritizes higher-quality, more recent,
    and stronger-evidence claims.

    Resolution strategy priority:
    1. ERW weight differential (> 0.3 delta → clear winner)
    2. Evidence type quality (meta-analysis beats case report)
    3. Recency (more recent claim wins ties)
    4. Unresolved (too close to call → both retained as contradictions)
    """

    # Weight differential threshold for "clear" resolution
    _CLEAR_RESOLUTION_THRESHOLD: float = 0.3

    def __init__(self) -> None:
        logger.info("AdvancedConflictResolver initialized")

    def resolve(
        self,
        claims: list[Claim],
        resolver: "BiologicalIdentifierResolver | None" = None,
    ) -> ConflictResolutionReport:
        """Detect and resolve all conflicts between claims.

        Args:
            claims:   All extracted claims from the reasoning pipeline.
            resolver: Optional BiologicalIdentifierResolver for Phase 4B canonical entity gating.
                      When provided, claims must reference canonically resolved biological entities
                      on BOTH subject AND object before they can be compared for contradiction.
                      Ungrounded claims (e.g. subject='compound', object='molecular target') are
                      silently skipped and logged as 'contradiction_skipped_ungrounded'.
                      When None (default), existing behavior is preserved unchanged.

        Returns:
            ConflictResolutionReport with raw contradictions and resolutions.
        """
        logger.info(
            "conflict_resolution_start",
            extra={"claim_count": len(claims)},
        )

        contradictions: list[Contradiction] = []
        resolutions: list[ConflictResolution] = []

        # Build index: (subject, object) → {predicate → claim}
        index: dict[str, dict[str, Claim]] = {}
        for claim in claims:
            key = f"{claim.subject.lower()}::{claim.object.lower()}"
            if key not in index:
                index[key] = {}
            index[key][claim.predicate.value] = claim

        # Detect conflicts
        for key, pred_map in index.items():
            for pred_a, pred_b in _CONFLICT_PAIRS:
                claim_a = pred_map.get(pred_a.value)
                claim_b = pred_map.get(pred_b.value)

                if claim_a is None or claim_b is None:
                    continue

                # Phase 4B: Canonical entity gating.
                # Skip contradictions where either claim's subject or object is
                # a generic ungrounded token (e.g. "compound", "molecular target").
                if resolver is not None:
                    from backend.reasoning.directional.canonical_entity_gate import claims_are_comparable
                    if not claims_are_comparable(claim_a, claim_b, resolver):
                        logger.debug(
                            "contradiction_skipped_ungrounded",
                            extra={
                                "subject_a": claim_a.subject,
                                "object_a": claim_a.object,
                                "subject_b": claim_b.subject,
                                "object_b": claim_b.object,
                                "predicate_a": pred_a.value,
                                "predicate_b": pred_b.value,
                            },
                        )
                        continue

                # Compute weighted scores
                weight_a = self._compute_claim_weight(claim_a)
                weight_b = self._compute_claim_weight(claim_b)

                # Build Contradiction (raw, for backward compat)
                contradiction_score = round(
                    (claim_a.erw.value + claim_b.erw.value) / 2 * 0.8, 4
                )
                subject_part = claim_a.subject
                contradiction = Contradiction(
                    claim_id_a=claim_a.id,
                    claim_id_b=claim_b.id,
                    conflict_type="directional",
                    contradiction_score=contradiction_score,
                    shared_subject=subject_part,
                    explanation=(
                        f"Directional conflict on '{claim_a.subject} → {claim_a.object}': "
                        f"'{pred_a.value}' vs '{pred_b.value}'."
                    ),
                )
                contradictions.append(contradiction)

                # Resolve the conflict
                resolution = self._resolve_pair(
                    claim_a=claim_a,
                    claim_b=claim_b,
                    pred_a=pred_a,
                    pred_b=pred_b,
                    weight_a=weight_a,
                    weight_b=weight_b,
                )
                resolutions.append(resolution)

        # Compute net conflict score
        net_score = self._compute_net_conflict_score(contradictions, resolutions)
        unresolved = sum(1 for r in resolutions if r.winner_claim_id is None)

        narrative = self._build_narrative(
            contradictions=contradictions,
            resolutions=resolutions,
            net_score=net_score,
            unresolved=unresolved,
        )

        report = ConflictResolutionReport(
            contradictions=contradictions,
            resolutions=resolutions,
            net_conflict_score=net_score,
            unresolved_count=unresolved,
            resolution_narrative=narrative,
        )

        logger.info(
            "conflict_resolution_complete",
            extra={
                "contradictions": len(contradictions),
                "resolved": len(resolutions) - unresolved,
                "unresolved": unresolved,
                "net_conflict_score": net_score,
            },
        )

        return report

    # ─────────────────────────────────────────────
    # Private Helpers
    # ─────────────────────────────────────────────

    def _compute_claim_weight(self, claim: Claim) -> float:
        """Compute a weighted quality score for a claim.

        Delegates to shared evidence_weighting.compute_claim_weight.
        Factors: ERW value × evidence_type_weight × recency_factor
        """
        return compute_claim_weight(claim)

    def _resolve_pair(
        self,
        claim_a: Claim,
        claim_b: Claim,
        pred_a: PredicateType,
        pred_b: PredicateType,
        weight_a: float,
        weight_b: float,
    ) -> ConflictResolution:
        """Resolve a conflict between two claims."""
        delta = abs(weight_a - weight_b)
        total = weight_a + weight_b

        if total == 0:
            return ConflictResolution(
                claim_id_a=str(claim_a.id),
                claim_id_b=str(claim_b.id),
                subject=claim_a.subject,
                predicate_a=pred_a.value,
                predicate_b=pred_b.value,
                weight_a=weight_a,
                weight_b=weight_b,
                winner_claim_id=None,
                resolution_strategy="UNRESOLVABLE",
                confidence=0.0,
                explanation="Both claims have zero weight — cannot resolve.",
            )

        confidence = round(delta / total, 4) if total > 0 else 0.0

        if delta >= self._CLEAR_RESOLUTION_THRESHOLD:
            # Clear winner
            winner = claim_a if weight_a > weight_b else claim_b
            winner_pred = pred_a if weight_a > weight_b else pred_b
            loser_pred = pred_b if weight_a > weight_b else pred_a
            strategy = "WEIGHT_DIFFERENTIAL"
            explanation = (
                f"Claim '{winner_pred.value}' resolved over '{loser_pred.value}' "
                f"(weight delta: {delta:.3f}, confidence: {confidence:.3f}). "
                f"Winner has higher ERW × evidence quality × recency score."
            )
            return ConflictResolution(
                claim_id_a=str(claim_a.id),
                claim_id_b=str(claim_b.id),
                subject=claim_a.subject,
                predicate_a=pred_a.value,
                predicate_b=pred_b.value,
                weight_a=weight_a,
                weight_b=weight_b,
                winner_claim_id=str(winner.id),
                resolution_strategy=strategy,
                confidence=confidence,
                explanation=explanation,
            )

        # Insufficient differential — unresolved
        return ConflictResolution(
            claim_id_a=str(claim_a.id),
            claim_id_b=str(claim_b.id),
            subject=claim_a.subject,
            predicate_a=pred_a.value,
            predicate_b=pred_b.value,
            weight_a=weight_a,
            weight_b=weight_b,
            winner_claim_id=None,
            resolution_strategy="UNRESOLVED",
            confidence=confidence,
            explanation=(
                f"Insufficient weight differential ({delta:.3f}) to resolve "
                f"'{pred_a.value}' vs '{pred_b.value}'. Both retained as contradictions."
            ),
        )

    def _compute_net_conflict_score(
        self,
        contradictions: list[Contradiction],
        resolutions: list[ConflictResolution],
    ) -> float:
        """Compute net conflict burden score [0.0, 1.0]."""
        if not contradictions:
            return 0.0

        import math

        # Sum contradiction scores weighted by resolution confidence
        net = 0.0
        for con, res in zip(contradictions, resolutions):
            # Resolved conflicts are penalized less
            penalty_factor = 0.4 if res.winner_claim_id else 1.0
            net += con.contradiction_score * penalty_factor

        k = 0.4
        score = 1.0 - math.exp(-k * net)
        return round(min(1.0, score), 4)

    def _build_narrative(
        self,
        contradictions: list[Contradiction],
        resolutions: list[ConflictResolution],
        net_score: float,
        unresolved: int,
    ) -> str:
        """Build a human-readable conflict resolution summary."""
        if not contradictions:
            return "No contradictions detected in the claim set."

        resolved_count = len(resolutions) - unresolved
        parts = [
            f"{len(contradictions)} conflict(s) detected. "
            f"{resolved_count} resolved, {unresolved} unresolved. "
            f"Net conflict score: {net_score:.3f}."
        ]

        if net_score >= 0.6:
            parts.append(
                "⚠️ High conflict burden — substantial contradictory evidence exists. "
                "Recommendation confidence is reduced."
            )
        elif net_score >= 0.3:
            parts.append(
                "Moderate conflicting evidence. Resolved claims provide directional guidance."
            )
        else:
            parts.append("Low conflict burden — evidence is largely consistent.")

        return " ".join(parts)
