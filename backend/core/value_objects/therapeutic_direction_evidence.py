"""Therapeutic Direction Evidence value objects and domain models.

Reference: Phase 4C — Therapeutic Direction Evidence Infrastructure

Separates three independent semantic layers:
1. Molecular drug-target action (ChEMBL): INHIBITOR / AGONIST / etc.
2. Target perturbation & disease-trait effect (Open Targets DoE): LoF / GoF + protect / risk
3. Explicit disease-specific therapeutic action (DATTs & Literature): INHIBITION / ACTIVATION / etc.

Also provides DrugMechDB mechanistic path validation and evidence family / independence tracking.
"""
from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.enums.molecular_polarity import MolecularPolarity


class EvidenceFamily(str, Enum):
    """Categorization of evidence origin to detect multi-database collinearity."""
    GENETIC = "GENETIC"
    CLINICAL_TRIAL = "CLINICAL_TRIAL"
    CURATED_REFERENCE = "CURATED_REFERENCE"
    BIOCHEMICAL = "BIOCHEMICAL"
    LITERATURE = "LITERATURE"
    MECHANISTIC_DATABASE = "MECHANISTIC_DATABASE"
    UNKNOWN = "UNKNOWN"


class TherapeuticAction(str, Enum):
    """Explicit therapeutic action required to treat or alleviate a disease."""
    INHIBITION = "INHIBITION"
    ACTIVATION = "ACTIVATION"
    TARGETING = "TARGETING"
    UNKNOWN = "UNKNOWN"


def normalize_therapeutic_action(action_str: str | None) -> TherapeuticAction:
    """Normalize raw string to TherapeuticAction."""
    if not action_str:
        return TherapeuticAction.UNKNOWN
    norm = action_str.strip().lower()
    if any(k in norm for k in ["inhibit", "antagon", "block", "suppress", "downregulat", "reduc"]):
        return TherapeuticAction.INHIBITION
    if any(k in norm for k in ["activat", "agoni", "stimulat", "upregulat", "induc", "increas", "open"]):
        return TherapeuticAction.ACTIVATION
    if "target" in norm:
        return TherapeuticAction.TARGETING
    return TherapeuticAction.UNKNOWN


class OpenTargetsDoEEvidence(BaseModel):
    """Direction of Effect evidence record from Open Targets Platform GraphQL API.

    Attributes:
        target_id: Ensembl gene ID (e.g., 'ENSG00000074803') or symbol.
        disease_id: MONDO / EFO disease identifier (e.g., 'MONDO_0009693').
        direction_on_target: Perturbation on target ('LoF', 'GoF', or None).
        direction_on_trait: Effect on disease trait ('protect', 'risk', or None).
        datasource_id: Source dataset ('clinical_precedence', 'eva', 'gwas', 'gene_burden', etc.).
        datatype_id: High-level datatype ('clinical', 'genetic_association', etc.).
        evidence_id: Unique evidence record ID if provided.
        score: Association / confidence score [0.0, 1.0].
        literature: List of PubMed IDs or citations if available.
        study_id: Study accession (e.g., GWAS study ID, trial ID).
        target_modulation: Target modulation description.
        target_role: Target role annotation.
        provenance: Raw metadata dictionary.
    """
    model_config = {"frozen": True}

    target_id: str
    disease_id: str
    target_symbol: str | None = None
    target_uniprot: str | None = None
    direction_on_target: str | None = None
    direction_on_trait: str | None = None
    datasource_id: str | None = None
    datatype_id: str | None = None
    evidence_id: str | None = None
    score: float | None = None
    literature: list[str] = Field(default_factory=list)
    study_id: str | None = None
    target_modulation: str | None = None
    target_role: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class DATTsEvidence(BaseModel):
    """Disease-Associated Therapeutic Target evidence record from DATTs.

    Attributes:
        datts_protein_id: DATTs internal protein ID (e.g., 'hsa:6557').
        gene_symbol: HGNC gene symbol (e.g., 'SLC12A1').
        uniprot_id: UniProt accession if available.
        disease_name: Disease name in DATTs.
        rel_type: Raw relationship type string (e.g., 'Inhibition', 'Activation').
        required_action: Normalized TherapeuticAction enum.
        literature: Primary literature or textbook citation reference.
        source: Database source string.
        comment: Curated commentary.
        provenance: Raw response dictionary.
    """
    model_config = {"frozen": True}

    datts_protein_id: str | None = None
    gene_symbol: str | None = None
    uniprot_id: str | None = None
    disease_name: str
    rel_type: str
    required_action: TherapeuticAction = TherapeuticAction.UNKNOWN
    literature: str | None = None
    source: str | None = None
    comment: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class DrugMechDBEvidence(BaseModel):
    """Curated mechanistic path validation record from DrugMechDB.

    Attributes:
        drug_name: Name of the drug.
        disease_name: Name of the disease / indication.
        drugbank_id: DrugBank accession (e.g., 'DB00695').
        mesh_disease: MeSH disease identifier (e.g., 'MESH:D004487').
        target_uniprot: Primary target UniProt ID in path if mapped.
        path_summary: Human-readable chain summary.
        is_curated_path_available: True if full verified mechanistic path exists.
        nodes: Graph node list.
        links: Graph edge list.
        provenance: Full graph metadata dictionary.
    """
    model_config = {"frozen": True}

    drug_name: str
    disease_name: str
    drugbank_id: str | None = None
    mesh_disease: str | None = None
    target_uniprot: str | None = None
    path_summary: str = "NONE"
    is_curated_path_available: bool = False
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


