"""DATTsConnector — queries the Disease-Associated Therapeutic Targets (DATTs) GraphQL API.

DATTs is a specialized curated database containing explicit therapeutic actions
(Inhibition, Activation, Targeting) required for therapeutic efficacy against specific diseases,
with literature and pharmacology textbook citations.

Endpoint: https://datts.nibb.ac.jp/graphql (POST, GraphQL)

Reference: Phase 4C — Directional Evidence Infrastructure
"""
from __future__ import annotations

import logging
from typing import Any

from backend.core.exceptions import SourceUnavailableError
from backend.core.value_objects.therapeutic_direction_evidence import (
    DATTsEvidence,
    TherapeuticAction,
    normalize_therapeutic_action,
)
from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

_DATTS_GQL_URL = "https://datts.nibb.ac.jp/graphql"

_GQL_PROTEIN_SEARCH = """
query SearchDatts($keyword: String!) {
  proteinList(keyword: $keyword) {
    id
    proteinId
    geneSymbol
    definition
    uniprotId
    keggGeneId
    diseases {
      id
      nameEn
      nameJp
      umls
      icd10
    }
    relationships {
      id
      relType
      source
      literature
      comment
      disease {
        id
        nameEn
        umls
      }
    }
  }
}
"""


class DATTsConnector(BaseConnector):
    """Connector for the DATTs GraphQL API."""

    source_name = "datts"
    base_url = _DATTS_GQL_URL
    timeout_seconds = 20.0

    async def fetch(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Fetch raw protein relationships from DATTs.

        Satisfies BaseConnector abstract contract.
        """
        keyword = str(kwargs.get("keyword") or kwargs.get("gene_symbol") or "")
        if not keyword:
            return []
        resp = await self._post(self.base_url, {"query": _GQL_PROTEIN_SEARCH, "variables": {"keyword": keyword}})
        return (resp.get("data") or {}).get("proteinList", [])

    async def fetch_therapeutic_actions(
        self,
        gene_symbol: str,
        uniprot_id: str | None,
        disease_name: str,
    ) -> list[DATTsEvidence]:
        """Fetch curated therapeutic target action records from DATTs for a target-disease pair.

        Args:
            gene_symbol: HGNC gene symbol (e.g., 'SLC12A1', 'CRBN').
            uniprot_id: UniProt accession if known (e.g., 'Q13621').
            disease_name: Name of the disease (e.g., 'Edema', 'Multiple Myeloma').

        Returns:
            List of matching DATTsEvidence records.
        """
        search_terms = [t for t in [gene_symbol, uniprot_id] if t]
        if not search_terms:
            return []

        dis_norm = disease_name.lower().strip()
        # Common disease token set for overlap matching
        dis_tokens = set(dis_norm.split())

        matched_evidence: list[DATTsEvidence] = []
        seen_keys: set[tuple[str, str, str]] = set()

        for term in search_terms:
            try:
                resp = await self._post(
                    self.base_url,
                    {"query": _GQL_PROTEIN_SEARCH, "variables": {"keyword": term}},
                )
            except Exception as exc:
                logger.warning(
                    "datts_search_failed",
                    extra={"term": term, "disease": disease_name, "error": str(exc)},
                )
                raise

            protein_list = (resp.get("data") or {}).get("proteinList", [])
            for protein in protein_list:
                prot_sym = protein.get("geneSymbol")
                prot_uni = protein.get("uniprotId")
                prot_id = protein.get("proteinId")

                relationships = protein.get("relationships", [])
                for rel in relationships:
                    disease_obj = rel.get("disease") or {}
                    d_name_en = (disease_obj.get("nameEn") or "").strip()
                    d_name_lower = d_name_en.lower()

                    # Match disease: substring match or token overlap
                    is_match = False
                    if dis_norm in d_name_lower or d_name_lower in dis_norm:
                        is_match = True
                    elif dis_tokens:
                        rel_tokens = set(d_name_lower.split())
                        if dis_tokens & rel_tokens and len(dis_tokens & rel_tokens) >= min(len(dis_tokens), 2):
                            is_match = True

                    if not is_match:
                        continue

                    rel_id = str(rel.get("id") or "")
                    dedup_key = (str(prot_id), rel_id, d_name_lower)
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    raw_rel_type = str(rel.get("relType") or "UNKNOWN")
                    norm_action = normalize_therapeutic_action(raw_rel_type)

                    matched_evidence.append(
                        DATTsEvidence(
                            datts_protein_id=prot_id,
                            gene_symbol=prot_sym,
                            uniprot_id=prot_uni,
                            disease_name=d_name_en,
                            rel_type=raw_rel_type,
                            required_action=norm_action,
                            literature=rel.get("literature"),
                            source=rel.get("source"),
                            comment=rel.get("comment"),
                            provenance=rel,
                        )
                    )

        logger.info(
            "datts_therapeutic_actions_fetched",
            extra={
                "gene_symbol": gene_symbol,
                "disease": disease_name,
                "matches": len(matched_evidence),
            },
        )
        return matched_evidence
