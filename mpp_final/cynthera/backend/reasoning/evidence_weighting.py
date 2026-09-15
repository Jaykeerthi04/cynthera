"""Production Evidence Weighting Engine (Phase 5.15).

Calculates multi-dimensional evidence weights based on:
1. Evidence quality tier (structural=0.0 < curated < causal < literature < independently validated)
2. Independence with diminishing returns (duplicate citations do not inflate linearly)
3. Directness (direct drug-target mechanism > indirect association)
4. Target relevance (primary therapeutic target > secondary off-target)
5. Directional certainty (actionable vs uncharacterized)
6. Provenance penalty (missing provenance conservatively discounted, never converted to opposition)

CRITICAL NOTICE — CALIBRATION STATUS:
All weight scalars in ProductionWeightConfig are labeled INITIAL_HEURISTIC.
They encode scientific priors and are NOT empirically calibrated against test data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from backend.core.domain.contradiction_state import ContradictionLevel
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.therapeutic_direction_evidence import (
    DirectionalEvidenceGroup,
    TherapeuticAction,
)


@dataclass(frozen=True)
class ProductionWeightConfig:
    """Configurable weights and thresholds for multi-dimensional evidence weighting.

    NOTE: INITIAL_HEURISTIC priors. Do not tune against test data.
    """
    config_name: str = "INITIAL_HEURISTIC_V1"

    # Quality multipliers
    quality_independently_validated: float = 1.00
    quality_literature_grounded: float = 0.95
    quality_causal: float = 0.90
    quality_curated: float = 0.80
    quality_structural: float = 0.00  # Hard zero: structural participation ≠ direction

    # Grounding multipliers
    grounding_direct: float = 1.00
    grounding_curated: float = 0.85
    grounding_inferred: float = 0.50
    grounding_structural: float = 0.00  # Hard zero

    # Independence diminishing returns: f(N) = 1.0 + min(N - 1, max_extra) * step
    independence_base: float = 1.00
    independence_step: float = 0.15
    independence_max_extra: int = 3

    # Directness multipliers
    direct_target_multiplier: float = 1.00
    indirect_target_multiplier: float = 0.70

    # Target relevance multipliers
    primary_target_multiplier: float = 1.00
    secondary_offtarget_multiplier: float = 0.40

    # Provenance penalty (conservative discount, NOT negative evidence)
    verified_provenance_multiplier: float = 1.00
    missing_provenance_multiplier: float = 0.50

    # Decision thresholds
    min_effective_weight: float = 0.25
    decision_ratio_threshold: float = 1.50  # supp / opp >= 1.50 -> SUPPORTS


DEFAULT_PRODUCTION_WEIGHT_CONFIG = ProductionWeightConfig()


@dataclass(frozen=True)
class EvidenceWeight:
    """Traceable calculation breakdown for an evidence unit."""
    target_id: str
    group_id: str
    evidence_family: str
    direction: str

    base_weight: float
    quality_multiplier: float
    independence_multiplier: float
    relevance_multiplier: float
    provenance_multiplier: float
    final_weight: float

    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "group_id": self.group_id,
            "evidence_family": self.evidence_family,
            "direction": self.direction,
            "base_weight": round(self.base_weight, 4),
            "quality_multiplier": round(self.quality_multiplier, 4),
            "independence_multiplier": round(self.independence_multiplier, 4),
            "relevance_multiplier": round(self.relevance_multiplier, 4),
            "provenance_multiplier": round(self.provenance_multiplier, 4),
            "final_weight": round(self.final_weight, 4),
            "explanation": self.explanation,
        }


@dataclass
class DirectionalAggregate:
    """Aggregated multi-dimensional directional evidence."""
    supporting_weight: float
    opposing_weight: float
    unresolved_weight: float

    supporting_groups: int
    opposing_groups: int

    conflict_level: ContradictionLevel
    confidence: float
    verdict: str  # SUPPORTS | OPPOSES | CONFLICT | INSUFFICIENT

    traceable_items: list[EvidenceWeight] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "supporting_weight": round(self.supporting_weight, 4),
            "opposing_weight": round(self.opposing_weight, 4),
            "unresolved_weight": round(self.unresolved_weight, 4),
            "supporting_groups": self.supporting_groups,
            "opposing_groups": self.opposing_groups,
            "conflict_level": self.conflict_level.value,
            "confidence": round(self.confidence, 4),
            "verdict": self.verdict,
            "traceable_items": [i.to_dict() for i in self.traceable_items],
            "rationale": self.rationale,
        }


class EvidenceWeightingEngine:
    """Computes transparent, multi-dimensional evidence weights."""

    def __init__(self, config: ProductionWeightConfig | None = None) -> None:
        self.config = config or DEFAULT_PRODUCTION_WEIGHT_CONFIG

    def compute_group_weight(
        self,
        group: DirectionalEvidenceGroup,
        target_id: str,
        drug_action: TherapeuticAction,
        is_primary_target: bool = True,
        mechanism_quality: str = "CURATED",
        is_direct_target: bool = True,
    ) -> EvidenceWeight:
        """Compute traceable weight for a single independent evidence group."""
        # 1. Base weight from causal grounding
        base_w = {
            CausalGrounding.DIRECT: self.config.grounding_direct,
            CausalGrounding.CURATED: self.config.grounding_curated,
            CausalGrounding.INFERRED: self.config.grounding_inferred,
            CausalGrounding.STRUCTURAL: self.config.grounding_structural,
            CausalGrounding.NONE: 0.0,
        }.get(group.causal_grounding, 0.0)

        # 2. Quality multiplier
        qual_mult = {
            "INDEPENDENTLY_VALIDATED": self.config.quality_independently_validated,
            "LITERATURE_GROUNDED": self.config.quality_literature_grounded,
            "CAUSAL": self.config.quality_causal,
            "CURATED": self.config.quality_curated,
            "STRUCTURAL": self.config.quality_structural,
        }.get(mechanism_quality, self.config.quality_curated)

        # 3. Independence factor with diminishing returns
        # An evidence group represents 1 or more collinear database records
        # Raw records within the group do NOT multiply linearly
        record_count = getattr(group, "member_record_count", len(getattr(group, "record_ids", [1])))
        if record_count <= 1:
            indep_mult = self.config.independence_base
        else:
            extra = min(record_count - 1, self.config.independence_max_extra)
            indep_mult = self.config.independence_base + (extra * self.config.independence_step)

        # 4. Relevance multiplier (primary target vs secondary off-target)
        rel_mult = (
            self.config.primary_target_multiplier
            if is_primary_target
            else self.config.secondary_offtarget_multiplier
        )

        # Directness adjustment
        direct_mult = (
            self.config.direct_target_multiplier
            if is_direct_target
            else self.config.indirect_target_multiplier
        )
        combined_rel = rel_mult * direct_mult

        # 5. Provenance multiplier (missing provenance is penalized conservatively, NOT opposition)
        refs = getattr(group, "references", [])
        underlying_ref = getattr(group, "underlying_reference", (refs[0] if refs else ""))
        has_verified_ref = bool(underlying_ref and underlying_ref != "unlinked")
        prov_mult = (
            self.config.verified_provenance_multiplier
            if has_verified_ref
            else self.config.missing_provenance_multiplier
        )

        # Final weight
        final_w = base_w * qual_mult * indep_mult * combined_rel * prov_mult

        # Direction determination
        if group.desired_action == TherapeuticAction.UNKNOWN or drug_action == TherapeuticAction.UNKNOWN:
            direction = "UNKNOWN"
        elif group.desired_action == drug_action:
            direction = "SUPPORTS"
        else:
            direction = "OPPOSES"

        family_val = getattr(group, "evidence_family", getattr(group, "family", "UNKNOWN"))
        family_str = family_val.value if hasattr(family_val, "value") else str(family_val)

        explanation = (
            f"Group {group.group_id} ({family_str}): base={base_w:.2f} [grounding={group.causal_grounding.value}], "
            f"quality={qual_mult:.2f} [{mechanism_quality}], indep={indep_mult:.2f} [{record_count} recs], "
            f"relevance={combined_rel:.2f} [{'primary' if is_primary_target else 'offtarget'}], "
            f"prov={prov_mult:.2f} [{'verified' if has_verified_ref else 'missing'}]. "
            f"Final weight={final_w:.3f} ({direction})."
        )

        return EvidenceWeight(
            target_id=target_id,
            group_id=group.group_id,
            evidence_family=family_str,
            direction=direction,
            base_weight=base_w,
            quality_multiplier=qual_mult,
            independence_multiplier=indep_mult,
            relevance_multiplier=combined_rel,
            provenance_multiplier=prov_mult,
            final_weight=final_w,
            explanation=explanation,
        )

    def aggregate_weights(
        self,
        weights: Sequence[EvidenceWeight],
    ) -> DirectionalAggregate:
        """Aggregate evidence weights and determine weighted decision."""
        supp_w = 0.0
        opp_w = 0.0
        unres_w = 0.0

        supp_groups = 0
        opp_groups = 0

        for w in weights:
            if w.direction == "SUPPORTS":
                supp_w += w.final_weight
                supp_groups += 1
            elif w.direction == "OPPOSES":
                opp_w += w.final_weight
                opp_groups += 1
            else:
                unres_w += w.final_weight

        total_dir = supp_w + opp_w

        # Conflict assessment
        if supp_w > 0.0 and opp_w > 0.0:
            balance = abs(supp_w - opp_w) / total_dir
            if (supp_w >= 0.50 and opp_w >= 0.50) or (abs(supp_w - opp_w) < 1e-4):
                conflict_level = ContradictionLevel.STRONG
            elif balance >= 0.75:
                conflict_level = ContradictionLevel.MINOR
            elif balance >= 0.40:
                conflict_level = ContradictionLevel.MODERATE
            else:
                conflict_level = ContradictionLevel.STRONG
        else:
            conflict_level = ContradictionLevel.NONE

        # Verdict logic
        if total_dir < self.config.min_effective_weight:
            verdict = "INSUFFICIENT"
            rationale = (
                f"Total effective directional weight ({total_dir:.2f}) is below minimum threshold "
                f"({self.config.min_effective_weight:.2f}). Evidence is insufficient."
            )
        elif conflict_level == ContradictionLevel.STRONG:
            verdict = "CONFLICT"
            rationale = (
                f"Strong weighted conflict: support={supp_w:.2f} ({supp_groups} groups), "
                f"opposition={opp_w:.2f} ({opp_groups} groups). Substantial evidence exists on both sides."
            )
        elif supp_w > opp_w and (opp_w == 0.0 or (supp_w / max(0.01, opp_w)) >= self.config.decision_ratio_threshold):
            verdict = "SUPPORTS"
            rationale = (
                f"Weighted evidence SUPPORTS hypothesis: support weight {supp_w:.2f} decisively outranks "
                f"opposition weight {opp_w:.2f} (ratio {(supp_w / max(0.01, opp_w)):.2f})."
            )
        elif opp_w > supp_w and (supp_w == 0.0 or (opp_w / max(0.01, supp_w)) >= self.config.decision_ratio_threshold):
            verdict = "OPPOSES"
            rationale = (
                f"Weighted evidence OPPOSES hypothesis: opposition weight {opp_w:.2f} decisively outranks "
                f"support weight {supp_w:.2f} (ratio {(opp_w / max(0.01, supp_w)):.2f})."
            )
        else:
            verdict = "CONFLICT"
            rationale = (
                f"Moderate weighted conflict without decisive majority: support={supp_w:.2f} vs opposition={opp_w:.2f}."
            )

        confidence = round(min(1.0, total_dir / max(1.0, supp_groups + opp_groups)), 4)

        return DirectionalAggregate(
            supporting_weight=supp_w,
            opposing_weight=opp_w,
            unresolved_weight=unres_w,
            supporting_groups=supp_groups,
            opposing_groups=opp_groups,
            conflict_level=conflict_level,
            confidence=confidence,
            verdict=verdict,
            traceable_items=list(weights),
            rationale=rationale,
        )