def compute_independence_group(
    evidence_family: EvidenceFamily,
    references: list[str] | None = None,
    source: str = "",
) -> str:
    """Compute a deterministic independence group identifier for evidence grouping.

    If two evidence records (even from different databases like Open Targets clinical_precedence
    and DATTs) cite the same underlying publication / trial (e.g. PMID, DOI, NCT ID, or standard citation),
    they will share the same independence group.

    Args:
        evidence_family: EvidenceFamily enum.
        references: List of citation strings, PMIDs, or DOIs.
        source: Fallback source name.

    Returns:
        Deterministic string grouping identifier.
    """
    normalized_refs: list[str] = []
    if references:
        for ref in references:
            if not ref:
                continue
            clean_ref = str(ref).strip().lower()
            # Extract PMID if present
            pmid_match = re.search(r"pubmed/(\d+)|pmid:?\s*(\d+)", clean_ref)
            if pmid_match:
                pmid = pmid_match.group(1) or pmid_match.group(2)
                normalized_refs.append(f"pmid:{pmid}")
                continue
            # Extract DOI if present
            doi_match = re.search(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", clean_ref)
            if doi_match:
                normalized_refs.append(f"doi:{doi_match.group(0)}")
                continue
            # Extract ClinicalTrial ID if present
            nct_match = re.search(r"nct\d{8}", clean_ref)
            if nct_match:
                normalized_refs.append(f"nct:{nct_match.group(0)}")
                continue
            # Normalize short citation
            short_ref = re.sub(r"[^\w\d]", "_", clean_ref)[:60]
            normalized_refs.append(f"ref:{short_ref}")

    if normalized_refs:
        # Prioritize PMID/DOI/NCT over generic ref
        prio_refs = sorted(set(normalized_refs), key=lambda x: (0 if x.startswith("pmid:") else (1 if x.startswith("doi:") else (2 if x.startswith("nct:") else 3))))
        primary_ref = prio_refs[0]
        return f"{evidence_family.value}:{primary_ref}"

    # Fallback to source-level group if no reference is present
    return f"{evidence_family.value}:{source.lower()}:unlinked"


class TherapeuticDirectionEvidence(BaseModel):
    """High-level normalized therapeutic direction evidence record.

    Represents a discrete directional claim from an external source with full provenance,
    canonical mapping status, and evidence independence tracking.

    Attributes:
        target_canonical_id: Canonical target identifier (e.g. gene symbol 'SLC12A1').
        disease_canonical_id: Canonical disease identifier (e.g. MONDO ID 'MONDO_0009693').
        source: Name of data source ('OpenTargets', 'DATTs', 'ChEMBL', 'Literature', 'DrugMechDB').
        target_direction: Perturbation direction on target ('LoF', 'GoF', 'INHIBITED', 'ACTIVATED', 'UNKNOWN').
        trait_direction: Effect on disease trait ('PROTECTIVE', 'RISK', 'IMPROVED', 'WORSENED', 'UNKNOWN').
        required_action: Therapeutic action required ('INHIBITION', 'ACTIVATION', 'TARGETING', 'UNKNOWN').
        evidence_type: Specific evidence type string.
        causal_grounding: CausalGrounding tier.
        evidence_family: EvidenceFamily classification for collinearity analysis.
        independence_group: Deterministic cluster key for shared underlying publications.
        underlying_reference: Primary citation/PMID/DOI string.
        original_target_id: Original source-provided target identifier (e.g. 'ENSG00000163631', 'Q13621').
        target_uniprot: UniProt accession if resolved.
        target_ensembl_id: Ensembl ID if resolved.
        mapping_status: Entity mapping status ('EXACT', 'RESOLVED', 'AMBIGUOUS', 'UNRESOLVED').
        confidence: Optional confidence score [0.0, 1.0].
        provenance: Detailed provenance dictionary.
    """
    model_config = {"frozen": True}

    target_canonical_id: str
    disease_canonical_id: str
    source: str
    target_direction: str | None = None
    trait_direction: str | None = None
    required_action: str | None = None
    evidence_type: str = "DATABASE_RECORD"
    causal_grounding: CausalGrounding = CausalGrounding.CURATED
    evidence_family: EvidenceFamily = EvidenceFamily.UNKNOWN
    independence_group: str | None = None
    underlying_reference: str | None = None
    original_target_id: str | None = None
    target_uniprot: str | None = None
    target_ensembl_id: str | None = None
    mapping_status: str = "EXACT"
    confidence: float | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class TherapeuticAlignment(str, Enum):
    """Directional compatibility of drug-target action with disease-target therapeutic requirements."""
    SUPPORTS = "SUPPORTS"
    OPPOSES = "OPPOSES"
    INSUFFICIENT = "INSUFFICIENT"
    MIXED = "MIXED"


class DirectionalEvidenceGroup(BaseModel):
    """Cluster of collinear directional evidence records sharing an underlying citation / origin.

    Prevents multiple database rows citing the same clinical trial, GWAS, or publication
    from casting multiple votes.
    """
    model_config = {"frozen": True}

    group_id: str
    target_id: str
    disease_id: str
    desired_action: TherapeuticAction
    evidence_family: EvidenceFamily
    causal_grounding: CausalGrounding
    references: list[str] = Field(default_factory=list)
    member_record_count: int = 1
    sources: list[str] = Field(default_factory=list)
    confidence: float | None = None
    summary: str = ""


class TargetDiseaseDirection(BaseModel):
    """Internal model representing the aggregated desired direction of target perturbation for a disease."""
    model_config = {"frozen": True}

    target_id: str
    desired_action: TherapeuticAction
    confidence: float = 0.0
    evidence_groups: list[DirectionalEvidenceGroup] = Field(default_factory=list)
    supporting_group_ids: list[str] = Field(default_factory=list)
    opposing_group_ids: list[str] = Field(default_factory=list)
    explanation: str = ""


class TargetTherapeuticAlignment(BaseModel):
    """Per-target therapeutic alignment assessment."""
    model_config = {"frozen": True}

    target_id: str
    target_name: str | None = None
    is_primary: bool = True
    drug_action: TherapeuticAction = TherapeuticAction.UNKNOWN
    desired_target_action: TherapeuticAction = TherapeuticAction.UNKNOWN
    alignment: TherapeuticAlignment = TherapeuticAlignment.INSUFFICIENT
    evidence_groups: list[DirectionalEvidenceGroup] = Field(default_factory=list)
    supporting_groups: list[str] = Field(default_factory=list)
    opposing_groups: list[str] = Field(default_factory=list)
    drugmechdb_validated: bool = False
    confidence: float = 0.0
    explanation: str = ""


class TherapeuticAlignmentReport(BaseModel):
    """Complete Phase 4D Therapeutic Alignment report for drug-disease hypothesis."""
    model_config = {"frozen": True}

    drug_name: str
    disease_name: str
    overall_alignment: TherapeuticAlignment = TherapeuticAlignment.INSUFFICIENT
    target_alignments: list[TargetTherapeuticAlignment] = Field(default_factory=list)
    primary_target_alignments: list[TargetTherapeuticAlignment] = Field(default_factory=list)
    secondary_target_alignments: list[TargetTherapeuticAlignment] = Field(default_factory=list)
    total_independent_groups: int = 0
    supporting_groups_count: int = 0
    opposing_groups_count: int = 0
    drugmechdb_validated: bool = False
    explanation: str = ""
