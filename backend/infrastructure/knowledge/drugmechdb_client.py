"""DrugMechDBClient — Independent mechanistic validation store & client.

Reference: Phase 4C — Directional Evidence Infrastructure

Provides independent validation of mechanistic paths from Drug to Disease:
Drug -> Target -> Biological Process -> Disease.
DrugMechDB does NOT vote on therapeutic direction; it provides independent validation
of whether an expert-curated mechanistic path exists for the drug-indication pair.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
import httpx
import yaml

from backend.core.value_objects.therapeutic_direction_evidence import DrugMechDBEvidence

logger = logging.getLogger(__name__)

_DRUGMECHDB_RAW_URL = "https://raw.githubusercontent.com/SuLab/DrugMechDB/main/indication_paths.yaml"
_LOCAL_CACHE_PATH = Path("data/drugmechdb_indication_paths.json")

# Disease synonym mapping for MeSH / DrugMechDB disease terms
_DISEASE_SYNONYMS: dict[str, list[str]] = {
    "edema": ["edema", "edemas", "hypertensive disorder"],
    "infantile hemangioma": ["hemangioma", "infantile hemangioma", "vascular disease"],
    "heart failure": ["heart failure", "cardiac failure", "congestive heart failure", "cardiomyopathy"],
    "multiple myeloma": ["multiple myeloma", "plasma cell myeloma", "myeloma"],
    "colorectal cancer": ["colorectal neoplasms", "colorectal cancer", "colon cancer", "rectal cancer"],
}


class DrugMechDBClient:
    """Client and index store for curated DrugMechDB mechanism paths."""

    _instance: DrugMechDBClient | None = None
    _paths: list[dict[str, Any]] | None = None

    def __init__(self, data_path: Path | None = None) -> None:
        self.data_path = data_path or _LOCAL_CACHE_PATH

    async def load_data(self) -> list[dict[str, Any]]:
        """Load DrugMechDB paths from local cache or fetch from remote."""
        if DrugMechDBClient._paths is not None:
            return DrugMechDBClient._paths

        # Check local cache first
        if self.data_path.exists():
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    DrugMechDBClient._paths = json.load(f)
                logger.info("drugmechdb_loaded_from_local_cache", extra={"count": len(DrugMechDBClient._paths)})
                return DrugMechDBClient._paths
            except Exception as exc:
                logger.warning("drugmechdb_cache_read_failed", extra={"error": str(exc)})

        # Fetch from remote repository
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.get(_DRUGMECHDB_RAW_URL)
                if resp.status_code == 200:
                    raw_data = yaml.safe_load(resp.text)
                    DrugMechDBClient._paths = raw_data
                    # Save to local cache
                    try:
                        self.data_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(self.data_path, "w", encoding="utf-8") as f:
                            json.dump(raw_data, f)
                    except Exception as cache_exc:
                        logger.warning("drugmechdb_cache_save_failed", extra={"error": str(cache_exc)})
                    logger.info("drugmechdb_loaded_from_remote", extra={"count": len(raw_data)})
                    return raw_data
        except Exception as exc:
            logger.warning("drugmechdb_remote_fetch_failed", extra={"error": str(exc)})

        DrugMechDBClient._paths = []
        return []

    async def lookup_mechanism(
        self,
        drug_name: str,
        disease_name: str,
        target_uniprot: str | None = None,
    ) -> DrugMechDBEvidence:
        """Query whether an expert-curated mechanistic path exists for drug -> disease.

        Args:
            drug_name: Name of the drug (e.g., 'Furosemide', 'Thalidomide').
            disease_name: Name of the disease (e.g., 'Edema', 'Multiple Myeloma').
            target_uniprot: Optional candidate target UniProt accession.

        Returns:
            DrugMechDBEvidence value object.
        """
        paths = await self.load_data()
        d_norm = drug_name.lower().strip()
        dis_norm = disease_name.lower().strip()

        synonyms = _DISEASE_SYNONYMS.get(dis_norm, [dis_norm])

        best_hit: dict[str, Any] | None = None
        exact_target_match = False

        for item in paths:
            graph = item.get("graph", {})
            item_drug = (graph.get("drug") or "").lower()
            item_dis = (graph.get("disease") or "").lower()

            if d_norm not in item_drug and item_drug not in d_norm:
                continue

            # Disease matching
            disease_matches = any(s in item_dis or item_dis in s for s in synonyms)
            if not disease_matches:
                continue

            links = item.get("links", [])
            # Check target match in links
            has_target = False
            if target_uniprot:
                target_token = f"UniProt:{target_uniprot}"
                for l in links:
                    if target_token in str(l.get("source")) or target_token in str(l.get("target")):
                        has_target = True
                        break

            if has_target:
                best_hit = item
                exact_target_match = True
                break
            elif best_hit is None:
                best_hit = item

        if best_hit:
            graph = best_hit.get("graph", {})
            links = best_hit.get("links", [])
            nodes = best_hit.get("nodes", [])
            chain_parts = []
            for l in links[:5]:
                src = str(l.get("source", ""))
                key = str(l.get("key", "->"))
                tgt = str(l.get("target", ""))
                chain_parts.append(f"({src} -[{key}]-> {tgt})")
            path_summary = " -> ".join(chain_parts) if chain_parts else "Curated Path Available"

            return DrugMechDBEvidence(
                drug_name=drug_name,
                disease_name=disease_name,
                drugbank_id=graph.get("drugbank"),
                mesh_disease=graph.get("disease_mesh"),
                target_uniprot=target_uniprot if exact_target_match else None,
                path_summary=path_summary,
                is_curated_path_available=True,
                nodes=nodes,
                links=links,
                provenance=best_hit,
            )

        return DrugMechDBEvidence(
            drug_name=drug_name,
            disease_name=disease_name,
            target_uniprot=target_uniprot,
            path_summary="NONE",
            is_curated_path_available=False,
        )
