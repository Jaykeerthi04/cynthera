"""DiseaseGeneEvidence — Domain model for tiered disease-associated gene evidence.

Phase 5.10 Feature:
Provides explicit provenance, ontology tiering, and source tracking for
disease-associated genes connecting pathways/targets to the disease node in EvidenceGraph.

Tiers:
  - EXACT: Direct association for the queried disease concept/identifier.
  - EQUIVALENT: Direct association for an officially cross-referenced ontology equivalent (dbXRefs, exact synonyms).
  - CHILD: Association from a validated subtype/child disease term (e.g., congestive heart failure under heart failure).
  - PARENT: Association from a broader parent class (e.g., heart disorder over heart failure).
           NOTE: PARENT evidence is strictly prohibited from creating direct mechanistic bridge edges.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DiseaseGeneScope(str, Enum):
    """Ontology scope tier for disease-gene evidence."""
    EXACT = "EXACT"
    EQUIVALENT = "EQUIVALENT"
    CHILD = "CHILD"
    PARENT = "PARENT"


@dataclass(frozen=True)
class DiseaseGeneEvidence:
    """A single evidence unit linking a gene to a disease with complete provenance.

    Attributes:
        gene_symbol: Approved HGNC gene symbol (e.g., 'TTN', 'SLC12A1').
        gene_id: Ensembl gene ID or database identifier (e.g., 'ENSG00000155657').
        disease_id: Disease identifier (e.g., 'MONDO:0005252', 'EFO:0000660', 'MESH:D006333').
        ontology_source: Ontology vocabulary source (e.g., 'MONDO', 'EFO', 'MESH').
        evidence_source: Primary data source platform (e.g., 'OpenTargets', 'DisGeNET').
        evidence_score: Quantitative association score [0.0, 1.0].
        scope: Provenance tier (EXACT, EQUIVALENT, CHILD, PARENT).
        provenance: Detailed human-readable provenance explanation.
        relationship: Optional relationship predicate (e.g., 'ASSOCIATED_WITH', 'SUBTYPE_OF').
        uniprot_accession: Optional Swiss-Prot reviewed UniProt accession.
    """

    gene_symbol: str
    gene_id: str | None = None
    disease_id: str = ""
    ontology_source: str = "MONDO"
    evidence_source: str = "OpenTargets"
    evidence_score: float | None = None
    scope: DiseaseGeneScope = DiseaseGeneScope.EXACT
    provenance: str | None = None
    relationship: str | None = None
    uniprot_accession: str | None = None

    def can_bridge_mechanistic_graph(self) -> bool:
        """Return True if this evidence tier is eligible to bridge a mechanistic path.

        Safety Invariant:
        Only EXACT and EQUIVALENT tiers (and selectively CHILD with subtype provenance)
        may form active graph edges. PARENT evidence must NEVER form a direct bridge.
        """
        return self.scope in (DiseaseGeneScope.EXACT, DiseaseGeneScope.EQUIVALENT, DiseaseGeneScope.CHILD)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gene_symbol": self.gene_symbol,
            "gene_id": self.gene_id,
            "disease_id": self.disease_id,
            "ontology_source": self.ontology_source,
            "evidence_source": self.evidence_source,
            "evidence_score": self.evidence_score,
            "scope": self.scope.value if isinstance(self.scope, DiseaseGeneScope) else str(self.scope),
            "provenance": self.provenance,
            "relationship": self.relationship,
            "uniprot_accession": self.uniprot_accession,
        }
