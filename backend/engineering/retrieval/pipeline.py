"""RetrievalPipeline — async parallel evidence retrieval engine.

Reference: 01_SYSTEM_ARCHITECTURE.md §8, 03_RETRIEVAL_SPECIFICATION.md
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime
from typing import Any

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.pathway import Pathway
from backend.core.domain.evidence import Evidence
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.approval_signal import ApprovalSignal
from backend.core.domain.reactome_reaction_evidence import ReactomeReactionEvidence
from backend.core.value_objects.biological_identifier import BiologicalIdentifierMapping
from backend.core.enums.evidence_type import EvidenceType
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.enums.statistical_direction import (
    OutcomeDirection,
    StatisticalReasonCode,
    OutcomeEvaluationResult,
)
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector
from backend.engineering.retrieval.connectors.uniprot import UniProtConnector
from backend.engineering.retrieval.connectors.pubmed import PubMedConnector
from backend.engineering.retrieval.connectors.reactome import ReactomeConnector
from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector
from backend.engineering.retrieval.connectors.disgenet import DisGeNETConnector
from backend.engineering.retrieval.disease_relation import (
    DiseaseRelation,
    classify_disease_relation,
    matches_for_approval_anchor,
    matches_for_trial_attribution,
)
from backend.infrastructure.cache.raw_response_cache import (
    RawResponseCache,
    TTL_STRUCTURAL,
    TTL_ASSOCIATIONS,
    TTL_LITERATURE,
    TTL_CLINICAL_TRIALS,
)
# Phase 2: Extended literature sources
try:
    from backend.engineering.retrieval.connectors.openalex import OpenAlexConnector
    from backend.engineering.retrieval.connectors.semantic_scholar import SemanticScholarConnector
    _EXTENDED_SOURCES_AVAILABLE = True
except ImportError:
    _EXTENDED_SOURCES_AVAILABLE = False
# Phase 4: New free data sources
try:
    from backend.engineering.retrieval.connectors.europepmc import EuropePMCConnector
    from backend.engineering.retrieval.connectors.opentargets import OpenTargetsConnector
    from backend.engineering.retrieval.connectors.datts import DATTsConnector
    from backend.infrastructure.knowledge.drugmechdb_client import DrugMechDBClient
    from backend.core.value_objects.therapeutic_direction_evidence import (
        OpenTargetsDoEEvidence,
        DATTsEvidence,
        DrugMechDBEvidence,
        TherapeuticDirectionEvidence,
    )
    from backend.reasoning.directional.directional_evidence_builder import DirectionalEvidenceBuilder
    _NEW_SOURCES_AVAILABLE = True
except ImportError:
    _NEW_SOURCES_AVAILABLE = False

logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """Async parallel retrieval pipeline that queries all data sources concurrently.

    Implements Phase 2 parallel execution from 01_SYSTEM_ARCHITECTURE.md:
    - ChEMBL, UniProt, PubMed, Reactome, ClinicalTrials queried in parallel
    - Results aggregated into a sealed RetrievalPackage

    Failure handling:
    - UniProt/ChEMBL failures → halt (SourceUnavailableError propagated)
    - Reactome/PubMed/ClinicalTrials failures → degrade gracefully, log warning
    """

    def __init__(
        self,
        ncbi_api_key: str | None = None,
        disgenet_api_key: str | None = None,
        semantic_scholar_api_key: str | None = None,
        db_path: str = "data/cynthera.db",
        bypass_raw_cache: bool = False,
    ) -> None:
        """Initialize the retrieval pipeline.

        Args:
            ncbi_api_key: Optional NCBI API key for higher PubMed rate limits.
            disgenet_api_key: Optional DisGeNET API key.
            semantic_scholar_api_key: Optional Semantic Scholar API key for higher rate limits.
            db_path: Path to the SQLite database for raw response cache.
            bypass_raw_cache: If True, skip cache reads (force fresh API calls).
                              Cache writes still occur so subsequent runs benefit.
        """
        import os
        from backend.core.utils.api_keys import sanitize_api_key
        self._ncbi_api_key = sanitize_api_key(ncbi_api_key)
        self._disgenet_api_key = sanitize_api_key(disgenet_api_key)
        self._semantic_scholar_api_key = sanitize_api_key(
            semantic_scholar_api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        )
        self._raw_cache = RawResponseCache(db_path=db_path)
        self._bypass_raw_cache = bypass_raw_cache

    async def execute(
        self,
        drug: Drug,
        disease: Disease,
        hypothesis_id: uuid.UUID,
    ) -> RetrievalPackage:
        """Execute the sequential-parallel retrieval pipeline.

        Phase 1: Sequential ID Fetch (ChEMBL first to get target UniProt accessions)
        Phase 2: Parallel Fetch (UniProt, Reactome, PubMed, ClinicalTrials in parallel)
        """
        logger.info(
            "retrieval_pipeline_start",
            extra={
                "drug": drug.name,
                "disease": disease.name,
                "hypothesis_id": str(hypothesis_id),
            },
        )

        chembl_id = drug.chembl_id or drug.name
        sources_queried: list[str] = []
        sources_failed: list[str] = []
        cache_hits: int = 0
        cache_misses: int = 0

        targets: list[Target] = []
        proteins: list[Protein] = []
        pathways: list[Pathway] = []
        evidence_records: list[Evidence] = []
        clinical_trials: list[ClinicalTrial] = []
        validated_disease_genes: dict[str, float] = {}

        # --- Phase 1: Sequential Fetch (ChEMBL — bioactivities + indications + molecule details) ---
        try:
            chembl_data = await self._fetch_chembl(chembl_id)
            sources_queried.append("chembl")
            targets, chembl_evidence = self._parse_chembl_data(chembl_data, drug)
            evidence_records.extend(chembl_evidence)
        except Exception as exc:
            sources_failed.append("chembl")
            logger.error("chembl_failed", extra={"error": str(exc)})
            chembl_data = {}

        # Extract unique UniProt IDs from targets to fetch in Phase 2
        uniprot_ids = list(set(t.protein_uniprot for t in targets if t.protein_uniprot))
        uniprot_to_sym: dict[str, str] = {}
        for t in targets:
            if t.protein_uniprot:
                # Target entity might have mechanism/provenance, symbol resolved in UniProt/Reactome
                uniprot_to_sym[t.protein_uniprot] = getattr(t, "gene_symbol", "")

        # --- Phase 2: Parallel Fetch (core sources) ---
        results = await asyncio.gather(
            self._fetch_uniprot(uniprot_ids),
            self._fetch_pubmed(drug.name, disease.name),
            self._fetch_reactome(uniprot_ids, uniprot_to_sym),
            self._fetch_clinicaltrials(drug.name, disease.name),
            self._fetch_disgenet(disease),
            return_exceptions=True,
        )

        uniprot_data, pubmed_data, reactome_data, trials_data, disgenet_data = results

        # --- Phase 2 Extended: OpenAlex + Semantic Scholar (non-critical) ---
        if _EXTENDED_SOURCES_AVAILABLE:
            ext_results = await asyncio.gather(
                self._fetch_openalex(drug.name, disease.name, hypothesis_id),
                self._fetch_semantic_scholar(drug.name, disease.name, hypothesis_id),
                return_exceptions=True,
            )
            openalex_ev, s2_ev = ext_results
            if isinstance(openalex_ev, Exception):
                sources_failed.append("openalex")
                logger.debug("openalex_failed", extra={"error": str(openalex_ev)})
            else:
                sources_queried.append("openalex")
                if isinstance(openalex_ev, list) and openalex_ev:
                    evidence_records.extend(openalex_ev)

            if isinstance(s2_ev, Exception):
                sources_failed.append("semantic_scholar")
                logger.debug("semantic_scholar_failed", extra={"error": str(s2_ev)})
            else:
                sources_queried.append("semantic_scholar")
                if isinstance(s2_ev, list) and s2_ev:
                    evidence_records.extend(s2_ev)

        # Process UniProt proteins
        if isinstance(uniprot_data, Exception):
            sources_failed.append("uniprot")
            logger.warning("uniprot_failed", extra={"error": str(uniprot_data)})
        else:
            sources_queried.append("uniprot")
            proteins = self._parse_uniprot_data(uniprot_data)

        # Process PubMed literature
        if isinstance(pubmed_data, Exception):
            sources_failed.append("pubmed")
            logger.warning("pubmed_failed", extra={"error": str(pubmed_data)})
        else:
            sources_queried.append("pubmed")
            lit_evidence = self._parse_pubmed_data(pubmed_data, drug, disease)
            evidence_records.extend(lit_evidence)

        # Collect source-provided biological identifier mappings
        identifier_mappings: list[BiologicalIdentifierMapping] = []
        reactome_reaction_evidence: list[ReactomeReactionEvidence] = []

        # Process Reactome pathways & reactions
        if isinstance(reactome_data, Exception):
            sources_failed.append("reactome")
            logger.warning("reactome_failed", extra={"error": str(reactome_data)})
        else:
            sources_queried.append("reactome")
            pathways = self._parse_reactome_data(reactome_data)
            reactome_reaction_evidence = reactome_data.get("reaction_evidence", [])
            for m in reactome_data.get("mappings", []):
                if isinstance(m, BiologicalIdentifierMapping):
                    identifier_mappings.append(m)
                elif isinstance(m, dict):
                    identifier_mappings.append(
                        BiologicalIdentifierMapping(
                            canonical_symbol=m.get("canonical_symbol"),
                            uniprot_accession=m.get("uniprot_accession"),
                            source=m.get("source", "Reactome"),
                            score=m.get("score"),
                            original_identifiers=tuple(m.get("original_identifiers", ())),
                        )
                    )

        # Process ClinicalTrials
        if isinstance(trials_data, Exception):
            sources_failed.append("clinicaltrials")
            logger.warning("clinicaltrials_failed", extra={"error": str(trials_data)})
        else:
            sources_queried.append("clinicaltrials")
            clinical_trials = self._parse_trials_data(trials_data, drug, disease)

        # Process DisGeNET disease-gene associations.
        # DisGeNET associations are indexed into validated_disease_genes, NOT evidence_records.
        # They represent gene-disease association strength, not literature claim quality.
        if isinstance(disgenet_data, Exception):
            logger.debug("disgenet_failed", extra={"error": str(disgenet_data)})
        elif disgenet_data:
            sources_queried.append("disgenet")
            dg_genes = self._parse_disgenet_to_gene_scores(disgenet_data)
            validated_disease_genes.update(dg_genes)
            logger.info(
                "disgenet_genes_indexed",
                extra={"gene_count": len(dg_genes)},
            )

        # --- Phase 2 Extended (b): Europe PMC + Open Targets ---
        if _NEW_SOURCES_AVAILABLE:
            new_results = await asyncio.gather(
                self._fetch_europepmc(drug.name, disease.name, hypothesis_id),
                self._fetch_opentargets(disease),
                return_exceptions=True,
            )
            epmc_ev, ot_result = new_results

            # Europe PMC → evidence_records (literature, same as OpenAlex/S2)
            if isinstance(epmc_ev, list):
                sources_queried.append("europepmc")
                evidence_records.extend(epmc_ev)
                # Track cache contribution — EuropePMC fetch updates cache_hits internally
            elif isinstance(epmc_ev, Exception):
                sources_failed.append("europepmc")
                logger.warning("europepmc_failed", extra={"error": str(epmc_ev)})

            # Open Targets → validated_disease_genes & identifier_mappings (NOT evidence_records)
            if isinstance(ot_result, dict):
                sources_queried.append("opentargets")
                if "gene_scores" in ot_result:
                    ot_scores = ot_result.get("gene_scores", {})
                    validated_disease_genes.update(ot_scores)
                    for m in ot_result.get("mappings", []):
                        if isinstance(m, BiologicalIdentifierMapping):
                            identifier_mappings.append(m)
                        elif isinstance(m, dict):
                            identifier_mappings.append(
                                BiologicalIdentifierMapping(
                                    canonical_symbol=m.get("canonical_symbol"),
                                    uniprot_accession=m.get("uniprot_accession"),
                                    source=m.get("source", "OpenTargets"),
                                    score=m.get("score"),
                                    original_identifiers=tuple(m.get("original_identifiers", ())),
                                )
                            )
                    logger.info(
                        "opentargets_genes_indexed",
                        extra={
                            "gene_count": len(ot_scores),
                            "mappings_count": len(ot_result.get("mappings", [])),
                        },
                    )
                else:
                    validated_disease_genes.update(ot_result)
                    logger.info(
                        "opentargets_genes_indexed",
                        extra={"gene_count": len(ot_result)},
                    )
            elif isinstance(ot_result, Exception):
                sources_failed.append("opentargets")
                logger.warning("opentargets_failed", extra={"error": str(ot_result)})

        # --- Phase 4C: Directional Evidence Retrieval (OT DoE, DATTs, DrugMechDB) ---
        opentargets_doe_evidence: list[OpenTargetsDoEEvidence] = []
        datts_evidence: list[DATTsEvidence] = []
        drugmechdb_evidence: list[DrugMechDBEvidence] = []
        therapeutic_direction_evidence: list[TherapeuticDirectionEvidence] = []

        if _NEW_SOURCES_AVAILABLE:
            doe_res, datts_res, dm_res = await asyncio.gather(
                self._fetch_opentargets_doe(targets, proteins, disease),
                self._fetch_datts(proteins, disease),
                self._fetch_drugmechdb(drug, disease, targets),
                return_exceptions=True,
            )

            if isinstance(doe_res, tuple):
                doe_list, doe_mappings = doe_res
                sources_queried.append("opentargets_doe")
                opentargets_doe_evidence.extend(doe_list)
                identifier_mappings.extend(doe_mappings)
            elif isinstance(doe_res, list):
                sources_queried.append("opentargets_doe")
                opentargets_doe_evidence.extend(doe_res)
            elif isinstance(doe_res, Exception):
                sources_failed.append("opentargets_doe")
                logger.warning("opentargets_doe_failed", extra={"error": str(doe_res)})

            if isinstance(datts_res, list):
                sources_queried.append("datts")
                datts_evidence.extend(datts_res)
            elif isinstance(datts_res, Exception):
                sources_failed.append("datts")
                logger.warning("datts_failed", extra={"error": str(datts_res)})

            if isinstance(dm_res, list):
                sources_queried.append("drugmechdb")
                drugmechdb_evidence.extend(dm_res)
            elif isinstance(dm_res, Exception):
                sources_failed.append("drugmechdb")
                logger.warning("drugmechdb_failed", extra={"error": str(dm_res)})

        # --- Determine approval signal from retrieved indication data ---
        approval_signal = self._parse_indication_data(
            chembl_data.get("indications", {}),
            chembl_data.get("molecule_details", {}),
            disease.name,
        )

        # --- Active-form indication rollup (Fix 2) ---
        # If no disease-matched indication found for the parent molecule,
        # try querying active-form ChEMBL IDs (salts/esters that may carry
        # the actual approved indications in ChEMBL).
        if (
            approval_signal is not None
            and not approval_signal.is_approved
        ):
            approval_signal = await self._try_active_form_indications(
                chembl_data, disease.name, approval_signal
            )

        # --- Determine clinical trial retrieval status (not just count) ---
        if "clinicaltrials" in sources_failed:
            ct_status = "API_FAILURE"
        elif "clinicaltrials" in sources_queried and len(clinical_trials) == 0:
            ct_status = "NOT_FOUND"
        elif len(clinical_trials) > 0:
            ct_status = "RETRIEVED"
        else:
            ct_status = "NOT_ATTEMPTED"

        # --- Determine retrieval confidence ---
        confidence = self._compute_confidence(
            targets, evidence_records, pathways, clinical_trials, sources_failed
        )

        # Preliminary package for directional builder normalization
        package_prelim = RetrievalPackage(
            hypothesis_id=hypothesis_id,
            drug=drug,
            disease=disease,
            targets=targets,
            proteins=proteins,
            pathways=pathways,
            evidence_records=evidence_records,
            clinical_trials=clinical_trials,
            retrieval_confidence=confidence,
            sources_queried=sources_queried,
            sources_failed=sources_failed,
            sealed_at=datetime.utcnow(),
            approval_signal=approval_signal,
            clinical_trial_retrieval_status=ct_status,
            validated_disease_genes=validated_disease_genes,
            identifier_mappings=identifier_mappings,
            reactome_reaction_evidence=reactome_reaction_evidence,
            opentargets_doe_evidence=opentargets_doe_evidence,
            datts_evidence=datts_evidence,
            drugmechdb_evidence=drugmechdb_evidence,
            therapeutic_direction_evidence=[],
        )

        # Build normalized TherapeuticDirectionEvidence
        try:
            builder = DirectionalEvidenceBuilder()
            therapeutic_direction_evidence = builder.build_all(package_prelim)
        except Exception as exc:
            logger.warning("directional_evidence_builder_failed", extra={"error": str(exc)})
            therapeutic_direction_evidence = []

        package = RetrievalPackage(
            hypothesis_id=hypothesis_id,
            drug=drug,
            disease=disease,
            targets=targets,
            proteins=proteins,
            pathways=pathways,
            evidence_records=evidence_records,
            clinical_trials=clinical_trials,
            retrieval_confidence=confidence,
            sources_queried=sources_queried,
            sources_failed=sources_failed,
            sealed_at=datetime.utcnow(),
            approval_signal=approval_signal,
            clinical_trial_retrieval_status=ct_status,
            validated_disease_genes=validated_disease_genes,
            identifier_mappings=identifier_mappings,
            reactome_reaction_evidence=reactome_reaction_evidence,
            opentargets_doe_evidence=opentargets_doe_evidence,
            datts_evidence=datts_evidence,
            drugmechdb_evidence=drugmechdb_evidence,
            therapeutic_direction_evidence=therapeutic_direction_evidence,
        )

        # Pipeline summary: cache stats for this run
        cache_stats = self._raw_cache.stats()
        logger.info(
            "retrieval_pipeline_complete",
            extra={
                "hypothesis_id": str(hypothesis_id),
                "evidence_count": len(evidence_records),
                "trial_count": len(clinical_trials),
                "pathway_count": len(pathways),
                "confidence": confidence,
                "sources_failed": sources_failed,
                "validated_gene_count": len(validated_disease_genes),
                "raw_cache_entries": cache_stats["active_entries"],
                "raw_cache_hits": cache_stats["total_cache_hits"],
            },
        )
        return package

    async def _fetch_chembl(self, chembl_id: str) -> dict[str, Any]:
        async with ChEMBLConnector() as conn:
            bioactivities = await conn.fetch(chembl_id)
            mechanisms = await conn.fetch_targets(chembl_id)

            # Fetch molecule details (max_phase, synonyms) and indications in parallel
            mol_details, ind_data = await asyncio.gather(
                conn.fetch_molecule_details(chembl_id),
                conn.fetch_indications(chembl_id),
                return_exceptions=True,
            )
            if isinstance(mol_details, Exception):
                logger.debug("chembl_mol_details_failed", extra={"error": str(mol_details)})
                mol_details = {}
            if isinstance(ind_data, Exception):
                logger.debug("chembl_ind_data_failed", extra={"error": str(ind_data)})
                ind_data = {"indications": []}

            # Prioritize target ChEMBL IDs from curated mechanism records FIRST,
            # falling back to frequency-ranked targets from bioactivities.
            mech_list = mechanisms.get("mechanisms", []) if isinstance(mechanisms, dict) else []
            mech_target_ids = [
                m.get("target_chembl_id")
                for m in mech_list
                if m.get("target_chembl_id")
            ]

            activities = bioactivities.get("activities", []) if isinstance(bioactivities, dict) else []
            activities_to_parse = activities[:50]
            target_id_counts: dict[str, int] = {}
            for act in activities_to_parse:
                tid = act.get("target_chembl_id")
                if tid:
                    target_id_counts[tid] = target_id_counts.get(tid, 0) + 1

            # Combined list: curated mechanism targets first, then top bioactivity targets up to 15 total
            bioactivity_target_ids = sorted(target_id_counts, key=target_id_counts.get, reverse=True)
            combined_target_ids: list[str] = []
            for tid in mech_target_ids + bioactivity_target_ids:
                if tid not in combined_target_ids:
                    combined_target_ids.append(tid)
            target_ids_to_fetch = combined_target_ids[:8]

            target_details_dict: dict[str, Any] = {}

            async def fetch_target_details(tid: str):
                try:
                    url = f"{conn.base_url}/target/{tid}.json"
                    res = await conn._get(url)
                    target_details_dict[tid] = res
                except Exception as e:
                    logger.debug("target_detail_fetch_failed", extra={"target_id": tid, "error": str(e)})

            if target_ids_to_fetch:
                await asyncio.gather(*(fetch_target_details(tid) for tid in target_ids_to_fetch))

            return {
                "bioactivities": bioactivities,
                "mechanisms": mechanisms,
                "target_details": target_details_dict,
                "molecule_details": mol_details,
                "indications": ind_data,
            }

    async def _try_active_form_indications(
        self,
        chembl_data: dict[str, Any],
        disease_name: str,
        fallback_signal: ApprovalSignal | None,
    ) -> ApprovalSignal | None:
        """Try active-form ChEMBL IDs when the parent molecule has no matched indication.

        Some drugs (e.g., Fluticasone) are parent INN names whose approved indications
        are registered in ChEMBL under active salt/ester forms (Fluticasone Propionate,
        Fluticasone Furoate).  This method resolves those active forms dynamically via
        ChEMBL pref_name prefix search, NOT via the parent's molecule_synonyms (which
        are often empty for parent entries).

        No drug names are hardcoded — active-form candidates are discovered from
        ChEMBL using a prefix query on pref_name.

        Validation gates:
        1. Candidate pref_name must start with the parent drug name.
        2. Candidate must have a suffix (salt/ester form, not the same molecule).
        3. Candidate must be a different ChEMBL ID from the parent.
        4. Only indication data that matches the queried disease is used.

        Args:
            chembl_data: The full ChEMBL data dict from _fetch_chembl().
            disease_name: The queried disease name.
            fallback_signal: The ApprovalSignal to return if no active form matches.

        Returns:
            An improved ApprovalSignal if an active form has a disease-matched
            indication, otherwise the original fallback_signal.
        """
        mol_details = chembl_data.get("molecule_details", {})
        parent_name = (mol_details.get("pref_name") or "").strip()
        parent_name_lower = parent_name.lower()

        if not parent_name or len(parent_name) < 3:
            return fallback_signal

        # --- Strategy 1: Dynamic discovery via ChEMBL pref_name prefix search ---
        active_form_candidates: list[dict[str, Any]] = []

        async with ChEMBLConnector() as conn:
            try:
                url = f"{conn.base_url}/molecule.json"
                search_res = await conn._get(url, params={
                    "pref_name__istartswith": parent_name,
                    "format": "json",
                    "limit": 10,
                })
                for mol in search_res.get("molecules", []):
                    cand_name = (mol.get("pref_name") or "").strip()
                    cand_id = mol.get("molecule_chembl_id", "")
                    cand_lower = cand_name.lower()

                    # Gate 1: Must start with parent name
                    if not cand_lower.startswith(parent_name_lower):
                        continue
                    # Gate 2: Must have a suffix (salt/ester, not the parent itself)
                    if cand_lower == parent_name_lower:
                        continue
                    if len(cand_lower) <= len(parent_name_lower) + 2:
                        continue
                    # Gate 3: Must be a different ChEMBL ID
                    parent_chembl_ids = set()
                    if chembl_data.get("bioactivities", {}).get("activities"):
                        first_act = chembl_data["bioactivities"]["activities"][0]
                        pid = first_act.get("molecule_chembl_id", "")
                        if pid:
                            parent_chembl_ids.add(pid)
                    # Also guard by the molecule details if available
                    if mol_details.get("pref_name", "").strip().lower() == cand_lower:
                        continue

                    active_form_candidates.append({
                        "name": cand_name,
                        "chembl_id": cand_id,
                    })
            except Exception as exc:
                logger.debug(
                    "active_form_prefix_search_failed",
                    extra={"parent": parent_name, "error": str(exc)},
                )

            # --- Strategy 2: Fallback to synonym-based discovery (original approach) ---
            if not active_form_candidates:
                synonyms = mol_details.get("molecule_synonyms", [])
                for syn in synonyms:
                    syn_clean = syn.strip()
                    syn_lower = syn_clean.lower()
                    if (
                        syn_lower != parent_name_lower
                        and syn_lower.startswith(parent_name_lower)
                        and len(syn_lower) > len(parent_name_lower) + 2
                    ):
                        active_form_candidates.append({
                            "name": syn_clean,
                            "chembl_id": None,  # needs resolution
                        })

            if not active_form_candidates:
                return fallback_signal

            # Limit to 4 active forms to avoid excessive API calls
            active_form_candidates = active_form_candidates[:4]
            logger.info(
                "active_form_rollup_attempting",
                extra={
                    "parent": parent_name,
                    "active_forms": [c["name"] for c in active_form_candidates],
                    "disease": disease_name,
                },
            )

            best_signal = fallback_signal

            for candidate in active_form_candidates:
                try:
                    af_chembl_id = candidate["chembl_id"]

                    # Resolve ChEMBL ID if not already known (synonym-based path)
                    if not af_chembl_id:
                        search_res = await conn.search_molecule(candidate["name"])
                        molecules = search_res.get("molecules", [])
                        if not molecules:
                            continue
                        af_chembl_id = molecules[0].get("molecule_chembl_id")
                        if not af_chembl_id:
                            continue

                    # Fetch indications and molecule details for the active form
                    af_ind_data, af_mol_details = await asyncio.gather(
                        conn.fetch_indications(af_chembl_id),
                        conn.fetch_molecule_details(af_chembl_id),
                        return_exceptions=True,
                    )

                    if isinstance(af_ind_data, Exception):
                        continue
                    if isinstance(af_mol_details, Exception):
                        af_mol_details = {}

                    af_signal = self._parse_indication_data(
                        af_ind_data, af_mol_details, disease_name, source=f"chembl:{candidate['name']}"
                    )

                    if af_signal is not None and (
                        af_signal.is_approved
                        or af_signal.match_confidence > (best_signal.match_confidence if best_signal else 0.0)
                    ):
                        logger.info(
                            "active_form_indication_match",
                            extra={
                                "active_form": candidate["name"],
                                "chembl_id": af_chembl_id,
                                "matched_term": af_signal.matched_indication_term,
                                "max_phase": af_signal.max_phase,
                                "confidence": af_signal.match_confidence,
                            },
                        )
                        best_signal = af_signal
                        if af_signal.is_approved:
                            break  # Found an approved match, no need to continue

                except Exception as exc:
                    logger.debug(
                        "active_form_indication_failed",
                        extra={"active_form": candidate["name"], "error": str(exc)},
                    )

        return best_signal


    async def _fetch_uniprot(self, uniprot_ids: list[str]) -> dict[str, Any]:
        """Fetch protein information from UniProt.

        Cache is applied at the per-protein level (inner fetch_one call),
        not the batch level. This allows cache hits to be shared across
        different drug queries that target the same protein (e.g. COX-1
        appears across many NSAID queries).
        """
        if not uniprot_ids:
            return {"proteins": []}
        async with UniProtConnector() as conn:
            proteins = []

            async def fetch_one(uid: str):
                cache_key = RawResponseCache.make_key("uniprot", uid, "entry.json")
                if not self._bypass_raw_cache:
                    cached = self._raw_cache.get(cache_key, source_name="uniprot")
                    if cached is not None:
                        proteins.append(cached)
                        return
                try:
                    res = await conn.fetch(uid)
                    proteins.append(res)
                    self._raw_cache.set(cache_key, "uniprot", uid, "entry.json", res, TTL_STRUCTURAL)
                except Exception as e:
                    logger.debug("uniprot_fetch_one_failed", extra={"uniprot_id": uid, "error": str(e)})

            await asyncio.gather(*(fetch_one(uid) for uid in uniprot_ids[:5]))
            return {"proteins": proteins}

    async def _fetch_pubmed(self, drug_name: str, disease_name: str) -> dict[str, Any]:
        async with PubMedConnector(api_key=self._ncbi_api_key) as conn:
            return await conn.fetch(drug_name, disease_name, max_results=50)

    async def _fetch_reactome(
        self,
        uniprot_ids: list[str],
        uniprot_to_symbol: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Fetch Reactome pathway and reaction/event data for target UniProt accessions.r UniProt participant lists.

        Two-phase retrieval:
          Phase 1 (forward): For each target UniProt ID, fetch which pathways contain it.
          Phase 2 (reverse): For each unique pathway, fetch which UniProt proteins participate.

        Cache is applied at the per-item inner call level (Gap 2 fix):
          - Phase 1: per-protein pathway list cached under reactome_pathways:{uid}
          - Phase 2: per-pathway participant list cached under reactome_participants:{stid}
        This enables cross-query cache reuse when the same protein or pathway appears
        in queries for different drugs.
        """
        if not uniprot_ids:
            return {"pathways": []}
        async with ReactomeConnector() as conn:
            # Phase 1: forward direction — which pathways contain each protein?
            raw_pathways: list[dict] = []
            target_to_pathways: dict[str, list[str]] = {}

            async def fetch_pathways_for_protein(uid: str) -> None:
                cache_key = RawResponseCache.make_key("reactome_pathways", uid, "allForms")
                if not self._bypass_raw_cache:
                    cached = self._raw_cache.get(cache_key, source_name="reactome_pathways")
                    if cached is not None:
                        pws = cached.get("pathways", [])
                        raw_pathways.extend(pws)
                        target_to_pathways[uid] = [p.get("stId") for p in pws if p.get("stId")]
                        return
                try:
                    res = await conn.fetch(uid)
                    pws = res.get("pathways", [])
                    raw_pathways.extend(pws)
                    target_to_pathways[uid] = [p.get("stId") for p in pws if p.get("stId")]
                    self._raw_cache.set(
                        cache_key, "reactome_pathways", uid, "allForms", res, TTL_STRUCTURAL
                    )
                except Exception as e:
                    logger.debug(
                        "reactome_fetch_one_failed",
                        extra={"uniprot_id": uid, "error": str(e)},
                    )
                    target_to_pathways[uid] = []

            await asyncio.gather(*(fetch_pathways_for_protein(uid) for uid in uniprot_ids[:5]))

            # Deduplicate pathways by stId, preserving insertion order.
            seen_stids: dict[str, dict] = {}
            for pw in raw_pathways:
                stid = pw.get("stId")
                if stid and stid not in seen_stids:
                    seen_stids[stid] = pw

            # Phase 2: reaction & event level evidence for target proteins
            # Maps target -> specific reactions -> roles -> existing pathways
            sem = asyncio.Semaphore(3)
            reaction_evidence_list: list[ReactomeReactionEvidence] = []
            target_reactions_map: dict[str, list[dict]] = {}

            async def fetch_reactions_for_target(uid: str) -> None:
                async with sem:
                    cache_key = RawResponseCache.make_key(
                        "reactome_target_reactions", uid, "reactions"
                    )
                    if not self._bypass_raw_cache:
                        cached = self._raw_cache.get(
                            cache_key, source_name="reactome_target_reactions"
                        )
                        if cached is not None and isinstance(cached, list):
                            target_reactions_map[uid] = cached
                            return
                    res = await conn.fetch_reactions(uid)
                    target_reactions_map[uid] = res
                    self._raw_cache.set(
                        cache_key, "reactome_target_reactions", uid, "reactions", res, TTL_STRUCTURAL
                    )

            await asyncio.gather(*(fetch_reactions_for_target(uid) for uid in uniprot_ids[:8]))

            # Collect unique reactions across targets (capped to top 25 reactions)
            unique_rxn_stids: list[str] = []
            for uid, rxns in target_reactions_map.items():
                for rxn in rxns:
                    rst = rxn.get("stId")
                    if rst and rst not in unique_rxn_stids:
                        unique_rxn_stids.append(rst)

            rxn_details_map: dict[str, dict] = {}
            rxn_ancestors_map: dict[str, list] = {}
            rxn_participants_map: dict[str, list] = {}

            async def fetch_single_rxn_info(rst: str) -> None:
                async with sem:
                    # 1. Reaction details
                    det_key = RawResponseCache.make_key("reactome_rxn_detail", rst, "detail")
                    cached_det = self._raw_cache.get(det_key, source_name="reactome_rxn_detail") if not self._bypass_raw_cache else None
                    if cached_det is not None and isinstance(cached_det, dict):
                        det = cached_det
                    else:
                        det = await conn.fetch_reaction_details(rst)
                        self._raw_cache.set(det_key, "reactome_rxn_detail", rst, "detail", det, TTL_STRUCTURAL)
                    rxn_details_map[rst] = det

                    # 2. Reaction ancestors
                    anc_key = RawResponseCache.make_key("reactome_rxn_anc", rst, "ancestors")
                    cached_anc = self._raw_cache.get(anc_key, source_name="reactome_rxn_anc") if not self._bypass_raw_cache else None
                    if cached_anc is not None and isinstance(cached_anc, list):
                        anc = cached_anc
                    else:
                        anc = await conn.fetch_reaction_ancestors(rst)
                        self._raw_cache.set(anc_key, "reactome_rxn_anc", rst, "ancestors", anc, TTL_STRUCTURAL)
                    rxn_ancestors_map[rst] = anc

                    # 3. Participating entities
                    part_key = RawResponseCache.make_key("reactome_rxn_part", rst, "entities")
                    cached_part = self._raw_cache.get(part_key, source_name="reactome_rxn_part") if not self._bypass_raw_cache else None
                    if cached_part is not None and isinstance(cached_part, list):
                        part = cached_part
                    else:
                        part = await conn.fetch_participating_entities(rst)
                        self._raw_cache.set(part_key, "reactome_rxn_part", rst, "entities", part, TTL_STRUCTURAL)
                    rxn_participants_map[rst] = part

            await asyncio.gather(*(fetch_single_rxn_info(rst) for rst in unique_rxn_stids[:25]))

            # Construct ReactomeReactionEvidence records
            seen_evidence_keys: set[tuple[str, str, str, str | None]] = set()

            for uid, rxns in target_reactions_map.items():
                for rxn in rxns:
                    rst = rxn.get("stId")
                    if not rst:
                        continue
                    det = rxn_details_map.get(rst, {})
                    anc = rxn_ancestors_map.get(rst, [])
                    part = rxn_participants_map.get(rst, [])

                    # Species check (prefer Homo sapiens or unspecified)
                    species_name = det.get("speciesName") or rxn.get("speciesName") or "Homo sapiens"
                    if species_name and "homo sapiens" not in str(species_name).lower():
                        continue

                    # Extract roles
                    target_sym = (uniprot_to_symbol or {}).get(uid) or ""
                    roles = ReactomeConnector.extract_target_roles(
                        det, part, uid, target_symbol=target_sym if target_sym else None
                    )
                    if not roles:
                        roles = [{
                            "role": "PARTICIPANT",
                            "direction": "UNKNOWN",
                            "raw_field": "reactions",
                            "object_name": rxn.get("displayName", "Reaction"),
                            "schema_class": rxn.get("schemaClass", "Reaction"),
                        }]

                    # Extract compartment
                    compartment_list = det.get("compartment", [])
                    compartments: list[str] = []
                    if isinstance(compartment_list, list):
                        for c in compartment_list:
                            if isinstance(c, dict) and c.get("displayName"):
                                compartments.append(str(c.get("displayName")))
                    compartment_str = ", ".join(compartments) if compartments else None

                    # Extract ancestor pathways
                    ancestor_pathways: dict[str, str] = {}
                    if isinstance(anc, list):
                        for path in anc:
                            if isinstance(path, list):
                                for node in path:
                                    if isinstance(node, dict):
                                        sc = node.get("schemaClass", "")
                                        if "Pathway" in sc:
                                            pst = node.get("stId")
                                            pname = node.get("displayName", pst)
                                            if pst:
                                                ancestor_pathways[pst] = pname

                    # Map to known pathways in seen_stids
                    matched_any_pathway = False
                    for pw_stid, pw_obj in seen_stids.items():
                        if pw_stid in ancestor_pathways:
                            matched_any_pathway = True
                            pw_name = pw_obj.get("displayName", pw_stid)
                            mapping_type = "HIERARCHICAL_PATHWAY_MAPPING"

                            for r_info in roles:
                                ev_key = (uid, rst, r_info["role"], pw_stid)
                                if ev_key in seen_evidence_keys:
                                    continue
                                seen_evidence_keys.add(ev_key)

                                reaction_evidence_list.append(
                                    ReactomeReactionEvidence(
                                        target_canonical_id=uid,
                                        target_original_id=uid,
                                        reaction_id=rst,
                                        reaction_name=det.get("displayName") or rxn.get("displayName", "Unnamed reaction"),
                                        schema_class=det.get("schemaClass") or rxn.get("schemaClass", "Reaction"),
                                        target_role=r_info["role"],
                                        pathway_id=pw_stid,
                                        pathway_name=pw_name,
                                        mapping_type=mapping_type,
                                        direction=r_info.get("direction", "UNKNOWN"),
                                        source="REACTOME",
                                        source_id=rst,
                                        evidence_type="CURATED_REACTION",
                                        species=species_name,
                                        compartment=compartment_str,
                                        disease_context=det.get("isInDisease", rxn.get("isInDisease", False)),
                                        provenance={
                                            "reactome_reaction": rst,
                                            "pathway_id": pw_stid,
                                            "raw_field": r_info.get("raw_field", "catalystActivity"),
                                            "object_name": r_info.get("object_name", ""),
                                        },
                                    )
                                )

                    # If no known pathway matched directly, record reaction without pathway association
                    if not matched_any_pathway:
                        for r_info in roles:
                            ev_key = (uid, rst, r_info["role"], None)
                            if ev_key in seen_evidence_keys:
                                continue
                            seen_evidence_keys.add(ev_key)

                            reaction_evidence_list.append(
                                ReactomeReactionEvidence(
                                    target_canonical_id=uid,
                                    target_original_id=uid,
                                    reaction_id=rst,
                                    reaction_name=det.get("displayName") or rxn.get("displayName", "Unnamed reaction"),
                                    schema_class=det.get("schemaClass") or rxn.get("schemaClass", "Reaction"),
                                    target_role=r_info["role"],
                                    pathway_id=None,
                                    pathway_name=None,
                                    mapping_type="DIRECT_PATHWAY_MAPPING",
                                    direction=r_info.get("direction", "UNKNOWN"),
                                    source="REACTOME",
                                    source_id=rst,
                                    evidence_type="CURATED_REACTION",
                                    species=species_name,
                                    compartment=compartment_str,
                                    disease_context=det.get("isInDisease", rxn.get("isInDisease", False)),
                                    provenance={
                                        "reactome_reaction": rst,
                                        "raw_field": r_info.get("raw_field", "catalystActivity"),
                                        "object_name": r_info.get("object_name", ""),
                                    },
                                )
                            )

            # Phase 3: Prioritized reverse participant fetching.
            # Fix: Ensure pathways required by reaction evidence are NEVER excluded by arbitrary cap.
            # Priority 1: Pathways referenced by reactome_reaction_evidence
            p1_reaction_pathways: list[str] = []
            for rev in reaction_evidence_list:
                if rev.pathway_id and rev.pathway_id in seen_stids and rev.pathway_id not in p1_reaction_pathways:
                    p1_reaction_pathways.append(rev.pathway_id)
            p1_set = set(p1_reaction_pathways)

            # Priority 2: Direct pathways associated with drug targets (interleaved across targets)
            p2_target_pathways: list[str] = []
            max_target_pws = max((len(pws) for pws in target_to_pathways.values()), default=0)
            for i in range(max_target_pws):
                for uid in uniprot_ids[:5]:
                    u_pws = target_to_pathways.get(uid, [])
                    if i < len(u_pws):
                        stid = u_pws[i]
                        if stid in seen_stids and stid not in p1_set and stid not in p2_target_pathways:
                            p2_target_pathways.append(stid)
            p2_set = set(p2_target_pathways)

            # Priority 3: Remaining pathways
            p3_remaining_pathways = [
                stid for stid in seen_stids.keys() if stid not in p1_set and stid not in p2_set
            ]

            # Build prioritized fetch list:
            # ALL Priority 1 reaction pathways are guaranteed.
            # Priority 2 and Priority 3 fill up to MAX_ORDINARY_PARTICIPANT_FETCH (default 10).
            MAX_ORDINARY_PARTICIPANT_FETCH = 10
            remaining_slots = max(0, MAX_ORDINARY_PARTICIPANT_FETCH - len(p1_reaction_pathways))
            selected_pathway_stids = list(p1_reaction_pathways)
            if remaining_slots > 0:
                selected_pathway_stids.extend((p2_target_pathways + p3_remaining_pathways)[:remaining_slots])

            logger.info(
                "reactome_prioritized_pathway_fetch",
                extra={
                    "total_pathways_discovered": len(seen_stids),
                    "reaction_referenced_pathways": len(p1_reaction_pathways),
                    "target_associated_pathways": len(p2_target_pathways),
                    "priority_pathways_selected": len(selected_pathway_stids),
                    "selected_stids": selected_pathway_stids,
                },
            )

            participant_map: dict[str, list[str]] = {}
            participant_mappings: list[BiologicalIdentifierMapping] = []

            async def fetch_participants_for_pathway(stid: str) -> None:
                async with sem:
                    cache_key = RawResponseCache.make_key(
                        "reactome_participants", stid, "participants"
                    )
                    if not self._bypass_raw_cache:
                        cached = self._raw_cache.get(
                            cache_key, source_name="reactome_participants"
                        )
                        if cached is not None:
                            participant_map[stid] = cached.get("uniprot_ids", [])
                            for m in cached.get("mappings", []):
                                if isinstance(m, BiologicalIdentifierMapping):
                                    participant_mappings.append(m)
                                elif isinstance(m, dict):
                                    participant_mappings.append(
                                        BiologicalIdentifierMapping(
                                            canonical_symbol=m.get("canonical_symbol"),
                                            uniprot_accession=m.get("uniprot_accession"),
                                            source=m.get("source", "Reactome"),
                                            score=m.get("score"),
                                            original_identifiers=tuple(m.get("original_identifiers", ())),
                                        )
                                    )
                            return
                    try:
                        res = await conn.fetch_participants(stid)
                        participant_map[stid] = res.get("uniprot_ids", [])
                        for m in res.get("mappings", []):
                            if isinstance(m, BiologicalIdentifierMapping):
                                participant_mappings.append(m)
                            elif isinstance(m, dict):
                                participant_mappings.append(
                                    BiologicalIdentifierMapping(
                                        canonical_symbol=m.get("canonical_symbol"),
                                        uniprot_accession=m.get("uniprot_accession"),
                                        source=m.get("source", "Reactome"),
                                        score=m.get("score"),
                                        original_identifiers=tuple(m.get("original_identifiers", ())),
                                    )
                                )
                        self._raw_cache.set(
                            cache_key, "reactome_participants", stid, "participants", res, TTL_STRUCTURAL
                        )
                    except Exception as e:
                        logger.debug(
                            "reactome_participants_fetch_failed",
                            extra={"stid": stid, "error": str(e)},
                        )
                        participant_map[stid] = []

            await asyncio.gather(*(fetch_participants_for_pathway(stid) for stid in selected_pathway_stids))

            # Attach participant lists to raw pathway dicts before parsing.
            for stid, pw in seen_stids.items():
                pw["_participant_uniprot_ids"] = participant_map.get(stid, [])

            return {
                "pathways": list(seen_stids.values()),
                "mappings": participant_mappings,
                "reaction_evidence": reaction_evidence_list,
            }

    async def _fetch_clinicaltrials(self, drug_name: str, disease_name: str) -> dict[str, Any]:
        async with ClinicalTrialsConnector() as conn:
            return await conn.fetch(drug_name, disease_name)

    async def _fetch_disgenet(self, disease: Disease) -> dict[str, Any]:
        """Fetch disease-gene associations from DisGeNET.

        Queries by the resolved MeSH ID when available (ontology-grounded),
        falling back to the disease name string.
        """
        disease_id = disease.mesh_id or disease.name.lower().replace(" ", "+")
        try:
            async with DisGeNETConnector(api_key=self._disgenet_api_key) as conn:
                result = await conn.fetch(disease_id=disease_id)
                return result
        except Exception as exc:
            logger.debug("disgenet_fetch_failed", extra={"error": str(exc)})
            return {}

    @staticmethod
    def _normalize_disease_variants(disease_name: str) -> list[str]:
        """Generate ontology-aware parent-term variants of a disease name.

        Handles common medical naming patterns where a queried disease is a
        subtype qualifier on a parent disease (e.g., 'ER-positive breast cancer'
        → 'breast cancer').  Returns the original name plus any derived parent
        terms (deduplicated, order-preserved).

        No drug names, disease names, or biomedical facts are hardcoded — this
        is purely a structural/linguistic normalization.

        Patterns handled:
        - Receptor-status qualifiers: 'ER-positive X', 'HER2-positive X'
        - Directional qualifiers: 'Secondary prevention of X'
        - Molecular subtypes: 'KRAS-mutant X', 'BRCA1-related X'
        """
        variants: list[str] = [disease_name]
        name_lower = disease_name.lower().strip()

        # Pattern 1: "XX-positive / XX-negative / XX-mutant / XX-related disease"
        # E.g., "ER-positive breast cancer" → "breast cancer"
        for qualifier_pattern in [
            r"^(?:er|pr|her2|hr|triple|egfr|alk|pd-?l1|kras|braf|brca\d?|nras|flt3|idh\d?)"
            r"[- ]?(?:positive|negative|mutant|mutated|wild[- ]?type|amplified|overexpressing"
            r"|related|driven|high|low|expressing)\s+",
        ]:
            match = re.match(qualifier_pattern, name_lower, re.IGNORECASE)
            if match:
                parent = disease_name[match.end():].strip()
                if parent and len(parent) >= 4:
                    variants.append(parent)

        # Pattern 2: "Secondary prevention of X", "Primary prevention of X"
        prev_match = re.match(
            r"^(?:secondary|primary|tertiary)\s+prevention\s+of\s+",
            name_lower,
        )
        if prev_match:
            parent = disease_name[prev_match.end():].strip()
            if parent and len(parent) >= 4:
                variants.append(parent)

        # Pattern 3: "advanced X", "metastatic X", "refractory X", "recurrent X"
        stage_match = re.match(
            r"^(?:advanced|metastatic|refractory|relapsed|recurrent|chronic"
            r"|acute|early[- ]?stage|late[- ]?stage|localized|unresectable)\s+",
            name_lower,
        )
        if stage_match:
            parent = disease_name[stage_match.end():].strip()
            if parent and len(parent) >= 4:
                variants.append(parent)

        # Pattern 4: Controlled clinical composite endpoints
        # Clinical composite prevention indications (such as "cardiovascular disease"
        # or "secondary prevention of cardiovascular disease") represent composite endpoints
        # whose regulatory approvals and clinical trial targets in ChEMBL are cataloged
        # under their constituent acute events (e.g., "myocardial infarction", "stroke").
        # Explicit, narrowly scoped decomposition through the disease normalization framework.
        composite_constituents: dict[str, list[str]] = {
            "cardiovascular disease": ["myocardial infarction", "stroke"],
            "cardiovascular diseases": ["myocardial infarction", "stroke"],
            "cvd": ["myocardial infarction", "stroke", "cardiovascular disease"],
        }
        for v in list(variants):
            vl = v.lower().strip()
            if vl in composite_constituents:
                for constituent in composite_constituents[vl]:
                    variants.append(constituent)

        # Deduplicate preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for v in variants:
            vl = v.lower()
            if vl not in seen:
                seen.add(vl)
                unique.append(v)
        return unique

    def _parse_indication_data(
        self,
        indication_data: dict[str, Any],
        molecule_data: dict[str, Any],
        disease_name: str,
        source: str = "chembl",
    ) -> ApprovalSignal | None:
        """Infer approval status from ChEMBL retrieved indication data.

        Uses fuzzy token matching to compare the queried disease_name against
        every EFO/MeSH indication term returned by ChEMBL. No drug names,
        disease names, or approval facts are hardcoded — the result is
        computed purely from retrieved data.

        Matching algorithm:
        1. Generate disease name variants (original + ontology-normalized parents)
        2. Tokenize both the queried disease variants and the indication term
        3. Compute token overlap ratio (Jaccard-like similarity)
        4. Consider a match if similarity > 0.35 or queried name is substring
        5. Select the best-matching indication
        6. Return ApprovalSignal based on max_phase_for_ind of best match

        Args:
            indication_data: Raw ChEMBL indication response dict.
            molecule_data: Raw ChEMBL molecule details dict.
            disease_name: The queried disease name (from user input).
            source: Provenance source string for this approval signal.

        Returns:
            ApprovalSignal built from retrieved data, or None if no ChEMBL data.
        """
        indications = indication_data.get("indications", [])
        if not indications and not molecule_data:
            return None

        # Count total approved indications for this drug (informational)
        approved_count = sum(
            1 for ind in indications
            if int(float(ind.get("max_phase_for_ind") or 0)) == 4
        )

        # Generate disease name variants for broader matching
        disease_variants = self._normalize_disease_variants(disease_name)

        best_match_phase = 0
        best_match_term = ""
        best_match_confidence = 0.0
        best_match_variant = disease_name

        for variant in disease_variants:
            # Tokenize queried disease variant
            query_tokens = set(
                re.sub(r"[^a-z0-9]", " ", variant.lower()).split()
            ) - {"the", "a", "an", "of", "and", "or", "for", "in", "to"}

            for ind in indications:
                efo_term = str(ind.get("efo_term") or "").lower()
                mesh_heading = str(ind.get("mesh_heading") or "").lower()
                max_phase = int(float(ind.get("max_phase_for_ind") or 0))

                # Try both EFO term and MeSH heading
                for term in (efo_term, mesh_heading):
                    if not term:
                        continue
                    term_tokens = set(
                        re.sub(r"[^a-z0-9]", " ", term).split()
                    ) - {"the", "a", "an", "of", "and", "or", "for", "in", "to"}

                    # Jaccard-like similarity on tokens
                    union = query_tokens | term_tokens
                    if not union:
                        continue
                    intersection = query_tokens & term_tokens

                    # Phase 2 Root Cause Fix: Generic category tokens must NOT establish
                    # therapeutic indication identity by themselves.
                    # Distinguishing disease/organ-specific components must match.
                    # Regression correction: removed the `has_meaningful_generic_only` fallback
                    # which allowed purely generic overlaps (e.g. {"cancer", "neoplasm"}) to
                    # establish indication identity across unrelated organ sites.
                    _GENERIC_DISEASE_TOKENS = {
                        "cancer", "cancers", "disease", "diseases", "disorder", "disorders",
                        "syndrome", "syndromes", "condition", "conditions", "neoplasm", "neoplasms",
                        "carcinoma", "carcinomas", "tumor", "tumors", "tumour", "tumours",
                        "malignant", "benign", "chronic", "acute", "primary", "secondary",
                        "advanced", "metastatic", "recurrent", "refractory",
                        "type", "stage", "grade", "positive", "negative",
                    }
                    specific_intersection = intersection - _GENERIC_DISEASE_TOKENS
                    has_specific_overlap = len(specific_intersection) > 0

                    if not has_specific_overlap:
                        continue

                    # Disease Relation Gate (§8 & §24):
                    # Sibling exclusions strictly reject approval anchor candidates (e.g. stroke vs hemorrhagic stroke)
                    orig_rel = classify_disease_relation(disease_name, term)
                    variant_rel = classify_disease_relation(variant, term)
                    if orig_rel == DiseaseRelation.SIBLING_EXCLUDED or variant_rel == DiseaseRelation.SIBLING_EXCLUDED:
                        logger.info(
                            "approval_indication_candidate_evaluated",
                            extra={
                                "queried_disease": disease_name,
                                "indication": term,
                                "disease_relation": "SIBLING_EXCLUDED",
                                "approval_anchor": False,
                                "disease_relation_policy": "APPROVAL_ANCHOR",
                            },
                        )
                        continue

                    # Rule -1 requires DiseaseRelation.SAME (Section 6 & 8)
                    is_anchor = matches_for_approval_anchor(disease_name, term) or (
                        variant != disease_name and matches_for_approval_anchor(variant, term)
                    )
                    if not is_anchor:
                        logger.info(
                            "approval_indication_candidate_evaluated",
                            extra={
                                "queried_disease": disease_name,
                                "indication": term,
                                "disease_relation": orig_rel.value,
                                "approval_anchor": False,
                                "disease_relation_policy": "APPROVAL_ANCHOR",
                            },
                        )
                        continue

                    logger.info(
                        "approval_indication_candidate_evaluated",
                        extra={
                            "queried_disease": disease_name,
                            "indication": term,
                            "disease_relation": "SAME",
                            "approval_anchor": True,
                            "disease_relation_policy": "APPROVAL_ANCHOR",
                        },
                    )

                    sim = len(intersection) / len(union)

                    # Substring containment boost (only when specific overlap exists)
                    q_clean = variant.lower().replace(" ", "")
                    t_clean = term.replace(" ", "")
                    if q_clean in t_clean or t_clean in q_clean:
                        sim = max(sim, 0.6)

                    # Apply a slight discount for parent-term matches (not the
                    # original query) to prefer exact matches when both exist.
                    if variant != disease_name:
                        sim *= 0.95

                    # Prioritize confirmed approved indications (Phase 4).
                    # Among disease-matched indications (DiseaseRelation.SAME), an approved
                    # Phase 4 indication establishes regulatory approval and must take precedence
                    # over lower-phase investigational records (e.g. Phase 3 trials) for the same disease.
                    # When phase status is equal, prefer higher lexical similarity.
                    candidate_rank = (max_phase == 4, max_phase, sim)
                    best_rank = (best_match_phase == 4, best_match_phase, best_match_confidence)
                    if candidate_rank > best_rank:
                        best_match_confidence = sim
                        best_match_term = term
                        best_match_phase = max_phase
                        best_match_variant = variant

        # Require minimum similarity to accept a match (prevents false positives)
        _MIN_MATCH_CONFIDENCE = 0.30
        if best_match_confidence < _MIN_MATCH_CONFIDENCE:
            # No meaningful match found — use global max_phase from molecule data
            global_max_phase = int(float(molecule_data.get("max_phase") or 0))
            if global_max_phase > 0:
                logger.info(
                    "approval_signal_global_phase_fallback",
                    extra={
                        "disease": disease_name,
                        "global_max_phase": global_max_phase,
                    },
                )
                return ApprovalSignal.from_chembl_indication_match(
                    max_phase=0,  # No indication match → treat as novel hypothesis
                    matched_term="",
                    match_confidence=0.0,
                    approved_count=approved_count,
                    source=source,
                    requested_disease=disease_name,
                    matching_rationale=f"No disease-specific indication matched '{disease_name}' above confidence threshold {_MIN_MATCH_CONFIDENCE}.",
                    disease_relation="UNRELATED",
                    disease_relation_policy="APPROVAL_ANCHOR",
                )
            return ApprovalSignal.no_data(
                requested_disease=disease_name,
                matching_rationale=f"No indication data matched '{disease_name}'.",
            )

        global_max = int(float(molecule_data.get("max_phase") or 0))
        # Phase 1 Root Cause Fix: Phase 3 indication must NEVER be promoted to Phase 4
        # based on unrelated global drug approval. Separate concepts strictly:
        # - matched_indication_phase = best_match_phase
        # - global_approval_phase = global_max
        matched_indication_phase = best_match_phase

        if best_match_variant.lower() == disease_name.lower():
            matching_rationale = (
                f"Direct disease match between requested '{disease_name}' and indication term "
                f"'{best_match_term}' (confidence {best_match_confidence:.2f}, phase {matched_indication_phase})."
            )
        else:
            matching_rationale = (
                f"Parent/subtype compatible match: requested disease '{disease_name}' resolved via "
                f"normalized variant '{best_match_variant}' to indication term '{best_match_term}' "
                f"(confidence {best_match_confidence:.2f}, phase {matched_indication_phase})."
            )

        logger.info(
            "approval_signal_match",
            extra={
                "disease": disease_name,
                "matched_term": best_match_term,
                "max_phase": matched_indication_phase,
                "global_max_phase": global_max,
                "confidence": round(best_match_confidence, 3),
            },
        )
        return ApprovalSignal.from_chembl_indication_match(
            max_phase=matched_indication_phase,
            matched_term=best_match_term,
            match_confidence=best_match_confidence,
            approved_count=approved_count,
            source=source,
            global_approval_phase=global_max,
            requested_disease=disease_name,
            matching_rationale=matching_rationale,
            disease_relation="SAME",
            disease_relation_policy="APPROVAL_ANCHOR",
        )


    def _parse_chembl_data(
        self,
        data: dict[str, Any],
        drug: Drug,
    ) -> tuple[list[Target], list[Evidence]]:
        """Parse ChEMBL mechanism and bioactivity data into Target and Evidence objects.

        Prioritizes curated mechanism data from /mechanism.json as the primary path.
        Only falls back to mining raw bioactivities if no curated mechanisms produce
        validated targets.
        """
        targets: list[Target] = []
        evidence: list[Evidence] = []
        activities = data.get("bioactivities", {}).get("activities", [])
        mechanisms = data.get("mechanisms", {}).get("mechanisms", [])
        target_details = data.get("target_details", {})

        # Build mapping from target ChEMBL ID to canonical UniProt accession
        # Prioritizes primary component accession (comp.get("accession"), e.g., P35354) over TrEMBL xrefs (A8K802)
        uniprot_map: dict[str, str] = {}
        for tid, tdata in target_details.items():
            components = tdata.get("target_components", [])
            for comp in components:
                acc = comp.get("accession")
                if acc and len(acc) >= 6:
                    uniprot_map[tid] = acc
                    break
                # Fallback to xrefs prioritizing Swiss-Prot accession prefixes (P, Q, O)
                xrefs = [
                    x.get("xref_id")
                    for x in comp.get("target_component_xrefs", [])
                    if x.get("xref_src_db") == "UniProt" and x.get("xref_id")
                ]
                if xrefs:
                    swissprot = [x for x in xrefs if x[0] in "PQO" and len(x) == 6]
                    uniprot_map[tid] = swissprot[0] if swissprot else xrefs[0]
                    break

        # ── Primary Path: Curated Mechanism of Action Data ───────────────────
        seen_uniprots: set[str] = set()
        for mech in mechanisms:
            target_chembl = mech.get("target_chembl_id", "")
            target_uniprot = uniprot_map.get(target_chembl, "")
            if not target_uniprot or target_uniprot in seen_uniprots:
                continue
            seen_uniprots.add(target_uniprot)

            action_type = mech.get("action_type") or "MODULATOR"
            mech_desc = mech.get("mechanism_of_action") or action_type
            prov = ProvenanceReference(
                source_name="ChEMBL-Mechanism",
                source_version="v33",
                record_id=str(mech.get("mec_id", target_chembl)),
                url=f"https://www.ebi.ac.uk/chembl/target_report_card/{target_chembl}",
            )
            # High-affinity default (1.0 nM) for curated mechanism targets
            erw = ERW.from_base(base_weight=EvidenceType.IN_VITRO.base_erw)
            target = Target(
                drug_chembl_id=drug.chembl_id or drug.name,
                protein_uniprot=target_uniprot,
                affinity_nm=1.0,
                affinity_type="IC50",
                mechanism=str(action_type).upper()[:20],
                erw=erw,
                provenance=prov,
            )
            targets.append(target)
            ev = Evidence(
                evidence_type=EvidenceType.IN_VITRO,
                erw=erw,
                citation_key=f"chembl_mech_{target_chembl}",
                title=f"ChEMBL curated mechanism: {drug.name} - {mech_desc}",
                provenance=prov,
                drug_chembl_id=drug.chembl_id,
                target_uniprot=target_uniprot,
            )
            evidence.append(ev)

        if targets:
            logger.info(
                "chembl_targets_from_curated_mechanisms",
                extra={"drug": drug.name, "target_count": len(targets)},
            )

        # ── Secondary/Fallback Path: Raw Bioactivity Mining ──────────────────
        # Runs if mechanisms produced no targets, or to supplement curated mechanisms.
        for act in activities[:50]:  # cap at 50
            try:
                standard_value = float(act.get("standard_value") or 0)
                affinity_type = act.get("standard_type", "IC50")
                target_chembl = act.get("target_chembl_id", "")

                target_uniprot = uniprot_map.get(target_chembl) or act.get("target_accession", "")
                mechanism = act.get("mechanism_of_action", "UNKNOWN")

                if not target_uniprot or standard_value <= 0 or target_uniprot in seen_uniprots:
                    continue
                seen_uniprots.add(target_uniprot)

                erw = ERW.from_base(
                    base_weight=EvidenceType.IN_VITRO.base_erw,
                )
                prov = ProvenanceReference(
                    source_name="ChEMBL",
                    source_version="v33",
                    record_id=str(act.get("activity_id", "unknown")),
                    url=f"https://www.ebi.ac.uk/chembl/activity/{act.get('activity_id', '')}",
                )
                target = Target(
                    drug_chembl_id=drug.chembl_id or drug.name,
                    protein_uniprot=target_uniprot,
                    affinity_nm=standard_value,
                    affinity_type=affinity_type if affinity_type in {
                        "Ki", "IC50", "Kd", "percent_inhibition", "EC50", "Potency"
                    } else "IC50",
                    mechanism=mechanism.upper().replace(" ", "_")[:20],
                    erw=erw,
                    provenance=prov,
                )
                targets.append(target)

                ev = Evidence(
                    evidence_type=EvidenceType.IN_VITRO,
                    erw=erw,
                    citation_key=str(act.get("activity_id", f"chembl_{len(evidence)}")),
                    title=f"ChEMBL bioactivity: {drug.name} vs {target_uniprot}",
                    provenance=prov,
                    drug_chembl_id=drug.chembl_id,
                    target_uniprot=target_uniprot,
                )
                evidence.append(ev)
            except Exception as exc:
                logger.debug("chembl_record_parse_error", extra={"error": str(exc)})
                continue
        return targets, evidence

    def _parse_uniprot_data(self, data: dict[str, Any]) -> list[Protein]:
        """Parse UniProt data into Protein objects."""
        proteins = []
        raw_proteins = data.get("proteins", [])
        for raw in raw_proteins:
            try:
                acc = raw.get("primaryAccession", "")
                if not acc:
                    continue
                gene_symbol = "UNKNOWN"
                name = "Unknown protein"
                
                genes = raw.get("genes", [])
                if genes:
                    gene_symbol = genes[0].get("geneName", {}).get("value", "UNKNOWN")
                
                protein_desc = raw.get("proteinDescription", {})
                rec_name = protein_desc.get("recommendedName", {})
                if rec_name:
                    name = rec_name.get("fullName", {}).get("value", "Unknown protein")

                # Parse review status: "UniProtKB reviewed (Swiss-Prot)" or "unreviewed (TrEMBL)"
                entry_type = raw.get("entryType", "")
                is_reviewed = "reviewed" in entry_type.lower() and "unreviewed" not in entry_type.lower()

                protein = Protein(
                    uniprot_accession=acc,
                    gene_symbol=gene_symbol.upper(),
                    name=name,
                    organism=raw.get("organism", {}).get("scientificName", "Homo sapiens"),
                    is_reviewed=is_reviewed,
                )
                proteins.append(protein)
            except Exception as e:
                logger.debug("uniprot_parse_error", extra={"error": str(e)})
                continue
        return proteins

    def _parse_pubmed_data(
        self,
        data: dict[str, Any],
        drug: Drug,
        disease: Disease,
    ) -> list[Evidence]:
        """Parse PubMed data into Evidence objects."""
        evidence: list[Evidence] = []
        pmids = data.get("pmids", [])
        abstracts = data.get("abstracts", {})
        for pmid in pmids[:20]:
            try:
                abstract_text = abstracts.get(pmid, "")
                erw = ERW.from_base(base_weight=EvidenceType.OBSERVATIONAL.base_erw)
                prov = ProvenanceReference(
                    source_name="PubMed",
                    source_version="2024",
                    record_id=pmid,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                )
                ev = Evidence(
                    evidence_type=EvidenceType.OBSERVATIONAL,
                    erw=erw,
                    citation_key=f"PMID:{pmid}",
                    title=f"PubMed article {pmid}",
                    abstract=abstract_text[:2000] if abstract_text else None,
                    provenance=prov,
                    drug_chembl_id=drug.chembl_id,
                    disease_identifier=disease.mesh_id,
                )
                evidence.append(ev)
            except Exception as exc:
                logger.debug("pubmed_record_parse_error", extra={"error": str(exc)})
                continue
        return evidence

    def _parse_reactome_data(self, data: dict[str, Any]) -> list[Pathway]:
        """Parse Reactome data into Pathway objects.

        Populates Pathway.participant_uniprot_ids from the '_participant_uniprot_ids'
        key injected by _fetch_reactome's Phase 2 participant lookup.
        When the participant fetch failed for a pathway, this field will be [] —
        the multi-hop reasoner's guard is designed to skip the membership check
        (not reject the path) in that case, degrading gracefully to pre-B behaviour.
        """
        pathways = []
        raw_pathways = data.get("pathways", [])
        seen = set()
        for raw in raw_pathways:
            reactome_id = raw.get("stId")
            if not reactome_id or reactome_id in seen:
                continue
            seen.add(reactome_id)
            try:
                import re
                if not re.match(r"^R-[A-Z]+-\d+$", reactome_id):
                    continue

                prov = ProvenanceReference(
                    source_name="Reactome",
                    source_version="2024",
                    record_id=reactome_id,
                    url=f"https://reactome.org/content/detail/{reactome_id}",
                )
                pathway = Pathway(
                    reactome_id=reactome_id,
                    name=raw.get("displayName", "Unnamed pathway"),
                    description=raw.get("displayName", "Unnamed pathway"),
                    provenance=prov,
                    participant_uniprot_ids=raw.get("_participant_uniprot_ids", []),
                )
                pathways.append(pathway)
            except Exception as e:
                logger.debug("reactome_parse_error", extra={"error": str(e)})
                continue
        return pathways

    @staticmethod
    def _is_safety_endpoint(title: str, description: str) -> bool:
        """Distinguish safety-only outcomes from therapeutic efficacy endpoints (Issue 5 / §15)."""
        text = f"{title} {description}".lower()
        safety_keywords = (
            "adverse event", "safety", "tolerability", "toxicity", "adverse effect",
            "toxicities", "vital sign", "laboratory abnormal", "discontinuation due to ae",
            "dose-limiting", "treatment-emergent adverse", "sae", "teae", "incidence of ae"
        )
        return any(kw in text for kw in safety_keywords)

    @staticmethod
    def _is_non_efficacy_endpoint(title: str, description: str) -> bool:
        """Distinguish device usability, patient preference, or PK from therapeutic disease efficacy endpoints."""
        text = f"{title} {description}".lower()
        non_efficacy_keywords = (
            "autoinjector", "injector", "needle apprehension", "device preference",
            "patient preference", "usability", "ease of use", "satisfaction questionnaire",
            "device handling", "injection site pain", "self-injection", "preference between",
            "pharmacokinetic", "pharmacodynamics", "bioequivalence", "bioavailability",
            "area under the curve", "cmax", "tmax", "steady state concentration",
            "compliance rate", "adherence rate", "pill count",
        )
        return any(kw in text for kw in non_efficacy_keywords)

    @staticmethod
    def _parse_float(val: Any) -> float | None:
        """Parse float value handling percentages, strings, and commas safely."""
        if val is None:
            return None
        try:
            s = str(val).strip().replace(",", "")
            if s.endswith("%"):
                return float(s[:-1]) / 100.0
            return float(s)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_p_value(val: Any) -> float | None:
        """Parse p-value handling inequalities (<0.001, >0.05, =0.05)."""
        if val is None:
            return None
        try:
            s = str(val).strip()
            if s.startswith("<"):
                raw = float(s[1:].strip())
                return max(0.0, raw - 0.0001)
            elif s.startswith(">"):
                raw = float(s[1:].strip())
                return raw + 0.0001
            elif s.startswith("="):
                return float(s[1:].strip())
            else:
                return float(s)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _extract_margin(comment: str, text: str) -> float | None:
        """Extract non-inferiority margin from comment or text."""
        combined = f"{comment} {text}".lower()
        patterns = [
            r"margin\s*(?:of|is|:|=)?\s*(-?[0-9]+(?:\.[0-9]+)?)\s*%",
            r"margin\s*(?:of|is|:|=)?\s*(-?[0-9]+(?:\.[0-9]+)?)",
            r"delta\s*(?:of|is|:|=)?\s*(-?[0-9]+(?:\.[0-9]+)?)",
            r"upper\s*(?:limit|bound)\s*<\s*(-?[0-9]+(?:\.[0-9]+)?)",
        ]
        for pat in patterns:
            m = re.search(pat, combined)
            if m:
                val_str = m.group(1)
                val = RetrievalPipeline._parse_float(val_str)
                if val is not None:
                    if "%" in pat:
                        return val / 100.0
                    return val
        return None

    @staticmethod
    def _extract_equivalence_bounds(comment: str, text: str) -> tuple[float, float] | None:
        """Extract equivalence bounds (e.g. 0.80 to 1.25) from comment or text."""
        combined = f"{comment} {text}".lower()
        patterns = [
            r"(?:bounds?|limits?|interval)\s*(?:of|is|:|=)?\s*\[?\s*(-?[0-9]+(?:\.[0-9]+)?)\s*(?:to|,|-)\s*(-?[0-9]+(?:\.[0-9]+)?)\s*\]?",
            r"(-?[0-9]+(?:\.[0-9]+)?)\s*(?:to|,)\s*(-?[0-9]+(?:\.[0-9]+)?)\s*(?:equivalence|bioequivalence)",
        ]
        for pat in patterns:
            m = re.search(pat, combined)
            if m:
                l = RetrievalPipeline._parse_float(m.group(1))
                u = RetrievalPipeline._parse_float(m.group(2))
                if l is not None and u is not None:
                    return (min(l, u), max(l, u))
        if "equivalence" in combined or "bioequivalence" in combined:
            return (0.80, 1.25)
        return None

    @staticmethod
    def _evaluate_outcome_measure_direction(om: dict[str, Any]) -> OutcomeEvaluationResult:
        """Inspect statistical results, p-values, effect sizes, and text in resultsSection outcome measure.

        Returns an OutcomeEvaluationResult (tuple of direction and reason, with .direction,
        .reason, and .reason_code properties) classifying evidence scientifically:
        - POSITIVE: Statistically significant therapeutic benefit or non-inferiority/equivalence success.
        - NEGATIVE: Genuine therapeutic failure, explicit futility, or statistically significant harm.
        - NEUTRAL: Non-significant result (p >= 0.05, CI crossing unity) without explicit failure.
        - INCONCLUSIVE: Incomplete statistical context or ambiguous NI/equivalence bounds.
        - SAFETY_HARM: Safety/tolerability/AE outcome showing elevated harm (separated from efficacy).
        - UNKNOWN: Non-efficacy endpoint, single-arm/within-group study, or missing context.
        """
        analyses = om.get("analyses", []) if isinstance(om, dict) else []
        title = str(om.get("title", "")) if (isinstance(om, dict) and om.get("title")) else ""
        desc = str(om.get("description", "")) if (isinstance(om, dict) and om.get("description")) else ""
        om_type = str(om.get("type", "")).upper() if isinstance(om, dict) else ""
        text_combined = f"{title} {desc}".lower()

        # 1. Non-efficacy endpoints (device usability, patient preference, PK)
        if RetrievalPipeline._is_non_efficacy_endpoint(title, desc):
            return OutcomeEvaluationResult(
                OutcomeDirection.UNKNOWN,
                f"Non-efficacy endpoint (device usability/preference/PK): '{title}'",
                StatisticalReasonCode.NON_EFFICACY_ENDPOINT,
            )

        # 2. Safety endpoints (Step 9)
        if RetrievalPipeline._is_safety_endpoint(title, desc):
            for ana in analyses:
                p_val = RetrievalPipeline._parse_p_value(ana.get("pValue"))
                param_val = RetrievalPipeline._parse_float(ana.get("paramValue"))
                if p_val is not None and p_val < 0.05:
                    if param_val is not None and param_val > 1.0:
                        return OutcomeEvaluationResult(
                            OutcomeDirection.SAFETY_HARM,
                            f"Safety endpoint '{title}' showed significant harm/toxicity increase (ratio={param_val}, p={p_val})",
                            StatisticalReasonCode.SAFETY_ENDPOINT,
                        )
                    return OutcomeEvaluationResult(
                        OutcomeDirection.SAFETY_HARM,
                        f"Safety endpoint '{title}' showed significant safety signal (p={p_val})",
                        StatisticalReasonCode.SAFETY_ENDPOINT,
                    )
            return OutcomeEvaluationResult(
                OutcomeDirection.UNKNOWN,
                f"Safety endpoint (tolerability/AEs): '{title}'",
                StatisticalReasonCode.SAFETY_ENDPOINT,
            )

        # 3. Explicit futility and explicit lack of efficacy in text (Step 8)
        explicit_futility_phrases = (
            "futility boundary crossed",
            "crossed futility boundary",
            "stopped early for futility",
            "terminated early for futility",
            "terminated for futility",
            "interim futility",
            "futility",
        )
        explicit_lack_of_efficacy_phrases = (
            "failed to meet primary endpoint",
            "failed to meet the primary endpoint",
            "did not meet primary endpoint",
            "did not meet the primary endpoint",
            "lack of efficacy",
            "no clinical benefit",
            "ineffective",
            "no evidence of efficacy",
            "failed superiority",
            "failed to demonstrate superiority",
        )
        if any(phrase in text_combined for phrase in explicit_futility_phrases):
            return OutcomeEvaluationResult(
                OutcomeDirection.NEGATIVE,
                f"Outcome text indicates futility: '{title}'",
                StatisticalReasonCode.EXPLICIT_FUTILITY,
            )
        if any(phrase in text_combined for phrase in explicit_lack_of_efficacy_phrases):
            return OutcomeEvaluationResult(
                OutcomeDirection.NEGATIVE,
                f"Outcome text indicates lack of efficacy: '{title}'",
                StatisticalReasonCode.EXPLICIT_LACK_OF_EFFICACY,
            )

        # 4. Statistical Analyses
        for ana in analyses:
            p_val = RetrievalPipeline._parse_p_value(ana.get("pValue"))
            stat_method = str(ana.get("statisticalMethod", "statistical analysis"))
            sm_lower = stat_method.lower()
            param_type = str(ana.get("paramType", "")).upper()
            param_val = RetrievalPipeline._parse_float(ana.get("paramValue"))
            ci_lower = RetrievalPipeline._parse_float(ana.get("ciLowerLimit"))
            ci_upper = RetrievalPipeline._parse_float(ana.get("ciUpperLimit"))
            ni_type = str(ana.get("nonInferiorityType", "")).upper()
            ni_comment = str(ana.get("nonInferiorityComment", ""))
            ana_group_desc = str(ana.get("analysisGroupDescription", "")).lower()
            stat_comment = str(ana.get("statisticalComment", "")).lower()
            combined_ana_text = f"{text_combined} {sm_lower} {ni_comment.lower()} {ana_group_desc} {stat_comment}"

            # A. Single-arm / within-group paired test check (Step 7)
            if "paired" in sm_lower or "within" in sm_lower or "single arm" in combined_ana_text or "one-sample" in sm_lower:
                return OutcomeEvaluationResult(
                    OutcomeDirection.UNKNOWN,
                    f"Outcome '{title}' within-group paired/single-arm analysis without comparator control ({stat_method})",
                    StatisticalReasonCode.SINGLE_ARM_NO_COMPARATOR,
                )

            # B. Subgroup analysis check (Step 10)
            is_subgroup = any(sg in combined_ana_text for sg in ("subgroup", "sub-group", "sub-population", "post-hoc"))

            # C. Non-Inferiority check (Step 5)
            is_ni = (
                "NON_INFERIORITY" in ni_type
                or "non-inferior" in combined_ana_text
                or "noninferior" in combined_ana_text
            ) and "EQUIVALENCE" not in ni_type

            if is_ni:
                if any(w in combined_ana_text for w in ("non-inferiority demonstrated", "met non-inferiority", "demonstrated non-inferiority", "was non-inferior")):
                    return OutcomeEvaluationResult(
                        OutcomeDirection.POSITIVE,
                        f"Outcome '{title}' demonstrated non-inferiority ({stat_method})",
                        StatisticalReasonCode.NON_INFERIOR,
                    )
                if any(w in combined_ana_text for w in ("failed to demonstrate non-inferiority", "did not meet non-inferiority", "non-inferiority not met")):
                    return OutcomeEvaluationResult(
                        OutcomeDirection.NEGATIVE,
                        f"Outcome '{title}' failed to demonstrate non-inferiority ({stat_method})",
                        StatisticalReasonCode.NON_INFERIORITY_FAILURE,
                    )

                margin = RetrievalPipeline._extract_margin(ni_comment, text_combined)
                if margin is not None and ci_upper is not None:
                    if ci_upper <= margin:
                        return OutcomeEvaluationResult(
                            OutcomeDirection.POSITIVE,
                            f"Outcome '{title}' met non-inferiority criterion: CI upper limit {ci_upper} <= margin {margin}",
                            StatisticalReasonCode.NON_INFERIOR,
                        )
                    else:
                        return OutcomeEvaluationResult(
                            OutcomeDirection.NEGATIVE,
                            f"Outcome '{title}' failed non-inferiority criterion: CI upper limit {ci_upper} > margin {margin}",
                            StatisticalReasonCode.NON_INFERIORITY_FAILURE,
                        )

                if p_val is not None:
                    if "non-inferior" in sm_lower or "noninferior" in sm_lower or "NON_INFERIORITY" in ni_type:
                        if p_val < 0.05:
                            return OutcomeEvaluationResult(
                                OutcomeDirection.POSITIVE,
                                f"Outcome '{title}' achieved non-inferiority (p={p_val} < 0.05, {stat_method})",
                                StatisticalReasonCode.NON_INFERIOR,
                            )
                        else:
                            return OutcomeEvaluationResult(
                                OutcomeDirection.NEGATIVE,
                                f"Outcome '{title}' failed non-inferiority test (p={p_val} >= 0.05, {stat_method})",
                                StatisticalReasonCode.NON_INFERIORITY_FAILURE,
                            )

                return OutcomeEvaluationResult(
                    OutcomeDirection.INCONCLUSIVE,
                    f"Outcome '{title}' non-inferiority design with inconclusive margin/CI statistical context",
                    StatisticalReasonCode.INSUFFICIENT_STATISTICAL_CONTEXT,
                )

            # D. Equivalence check (Step 6)
            is_equiv = "EQUIVALENCE" in ni_type or "equivalence" in combined_ana_text
            if is_equiv:
                if any(w in combined_ana_text for w in ("equivalence demonstrated", "met equivalence", "proven equivalent")):
                    return OutcomeEvaluationResult(
                        OutcomeDirection.POSITIVE,
                        f"Outcome '{title}' demonstrated equivalence ({stat_method})",
                        StatisticalReasonCode.EQUIVALENT,
                    )
                if any(w in combined_ana_text for w in ("failed to demonstrate equivalence", "not equivalent")):
                    return OutcomeEvaluationResult(
                        OutcomeDirection.NEGATIVE,
                        f"Outcome '{title}' failed equivalence test ({stat_method})",
                        StatisticalReasonCode.EQUIVALENCE_FAILURE,
                    )
                eq_bounds = RetrievalPipeline._extract_equivalence_bounds(ni_comment, text_combined)
                if eq_bounds is not None and ci_lower is not None and ci_upper is not None:
                    lower_b, upper_b = eq_bounds
                    if ci_lower >= lower_b and ci_upper <= upper_b:
                        return OutcomeEvaluationResult(
                            OutcomeDirection.POSITIVE,
                            f"Outcome '{title}' met equivalence bounds [{lower_b}, {upper_b}]: CI [{ci_lower}, {ci_upper}]",
                            StatisticalReasonCode.EQUIVALENT,
                        )
                    else:
                        return OutcomeEvaluationResult(
                            OutcomeDirection.NEGATIVE,
                            f"Outcome '{title}' failed equivalence bounds [{lower_b}, {upper_b}]: CI [{ci_lower}, {ci_upper}]",
                            StatisticalReasonCode.EQUIVALENCE_FAILURE,
                        )
                return OutcomeEvaluationResult(
                    OutcomeDirection.INCONCLUSIVE,
                    f"Outcome '{title}' equivalence design with inconclusive bounds statistical context",
                    StatisticalReasonCode.INSUFFICIENT_STATISTICAL_CONTEXT,
                )

            # E. Standard Superiority P-value evaluation (Steps 2, 4, 8, 10)
            if p_val is not None:
                if p_val < 0.05:
                    harm_terms = ("mortality", "death", "progression", "hospitalization", "failure", "cardiovascular event")
                    if param_val is not None and param_val > 1.0 and any(h in text_combined for h in harm_terms):
                        return OutcomeEvaluationResult(
                            OutcomeDirection.NEGATIVE,
                            f"Outcome '{title}' significantly increased risk/worsened outcome (ratio={param_val}, p={p_val})",
                            StatisticalReasonCode.STATISTICALLY_SIGNIFICANT_HARM,
                        )
                    return OutcomeEvaluationResult(
                        OutcomeDirection.POSITIVE,
                        f"Outcome '{title}' achieved statistical significance (p={p_val} < 0.05, {stat_method})",
                        StatisticalReasonCode.STATISTICALLY_SIGNIFICANT_BENEFIT,
                    )
                else:  # p_val >= 0.05
                    # Non-significant result is NEUTRAL (Step 2)
                    if is_subgroup:
                        return OutcomeEvaluationResult(
                            OutcomeDirection.NEUTRAL,
                            f"Subgroup outcome '{title}' did not achieve statistical significance (p={p_val} >= 0.05, {stat_method})",
                            StatisticalReasonCode.NON_SIGNIFICANT_SUBGROUP,
                        )
                    elif om_type == "SECONDARY":
                        return OutcomeEvaluationResult(
                            OutcomeDirection.NEUTRAL,
                            f"Secondary outcome '{title}' did not achieve statistical significance (p={p_val} >= 0.05, {stat_method})",
                            StatisticalReasonCode.NON_SIGNIFICANT_SECONDARY_ENDPOINT,
                        )
                    else:
                        return OutcomeEvaluationResult(
                            OutcomeDirection.NEUTRAL,
                            f"Primary outcome '{title}' did not achieve statistical significance (p={p_val} >= 0.05, {stat_method})",
                            StatisticalReasonCode.NON_SIGNIFICANT_PRIMARY_ENDPOINT,
                        )

            # F. Confidence intervals for ratio measures (without p-value)
            if ci_lower is not None and ci_upper is not None:
                if any(r in param_type for r in ("RATIO", "HR", "RR", "OR")):
                    if ci_lower <= 1.0 <= ci_upper:
                        if is_subgroup:
                            return OutcomeEvaluationResult(
                                OutcomeDirection.NEUTRAL,
                                f"Subgroup outcome '{title}' confidence interval [{ci_lower}, {ci_upper}] crosses unity (neutral result)",
                                StatisticalReasonCode.NON_SIGNIFICANT_SUBGROUP,
                            )
                        elif om_type == "SECONDARY":
                            return OutcomeEvaluationResult(
                                OutcomeDirection.NEUTRAL,
                                f"Secondary outcome '{title}' confidence interval [{ci_lower}, {ci_upper}] crosses unity (neutral result)",
                                StatisticalReasonCode.NON_SIGNIFICANT_SECONDARY_ENDPOINT,
                            )
                        else:
                            return OutcomeEvaluationResult(
                                OutcomeDirection.NEUTRAL,
                                f"Outcome '{title}' confidence interval [{ci_lower}, {ci_upper}] crosses unity (neutral result)",
                                StatisticalReasonCode.NON_SIGNIFICANT_PRIMARY_ENDPOINT,
                            )

        # 5. Text-level assessment if no numerical analysis resolved direction
        neutral_phrases = (
            "no significant difference",
            "not statistically significant",
            "no statistically significant difference",
            "no significant benefit",
            "did not reach statistical significance",
            "did not achieve statistical significance",
            "no difference",
            "did not significantly improve",
        )
        positive_phrases = (
            "statistically significant improvement",
            "met primary endpoint",
            "significant reduction in",
            "significantly improved",
            "superiority demonstrated",
            "significant benefit",
        )
        for np in neutral_phrases:
            if np in text_combined:
                code = (
                    StatisticalReasonCode.NON_SIGNIFICANT_SECONDARY_ENDPOINT
                    if om_type == "SECONDARY"
                    else StatisticalReasonCode.NON_SIGNIFICANT_PRIMARY_ENDPOINT
                )
                return OutcomeEvaluationResult(
                    OutcomeDirection.NEUTRAL,
                    f"Outcome text indicates neutral result: '{title}'",
                    code,
                )
        for pp in positive_phrases:
            if pp in text_combined:
                return OutcomeEvaluationResult(
                    OutcomeDirection.POSITIVE,
                    f"Outcome text indicates success: '{title}'",
                    StatisticalReasonCode.STATISTICALLY_SIGNIFICANT_BENEFIT,
                )

        return OutcomeEvaluationResult(
            OutcomeDirection.UNKNOWN,
            None,
            StatisticalReasonCode.INSUFFICIENT_STATISTICAL_CONTEXT,
        )

    def _parse_trials_data(
        self,
        data: dict[str, Any],
        drug: Drug,
        disease: Disease,
    ) -> list[ClinicalTrial]:
        """Parse ClinicalTrials.gov data into ClinicalTrial objects including resultsSection."""
        trials: list[ClinicalTrial] = []
        studies = data.get("studies", [])
        for study in studies:
            try:
                protocol = study.get("protocolSection", {})
                ident = protocol.get("identificationModule", {})
                status_mod = protocol.get("statusModule", {})
                design_mod = protocol.get("designModule", {})
                cond_mod = protocol.get("conditionsModule", {})

                nct_id = ident.get("nctId", "")
                if not nct_id or not nct_id.startswith("NCT"):
                    continue

                raw_status = status_mod.get("overallStatus", "UNKNOWN").upper()
                why_stopped = str(status_mod.get("whyStopped", "")).lower()

                # Parse resultsSection (Issue 5)
                results_sec = study.get("resultsSection", {})
                has_results = bool(study.get("hasResults") or results_sec)
                outcome_measures_raw = results_sec.get("outcomeMeasuresModule", {}).get("outcomeMeasures", [])
                condition_names = cond_mod.get("conditions", [])

                is_neg_efficacy = False
                neg_efficacy_reason: str | None = None
                has_pos_efficacy = False
                pos_efficacy_reason: str | None = None

                parsed_outcomes: list[dict[str, Any]] = []
                for om in outcome_measures_raw:
                    om_type = str(om.get("type", "")).upper()
                    om_title = om.get("title", "")
                    om_desc = om.get("description", "")

                    is_safety = self._is_safety_endpoint(om_title, om_desc)
                    is_non_eff = self._is_non_efficacy_endpoint(om_title, om_desc)
                    dir_res = self._evaluate_outcome_measure_direction(om)

                    direction = dir_res.direction.value if hasattr(dir_res, "direction") else str(dir_res[0])
                    dir_reason = dir_res.reason if hasattr(dir_res, "reason") else dir_res[1]
                    reason_code = (
                        dir_res.reason_code.value
                        if (hasattr(dir_res, "reason_code") and dir_res.reason_code)
                        else None
                    )

                    if direction == OutcomeDirection.SAFETY_HARM.value:
                        is_safety = True

                    parsed_outcomes.append({
                        "type": om_type,
                        "title": om_title,
                        "is_safety": is_safety,
                        "is_non_efficacy": is_non_eff,
                        "direction": direction,
                        "reason": dir_reason,
                        "reason_code": reason_code,
                    })

                    # Primary Efficacy Priority: Only genuine NEGATIVE on PRIMARY efficacy endpoint triggers is_neg_efficacy
                    if not is_safety and not is_non_eff and om_type == "PRIMARY":
                        if direction == OutcomeDirection.NEGATIVE.value and not is_neg_efficacy:
                            is_neg_efficacy = True
                            neg_efficacy_reason = dir_reason
                        elif direction == OutcomeDirection.POSITIVE.value and not has_pos_efficacy:
                            has_pos_efficacy = True
                            pos_efficacy_reason = dir_reason

                # Secondary Efficacy evaluation if primary is silent or inconclusive
                # NOTE: Secondary endpoints can support efficacy (POSITIVE) if primary is silent,
                # but a non-significant or secondary endpoint alone must NOT brand the entire trial as therapeutic failure!
                if not is_neg_efficacy and not has_pos_efficacy:
                    for po in parsed_outcomes:
                        if not po["is_safety"] and not po.get("is_non_efficacy", False) and po["type"] == "SECONDARY":
                            if po["direction"] == OutcomeDirection.POSITIVE.value:
                                has_pos_efficacy = True
                                pos_efficacy_reason = po["reason"]
                                break

                # Inspect whyStopped text for terminated / suspended / withdrawn trials (§13)
                negated_safety_phrases = (
                    "no safety concern",
                    "no safety concerns",
                    "without safety concern",
                    "without safety concerns",
                    "not due to safety",
                    "no safety issue",
                    "no safety issues",
                    "no safety problems",
                    "no safety problem",
                    "no evidence of safety concerns",
                    "no safety signal",
                    "no safety signals",
                )
                safety_kw = ("safety", "adverse", "toxicity", "harm", "death", "side effect")
                efficacy_kw = (
                    "futility", "lack of efficacy", "ineffective", "no benefit",
                    "primary endpoint", "lack of effect", "parent study", "study results",
                    "interim analysis", "results", "dsb", "dmcb", "endpoint", "analysis",
                    "poor response", "who report", "futility boundary", "interim futility"
                )

                has_negated_safety = any(phrase in why_stopped for phrase in negated_safety_phrases)
                has_positive_safety = False
                if any(kw in why_stopped for kw in safety_kw):
                    if has_negated_safety:
                        cleaned_why = why_stopped
                        for phrase in negated_safety_phrases:
                            cleaned_why = cleaned_why.replace(phrase, " ")
                        has_positive_safety = any(kw in cleaned_why for kw in ("adverse", "toxicity", "harm", "death", "side effect"))
                    else:
                        has_positive_safety = True

                has_efficacy_reason = any(kw in why_stopped for kw in efficacy_kw)

                if raw_status in ("TERMINATED", "SUSPENDED", "WITHDRAWN"):
                    # Negated safety (e.g. "Lack of efficacy; no safety concern") must NOT trigger TERMINATED_SAFETY
                    if has_efficacy_reason or is_neg_efficacy:
                        if not has_positive_safety:
                            status = TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY
                            is_neg_efficacy = True
                            if not neg_efficacy_reason:
                                neg_efficacy_reason = f"Trial terminated early: {status_mod.get('whyStopped')}"
                        else:
                            status = TrialOutcomeStatus.TERMINATED_SAFETY
                    elif has_positive_safety:
                        status = TrialOutcomeStatus.TERMINATED_SAFETY
                    else:
                        status = TrialOutcomeStatus.TERMINATED_ADMINISTRATIVE
                elif raw_status == "COMPLETED":
                    if is_neg_efficacy:
                        status = TrialOutcomeStatus.COMPLETED_FAILURE
                    elif has_pos_efficacy:
                        status = TrialOutcomeStatus.COMPLETED_SUCCESS
                    else:
                        status = TrialOutcomeStatus.UNKNOWN
                elif raw_status in ("RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"):
                    status = TrialOutcomeStatus.ACTIVE
                else:
                    status = TrialOutcomeStatus.UNKNOWN

                phase_list = design_mod.get("phases", ["N/A"])
                phase_map: dict[str, str] = {
                    "PHASE1": "Phase I", "PHASE2": "Phase II",
                    "PHASE3": "Phase III", "PHASE4": "Phase IV",
                    "PHASE1_PHASE2": "Phase I/II", "PHASE2_PHASE3": "Phase II/III",
                }
                phase = phase_map.get(phase_list[0] if phase_list else "N/A", "N/A")

                # Extract arms and study design metadata
                arms_mod = protocol.get("armsInterventionsModule", {})
                comparator_names: list[str] = []
                intervention_names: list[str] = []
                for arm in arms_mod.get("armGroups", []):
                    arm_type = str(arm.get("type", "")).upper()
                    inames = arm.get("interventionNames", [])
                    clean_inames = [re.sub(r"^(Drug|Biological|Device|Other|Dietary Supplement):\s*", "", n, flags=re.IGNORECASE).strip() for n in inames]
                    if "COMPARATOR" in arm_type or "CONTROL" in arm_type or "PLACEBO" in arm_type:
                        comparator_names.extend(clean_inames)
                    else:
                        intervention_names.extend(clean_inames)

                study_type = design_mod.get("studyType")
                design_info = design_mod.get("designInfo", {})
                design_allocation = design_info.get("allocation")

                prov = ProvenanceReference(
                    source_name="ClinicalTrials.gov",
                    source_version="2024",
                    record_id=nct_id,
                    url=f"https://clinicaltrials.gov/study/{nct_id}",
                )
                trial = ClinicalTrial(
                    nct_id=nct_id,
                    title=ident.get("briefTitle", "Unknown trial"),
                    phase=phase,
                    status=status,
                    drug_chembl_id=drug.chembl_id,
                    disease_identifier=disease.mesh_id,
                    provenance=prov,
                    study_type=study_type,
                    design_allocation=design_allocation,
                    intervention_names=intervention_names,
                    comparator_names=comparator_names,
                    why_stopped=status_mod.get("whyStopped") or None,
                    has_results=has_results,
                    outcome_measures=parsed_outcomes,
                    is_negative_efficacy=is_neg_efficacy,
                    negative_efficacy_reason=neg_efficacy_reason,
                    condition_names=condition_names,
                )
                trials.append(trial)
            except Exception as exc:
                logger.debug("trial_parse_error", extra={"error": str(exc)})
                continue
        return trials

    def _parse_disgenet_data(
        self,
        data: dict[str, Any],
        drug: Drug,
        disease: Disease,
    ) -> list[Evidence]:
        """Parse DisGeNET gene-disease association data into Evidence objects.

        Args:
            data: Raw DisGeNET response (list of associations or dict with list).
            drug: Drug entity (for provenance context).
            disease: Disease entity.

        Returns:
            List of Evidence records derived from DisGeNET associations.
        """
        evidence: list[Evidence] = []
        # DisGeNET response may be a list or a dict with a 'payload' key
        associations: list[dict[str, Any]] = []
        if isinstance(data, list):
            associations = data
        elif isinstance(data, dict):
            associations = data.get("payload", data.get("results", []))

        for assoc in associations[:20]:  # cap at 20
            try:
                gene_symbol = assoc.get("gene_symbol") or assoc.get("geneName", "UNKNOWN")
                score = float(assoc.get("score", 0.0))
                if score <= 0:
                    continue

                erw = ERW.from_base(base_weight=EvidenceType.OBSERVATIONAL.base_erw)
                prov = ProvenanceReference(
                    source_name="DisGeNET",
                    source_version="2024",
                    record_id=f"disgenet_{gene_symbol}",
                    url=f"https://www.disgenet.org/browser/0/1/0/{gene_symbol}/",
                )
                ev = Evidence(
                    evidence_type=EvidenceType.OBSERVATIONAL,
                    erw=erw,
                    citation_key=f"DisGeNET:{gene_symbol}:{disease.name}",
                    title=f"DisGeNET association: {gene_symbol} — {disease.name}",
                    abstract=(
                        f"Gene {gene_symbol} is associated with {disease.name} "
                        f"with DisGeNET score {score:.3f}."
                    ),
                    provenance=prov,
                    disease_identifier=disease.mesh_id,
                )
                evidence.append(ev)
            except Exception as exc:
                logger.debug("disgenet_parse_error", extra={"error": str(exc)})
                continue
        return evidence

    async def _fetch_openalex(
        self,
        drug_name: str,
        disease_name: str,
        hypothesis_id: uuid.UUID,
    ) -> list[Evidence]:
        """Fetch literature from OpenAlex (Phase 2 extended source)."""
        if not _EXTENDED_SOURCES_AVAILABLE:
            return []
        async with OpenAlexConnector() as connector:
            return await connector.fetch_literature(drug_name, disease_name, hypothesis_id)

    async def _fetch_semantic_scholar(
        self,
        drug_name: str,
        disease_name: str,
        hypothesis_id: uuid.UUID,
    ) -> list[Evidence]:
        """Fetch literature from Semantic Scholar (Phase 2 extended source)."""
        if not _EXTENDED_SOURCES_AVAILABLE:
            return []
        async with SemanticScholarConnector(api_key=self._semantic_scholar_api_key) as connector:
            return await connector.fetch_literature(drug_name, disease_name, hypothesis_id)

    async def _fetch_europepmc(
        self,
        drug_name: str,
        disease_name: str,
        hypothesis_id: uuid.UUID,
    ) -> list[Evidence]:
        """Fetch literature from Europe PMC (Phase 4 new source).

        Cache is applied at the whole-query level here because the
        query string IS the resolved identifier (drug + disease name
        normalized). Unlike UniProt/Reactome where the same protein
        appears across many drug queries, literature queries are unique
        to the drug-disease pair.

        sources_failed vs sources_queried contract (same as OpenAlex/S2):
            - Exception → sources_failed (caller handles)
            - Empty list with no exception → sources_queried with zero results
        """
        if not _NEW_SOURCES_AVAILABLE:
            return []

        import hashlib
        query = f"{drug_name.lower().strip()} AND {disease_name.lower().strip()}"
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        cache_key = RawResponseCache.make_key("europepmc", query_hash, "search")

        if not self._bypass_raw_cache:
            cached = self._raw_cache.get(cache_key, source_name="europepmc")
            if cached is not None and isinstance(cached, list):
                from backend.core.domain.evidence import Evidence as _Ev
                try:
                    return [_Ev.model_validate(item) for item in cached]
                except Exception:
                    pass  # Cache corrupted — fall through to fresh fetch

        async with EuropePMCConnector() as connector:
            result = await connector.fetch_literature(drug_name, disease_name, hypothesis_id)

        if result is not None:
            # Cache the serialized evidence list
            self._raw_cache.set(
                cache_key, "europepmc", query_hash, "search",
                [ev.model_dump(mode="json") for ev in result],
                TTL_LITERATURE,
            )
        return result if result is not None else []

    async def _fetch_opentargets(self, disease: Disease) -> dict[str, float]:
        """Fetch gene-disease associations from Open Targets (Phase 4 new source).

        Returns a flat dict {gene_symbol: score, uniprot_accession: score}
        for use in RetrievalPackage.validated_disease_genes.

        Uses the resolved disease.mondo_id when available (stable cache key).
        Falls back to an inline MONDO ID resolution via the connector's own
        resolve_mondo_id() when mondo_id is None (e.g. OT was unavailable
        during identity resolution).

        Cache is applied at the MONDO ID level — the most stable resolved identifier.

        sources_failed vs sources_queried contract:
            - Exception → sources_failed (caller handles)
            - Empty dict with no exception → sources_queried with zero results
        """
        if not _NEW_SOURCES_AVAILABLE:
            return {}

        mondo_id = disease.mondo_id

        async with OpenTargetsConnector() as connector:
            # Resolve MONDO ID if not already available
            if not mondo_id:
                mondo_id = await connector.resolve_mondo_id(disease.name)
                if not mondo_id:
                    logger.info(
                        "opentargets_mondo_unavailable",
                        extra={"disease": disease.name},
                    )
                    return {}

            cache_key = RawResponseCache.make_key(
                "opentargets_assoc", mondo_id, "associations", {"size": 250}
            )

            if not self._bypass_raw_cache:
                cached = self._raw_cache.get(cache_key, source_name="opentargets_assoc")
                if cached is not None and isinstance(cached, dict):
                    return cached

            gene_scores, mappings = await connector.fetch_association_mappings(mondo_id, page_size=250)

            result = {
                "gene_scores": gene_scores,
                "mappings": mappings,
            }

            if gene_scores is not None:
                self._raw_cache.set(
                    cache_key, "opentargets_assoc", mondo_id, "associations",
                    result, TTL_ASSOCIATIONS,
                )
            return result

    async def _fetch_opentargets_doe(
        self,
        targets: list[Target],
        proteins: list[Protein],
        disease: Disease,
    ) -> tuple[list[OpenTargetsDoEEvidence], list[BiologicalIdentifierMapping]]:
        """Fetch Open Targets Direction of Effect (DoE) records for retrieved targets."""
        if not _NEW_SOURCES_AVAILABLE:
            return [], []

        async with OpenTargetsConnector() as connector:
            mondo_id = disease.mondo_id
            if not mondo_id:
                mondo_id = await connector.resolve_mondo_id(disease.name)
            if not mondo_id:
                return [], []

            results: list[OpenTargetsDoEEvidence] = []
            doe_mappings: list[BiologicalIdentifierMapping] = []
            seen_ensembl: set[str] = set()

            for p in proteins[:12]:
                query_sym = p.gene_symbol if p.gene_symbol != "UNKNOWN" else p.uniprot_accession
                ensembl_id, _ = await connector.resolve_target_ensembl_id(query_sym, gene_symbol=p.gene_symbol)
                if ensembl_id and ensembl_id not in seen_ensembl:
                    seen_ensembl.add(ensembl_id)
                    doe_mappings.append(
                        BiologicalIdentifierMapping(
                            canonical_symbol=p.gene_symbol if p.gene_symbol != "UNKNOWN" else None,
                            uniprot_accession=p.uniprot_accession,
                            ensembl_id=ensembl_id,
                            source="OpenTargets",
                            original_identifiers=(p.gene_symbol, p.uniprot_accession, ensembl_id),
                        )
                    )
                    cache_key = RawResponseCache.make_key("ot_doe", ensembl_id, mondo_id)
                    if not self._bypass_raw_cache:
                        cached = self._raw_cache.get(cache_key, source_name="ot_doe")
                        if cached is not None and isinstance(cached, list):
                            try:
                                results.extend([OpenTargetsDoEEvidence.model_validate(r) for r in cached])
                                continue
                            except Exception:
                                pass

                    doe_rows = await connector.fetch_direction_of_effect(ensembl_id, mondo_id)
                    results.extend(doe_rows)
                    if doe_rows:
                        self._raw_cache.set(
                            cache_key,
                            "ot_doe",
                            ensembl_id,
                            mondo_id,
                            [r.model_dump(mode="json") for r in doe_rows],
                            TTL_ASSOCIATIONS,
                        )
            return results, doe_mappings

    async def _fetch_datts(
        self,
        proteins: list[Protein],
        disease: Disease,
    ) -> list[DATTsEvidence]:
        """Fetch DATTs therapeutic action records for retrieved targets and disease."""
        if not _NEW_SOURCES_AVAILABLE:
            return []

        async with DATTsConnector() as connector:
            results: list[DATTsEvidence] = []
            seen_queries: set[tuple[str, str, str]] = set()

            for p in proteins[:12]:
                sym = p.gene_symbol if p.gene_symbol != "UNKNOWN" else ""
                uni = p.uniprot_accession
                k = (sym, uni, disease.name.lower())
                if k in seen_queries:
                    continue
                seen_queries.add(k)

                cache_key = RawResponseCache.make_key("datts", sym or uni, disease.name)
                if not self._bypass_raw_cache:
                    cached = self._raw_cache.get(cache_key, source_name="datts")
                    if cached is not None and isinstance(cached, list):
                        try:
                            results.extend([DATTsEvidence.model_validate(r) for r in cached])
                            continue
                        except Exception:
                            pass

                datts_rows = await connector.fetch_therapeutic_actions(sym, uni, disease.name)
                results.extend(datts_rows)
                if datts_rows:
                    self._raw_cache.set(
                        cache_key,
                        "datts",
                        sym or uni,
                        disease.name,
                        [r.model_dump(mode="json") for r in datts_rows],
                        TTL_ASSOCIATIONS,
                    )
            return results

    async def _fetch_drugmechdb(
        self,
        drug: Drug,
        disease: Disease,
        targets: list[Target],
    ) -> list[DrugMechDBEvidence]:
        """Fetch DrugMechDB curated mechanistic path validation records."""
        if not _NEW_SOURCES_AVAILABLE:
            return []

        client = DrugMechDBClient()
        results: list[DrugMechDBEvidence] = []
        uniprot_ids = list(set(t.protein_uniprot for t in targets if t.protein_uniprot))

        if uniprot_ids:
            for uid in uniprot_ids[:5]:
                ev = await client.lookup_mechanism(drug.name, disease.name, uid)
                if ev.is_curated_path_available:
                    results.append(ev)
                    break
        if not results:
            ev = await client.lookup_mechanism(drug.name, disease.name, None)
            if ev.is_curated_path_available:
                results.append(ev)

        return results

    def _parse_disgenet_to_gene_scores(
        self,
        data: dict[str, Any],
    ) -> dict[str, float]:
        """Extract gene → DisGeNET score mapping from raw DisGeNET response.

        Returns a flat dict {gene_symbol: score} for use in
        validated_disease_genes. This is the corrected routing for DisGeNET
        associations — they go into the validated gene set, NOT evidence_records.

        The old _parse_disgenet_data() that created Evidence objects from
        DisGeNET is preserved below for backwards compatibility but is no
        longer called from execute(). It is intentionally not deleted so
        that any external callers that may reference it directly continue to work.
        """
        gene_scores: dict[str, float] = {}
        associations: list[dict[str, Any]] = []
        if isinstance(data, list):
            associations = data
        elif isinstance(data, dict):
            associations = data.get("payload", data.get("results", []))

        for assoc in associations[:50]:
            try:
                gene_symbol = assoc.get("gene_symbol") or assoc.get("geneName") or ""
                score = float(assoc.get("score", 0.0))
                if gene_symbol and score > 0:
                    gene_scores[gene_symbol] = round(score, 6)
            except (TypeError, ValueError):
                continue
        return gene_scores



    def _compute_confidence(
        self,
        targets: list[Target],
        evidence: list[Evidence],
        pathways: list[Pathway],
        trials: list[ClinicalTrial],
        sources_failed: list[str],
    ) -> str:
        """Determine retrieval confidence level based on data richness.

        Returns:
            'HIGH', 'MEDIUM', or 'LOW'.
        """
        if "chembl" in sources_failed or "uniprot" in sources_failed:
            return "LOW"
        score = 0
        if len(targets) >= 1:
            score += 2
        if len(evidence) >= 5:
            score += 2
        if len(pathways) >= 1:
            score += 1
        if len(trials) >= 1:
            score += 1
        if score >= 5:
            return "HIGH"
        if score >= 2:
            return "MEDIUM"
        return "LOW"
