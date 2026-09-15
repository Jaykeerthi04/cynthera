"""ReactomeConnector — queries Reactome ContentService for pathway data.

Reference: 03_RETRIEVAL_SPECIFICATION.md
API: https://reactome.org/ContentService/

Endpoint verification (live-tested 2026-08-04):
  GET /data/participants/{stId} returns:
    list[{ peDbId, displayName, schemaClass, refEntities: [
        { identifier: "Q13976-1", schemaClass: "ReferenceGeneProduct"|"ReferenceIsoform",
          displayName: "UniProt:Q13976-1 PRKG1", ... }
    ]}]
  UniProt accessions are in refEntities[*].identifier when schemaClass is
  "ReferenceGeneProduct" or "ReferenceIsoform".
  The endpoint requires a User-Agent header (403 without one).
"""
from __future__ import annotations

import logging
from typing import Any

from backend.core.value_objects.biological_identifier import BiologicalIdentifierMapping
from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

REACTOME_BASE = "https://reactome.org/ContentService"

# Reactome's ContentService returns 403 without a User-Agent.
_USER_AGENT = "CYNTHERA-Research/1.0 (scientific drug repurposing tool)"

# Physical entity schema classes that map 1:1 to a UniProt protein record.
_PROTEIN_SCHEMA_CLASSES = frozenset({"ReferenceGeneProduct", "ReferenceIsoform"})


