"""Canonical Biological Identifier — value objects for gene/protein identity and source mappings.

Preserves canonical keys, classifications, source-provided mappings, original identifiers,
and complete provenance without static lookups or hardcoding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BiologicalIdentifierType(str, Enum):
    """Classification of biological identifier types."""
    GENE_SYMBOL = "GENE_SYMBOL"
    UNIPROT = "UNIPROT"
    ENSEMBL = "ENSEMBL"
    NCBI_GENE = "NCBI_GENE"
    UNKNOWN = "UNKNOWN"


class BiologicalDirection(str, Enum):
    """Directional polarity of a biological interaction."""
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    UNKNOWN = "UNKNOWN"


class BiologicalRelationshipType(str, Enum):
    """Semantic relationship types in biological evidence graphs."""
    INHIBITS = "INHIBITS"
    ACTIVATES = "ACTIVATES"
    AGONIZES = "AGONIZES"
    ANTAGONIZES = "ANTAGONIZES"
    BINDS = "BINDS"
    MODULATES = "MODULATES"
    PARTICIPATES_IN = "PARTICIPATES_IN"
    ENCODED_BY_DISEASE_ASSOCIATED_GENE = "ENCODED_BY_DISEASE_ASSOCIATED_GENE"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    CONTAINS_ASSOCIATED_GENE = "CONTAINS_ASSOCIATED_GENE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BiologicalIdentifierMapping:
    """Source-provided mapping between biological identifiers (e.g. Gene Symbol <-> UniProt <-> Ensembl).

    Preserves row-level paired relationships directly from Open Targets, Reactome, etc.
    """
    canonical_symbol: str | None
    uniprot_accession: str | None
    source: str
    score: float | None = None
    original_identifiers: tuple[str, ...] = field(default_factory=tuple)
    ensembl_id: str | None = None
    identifier_type: str | None = None


@dataclass(frozen=True)
class CanonicalBiologicalIdentifier:
    """Canonical representation of a biological gene/protein identity.

    The canonical key is used for matching. Original identifiers are retained
    for provenance, auditing, and explainability.
    """

    canonical_identifier: str
    canonical_symbol: str | None
    identifier_type: BiologicalIdentifierType

    original_identifier: str
    source: str

    confidence: float | None = None

    source_identifiers: tuple[str, ...] = field(default_factory=tuple)

    @property
    def canonical_id(self) -> str:
        """Alias for canonical_identifier."""
        return self.canonical_identifier

    @property
    def original_id(self) -> str:
        """Alias for original_identifier."""
        return self.original_identifier
