"""DirectionalEvidenceBuilder — normalizes multi-source directional evidence into TherapeuticDirectionEvidence records.

Reference: Phase 4C — Directional Evidence Infrastructure

Assembles and normalizes evidence from:
1. ChEMBL drug-target actions (Biochemical)
2. Open Targets Direction of Effect (Genetic / Clinical)
3. DATTs required therapeutic actions (Curated Reference)
4. Grounded literature directional claims (Literature)
5. DrugMechDB mechanistic paths (Mechanistic Validation)

Applies canonical entity gating and deterministic independence grouping across all records.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.value_objects.therapeutic_direction_evidence import (
    EvidenceFamily,
    TherapeuticAction,
    TherapeuticDirectionEvidence,
    OpenTargetsDoEEvidence,
    DATTsEvidence,
    DrugMechDBEvidence,
    compute_independence_group,
)
from backend.reasoning.directional.chembl_polarity import (
    chembl_action_to_polarity,
    chembl_action_to_grounding,
)
from backend.reasoning.directional.canonical_entity_gate import is_canonically_grounded

if TYPE_CHECKING:
    from backend.core.domain.retrieval_package import RetrievalPackage
    from backend.core.domain.claim import Claim
    from backend.reasoning.normalization.biological_identifier_resolver import (
        BiologicalIdentifierResolver,
    )

logger = logging.getLogger(__name__)


class DirectionalEvidenceBuilder:
    """Builder that normalizes raw package evidence into structured TherapeuticDirectionEvidence records."""

    def build_all(
        self,
        package: "RetrievalPackage",
        resolver: "BiologicalIdentifierResolver" | None = None,
        claims: list["Claim"] | None = None,
    ) -> list[TherapeuticDirectionEvidence]:
        """Normalize all directional evidence from package and extracted claims.

        Args:
            package: Sealed or active RetrievalPackage.
            resolver: BiologicalIdentifierResolver for canonical entity validation.
            claims: Extracted Claim objects from literature.

        Returns:
            List of normalized TherapeuticDirectionEvidence records.
        """
        evidence_list: list[TherapeuticDirectionEvidence] = []
        disease_canonical = str(package.disease.name).strip()

        # Build or initialize resolver if not provided
        if resolver is None:
            from backend.reasoning.normalization.biological_identifier_resolver import (
                BiologicalIdentifierResolver as _BIR,
            )
            resolver = _BIR(
                proteins=package.proteins,
                genes=package.genes,
                mappings=package.identifier_mappings,
            )

        # Register mappings from Open Targets DoE records (target_symbol <-> target_id)
        for doe in package.opentargets_doe_evidence:
            if doe.target_symbol and doe.target_id:
                resolver.add_mapping(canonical_symbol=doe.target_symbol, ensembl_id=doe.target_id)

        # 1. ChEMBL Drug Target Actions
        for target in package.targets:
            uni = (target.protein_uniprot or "").strip().upper()
            res = resolver.resolve(uni, source="ChEMBL")
            gene_sym = res.canonical_symbol or res.canonical_identifier or uni
            polarity = chembl_action_to_polarity(target.mechanism)
            grounding = chembl_action_to_grounding(target.mechanism)
            status = "EXACT" if is_canonically_grounded(gene_sym, resolver) else "RESOLVED"

            ref = target.provenance.record_id if target.provenance else None
            indep_group = compute_independence_group(
                EvidenceFamily.BIOCHEMICAL,
                [ref] if ref else None,
                source="ChEMBL",
            )

            evidence_list.append(
                TherapeuticDirectionEvidence(
                    target_canonical_id=gene_sym,
                    disease_canonical_id=disease_canonical,
                    source="ChEMBL",
                    target_direction=polarity.value,
                    trait_direction=None,
                    required_action=None,
                    evidence_type="BIOCHEMICAL_BINDING_ASSAY",
                    causal_grounding=grounding,
                    evidence_family=EvidenceFamily.BIOCHEMICAL,
                    independence_group=indep_group,
                    underlying_reference=ref,
                    original_target_id=uni,
                    target_uniprot=uni,
                    target_ensembl_id=resolver._symbol_to_ensembl.get(gene_sym),
                    mapping_status=status,
                    confidence=target.erw.value if target.erw else None,
                    provenance={
                        "mechanism": target.mechanism,
                        "affinity_nm": target.affinity_nm,
                        "affinity_type": target.affinity_type,
                        "chembl_id": target.drug_chembl_id,
                    },
                )
            )

        # 2. Open Targets Direction of Effect
        for doe in package.opentargets_doe_evidence:
            target_id = doe.target_id.strip().upper()
            res = resolver.resolve(target_id, source="OpenTargets")
            gene_sym = res.canonical_symbol or doe.target_symbol or res.canonical_identifier or target_id
            status = "EXACT" if is_canonically_grounded(gene_sym, resolver) else "RESOLVED"

            # Determine EvidenceFamily: clinical_precedence is CLINICAL_TRIAL, others are GENETIC
            ds_id = str(doe.datasource_id or "").lower()
            ev_family = EvidenceFamily.CLINICAL_TRIAL if "clinical" in ds_id else EvidenceFamily.GENETIC
            grounding = CausalGrounding.CURATED if (doe.direction_on_target or doe.direction_on_trait) else CausalGrounding.STRUCTURAL

            refs = list(doe.literature)
            if doe.study_id:
                refs.append(doe.study_id)

            indep_group = compute_independence_group(
                ev_family,
                refs if refs else None,
                source=f"OpenTargets_{ds_id}",
            )

            evidence_list.append(
                TherapeuticDirectionEvidence(
                    target_canonical_id=gene_sym,
                    disease_canonical_id=doe.disease_id,
                    source="OpenTargets",
                    target_direction=doe.direction_on_target or "UNKNOWN",
                    trait_direction=doe.direction_on_trait or "UNKNOWN",
                    required_action=None,
                    evidence_type=doe.datatype_id or "GENETIC_OR_CLINICAL_EVIDENCE",
                    causal_grounding=grounding,
                    evidence_family=ev_family,
                    independence_group=indep_group,
                    underlying_reference=refs[0] if refs else None,
                    original_target_id=target_id,
                    target_uniprot=resolver._symbol_to_uniprot.get(gene_sym),
                    target_ensembl_id=target_id if target_id.startswith("ENSG") else resolver._symbol_to_ensembl.get(gene_sym),
                    mapping_status=status,
                    confidence=doe.score,
                    provenance=doe.provenance,
                )
            )

        # 3. DATTs Therapeutic Action Evidence
        for datts in package.datts_evidence:
            sym = str(datts.gene_symbol or datts.uniprot_id or "").strip().upper()
            res = resolver.resolve(sym, source="DATTs")
            gene_sym = res.canonical_symbol or res.canonical_identifier or sym
            status = "EXACT" if is_canonically_grounded(gene_sym, resolver) else "RESOLVED"
            grounding = CausalGrounding.CURATED if datts.required_action != TherapeuticAction.UNKNOWN else CausalGrounding.NONE

            ref_list = [datts.literature] if datts.literature else None
            indep_group = compute_independence_group(
                EvidenceFamily.CURATED_REFERENCE,
                ref_list,
                source="DATTs",
            )

            evidence_list.append(
                TherapeuticDirectionEvidence(
                    target_canonical_id=gene_sym,
                    disease_canonical_id=datts.disease_name,
                    source="DATTs",
                    target_direction=None,
                    trait_direction=None,
                    required_action=datts.required_action.value,
                    evidence_type="CURATED_TEXTBOOK_PHARMACOLOGY",
                    causal_grounding=grounding,
                    evidence_family=EvidenceFamily.CURATED_REFERENCE,
                    independence_group=indep_group,
                    underlying_reference=datts.literature,
                    original_target_id=sym,
                    target_uniprot=datts.uniprot_id or resolver._symbol_to_uniprot.get(gene_sym),
                    target_ensembl_id=resolver._symbol_to_ensembl.get(gene_sym),
                    mapping_status=status,
                    provenance=datts.provenance,
                )
            )

        # 4. Grounded Literature Directional Claims
        if claims and resolver:
            for cl in claims:
                # Check canonical grounding for subject and object
                subj_grounded = is_canonically_grounded(cl.subject, resolver)
                obj_grounded = is_canonically_grounded(cl.object, resolver)

                if not (subj_grounded and obj_grounded):
                    continue

                subj_res = resolver.resolve(cl.subject, source="directional_builder")
                obj_res = resolver.resolve(cl.object, source="directional_builder")

                # Match directional predicates
                pred_val = str(cl.predicate.value).upper()
                if pred_val not in ("INHIBITS", "ACTIVATES", "PREVENTS", "TREATS", "CAUSES", "EXACERBATES"):
                    continue

                req_action = None
                trait_dir = None
                if pred_val in ("INHIBITS", "PREVENTS", "TREATS"):
                    req_action = "INHIBITION"
                    trait_dir = "PROTECTIVE"
                elif pred_val in ("ACTIVATES",):
                    req_action = "ACTIVATION"
                    trait_dir = "PROTECTIVE"
                elif pred_val in ("CAUSES", "EXACERBATES"):
                    trait_dir = "RISK"

                indep_group = compute_independence_group(
                    EvidenceFamily.LITERATURE,
                    [str(cl.citation_key or cl.id)],
                    source="Literature",
                )

                evidence_list.append(
                    TherapeuticDirectionEvidence(
                        target_canonical_id=subj_res.canonical_identifier,
                        disease_canonical_id=obj_res.canonical_identifier,
                        source="Literature",
                        target_direction=pred_val,
                        trait_direction=trait_dir,
                        required_action=req_action,
                        evidence_type="CANONICALLY_GROUNDED_LITERATURE_CLAIM",
                        causal_grounding=CausalGrounding.CURATED,
                        evidence_family=EvidenceFamily.LITERATURE,
                        independence_group=indep_group,
                        underlying_reference=cl.citation_key,
                        mapping_status="EXACT",
                        confidence=cl.confidence,
                        provenance={"raw_text": cl.raw_text, "claim_id": str(cl.id)},
                    )
                )

        # 5. DrugMechDB Mechanistic Validation Evidence
        for dm in package.drugmechdb_evidence:
            if not dm.is_curated_path_available:
                continue

            indep_group = compute_independence_group(
                EvidenceFamily.MECHANISTIC_DATABASE,
                [dm.drugbank_id or dm.drug_name],
                source="DrugMechDB",
            )

            evidence_list.append(
                TherapeuticDirectionEvidence(
                    target_canonical_id=dm.target_uniprot or "CURATED_PATH_TARGET",
                    disease_canonical_id=dm.disease_name,
                    source="DrugMechDB",
                    target_direction=None,
                    trait_direction=None,
                    required_action=None,
                    evidence_type="CURATED_MECHANISTIC_GRAPH_PATH",
                    causal_grounding=CausalGrounding.CURATED,
                    evidence_family=EvidenceFamily.MECHANISTIC_DATABASE,
                    independence_group=indep_group,
                    underlying_reference=dm.drugbank_id,
                    mapping_status="EXACT" if dm.target_uniprot else "RESOLVED",
                    provenance={"path_summary": dm.path_summary},
                )
            )

        logger.info(
            "directional_evidence_built",
            extra={
                "total_records": len(evidence_list),
                "sources": list(set(e.source for e in evidence_list)),
                "independence_groups": len(set(e.independence_group for e in evidence_list if e.independence_group)),
            },
        )
        return evidence_list
