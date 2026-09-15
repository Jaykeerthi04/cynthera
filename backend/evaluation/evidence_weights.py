"""Evidence weighting by causal grounding tier — evaluation-only comparator.

Design Rationale
----------------
Different evidence sources carry different epistemic reliability. A direct RCT-backed
clinical causal statement is more reliable than a structural database annotation.
The CausalGrounding enum already captures this tier structure.

WeightConfig translates causal grounding tiers into multiplicative weights for
use in the weighted alignment comparator.

CRITICAL NOTICE — CALIBRATION STATUS
--------------------------------------
The numerical weight values in the predefined WeightConfig instances below are
INITIAL HEURISTIC VALUES. They encode a scientific prior:
    DIRECT evidence > CURATED evidence > INFERRED evidence > STRUCTURAL/NONE

They are NOT empirically calibrated. Calibration requires a development set with
sufficient coverage of all three label classes (POSITIVE, NEGATIVE, UNCERTAIN)
that is SEPARATE from the test set. We do not currently have such a set.

Do NOT tune these values to improve benchmark metrics on the TEST split.
Doing so would constitute train-test contamination.

Usage Scope
-----------
WeightConfig is used exclusively by:
1. TherapeuticAlignmentEngine.weighted_align_target() — evaluation comparator
2. EvaluationRunner.run_with_config() — when use_evidence_weighting=True

The production alignment path (TherapeuticAlignmentEngine.align_target()) uses
equal binary votes and is UNCHANGED by this module.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.core.enums.causal_grounding import CausalGrounding


@dataclass(frozen=True)
class WeightConfig:
    """Configurable evidence weighting by causal grounding tier.

    Weights are multiplicative scalars applied to evidence group contributions
    in the weighted alignment comparator.

    Attributes:
        name: Configuration identifier.
        direct: Weight for CausalGrounding.DIRECT evidence.
        curated: Weight for CausalGrounding.CURATED evidence.
        inferred: Weight for CausalGrounding.INFERRED evidence.
        structural: Weight for CausalGrounding.STRUCTURAL evidence.
            Set to 0.0 — structural edges encode connectivity, not direction,
            and must not contribute signed votes (see CausalGrounding docstring).
        none: Weight for CausalGrounding.NONE evidence.
            Set to 0.0 — no directional grounding, cannot contribute signed votes.
        min_effective_weight: Minimum total weight for a verdict to be accepted.
            If both support_weight and opposition_weight are below this threshold,
            emit INSUFFICIENT (not enough grounded evidence to decide either way).

    NOTE: These values are INITIAL HEURISTIC WEIGHTS, not calibrated values.
    """
    name: str = "DEFAULT_HEURISTIC"
    direct: float = 1.0
    curated: float = 0.9
    inferred: float = 0.5
    structural: float = 0.0  # Must remain 0.0 — structural edges carry no direction
    none: float = 0.0        # Must remain 0.0 — no directional grounding
    min_effective_weight: float = 0.5

    def weight_for(self, grounding: CausalGrounding) -> float:
        """Return the weight scalar for a given causal grounding tier.

        Args:
            grounding: CausalGrounding tier of an evidence group.

        Returns:
            Float weight in [0.0, 1.0]. Returns 0.0 for STRUCTURAL and NONE
            regardless of configuration, enforcing the rule that ungrounded
            edges never contribute directional votes.
        """
        if grounding == CausalGrounding.DIRECT:
            return self.direct
        elif grounding == CausalGrounding.CURATED:
            return self.curated
        elif grounding == CausalGrounding.INFERRED:
            return self.inferred
        elif grounding == CausalGrounding.STRUCTURAL:
            # Hard zero — structural connectivity ≠ directional evidence
            return 0.0
        else:
            # CausalGrounding.NONE and any unknown
            return 0.0


# ── Predefined weight configurations for sensitivity analysis ─────────────────
# These differ only in how much they discount CURATED relative to DIRECT evidence.
# CONFIG_A: gentle discount (0.9 curated)
# CONFIG_B: stronger discount (0.8 curated)
# CONFIG_C: equal curated and direct (tests whether tiering matters)

DEFAULT_WEIGHT_CONFIG = WeightConfig(
    name="DEFAULT_HEURISTIC",
    direct=1.0,
    curated=0.9,
    inferred=0.5,
    structural=0.0,
    none=0.0,
    min_effective_weight=0.5,
)

CONFIG_A = WeightConfig(
    name="CONFIG_A",
    direct=1.0,
    curated=0.9,
    inferred=0.5,
    structural=0.0,
    none=0.0,
    min_effective_weight=0.5,
)

CONFIG_B = WeightConfig(
    name="CONFIG_B",
    direct=1.0,
    curated=0.8,
    inferred=0.4,
    structural=0.0,
    none=0.0,
    min_effective_weight=0.5,
)

CONFIG_C = WeightConfig(
    name="CONFIG_C",
    direct=1.0,
    curated=1.0,  # No discount — tests whether tiering matters at all
    inferred=0.5,
    structural=0.0,
    none=0.0,
    min_effective_weight=0.5,
)

WEIGHT_CONFIGS: dict[str, WeightConfig] = {
    "DEFAULT_HEURISTIC": DEFAULT_WEIGHT_CONFIG,
    "CONFIG_A": CONFIG_A,
    "CONFIG_B": CONFIG_B,
    "CONFIG_C": CONFIG_C,
}

# ── Calibration Provenance ──────────────────────────────────────────────────
# Records which WeightConfig was selected as best during Phase 5.8 DEV calibration.
# Updated after running scratch/run_phase5_8_calibration.py on the DEVELOPMENT split.
# DO NOT modify this based on TEST split results — that would be train-test contamination.
# This constant is documentation-only: it is not used by any production code path.
CALIBRATION_SELECTED_CONFIG: str = "CONFIG_A"
CALIBRATION_DEV_MCC: float = 1.0000


@dataclass(frozen=True)
class CalibrationMetadata:
    selected_config: str = "CONFIG_A"
    selection_metric: str = "MCC"
    selection_split: str = "DEVELOPMENT"
    test_used_for_selection: bool = False
    status: str = "FROZEN"
    dev_cases_count: int = 11
    dev_mcc: float = 1.0000
    dev_f1: float = 0.3333
    dev_accuracy: float = 0.3636
    notes: str = (
        "CONFIG_A selected as standard scientific prior tie-breaker on DEVELOPMENT split. "
        "All candidate configurations (CONFIG_A, CONFIG_B, CONFIG_C) performed identically "
        "on the 11 DEV cases (MCC=1.0, F1=0.333, Acc=0.364). TEST split was strictly isolated."
    )


CALIBRATION_METADATA: CalibrationMetadata = CalibrationMetadata()

