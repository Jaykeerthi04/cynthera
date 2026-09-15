"""ChEMBL action_type → MolecularPolarity mapper.

Reference: Phase 4B — Directional Evidence Infrastructure

Maps curated ChEMBL mechanism action_type strings to MolecularPolarity.
Only explicit curated action types yield POSITIVE or NEGATIVE.
MODULATOR and all unrecognized types → UNKNOWN (never invent direction).

Scientific basis:
    INHIBITOR/ANTAGONIST/BLOCKER: drug reduces target activity → NEGATIVE
    AGONIST/ACTIVATOR/OPENER:     drug increases target activity → POSITIVE
    MODULATOR:                    direction ambiguous (could be context-dependent) → UNKNOWN

CausalGrounding for all ChEMBL-derived directional claims: CURATED
(ChEMBL assigns action_type from peer-reviewed curated binding data).
"""
from __future__ import annotations

from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.enums.causal_grounding import CausalGrounding


# Mapping from ChEMBL action_type (uppercased) to MolecularPolarity.
# Any action_type NOT in this map → UNKNOWN.
CHEMBL_POLARITY_MAP: dict[str, MolecularPolarity] = {
    # --- Inhibitory / negative direction ---
    "INHIBITOR": MolecularPolarity.NEGATIVE,
    "ANTAGONIST": MolecularPolarity.NEGATIVE,
    "BLOCKER": MolecularPolarity.NEGATIVE,
    "NEGATIVE_ALLOSTERIC_MODULATOR": MolecularPolarity.NEGATIVE,
    "NEGATIVE ALLOSTERIC MODULATOR": MolecularPolarity.NEGATIVE,
    "IRREVERSIBLE_INHIBITOR": MolecularPolarity.NEGATIVE,
    "IRREVERSIBLE INHIBITOR": MolecularPolarity.NEGATIVE,
    "INVERSE_AGONIST": MolecularPolarity.NEGATIVE,
    "INVERSE AGONIST": MolecularPolarity.NEGATIVE,
    "INHIBITS": MolecularPolarity.NEGATIVE,

    # --- Activating / positive direction ---
    "AGONIST": MolecularPolarity.POSITIVE,
    "ACTIVATOR": MolecularPolarity.POSITIVE,
    "OPENER": MolecularPolarity.POSITIVE,
    "POSITIVE_ALLOSTERIC_MODULATOR": MolecularPolarity.POSITIVE,
    "POSITIVE ALLOSTERIC MODULATOR": MolecularPolarity.POSITIVE,
    "PARTIAL_AGONIST": MolecularPolarity.POSITIVE,
    "PARTIAL AGONIST": MolecularPolarity.POSITIVE,
    "FULL_AGONIST": MolecularPolarity.POSITIVE,
    "FULL AGONIST": MolecularPolarity.POSITIVE,
    "ACTIVATES": MolecularPolarity.POSITIVE,

    # --- Explicitly UNKNOWN (ambiguous or bimodal action) ---
    # MODULATOR is explicitly NOT assigned a sign — do not add it as POSITIVE or NEGATIVE.
    # Any unrecognized key falls through to UNKNOWN in the function.
}


def chembl_action_to_polarity(action_type: str | None) -> MolecularPolarity:
    """Map a ChEMBL action_type string to MolecularPolarity.

    Args:
        action_type: Raw ChEMBL mechanism action_type (e.g. "INHIBITOR", "AGONIST").
                     May be None or empty.

    Returns:
        MolecularPolarity.NEGATIVE, .POSITIVE, or .UNKNOWN.
        Returns UNKNOWN for None, empty string, "MODULATOR", or unrecognized types.

    Examples:
        >>> chembl_action_to_polarity("INHIBITOR")
        <MolecularPolarity.NEGATIVE: 'NEGATIVE'>
        >>> chembl_action_to_polarity("AGONIST")
        <MolecularPolarity.POSITIVE: 'POSITIVE'>
        >>> chembl_action_to_polarity("MODULATOR")
        <MolecularPolarity.UNKNOWN: 'UNKNOWN'>
        >>> chembl_action_to_polarity(None)
        <MolecularPolarity.UNKNOWN: 'UNKNOWN'>
    """
    if not action_type:
        return MolecularPolarity.UNKNOWN
    return CHEMBL_POLARITY_MAP.get(action_type.upper().strip(), MolecularPolarity.UNKNOWN)


def chembl_action_to_grounding(action_type: str | None) -> CausalGrounding:
    """Return the CausalGrounding tier for a ChEMBL action_type.

    Rules:
        Any explicitly known POSITIVE or NEGATIVE action_type → CURATED
        MODULATOR or unrecognized action_type → NONE (no direction to ground)
        None/empty → NONE

    Args:
        action_type: Raw ChEMBL mechanism action_type string or None.

    Returns:
        CausalGrounding.CURATED if the polarity is known, else CausalGrounding.NONE.
    """
    polarity = chembl_action_to_polarity(action_type)
    if polarity == MolecularPolarity.UNKNOWN:
        return CausalGrounding.NONE
    return CausalGrounding.CURATED
