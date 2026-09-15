"""CausalGrounding enum — reliability tier of a directional claim.

Reference: Phase 4B — Directional Evidence Infrastructure

Describes HOW a directional relationship was established, not what direction it is.
Lower tiers mean the direction is less certain and must not be treated as causal evidence.
"""
from enum import Enum


class CausalGrounding(str, Enum):
    """Reliability tier of a directional evidence claim.

    DIRECT:     Explicit causal statement from a curated experiment or primary source.
                Example: a published RCT demonstrates direct mechanistic causation.

    CURATED:    Curated database directional relationship with explicit annotation.
                Example: ChEMBL action_type = INHIBITOR, Reactome PositiveRegulation.

    INFERRED:   Direction inferred by a validated reasoning rule from structural data.
                Example: if drug inhibits X and X is a negative regulator, then net effect = positive.
                         (This inference is NOT produced in Phase 4B — reserved for Phase 4C.)

    STRUCTURAL: Graph connectivity confirmed, but no directional annotation present.
                Example: Reactome CATALYST, INPUT, OUTPUT, PARTICIPATES_IN roles.
                         These establish a biological relationship exists, not its direction.

    NONE:       No directional grounding. Direction cannot be inferred at all.
                Default for all new DirectionalEvidence records unless explicitly set.

    IMPORTANT:
        STRUCTURAL edges must NEVER contribute a sign to causal product computations.
        NONE edges must NEVER contribute a sign.
        Only DIRECT and CURATED edges may carry signed polarity.
    """

    DIRECT = "DIRECT"
    CURATED = "CURATED"
    INFERRED = "INFERRED"
    STRUCTURAL = "STRUCTURAL"
    NONE = "NONE"
