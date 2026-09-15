"""ChEMBLConnector — queries ChEMBL API for drug bioactivities, targets and indications.

Reference: 03_RETRIEVAL_SPECIFICATION.md
API: https://www.ebi.ac.uk/chembl/api/data/

Approval inference rule (no hardcoded facts):
  max_phase == 4 → Approved (FDA/EMA)
  max_phase == 3 → Phase III
  max_phase == 2 → Phase II
  max_phase == 1 → Phase I
  max_phase == 0 → Preclinical / No development record
"""
from __future__ import annotations

import logging
from typing import Any

from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"


class ChEMBLConnector(BaseConnector):
    """Connector for the ChEMBL bioactivity, target and indication database.

    Fetches:
    - Drug bioactivity records (IC50, Ki, Kd)
    - Drug-target interaction mechanisms
    - Drug approval status (max_phase from molecule endpoint)
    - Disease indications with per-indication max_phase (drug_indication endpoint)
    """

    source_name = "chembl"
    base_url = CHEMBL_BASE
    timeout_seconds = 30.0

    @staticmethod
    def _safe_parse_phase(raw_value: Any) -> int:
        """Safely parse a ChEMBL max_phase value to an integer.

        ChEMBL API may return max_phase as an int, a float string (e.g. "4.0"),
        None, or a malformed value.  This method handles all cases gracefully:
          "4.0" -> 4,  "3.0" -> 3,  4 -> 4,  None -> 0,  malformed -> 0

        Malformed values are never silently interpreted as Phase 4.
        Result is clamped to [0, 4].
        """
        if raw_value is None:
            return 0
        try:
            return max(0, min(4, int(float(raw_value))))
        except (TypeError, ValueError):
            logger.warning(
                "chembl_phase_unparseable",
                extra={"raw_value": raw_value},
            )
            return 0


    async def fetch(self, chembl_id: str, limit: int = 100) -> dict[str, Any]:
        """Fetch bioactivity records for a ChEMBL compound.

        Args:
            chembl_id: ChEMBL compound identifier (e.g., 'CHEMBL941').
            limit: Maximum number of records to retrieve (default 100).

        Returns:
            Raw JSON payload from ChEMBL /activity endpoint.
        """
        url = f"{self.base_url}/activity.json"
        params = {
            "molecule_chembl_id": chembl_id,
            "limit": limit,
            "format": "json",
        }
        logger.info("chembl_fetch", extra={"chembl_id": chembl_id, "limit": limit})
        return await self._get(url, params=params)

    async def fetch_molecule(self, chembl_id: str) -> dict[str, Any]:
        """Fetch molecule details for a ChEMBL compound (legacy, use fetch_molecule_details).

        Args:
            chembl_id: ChEMBL compound identifier.

        Returns:
            Raw JSON molecule record from ChEMBL.
        """
        url = f"{self.base_url}/molecule/{chembl_id}.json"
        return await self._get(url)

    async def fetch_molecule_details(self, chembl_id: str) -> dict[str, Any]:
        """Fetch full molecule details including max_phase and approval status.

        This is the primary mechanism for detecting whether a drug is approved.
        ChEMBL max_phase meanings:
        - 4 = Approved (FDA/EMA)
        - 3 = Phase III clinical trial
        - 2 = Phase II clinical trial
        - 1 = Phase I clinical trial
        - 0 = Preclinical / not in clinical development

        No drug names, disease names, or approval facts are hardcoded here.
        The approval status is inferred purely from the retrieved max_phase value.

        Args:
            chembl_id: ChEMBL compound identifier (e.g., 'CHEMBL941').

        Returns:
            Dict containing:
              max_phase (int): 0-4, global maximum clinical phase
              pref_name (str): Preferred compound name
              molecule_type (str): e.g. 'Small molecule', 'Antibody'
              therapeutic_flag (bool): True if compound has therapeutic use
              molecule_synonyms (list[str]): Known trade/brand names
            Returns empty dict on failure (graceful degradation).
        """
        try:
            url = f"{self.base_url}/molecule/{chembl_id}.json"
            raw = await self._get(url)
            return {
                "max_phase": self._safe_parse_phase(raw.get("max_phase")),
                "pref_name": raw.get("pref_name") or "",
                "molecule_type": raw.get("molecule_type") or "",
                "therapeutic_flag": bool(raw.get("therapeutic_flag", False)),
                "molecule_synonyms": [
                    s.get("molecule_synonym", "")
                    for s in raw.get("molecule_synonyms", [])
                    if s.get("molecule_synonym")
                ][:15],
            }
        except Exception as exc:
            logger.debug(
                "chembl_molecule_details_failed",
                extra={"chembl_id": chembl_id, "error": str(exc)},
            )
            return {}

    async def fetch_indications(self, chembl_id: str, limit: int = 100) -> dict[str, Any]:
        """Fetch per-indication approval data from ChEMBL drug_indication endpoint.

        Returns all disease indications for which this drug has clinical data,
        with max_phase_for_ind indicating the highest phase reached for each:
        - max_phase_for_ind == 4 → approved for that specific indication
        - max_phase_for_ind == 3 → Phase III for that indication
        - etc.

        This is the ONLY mechanism used to classify approved vs. repurposing
        vs. novel status. No disease names are hardcoded — the comparison
        against the queried disease happens at reasoning time using the
        returned efo_term / mesh_heading strings.

        Args:
            chembl_id: ChEMBL compound identifier (e.g., 'CHEMBL941').
            limit: Maximum number of indication records.

        Returns:
            Dict with 'indications' list. Each indication dict contains:
              efo_id (str): EFO ontology ID
              efo_term (str): EFO disease/condition term
              mesh_id (str): MeSH identifier (may be empty)
              mesh_heading (str): MeSH disease heading (may be empty)
              max_phase_for_ind (int): Highest clinical phase for this indication
              indication_refs (list): Source reference documents
            Returns {'indications': []} on failure (graceful degradation).
        """
        try:
            url = f"{self.base_url}/drug_indication.json"
            params = {
                "molecule_chembl_id": chembl_id,
                "limit": limit,
                "format": "json",
            }
            raw = await self._get(url, params=params)
            indications = []
            for ind in raw.get("drug_indications", []):
                # ChEMBL currently serializes this value as strings such as
                # ``"4.0"``.  Parsing it with int() rejects the whole response
                # and previously made disease-matched approvals disappear.
                # An invalid *individual* row is treated as phase 0 rather than
                # discarding other well-formed indication records.
                raw_phase = ind.get("max_phase_for_ind")
                try:
                    max_phase = int(float(raw_phase)) if raw_phase is not None else 0
                except (TypeError, ValueError):
                    logger.warning(
                        "chembl_indication_phase_unparseable",
                        extra={"chembl_id": chembl_id, "raw_phase": raw_phase},
                    )
                    max_phase = 0
                indications.append({
                    "efo_id": ind.get("efo_id", ""),
                    "efo_term": (ind.get("efo_term") or "").lower(),
                    "mesh_id": ind.get("mesh_id", ""),
                    "mesh_heading": (ind.get("mesh_heading") or "").lower(),
                    "max_phase_for_ind": max(0, min(4, max_phase)),
                    "indication_refs": ind.get("indication_refs", []),
                })
            logger.info(
                "chembl_indications_fetched",
                extra={"chembl_id": chembl_id, "count": len(indications)},
            )
            return {"indications": indications}
        except Exception as exc:
            logger.debug(
                "chembl_indications_failed",
                extra={"chembl_id": chembl_id, "error": str(exc)},
            )
            return {"indications": []}

    async def fetch_targets(self, chembl_id: str) -> dict[str, Any]:
        """Fetch drug-target interaction data for a ChEMBL compound.

        Args:
            chembl_id: ChEMBL compound identifier.

        Returns:
            Raw JSON payload from ChEMBL /mechanism endpoint.
        """
        url = f"{self.base_url}/mechanism.json"
        params = {"molecule_chembl_id": chembl_id, "format": "json"}
        return await self._get(url, params=params)

    async def search_molecule(self, drug_name: str) -> dict[str, Any]:
        """Search for a molecule by name to resolve ChEMBL ID.

        Args:
            drug_name: Drug common name to search.

        Returns:
            Raw JSON search results from ChEMBL.
        """
        clean_name = drug_name.strip()
        url_mol = f"{self.base_url}/molecule.json"
        
        try:
            res = await self._get(url_mol, params={"pref_name__iexact": clean_name, "format": "json"})
            if res.get("molecules"):
                return res
        except Exception:
            pass

        try:
            res = await self._get(url_mol, params={"molecule_synonyms__molecule_synonym__iexact": clean_name, "format": "json"})
            if res.get("molecules"):
                return res
        except Exception:
            pass

        url = f"{self.base_url}/molecule/search.json"
        params = {"q": drug_name, "format": "json"}
        return await self._get(url, params=params)
