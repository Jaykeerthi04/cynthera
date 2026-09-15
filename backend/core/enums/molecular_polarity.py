"""MolecularPolarity enum — directional polarity of a molecular interaction.

Reference: Phase 4B — Directional Evidence Infrastructure

This is the canonical Phase 4B polarity enum.
BiologicalDirection in biological_identifier.py is preserved for backward compat.

IMPORTANT: These concepts are intentionally distinct:
  - MolecularPolarity: biochemical activation/inhibition sign (THIS ENUM)
  - CausalGrounding:   how reliable the directional claim is (see causal_grounding.py)
  - Therapeutic direction: whether the drug helps/harms (Phase 4C, not yet implemented)
"""
from enum import Enum


class MolecularPolarity(str, Enum):
    """Directional polarity of a molecular interaction or biological effect.

    POSITIVE: The interaction increases/activates/upregulates the target.
    NEGATIVE: The interaction decreases/inhibits/downregulates the target.
    UNKNOWN:  Direction cannot be determined from available structured data.

    Scientific invariants:
        CATALYST role in Reactome → UNKNOWN (not POSITIVE)
        INPUT role in Reactome    → UNKNOWN (not NEGATIVE)
        OUTPUT role in Reactome   → UNKNOWN (not POSITIVE)
        MODULATOR in ChEMBL       → UNKNOWN (never invent direction)
    """

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    UNKNOWN = "UNKNOWN"
