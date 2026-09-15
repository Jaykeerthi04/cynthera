"""Canonical entity gating for directional claims.

Reference: Phase 4B — Directional Evidence Infrastructure

A directional contradiction claim is only meaningful when BOTH subject and object
can be resolved to real, canonical biological entities. Generic placeholder tokens
like "compound", "molecular target", "drug", "protein" must never be treated as
canonical biological entities — they cannot create valid directional contradictions.

This module provides the validation gate used by AdvancedConflictResolver.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.core.value_objects.biological_identifier import BiologicalIdentifierType

if TYPE_CHECKING:
    from backend.core.domain.claim import Claim
    from backend.reasoning.normalization.biological_identifier_resolver import (
        BiologicalIdentifierResolver,
    )

logger = logging.getLogger(__name__)

# Generic placeholder tokens that the keyword-fallback claim extractor may produce.
# These must never be used as canonical entity identifiers in contradiction logic.
_UNGROUNDED_TOKENS: frozenset[str] = frozenset({
    "compound",
    "drug",
    "the drug",
    "a drug",
    "molecular target",
    "the target",
    "a target",
    "target",
    "protein",
    "the protein",
    "a protein",
    "gene",
    "the gene",
    "a gene",
    "substrate",
    "inhibitor",
    "activator",
    "modulator",
    "ligand",
    "molecule",
    "agent",
    "treatment",
    "therapy",
    "disease",
    "the disease",
    "condition",
    "pathway",
    "the pathway",
})


def is_canonically_grounded(
    identifier: str,
    resolver: "BiologicalIdentifierResolver",
) -> bool:
    """Return True only if the identifier resolves to a real canonical biological entity.

    Conditions for True:
      1. The identifier is not in _UNGROUNDED_TOKENS.
      2. The resolver classifies it as UNIPROT or GENE_SYMBOL (not UNKNOWN).
      3. The resolver returns a canonical_symbol (for GENE_SYMBOL/UNIPROT with mapping).

    Args:
        identifier: The raw claim subject or object string.
        resolver:   BiologicalIdentifierResolver populated with retrieved proteins/genes.

    Returns:
        True if canonically grounded, False otherwise.
    """
    normalized = identifier.strip().lower()
    if normalized in _UNGROUNDED_TOKENS:
        return False

    resolved = resolver.resolve(identifier, source="canonical_gate")

    # Must not be UNKNOWN type
    if resolved.identifier_type == BiologicalIdentifierType.UNKNOWN:
        return False

    return True


def validate_directional_claim(
    claim: "Claim",
    resolver: "BiologicalIdentifierResolver",
) -> tuple[str, str] | None:
    """Validate that a claim's subject and object are both canonically grounded.

    Args:
        claim:    The Claim to validate.
        resolver: BiologicalIdentifierResolver for entity resolution.

    Returns:
        (canonical_subject_id, canonical_object_id) if both are grounded, else None.
    """
    subject_grounded = is_canonically_grounded(claim.subject, resolver)
    if not subject_grounded:
        logger.debug(
            "directional_claim_subject_ungrounded",
            extra={"subject": claim.subject, "claim_id": str(claim.id)},
        )
        return None

    object_grounded = is_canonically_grounded(claim.object, resolver)
    if not object_grounded:
        logger.debug(
            "directional_claim_object_ungrounded",
            extra={"object": claim.object, "claim_id": str(claim.id)},
        )
        return None

    # Resolve to canonical IDs
    subject_resolved = resolver.resolve(claim.subject, source="canonical_gate")
    object_resolved = resolver.resolve(claim.object, source="canonical_gate")

    subject_id = subject_resolved.canonical_identifier
    object_id = object_resolved.canonical_identifier

    return (subject_id, object_id)


def claims_are_comparable(
    claim_a: "Claim",
    claim_b: "Claim",
    resolver: "BiologicalIdentifierResolver",
) -> bool:
    """Return True only when both claims reference the same canonically resolved entity pair.

    Two claims are comparable (eligible for contradiction detection) if and only if:
      1. Both subjects resolve to the same canonical ID.
      2. Both objects resolve to the same canonical ID.
      3. Neither subject nor object is a generic placeholder.

    This prevents false contradictions from keyword-extracted claims like:
        "compound" → CAUSES → "molecular target"
        "compound" → PREVENTS → "molecular target"

    Args:
        claim_a:  First claim.
        claim_b:  Second claim.
        resolver: BiologicalIdentifierResolver for entity resolution.

    Returns:
        True if the claims describe the same directional entity pair and are comparable.
    """
    ids_a = validate_directional_claim(claim_a, resolver)
    ids_b = validate_directional_claim(claim_b, resolver)

    if ids_a is None or ids_b is None:
        return False

    return ids_a == ids_b