class ReactomeConnector(BaseConnector):
    """Connector for the Reactome pathway knowledgebase.

    Fetches:
    - Pathways containing a given UniProt protein (forward direction)
    - UniProt participants of a given pathway (reverse direction)
    - Pathway detail records
    """

    source_name = "reactome"
    base_url = REACTOME_BASE
    timeout_seconds = 30.0

    def _build_headers(self) -> dict[str, str]:
        """Build default headers override to include custom User-Agent required by Reactome."""
        headers = super()._build_headers()
        headers["User-Agent"] = _USER_AGENT
        return headers

    async def fetch(self, uniprot_accession: str) -> dict[str, Any]:
        """Fetch all pathways that contain a given UniProt protein.

        Args:
            uniprot_accession: UniProt accession (e.g., 'O76074').

        Returns:
            Dict with 'pathways': list of raw pathway summary dicts from Reactome.
        """
        clean_acc = (uniprot_accession or "").strip().upper()
        if not clean_acc:
            return {"pathways": []}
        url = f"{self.base_url}/data/mapping/UniProt/{clean_acc}/pathways"
        params: dict[str, Any] = {"species": "Homo sapiens"}
        logger.info("reactome_fetch", extra={"uniprot": clean_acc})
        try:
            result = await self._get(url, params=params)
            return {"pathways": result if isinstance(result, list) else []}
        except Exception as exc:
            logger.debug(
                "reactome_pathways_fetch_failed",
                extra={"uniprot": clean_acc, "error": str(exc)},
            )
            return {"pathways": []}

    async def fetch_participants(self, reactome_stid: str) -> dict[str, Any]:
        """Fetch UniProt accessions of all protein participants in a pathway.

        Uses GET /data/participants/{stId} which returns PhysicalEntity objects
        each containing a refEntities list. UniProt accessions are extracted
        from refEntities where schemaClass is ReferenceGeneProduct or ReferenceIsoform.

        Live-verified endpoint shape (2026-08-04):
          [{ peDbId, displayName, schemaClass, refEntities: [
              { identifier: "Q13976-1", schemaClass: "ReferenceGeneProduct",
                displayName: "UniProt:Q13976-1 PRKG1" }
          ]}]

        Args:
            reactome_stid: Reactome stable identifier (e.g., 'R-HSA-418457').

        Returns:
            Dict with 'uniprot_ids': list[str] of UniProt accessions (deduplicated),
            and 'mappings': list[BiologicalIdentifierMapping] preserving UniProt ↔ gene symbol.
            Returns {'uniprot_ids': [], 'mappings': []} on any failure.
        """
        clean_stid = (reactome_stid or "").strip()
        url = f"{self.base_url}/data/participants/{clean_stid}"
        try:
            result = await self._get(url)
            uniprot_ids: list[str] = []
            mappings: list[BiologicalIdentifierMapping] = []

            if isinstance(result, list):
                for physical_entity in result:
                    if isinstance(physical_entity, dict):
                        for ref in physical_entity.get("refEntities", []):
                            if isinstance(ref, dict) and ref.get("schemaClass") in _PROTEIN_SCHEMA_CLASSES:
                                identifier = ref.get("identifier", "") or ""
                                base_accession = identifier.split("-")[0].strip().upper() if identifier else ""
                                if not base_accession:
                                    continue

                                if base_accession not in uniprot_ids:
                                    uniprot_ids.append(base_accession)

                                # Extract gene symbol dynamically from response
                                gene_symbol: str | None = None
                                gene_names = ref.get("geneName")
                                if isinstance(gene_names, list) and gene_names:
                                    first_name = str(gene_names[0]).strip().upper()
                                    if first_name:
                                        gene_symbol = first_name
                                elif isinstance(gene_names, str) and gene_names.strip():
                                    gene_symbol = gene_names.strip().upper()

                                if not gene_symbol:
                                    # Fall back to schema-consistent displayName parsing: "UniProt:ACC SYMBOL"
                                    display_name = str(ref.get("displayName") or "").strip()
                                    if display_name.startswith("UniProt:"):
                                        parts = display_name[len("UniProt:"):].strip().split()
                                        if len(parts) >= 2:
                                            candidate = parts[1].strip().upper()
                                            if candidate and candidate != base_accession:
                                                gene_symbol = candidate

                                orig_ids = (identifier, gene_symbol) if gene_symbol else (identifier,)
                                mappings.append(
                                    BiologicalIdentifierMapping(
                                        canonical_symbol=gene_symbol,
                                        uniprot_accession=base_accession,
                                        source="Reactome",
                                        score=None,
                                        original_identifiers=orig_ids,
                                    )
                                )
            logger.debug(
                "reactome_participants_fetched",
                extra={
                    "reactome_stid": clean_stid,
                    "uniprot_count": len(uniprot_ids),
                    "mappings_count": len(mappings),
                },
            )
            return {"uniprot_ids": uniprot_ids, "mappings": mappings}
        except Exception as exc:
            logger.warning(
                "reactome_participants_fetch_failed",
                extra={"reactome_stid": clean_stid, "error": str(exc), "error_type": type(exc).__name__},
            )
            return {"uniprot_ids": [], "mappings": []}

    async def fetch_pathway_details(self, reactome_id: str) -> dict[str, Any]:
        """Fetch detailed information for a specific Reactome pathway.

        Args:
            reactome_id: Reactome stable identifier (e.g., 'R-HSA-202127').

        Returns:
            Raw JSON pathway detail record.
        """
        clean_id = (reactome_id or "").strip()
        url = f"{self.base_url}/data/query/{clean_id}"
        return await self._get(url)

    async def fetch_reactions(self, uniprot_accession: str) -> list[dict[str, Any]]:
        """Fetch all reactions/events directly associated with a UniProt protein.

        Endpoint: GET /data/mapping/UniProt/{uniprotId}/reactions

        Args:
            uniprot_accession: UniProt accession (e.g. 'P08588').

        Returns:
            List of raw reaction summary dictionaries from Reactome.
        """
        clean_acc = (uniprot_accession or "").strip().upper()
        if not clean_acc:
            return []
        url = f"{self.base_url}/data/mapping/UniProt/{clean_acc}/reactions"
        try:
            res = await self._get(url)
            return res if isinstance(res, list) else []
        except Exception as exc:
            logger.warning(
                "reactome_reactions_fetch_failed",
                extra={"uniprot": clean_acc, "error": str(exc)},
            )
            return []

    async def fetch_reaction_details(self, reaction_stid: str) -> dict[str, Any]:
        """Fetch enhanced reaction details including catalystActivity, input, output, regulations.

        Endpoint: GET /data/query/enhanced/{stId}

        Args:
            reaction_stid: Reactome stable ID for reaction (e.g. 'R-HSA-379044').

        Returns:
            Enhanced reaction object dict.
        """
        clean_id = (reaction_stid or "").strip()
        if not clean_id:
            return {}
        url = f"{self.base_url}/data/query/enhanced/{clean_id}"
        try:
            res = await self._get(url)
            return res if isinstance(res, dict) else {}
        except Exception as exc:
            logger.warning(
                "reactome_reaction_details_fetch_failed",
                extra={"reaction_stid": clean_id, "error": str(exc)},
            )
            return {}

    async def fetch_reaction_ancestors(self, reaction_stid: str) -> list[list[dict[str, Any]]]:
        """Fetch hierarchical ancestor pathway chains for a reaction.

        Endpoint: GET /data/event/{stId}/ancestors

        Args:
            reaction_stid: Reactome stable ID for reaction.

        Returns:
            List of ancestor path lists from reaction up to root pathways.
        """
        clean_id = (reaction_stid or "").strip()
        if not clean_id:
            return []
        url = f"{self.base_url}/data/event/{clean_id}/ancestors"
        try:
            res = await self._get(url)
            return res if isinstance(res, list) else []
        except Exception as exc:
            logger.warning(
                "reactome_reaction_ancestors_fetch_failed",
                extra={"reaction_stid": clean_id, "error": str(exc)},
            )
            return []

    async def fetch_pathway_events(self, pathway_stid: str) -> dict[str, Any]:
        """Fetch enhanced pathway record including child hasEvent list.

        Endpoint: GET /data/query/enhanced/{stId}

        Args:
            pathway_stid: Reactome pathway stable ID (e.g. 'R-HSA-189200').

        Returns:
            Enhanced pathway object dict.
        """
        clean_id = (pathway_stid or "").strip()
        if not clean_id:
            return {}
        url = f"{self.base_url}/data/query/enhanced/{clean_id}"
        try:
            res = await self._get(url)
            return res if isinstance(res, dict) else {}
        except Exception as exc:
            logger.warning(
                "reactome_pathway_events_fetch_failed",
                extra={"pathway_stid": clean_id, "error": str(exc)},
            )
            return {}

    async def fetch_participating_entities(self, event_stid: str) -> list[dict[str, Any]]:
        """Fetch participating physical entities for an event/reaction.

        Endpoint: GET /data/participants/{stId}/participatingPhysicalEntities

        Args:
            event_stid: Reactome stable ID for event or reaction.

        Returns:
            List of participant entity dicts.
        """
        clean_id = (event_stid or "").strip()
        if not clean_id:
            return []
        url = f"{self.base_url}/data/participants/{clean_id}/participatingPhysicalEntities"
        try:
            res = await self._get(url)
            return res if isinstance(res, list) else []
        except Exception as exc:
            logger.debug(
                "reactome_participating_entities_fetch_failed",
                extra={"event_stid": clean_id, "error": str(exc)},
            )
            return []

    @staticmethod
    def extract_entity_uniprots(entity: Any, visited: set[int] | None = None) -> set[str]:
        """Recursively extract all UniProt accessions from a PhysicalEntity, Complex, or EntitySet.

        Safeguarded with visited dbId set against circular graph references.
        """
        if not isinstance(entity, dict):
            return set()

        if visited is None:
            visited = set()

        db_id = entity.get("dbId")
        if isinstance(db_id, int):
            if db_id in visited:
                return set()
            visited.add(db_id)

        uniprots: set[str] = set()

        # 1. Direct refEntities
        for ref in entity.get("refEntities", []):
            if isinstance(ref, dict):
                ident = ref.get("identifier", "")
                if ident:
                    base = ident.split("-")[0].strip().upper()
                    if base:
                        uniprots.add(base)

        # 2. Direct referenceEntity
        ref_ent = entity.get("referenceEntity")
        if isinstance(ref_ent, dict):
            ident = ref_ent.get("identifier", "")
            if ident:
                base = ident.split("-")[0].strip().upper()
                if base:
                    uniprots.add(base)

        # 3. CrossReferences
        for cr in entity.get("crossReference", []):
            if isinstance(cr, dict):
                ident = cr.get("identifier", "")
                if ident:
                    base = ident.split("-")[0].strip().upper()
                    if base:
                        uniprots.add(base)

        # 4. Complex sub-components (hasComponent)
        for comp in entity.get("hasComponent", []):
            uniprots.update(ReactomeConnector.extract_entity_uniprots(comp, visited))

        # 5. EntitySet members (hasMember)
        for mem in entity.get("hasMember", []):
            uniprots.update(ReactomeConnector.extract_entity_uniprots(mem, visited))

        # 6. Polymer units (repeatedUnit)
        for rep in entity.get("repeatedUnit", []):
            uniprots.update(ReactomeConnector.extract_entity_uniprots(rep, visited))

        return uniprots

    @staticmethod
    def entity_matches_target(
        entity: Any,
        target_uniprot: str,
        target_symbol: str | None = None,
        visited: set[int] | None = None,
    ) -> bool:
        """Check if an entity contains or matches the target protein/gene."""
        if not isinstance(entity, dict):
            return False

        clean_target_acc = target_uniprot.split("-")[0].strip().upper() if target_uniprot else ""
        if clean_target_acc:
            accs = ReactomeConnector.extract_entity_uniprots(entity, visited)
            if clean_target_acc in accs:
                return True

        if target_symbol:
            sym_u = target_symbol.strip().upper()
            disp = str(entity.get("displayName") or "")
            # Word boundary or token check in displayName
            tokens = [t.strip(":,()[]{}") for t in disp.split()]
            if sym_u in tokens:
                return True
            for name in entity.get("name", []):
                if isinstance(name, str) and sym_u in [t.strip(":,()[]{}") for t in name.split()]:
                    return True

        return False

    @classmethod
    def extract_target_roles(
        cls,
        reaction_detail: dict[str, Any],
        participants: list[dict[str, Any]],
        target_uniprot: str,
        target_symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """Extract all target roles within a reaction.

        Handles multi-role relationships, CatalystActivity, Input, Output,
        PositiveRegulation, NegativeRegulation, Requirement, and Complex/EntitySet components.

        Returns list of dicts with keys:
            role: str (CATALYST, INPUT, OUTPUT, POSITIVE_REGULATOR, NEGATIVE_REGULATOR, REQUIREMENT, PARTICIPANT, etc.)
            direction: str ('UNKNOWN', 'POSITIVE', 'NEGATIVE')
            raw_field: str
            object_name: str
            schema_class: str
        """
        clean_target_acc = target_uniprot.split("-")[0].strip().upper() if target_uniprot else ""
        roles: list[dict[str, Any]] = []

        # Find all participant entities matching the target
        matched_participants: list[dict[str, Any]] = []
        matched_db_ids: set[int] = set()
        matched_names: set[str] = set()

        for p in participants:
            if isinstance(p, dict) and cls.entity_matches_target(p, clean_target_acc, target_symbol):
                matched_participants.append(p)
                db_id = p.get("dbId")
                if isinstance(db_id, int):
                    matched_db_ids.add(db_id)
                disp = str(p.get("displayName") or "")
                name_clean = disp.split("[")[0].strip().upper()
                if name_clean:
                    matched_names.add(name_clean)

        # 1. Catalyst Activity
        for cat in reaction_detail.get("catalystActivity") or []:
            if not isinstance(cat, dict):
                continue
            cat_disp = str(cat.get("displayName") or "")
            pe = cat.get("physicalEntity", {})
            pe_disp = str(pe.get("displayName") or "") if isinstance(pe, dict) else ""
            pe_db_id = pe.get("dbId") if isinstance(pe, dict) else None

            in_pe = cls.entity_matches_target(pe, clean_target_acc, target_symbol)
            in_disp = (target_symbol and target_symbol.upper() in cat_disp.upper())
            in_part = (pe_db_id is not None and pe_db_id in matched_db_ids) or any(
                n and (n in cat_disp.upper() or n in pe_disp.upper()) for n in matched_names
            )

            if in_pe or in_disp or in_part:
                roles.append({
                    "role": "CATALYST",
                    "direction": "UNKNOWN",  # Catalyst is NOT automatically assumed to activate
                    "raw_field": "catalystActivity",
                    "object_name": cat_disp or pe_disp or "CatalystActivity",
                    "schema_class": cat.get("schemaClass", "CatalystActivity"),
                })

        # 2. Positive Regulation
        for reg in reaction_detail.get("positiveRegulation") or []:
            if not isinstance(reg, dict):
                continue
            reg_disp = str(reg.get("displayName") or "")
            regulator = reg.get("regulator", {})
            reg_db_id = regulator.get("dbId") if isinstance(regulator, dict) else None

            in_reg = cls.entity_matches_target(regulator, clean_target_acc, target_symbol)
            in_disp = (target_symbol and target_symbol.upper() in reg_disp.upper())
            in_part = (reg_db_id is not None and reg_db_id in matched_db_ids) or any(
                n and n in reg_disp.upper() for n in matched_names
            )

            if in_reg or in_disp or in_part:
                roles.append({
                    "role": "POSITIVE_REGULATOR",
                    "direction": "POSITIVE",  # Explicit positive regulation
                    "raw_field": "positiveRegulation",
                    "object_name": reg_disp or "PositiveRegulation",
                    "schema_class": reg.get("schemaClass", "PositiveRegulation"),
                })

        # 3. Negative Regulation
        for reg in reaction_detail.get("negativeRegulation") or []:
            if not isinstance(reg, dict):
                continue
            reg_disp = str(reg.get("displayName") or "")
            regulator = reg.get("regulator", {})
            reg_db_id = regulator.get("dbId") if isinstance(regulator, dict) else None

            in_reg = cls.entity_matches_target(regulator, clean_target_acc, target_symbol)
            in_disp = (target_symbol and target_symbol.upper() in reg_disp.upper())
            in_part = (reg_db_id is not None and reg_db_id in matched_db_ids) or any(
                n and n in reg_disp.upper() for n in matched_names
            )

            if in_reg or in_disp or in_part:
                roles.append({
                    "role": "NEGATIVE_REGULATOR",
                    "direction": "NEGATIVE",  # Explicit negative regulation
                    "raw_field": "negativeRegulation",
                    "object_name": reg_disp or "NegativeRegulation",
                    "schema_class": reg.get("schemaClass", "NegativeRegulation"),
                })

        # 4. Requirement
        for req in reaction_detail.get("requirement") or []:
            if not isinstance(req, dict):
                continue
            req_disp = str(req.get("displayName") or "")
            regulator = req.get("regulator", {})
            reg_db_id = regulator.get("dbId") if isinstance(regulator, dict) else None

            in_req = cls.entity_matches_target(regulator, clean_target_acc, target_symbol)
            in_disp = (target_symbol and target_symbol.upper() in req_disp.upper())
            in_part = (reg_db_id is not None and reg_db_id in matched_db_ids) or any(
                n and n in req_disp.upper() for n in matched_names
            )

            if in_req or in_disp or in_part:
                roles.append({
                    "role": "REQUIREMENT",
                    "direction": "UNKNOWN",
                    "raw_field": "requirement",
                    "object_name": req_disp or "Requirement",
                    "schema_class": req.get("schemaClass", "Requirement"),
                })

        # 5. Input
        for inp in reaction_detail.get("input") or []:
            if not isinstance(inp, dict):
                continue
            inp_disp = str(inp.get("displayName") or "")
            inp_db_id = inp.get("dbId")

            in_inp = cls.entity_matches_target(inp, clean_target_acc, target_symbol)
            in_disp = (target_symbol and target_symbol.upper() in inp_disp.upper())
            in_part = (inp_db_id is not None and inp_db_id in matched_db_ids) or any(
                n and n in inp_disp.upper() for n in matched_names
            )

            if in_inp or in_disp or in_part:
                sc = inp.get("schemaClass", "Input")
                role_name = "COMPLEX_COMPONENT" if "Complex" in sc else ("ENTITY_SET_MEMBER" if "Set" in sc else "INPUT")
                roles.append({
                    "role": role_name,
                    "direction": "UNKNOWN",
                    "raw_field": "input",
                    "object_name": inp_disp or "Input",
                    "schema_class": sc,
                })

        # 6. Output
        for out in reaction_detail.get("output") or []:
            if not isinstance(out, dict):
                continue
            out_disp = str(out.get("displayName") or "")
            out_db_id = out.get("dbId")

            in_out = cls.entity_matches_target(out, clean_target_acc, target_symbol)
            in_disp = (target_symbol and target_symbol.upper() in out_disp.upper())
            in_part = (out_db_id is not None and out_db_id in matched_db_ids) or any(
                n and n in out_disp.upper() for n in matched_names
            )

            if in_out or in_disp or in_part:
                sc = out.get("schemaClass", "Output")
                role_name = "COMPLEX_COMPONENT" if "Complex" in sc else ("ENTITY_SET_MEMBER" if "Set" in sc else "OUTPUT")
                roles.append({
                    "role": role_name,
                    "direction": "UNKNOWN",
                    "raw_field": "output",
                    "object_name": out_disp or "Output",
                    "schema_class": sc,
                })

        # Fallback to participants if no specific role was matched
        if not roles:
            for p in matched_participants:
                sc = p.get("schemaClass", "PhysicalEntity")
                role_name = "COMPLEX_COMPONENT" if "Complex" in sc else ("ENTITY_SET_MEMBER" if "Set" in sc else "PARTICIPANT")
                roles.append({
                    "role": role_name,
                    "direction": "UNKNOWN",
                    "raw_field": "participants",
                    "object_name": p.get("displayName", "") or "Participant",
                    "schema_class": sc,
                })

        # Deep fallback: if reaction came from UniProt mapping but participants were unexpanded complexes
        if not roles:
            # Check inputs for Complex or DefinedSet
            for inp in reaction_detail.get("input") or []:
                if isinstance(inp, dict):
                    sc = inp.get("schemaClass", "")
                    if "Complex" in sc or "Set" in sc:
                        role_name = "COMPLEX_COMPONENT" if "Complex" in sc else "ENTITY_SET_MEMBER"
                        roles.append({
                            "role": role_name,
                            "direction": "UNKNOWN",
                            "raw_field": "input",
                            "object_name": inp.get("displayName", "") or "Complex Input",
                            "schema_class": sc,
                        })
                        break

            if not roles:
                for out in reaction_detail.get("output") or []:
                    if isinstance(out, dict):
                        sc = out.get("schemaClass", "")
                        if "Complex" in sc or "Set" in sc:
                            role_name = "COMPLEX_COMPONENT" if "Complex" in sc else "ENTITY_SET_MEMBER"
                            roles.append({
                                "role": role_name,
                                "direction": "UNKNOWN",
                                "raw_field": "output",
                                "object_name": out.get("displayName", "") or "Complex Output",
                                "schema_class": sc,
                            })
                            break

        return roles


