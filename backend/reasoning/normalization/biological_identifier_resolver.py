"""BiologicalIdentifierResolver — dynamic canonical resolution of gene/protein identifiers.

Resolves retrieved biological identifiers (gene symbols, UniProt accessions, Ensembl IDs)
into canonical identities using authoritative mappings from retrieved Protein, Gene,
and Open Targets / Reactome source records without static dictionaries or hardcoded lists.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, Any

from backend.core.domain.gene import Gene
from backend.core.domain.protein import Protein
from backend.core.value_objects.biological_identifier import (
    BiologicalIdentifierMapping,
    BiologicalIdentifierType,
    CanonicalBiologicalIdentifier,
)

logger = logging.getLogger(__name__)

# Official UniProtKB accession regular expression
_UNIPROT_PATTERN = re.compile(
    r"^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9]|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9][A-Z][A-Z0-9]{2}[0-9])(?:-[0-9]+)?$"
)
_HGNC_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{0,15}$")
_ENSEMBL_PATTERN = re.compile(r"^ENSG[0-9]{11}$")


class BiologicalIdentifierResolver:
    """Resolves retrieved biological identifiers into canonical identities.

    Builds dynamic mappings from retrieved Protein, Gene, and source-provided
    BiologicalIdentifierMapping entities without static or hardcoded lookups.
    """

    def __init__(
        self,
        proteins: Iterable[Protein] = (),
        genes: Iterable[Gene] = (),
        mappings: Iterable[BiologicalIdentifierMapping | dict[str, Any]] = (),
    ) -> None:
        self._uniprot_to_symbol: dict[str, str] = {}
        self._symbol_to_uniprot: dict[str, str] = {}
        self._ensembl_to_symbol: dict[str, str] = {}
        self._symbol_to_ensembl: dict[str, str] = {}
        self._ensembl_to_uniprot: dict[str, str] = {}
        self._uniprot_to_ensembl: dict[str, str] = {}

        # Authoritative mappings from retrieved Protein records
        for protein in proteins:
            accession = self._clean_uniprot(getattr(protein, "uniprot_accession", None))
            symbol = getattr(protein, "gene_symbol", "") or ""
            symbol = symbol.strip().upper()
            if accession and symbol:
                self._uniprot_to_symbol[accession] = symbol
                self._symbol_to_uniprot[symbol] = accession

        # Dynamic mappings from retrieved Gene records
        for gene in genes:
            symbol = (
                getattr(gene, "hgnc_symbol", None)
                or getattr(gene, "symbol", None)
                or getattr(gene, "gene_symbol", None)
                or ""
            ).strip().upper()
            protein_ids = getattr(gene, "protein_ids", None) or []
            gene_id = getattr(gene, "id", None) or getattr(gene, "gene_id", None) or ""
            gene_id_str = str(gene_id).strip().upper()

            if _ENSEMBL_PATTERN.match(gene_id_str) and symbol:
                self._ensembl_to_symbol[gene_id_str] = symbol
                self._symbol_to_ensembl[symbol] = gene_id_str

            for accession in protein_ids:
                clean_acc = self._clean_uniprot(accession)
                if clean_acc and symbol:
                    self._uniprot_to_symbol[clean_acc] = symbol
                    self._symbol_to_uniprot[symbol] = clean_acc
                if clean_acc and _ENSEMBL_PATTERN.match(gene_id_str):
                    self._ensembl_to_uniprot[gene_id_str] = clean_acc
                    self._uniprot_to_ensembl[clean_acc] = gene_id_str

        # Source-provided mappings (Open Targets, Reactome, etc.)
        for mapping in mappings:
            symbol = getattr(mapping, "canonical_symbol", None)
            if symbol is None and isinstance(mapping, dict):
                symbol = mapping.get("canonical_symbol")
            accession = getattr(mapping, "uniprot_accession", None)
            if accession is None and isinstance(mapping, dict):
                accession = mapping.get("uniprot_accession")
            ensembl_id = getattr(mapping, "ensembl_id", None)
            if ensembl_id is None and isinstance(mapping, dict):
                ensembl_id = mapping.get("ensembl_id")

            # Check original_identifiers for Ensembl ID
            orig_ids = getattr(mapping, "original_identifiers", None)
            if orig_ids is None and isinstance(mapping, dict):
                orig_ids = mapping.get("original_identifiers", ())
            if orig_ids and not ensembl_id:
                for oid in orig_ids:
                    s_oid = str(oid).strip().upper()
                    if _ENSEMBL_PATTERN.match(s_oid):
                        ensembl_id = s_oid
                        break

            clean_acc = self._clean_uniprot(accession)
            clean_sym = symbol.strip().upper() if symbol else ""
            clean_ens = ensembl_id.strip().upper() if ensembl_id else ""

            self.add_mapping(
                canonical_symbol=clean_sym or None,
                uniprot_accession=clean_acc or None,
                ensembl_id=clean_ens or None,
            )

    def add_mapping(
        self,
        canonical_symbol: str | None = None,
        uniprot_accession: str | None = None,
        ensembl_id: str | None = None,
        source: str = "",
    ) -> None:
        """Dynamically register paired identifiers into the resolver mapping tables."""
        clean_sym = canonical_symbol.strip().upper() if canonical_symbol else None
        clean_acc = self._clean_uniprot(uniprot_accession) if uniprot_accession else None
        clean_ens = ensembl_id.strip().upper() if ensembl_id else None

        if clean_sym and clean_acc:
            self._uniprot_to_symbol[clean_acc] = clean_sym
            self._symbol_to_uniprot[clean_sym] = clean_acc

        if clean_sym and clean_ens:
            self._ensembl_to_symbol[clean_ens] = clean_sym
            self._symbol_to_ensembl[clean_sym] = clean_ens

        if clean_acc and clean_ens:
            self._ensembl_to_uniprot[clean_ens] = clean_acc
            self._uniprot_to_ensembl[clean_acc] = clean_ens

    @staticmethod
    def _clean_uniprot(identifier: str | None) -> str:
        """Strip isoform suffix and whitespace from UniProt accession."""
        if not identifier:
            return ""
        return str(identifier).split("-")[0].strip().upper()

    @classmethod
    def _classify_identifier(cls, raw: str) -> BiologicalIdentifierType:
        """Classify biological identifier type based on structural patterns."""
        norm = raw.strip().upper()
        if not norm:
            return BiologicalIdentifierType.UNKNOWN
        if bool(_ENSEMBL_PATTERN.match(norm)):
            return BiologicalIdentifierType.ENSEMBL
        if bool(_UNIPROT_PATTERN.match(norm)):
            return BiologicalIdentifierType.UNIPROT
        if bool(_HGNC_SYMBOL_PATTERN.match(norm)):
            return BiologicalIdentifierType.GENE_SYMBOL
        return BiologicalIdentifierType.UNKNOWN

    def resolve(
        self,
        identifier: str,
        source: str,
        confidence: float | None = None,
    ) -> CanonicalBiologicalIdentifier:
        """Resolve a biological identifier to its canonical representation.

        Resolves Ensembl IDs, UniProt accessions, or HGNC symbols into unified
        canonical identities while preserving the original source identifier.

        Args:
            identifier: Raw biological identifier string (e.g. 'ENSG00000163631', 'Q13621', 'SLC12A1').
            source: Name of the originating source/connector.
            confidence: Optional confidence or association score.

        Returns:
            CanonicalBiologicalIdentifier with canonical key, symbol (if resolvable),
            classification, and preserved provenance.
        """
        raw = str(identifier).strip() if identifier is not None else ""
        if not raw:
            return CanonicalBiologicalIdentifier(
                canonical_identifier="",
                canonical_symbol=None,
                identifier_type=BiologicalIdentifierType.UNKNOWN,
                original_identifier=str(identifier) if identifier is not None else "",
                source=source,
                confidence=confidence,
                source_identifiers=(),
            )

        norm = raw.upper()
        clean = self._clean_uniprot(norm)

        # 1. Direct lookup: known Ensembl gene ID (e.g. 'ENSG00000163631')
        if norm in self._ensembl_to_symbol:
            symbol = self._ensembl_to_symbol[norm]
            accession = self._ensembl_to_uniprot.get(norm) or self._symbol_to_uniprot.get(symbol)
            source_ids = [raw, symbol]
            if accession:
                source_ids.append(accession)
            return CanonicalBiologicalIdentifier(
                canonical_identifier=accession or symbol,
                canonical_symbol=symbol,
                identifier_type=BiologicalIdentifierType.ENSEMBL,
                original_identifier=raw,
                source=source,
                confidence=confidence,
                source_identifiers=tuple(source_ids),
            )

        # 2. Direct lookup: known UniProt accession (e.g. 'Q13621')
        if clean in self._uniprot_to_symbol:
            symbol = self._uniprot_to_symbol[clean]
            ensembl_id = self._uniprot_to_ensembl.get(clean) or self._symbol_to_ensembl.get(symbol)
            source_ids = [raw, symbol]
            if ensembl_id:
                source_ids.append(ensembl_id)
            return CanonicalBiologicalIdentifier(
                canonical_identifier=clean,
                canonical_symbol=symbol,
                identifier_type=BiologicalIdentifierType.UNIPROT,
                original_identifier=raw,
                source=source,
                confidence=confidence,
                source_identifiers=tuple(source_ids),
            )

        # 3. Direct lookup: known Gene Symbol (e.g. 'SLC12A1')
        if norm in self._symbol_to_uniprot or norm in self._symbol_to_ensembl:
            accession = self._symbol_to_uniprot.get(norm)
            ensembl_id = self._symbol_to_ensembl.get(norm)
            source_ids = [raw]
            if accession:
                source_ids.append(accession)
            if ensembl_id:
                source_ids.append(ensembl_id)
            return CanonicalBiologicalIdentifier(
                canonical_identifier=accession or norm,
                canonical_symbol=norm,
                identifier_type=BiologicalIdentifierType.GENE_SYMBOL,
                original_identifier=raw,
                source=source,
                confidence=confidence,
                source_identifiers=tuple(source_ids),
            )

        # 4. Structural classification fallback for unmapped identifiers
        id_type = self._classify_identifier(raw)

        if id_type == BiologicalIdentifierType.ENSEMBL:
            return CanonicalBiologicalIdentifier(
                canonical_identifier=norm,
                canonical_symbol=None,
                identifier_type=BiologicalIdentifierType.ENSEMBL,
                original_identifier=raw,
                source=source,
                confidence=confidence,
                source_identifiers=(raw,),
            )

        if id_type == BiologicalIdentifierType.UNIPROT:
            return CanonicalBiologicalIdentifier(
                canonical_identifier=clean,
                canonical_symbol=None,
                identifier_type=BiologicalIdentifierType.UNIPROT,
                original_identifier=raw,
                source=source,
                confidence=confidence,
                source_identifiers=(raw,),
            )

        if id_type == BiologicalIdentifierType.GENE_SYMBOL:
            return CanonicalBiologicalIdentifier(
                canonical_identifier=norm,
                canonical_symbol=norm,
                identifier_type=BiologicalIdentifierType.GENE_SYMBOL,
                original_identifier=raw,
                source=source,
                confidence=confidence,
                source_identifiers=(raw,),
            )

        return CanonicalBiologicalIdentifier(
            canonical_identifier=norm,
            canonical_symbol=None,
            identifier_type=BiologicalIdentifierType.UNKNOWN,
            original_identifier=raw,
            source=source,
            confidence=confidence,
            source_identifiers=(raw,),
        )
