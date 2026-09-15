"""Reactome role → MolecularPolarity + CausalGrounding mapper.

Reference: Phase 4B — Directional Evidence Infrastructure

Maps Reactome participation role strings to MolecularPolarity and CausalGrounding.

CRITICAL scientific constraints enforced here:
    CATALYST  ≠ ACTIVATES  → MolecularPolarity.UNKNOWN
    INPUT     ≠ INHIBITS   → MolecularPolarity.UNKNOWN
    OUTPUT    ≠ ACTIVATES  → MolecularPolarity.UNKNOWN

Only explicit regulatory roles carry a signed polarity:
    POSITIVE_REGULATOR → POSITIVE (causal grounding: CURATED)
    NEGATIVE_REGULATOR → NEGATIVE (causal grounding: CURATED)

All other participation roles → UNKNOWN + STRUCTURAL.
STRUCTURAL grounding means the biological relationship is confirmed (target participates
in the reaction/pathway) but the directional sign cannot be determined.
"""
from __future__ import annotations

from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.enums.causal_grounding import CausalGrounding


# Mapping from Reactome role (uppercased) to MolecularPolarity.
# Roles not listed here default to UNKNOWN via the function.
REACTOME_ROLE_POLARITY_MAP: dict[str, MolecularPolarity] = {
    # Explicit directional regulatory roles
    "POSITIVE_REGULATOR": MolecularPolarity.POSITIVE,
    "POSITIVE REGULATOR": MolecularPolarity.POSITIVE,
    "POSITIVE_REGULATES": MolecularPolarity.POSITIVE,
    "POSITIVELY_REGULATES": MolecularPolarity.POSITIVE,

    "NEGATIVE_REGULATOR": MolecularPolarity.NEGATIVE,
    "NEGATIVE REGULATOR": MolecularPolarity.NEGATIVE,
    "NEGATIVE_REGULATES": MolecularPolarity.NEGATIVE,
    "NEGATIVELY_REGULATES": MolecularPolarity.NEGATIVE,

    # All structural participation roles → UNKNOWN
    # Do NOT assign polarity to these — they describe biochemical role, not direction.
    "CATALYST": MolecularPolarity.UNKNOWN,
    "CATALYZES": MolecularPolarity.UNKNOWN,
    "INPUT": MolecularPolarity.UNKNOWN,
    "INPUT_TO": MolecularPolarity.UNKNOWN,
    "OUTPUT": MolecularPolarity.UNKNOWN,
    "OUTPUT_OF": MolecularPolarity.UNKNOWN,
    "PARTICIPANT": MolecularPolarity.UNKNOWN,
    "PARTICIPATES_IN": MolecularPolarity.UNKNOWN,
    "PARTICIPATES_IN_REACTION": MolecularPolarity.UNKNOWN,
    "COMPLEX_COMPONENT": MolecularPolarity.UNKNOWN,
    "COMPLEX_COMPONENT_OF": MolecularPolarity.UNKNOWN,
    "ENTITY_SET_MEMBER": MolecularPolarity.UNKNOWN,
    "ENTITY_SET_MEMBER_OF": MolecularPolarity.UNKNOWN,
    "REQUIREMENT": MolecularPolarity.UNKNOWN,
    "REQUIREMENT_FOR": MolecularPolarity.UNKNOWN,
    "PART_OF": MolecularPolarity.UNKNOWN,
    "CONTAINS_ASSOCIATED_GENE": MolecularPolarity.UNKNOWN,
    "ENCODED_BY_DISEASE_ASSOCIATED_GENE": MolecularPolarity.UNKNOWN,
    "ASSOCIATED_WITH": MolecularPolarity.UNKNOWN,
    "UNKNOWN": MolecularPolarity.UNKNOWN,
}

# Which roles carry CURATED grounding vs STRUCTURAL
_CURATED_ROLES: frozenset[str] = frozenset({
    "POSITIVE_REGULATOR",
    "POSITIVE REGULATOR",
    "POSITIVE_REGULATES",
    "POSITIVELY_REGULATES",
    "NEGATIVE_REGULATOR",
    "NEGATIVE REGULATOR",
    "NEGATIVE_REGULATES",
    "NEGATIVELY_REGULATES",
})


def reactome_role_to_polarity(role: str | None) -> MolecularPolarity:
    """Map a Reactome participation role string to MolecularPolarity.

    Args:
        role: Reactome role string (e.g. "CATALYST", "POSITIVE_REGULATOR").
              May be None or empty.

    Returns:
        MolecularPolarity.POSITIVE, .NEGATIVE, or .UNKNOWN.
        Returns UNKNOWN for None, empty string, or any unrecognized role.

    Examples:
        >>> reactome_role_to_polarity("POSITIVE_REGULATOR")
        <MolecularPolarity.POSITIVE: 'POSITIVE'>
        >>> reactome_role_to_polarity("NEGATIVE_REGULATOR")
        <MolecularPolarity.NEGATIVE: 'NEGATIVE'>
        >>> reactome_role_to_polarity("CATALYST")
        <MolecularPolarity.UNKNOWN: 'UNKNOWN'>
        >>> reactome_role_to_polarity("INPUT")
        <MolecularPolarity.UNKNOWN: 'UNKNOWN'>
    """
    if not role:
        return MolecularPolarity.UNKNOWN
    return REACTOME_ROLE_POLARITY_MAP.get(role.upper().strip(), MolecularPolarity.UNKNOWN)


def reactome_role_to_grounding(role: str | None) -> CausalGrounding:
    """Map a Reactome participation role string to CausalGrounding.

    Args:
        role: Reactome role string (e.g. "CATALYST", "POSITIVE_REGULATOR").

    Returns:
        CausalGrounding.CURATED for explicit regulatory roles,
        CausalGrounding.STRUCTURAL for all participation/structural roles,
        CausalGrounding.NONE for None/empty input.

    Examples:
        >>> reactome_role_to_grounding("POSITIVE_REGULATOR")
        <CausalGrounding.CURATED: 'CURATED'>
        >>> reactome_role_to_grounding("CATALYST")
        <CausalGrounding.STRUCTURAL: 'STRUCTURAL'>
    """
    if not role:
        return CausalGrounding.NONE
    norm = role.upper().strip()
    if norm in _CURATED_ROLES:
        return CausalGrounding.CURATED
    if norm in REACTOME_ROLE_POLARITY_MAP:
        return CausalGrounding.STRUCTURAL
    # Unrecognized role — structural fallback (we know the relationship exists)
    return CausalGrounding.STRUCTURAL
