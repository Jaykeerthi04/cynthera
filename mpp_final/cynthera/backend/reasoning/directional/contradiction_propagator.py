"""ContradictionPropagator Engine (Phase 5.14).

Propagates directional conflicts and epistemic uncertainty upward through the reasoning pipeline:
evidence -> target -> mechanism -> drug -> final recommendation.

Enforces:
1. Evidence-aware contradiction quantification (not raw record counts).
2. Strong-conflict safety rule: strong grounded evidence on both sides forces UNCERTAIN.
3. Uncertainty propagation: UNKNOWN and PARTIAL propagate without becoming negative evidence.
4. Transparent explanations tracing biological targets and evidence citations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from backend.core.domain.contradiction_state import ContradictionLevel, ContradictionState
from backend.core.domain.multitarget_synthesis import MultiTargetSynthesis
from backend.core.domain.target_evidence_summary import TargetEvidenceSummary


@dataclass(frozen=True)
class ContradictionConfig:
    """Configurable thresholds for contradiction quantification.

    NOTE: Initial heuristic thresholds, not empirically calibrated against test data.
    """
    minor_balance_threshold: float = 0.75     # |supp - opp| / total >= 0.75 -> MINOR
    moderate_balance_threshold: float = 0.40  # |supp - opp| / total >= 0.40 -> MODERATE (else STRONG)
    strong_min_weight: float = 0.50           # Minimum weight on both sides to trigger strong_conflict


DEFAULT_CONTRADICTION_CONFIG = ContradictionConfig()


class ContradictionPropagator:
    """Quantifies contradiction and propagates uncertainty."""

    def __init__(self, config: ContradictionConfig | None = None) -> None:
        self.config = config or DEFAULT_CONTRADICTION_CONFIG

    def compute_contradiction_state(
        self,
        supporting_weight: float,
        opposing_weight: float,
        unresolved_weight: float = 0.0,
        supporting_groups: int = 0,
        opposing_groups: int = 0,
        affected_targets: Sequence[str] | None = None,
        target_details: Sequence[TargetEvidenceSummary] | None = None,
    ) -> ContradictionState:
        """Compute categorical contradiction level and conflict state.

        Args:
            supporting_weight: Cumulative grounded weight supporting hypothesis.
            opposing_weight: Cumulative grounded weight opposing hypothesis.
            unresolved_weight: Weight of uncharacterized/ambiguous evidence.
            supporting_groups: Independent supporting groups count.
            opposing_groups: Independent opposing groups count.
            affected_targets: Identifiers of discordant targets.
            target_details: Optional TargetEvidenceSummary list for enriched explanation.

        Returns:
            ContradictionState domain model.
        """
        targets = list(affected_targets or [])
        total_directional = supporting_weight + opposing_weight

        # If zero directional evidence on either side, no contradiction exists
        if supporting_weight <= 1e-4 or opposing_weight <= 1e-4 or total_directional <= 1e-4:
            has_conflict = False
            strong_conflict = False
            level = ContradictionLevel.NONE
            if supporting_weight > 0.0:
                explanation = f"Unilateral directional support (weight={supporting_weight:.2f}, {supporting_groups} groups). No conflict."
            elif opposing_weight > 0.0:
                explanation = f"Unilateral directional opposition (weight={opposing_weight:.2f}, {opposing_groups} groups). No conflict."
            else:
                explanation = f"Directional evidence is uncharacterized or insufficient (unresolved={unresolved_weight:.2f}). No conflict."
        else:
            has_conflict = True
            balance = abs(supporting_weight - opposing_weight) / total_directional

            # Strong conflict requires substantial grounded evidence on both sides
            strong_conflict = (
                supporting_weight >= self.config.strong_min_weight
                and opposing_weight >= self.config.strong_min_weight
            ) or (abs(supporting_weight - opposing_weight) < 1e-4 and supporting_weight >= 0.20)

            if balance >= self.config.minor_balance_threshold:
                level = ContradictionLevel.MINOR
                dominant = "SUPPORT" if supporting_weight > opposing_weight else "OPPOSITION"
                explanation = (
                    f"MINOR CONFLICT: Dominant {dominant} direction (supp={supporting_weight:.2f} vs opp={opposing_weight:.2f}). "
                    f"Affected target(s): {', '.join(targets)}."
                )
            elif balance >= self.config.moderate_balance_threshold:
                level = ContradictionLevel.MODERATE
                explanation = (
                    f"MODERATE CONFLICT: Noticeable discordance across evidence (supp={supporting_weight:.2f}, opp={opposing_weight:.2f}). "
                    f"Affected target(s): {', '.join(targets)}."
                )
            else:
                level = ContradictionLevel.STRONG
                explanation = (
                    f"STRONG CONFLICT: Substantial evidence supporting opposing directions "
                    f"(supp={supporting_weight:.2f} [{supporting_groups} groups], opp={opposing_weight:.2f} [{opposing_groups} groups]). "
                    f"Affected target(s): {', '.join(targets)}."
                )

        if unresolved_weight > 0.0:
            explanation += f" Epistemic uncertainty present (unresolved weight: {unresolved_weight:.2f})."

        return ContradictionState(
            level=level,
            supporting_weight=supporting_weight,
            opposing_weight=opposing_weight,
            unresolved_weight=unresolved_weight,
            supporting_groups=supporting_groups,
            opposing_groups=opposing_groups,
            affected_targets=targets,
            has_conflict=has_conflict,
            strong_conflict=strong_conflict,
            explanation=explanation,
        )

    def propagate_from_multitarget(
        self,
        synthesis: MultiTargetSynthesis,
    ) -> ContradictionState:
        """Propagate contradiction upward from a MultiTargetSynthesis object."""
        affected = list(set(synthesis.supporting_targets) & set(synthesis.opposing_targets))
        if not affected and synthesis.conflict_detected:
            affected = synthesis.supporting_targets + synthesis.opposing_targets

        supp_groups = sum(t.supporting_evidence_groups for t in synthesis.target_summaries)
        opp_groups = sum(t.opposing_evidence_groups for t in synthesis.target_summaries)

        return self.compute_contradiction_state(
            supporting_weight=synthesis.supporting_weight,
            opposing_weight=synthesis.opposing_weight,
            unresolved_weight=synthesis.unresolved_weight,
            supporting_groups=supp_groups,
            opposing_groups=opp_groups,
            affected_targets=affected,
            target_details=synthesis.target_summaries,
        )

    def apply_strong_conflict_guard(
        self,
        tentative_recommendation: str,
        contradiction_state: ContradictionState,
    ) -> tuple[str, str | None]:
        """Enforce the Strong-Conflict Safety Property.

        If strong evidence exists on both sides, the recommendation must NOT produce
        PROMISING or NOT_RECOMMENDED solely due to a slight weight disparity.
        It must produce UNCERTAIN.
        """
        if contradiction_state.strong_conflict and tentative_recommendation in ("PROMISING", "NOT_RECOMMENDED"):
            override_reason = (
                f"STRONG CONFLICT SAFETY OVERRIDE: Both supporting (w={contradiction_state.supporting_weight:.2f}) "
                f"and opposing (w={contradiction_state.opposing_weight:.2f}) directions possess substantial grounded evidence. "
                "Recommendation capped at UNCERTAIN; majority victory not permitted under strong conflict."
            )
            return "UNCERTAIN", override_reason
        return tentative_recommendation, None
