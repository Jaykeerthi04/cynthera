"""Normalization Audit — dynamic auditing of identifier normalization and matching.

Provides generic inspection of biological identifiers in any RetrievalPackage,
tracking classification, canonical resolution rate, and comparing raw vs
canonical matching between pathways and disease-associated genes.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from backend.core.domain.retrieval_package import RetrievalPackage
from backend.reasoning.normalization.biological_identifier_resolver import (
    BiologicalIdentifierResolver,
)


@dataclass(frozen=True)
class IdentifierAuditRecord:
    """Audit record for a single biological identifier encountered in retrieval."""
    raw_identifier: str
    detected_identifier_type: str
    canonical_identifier: str
    canonical_gene_symbol: str | None
    source: str
    resolution_status: str


@dataclass(frozen=True)
class NormalizationAudit:
    """Summary metrics of identifier normalization for a RetrievalPackage."""
    total_identifiers: int
    gene_symbols: int
    uniprot_accessions: int
    other_identifiers: int

    resolved: int
    unresolved: int
    resolution_rate: float

    canonical_entities: int
    duplicate_raw_identifiers: int

    records: tuple[IdentifierAuditRecord, ...]


def audit_identifiers(
    identifiers: list[tuple[str, str]],
    resolver: BiologicalIdentifierResolver,
) -> NormalizationAudit:
    """Audit a collection of (raw_identifier, source) pairs using the resolver."""
    records: list[IdentifierAuditRecord] = []

    for raw_identifier, source in identifiers:
        resolved = resolver.resolve(raw_identifier, source)
        status = "RESOLVED" if resolved.canonical_symbol else "UNRESOLVED"
        records.append(
            IdentifierAuditRecord(
                raw_identifier=raw_identifier,
                detected_identifier_type=resolved.identifier_type.value,
                canonical_identifier=resolved.canonical_identifier,
                canonical_gene_symbol=resolved.canonical_symbol,
                source=resolved.source,
                resolution_status=status,
            )
        )

    total = len(records)
    resolved_count = sum(1 for r in records if r.resolution_status == "RESOLVED")
    unresolved_count = total - resolved_count
    type_counts = Counter(r.detected_identifier_type for r in records)

    canonical_keys = {
        r.canonical_identifier for r in records if r.resolution_status == "RESOLVED"
    }
    raw_keys = [r.raw_identifier for r in records]
    duplicate_raw = len(raw_keys) - len(set(raw_keys))

    return NormalizationAudit(
        total_identifiers=total,
        gene_symbols=type_counts.get("GENE_SYMBOL", 0),
        uniprot_accessions=type_counts.get("UNIPROT", 0),
        other_identifiers=(
            total
            - type_counts.get("GENE_SYMBOL", 0)
            - type_counts.get("UNIPROT", 0)
        ),
        resolved=resolved_count,
        unresolved=unresolved_count,
        resolution_rate=(
            round(resolved_count / total, 4) if total > 0 else 1.0
        ),
        canonical_entities=len(canonical_keys),
        duplicate_raw_identifiers=duplicate_raw,
        records=tuple(records),
    )


def build_package_normalization_audit(
    package: RetrievalPackage,
) -> NormalizationAudit:
    """Extract all biological identifiers from a RetrievalPackage and run normalization audit."""
    resolver = BiologicalIdentifierResolver(
        proteins=package.proteins,
        genes=package.genes,
        mappings=getattr(package, "identifier_mappings", []),
    )

    identifiers: list[tuple[str, str]] = []

    # Disease genes
    val_genes = getattr(package, "validated_disease_genes", None) or {}
    for identifier in val_genes.keys():
        identifiers.append((str(identifier), "validated_disease_genes"))

    # Protein identifiers
    for protein in package.proteins:
        if getattr(protein, "uniprot_accession", None):
            identifiers.append((protein.uniprot_accession, "UniProt"))
        if getattr(protein, "gene_symbol", None):
            identifiers.append((protein.gene_symbol, "UniProt"))

    # Pathway participants
    for pathway in package.pathways:
        for identifier in (getattr(pathway, "participant_uniprot_ids", None) or []):
            identifiers.append((str(identifier), "Reactome"))

    return audit_identifiers(identifiers, resolver)


def calculate_matching_audit(
    package: RetrievalPackage,
    resolver: BiologicalIdentifierResolver,
) -> dict[str, int]:
    """Compare raw vs canonical matching between pathway participants and disease genes."""
    # ── Raw matching (prior behavior: exact string intersection) ───────
    raw_val_genes = getattr(package, "validated_disease_genes", None) or {}
    raw_disease_ids = {str(k).strip().upper() for k in raw_val_genes.keys()}

    raw_pathway_ids: set[str] = set()
    for pathway in package.pathways:
        for identifier in (getattr(pathway, "participant_uniprot_ids", None) or []):
            raw_pathway_ids.add(str(identifier).strip().upper())

    raw_matches = len(raw_disease_ids & raw_pathway_ids)

    # ── Canonical matching (normalized symbols) ───────────────────────
    canonical_disease_ids: set[str] = set()
    for identifier in raw_disease_ids:
        resolved = resolver.resolve(identifier, "validated_disease_genes")
        if resolved.canonical_symbol:
            canonical_disease_ids.add(resolved.canonical_symbol)

    canonical_pathway_ids: set[str] = set()
    for identifier in raw_pathway_ids:
        resolved = resolver.resolve(identifier, "Reactome")
        if resolved.canonical_symbol:
            canonical_pathway_ids.add(resolved.canonical_symbol)

    canonical_matches = len(canonical_disease_ids & canonical_pathway_ids)

    return {
        "raw_matches": raw_matches,
        "canonical_matches": canonical_matches,
        "raw_match_count": raw_matches,
        "canonical_match_count": canonical_matches,
        "new_matches_revealed": canonical_matches - raw_matches,
    }
