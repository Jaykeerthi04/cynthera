"""EvidenceWeightPolicy domain model (Phase 5.7).

Configures production evidence weighting while guaranteeing EQUAL_VOTE as the production default.
GROUNDING_WEIGHTED is available as an opt-in evaluation-gated mode until development-set calibration
is completed.
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field

from backend.core.enums.causal_grounding import CausalGrounding
from backend.evaluation.evidence_weights import WeightConfig


class WeightMode(str, Enum):
    """Evidence weighting operation mode."""
    EQUAL_VOTE = "EQUAL_VOTE"                 # Production default: 1 vote per independent group
    GROUNDING_WEIGHTED = "GROUNDING_WEIGHTED"  # Opt-in: weighted by causal grounding tier


class EvidenceWeightPolicy(BaseModel):
    """Policy governing evidence weighting in therapeutic alignment.

    IMPORTANT NOTICE:
    EQUAL_VOTE is the mandatory production default.
    The numerical weights for GROUNDING_WEIGHTED represent initial heuristic priors
    and must not be treated as empirically calibrated without a separate dev set.
    """

    model_config = {"frozen": True}

    mode: WeightMode = Field(
        default=WeightMode.EQUAL_VOTE,
        description="Weighting mode: EQUAL_VOTE (production default) or GROUNDING_WEIGHTED (opt-in).",
    )
    direct_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    curated_weight: float = Field(default=0.9, ge=0.0, le=1.0)
    inferred_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    structural_weight: float = Field(default=0.0, ge=0.0, le=0.0)  # Must be 0.0
    none_weight: float = Field(default=0.0, ge=0.0, le=0.0)        # Must be 0.0
    min_effective_weight: float = Field(default=0.5, ge=0.0)
    family_weight: float = Field(default=1.0, ge=0.0)

    def weight_for_grounding(self, grounding: CausalGrounding | str) -> float:
        """Return the weight for a given causal grounding tier."""
        g = grounding.value if isinstance(grounding, CausalGrounding) else str(grounding).upper()
        if g == CausalGrounding.DIRECT.value:
            return self.direct_weight
        if g == CausalGrounding.CURATED.value:
            return self.curated_weight
        if g == CausalGrounding.INFERRED.value:
            return self.inferred_weight
        return 0.0  # STRUCTURAL and NONE are always 0.0

    def to_weight_config(self) -> WeightConfig:
        """Convert policy to WeightConfig for compatibility with existing weighted comparator."""
        return WeightConfig(
            name=self.mode.value,
            direct=self.direct_weight,
            curated=self.curated_weight,
            inferred=self.inferred_weight,
            structural=0.0,
            none=0.0,
            min_effective_weight=self.min_effective_weight,
        )


DEFAULT_WEIGHT_POLICY = EvidenceWeightPolicy(mode=WeightMode.EQUAL_VOTE)
