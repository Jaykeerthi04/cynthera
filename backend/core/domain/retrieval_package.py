"""RetrievalPackage entity — sealed output of the retrieval subsystem.

Reference: 01_SYSTEM_ARCHITECTURE.md §5, 03_RETRIEVAL_SPECIFICATION.md
"""
from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.gene import Gene
from backend.core.domain.pathway import Pathway
from backend.core.domain.evidence import Evidence
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.approval_signal import ApprovalSignal
from backend.core.domain.reactome_reaction_evidence import ReactomeReactionEvidence
from backend.core.domain.disease_gene_evidence import DiseaseGeneEvidence
from backend.core.value_objects.biological_identifier import BiologicalIdentifierMapping
from backend.core.value_objects.therapeutic_direction_evidence import (
    OpenTargetsDoEEvidence,
    DATTsEvidence,
    DrugMechDBEvidence,
    TherapeuticDirectionEvidence,
)


class RetrievalPackage(BaseModel):
    """Sealed, immutable output of the retrieval pipeline.

    Produced by the MasterOrchestrator after all sources have been queried,
    normalized, and quality-gated. Once sealed, it is read-only.

    Attributes:
        id: Internal UUID.
        hypothesis_id: UUID of the owning Hypothesis.
        drug: Resolved Drug entity.
        disease: Resolved Disease entity.
        targets: All drug-protein Target relationships retrieved.
        proteins: All Protein entities referenced by targets.
        genes: All Gene entities associated with targets.
        pathways: All Pathway entities retrieved.
        evidence_records: All Evidence records retrieved.
        clinical_trials: All ClinicalTrial records retrieved.
        retrieval_confidence: Overall confidence in data completeness ('HIGH', 'MEDIUM', 'LOW').
        sources_queried: Names of all data sources successfully queried.
        sources_failed: Names of all data sources that failed during retrieval.
        sealed_at: UTC timestamp when this package was sealed.
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Package unique identifier.")
    hypothesis_id: uuid.UUID = Field(..., description="UUID of the owning Hypothesis.")
    drug: Drug = Field(..., description="Resolved Drug entity.")
    disease: Disease = Field(..., description="Resolved Disease entity.")
    targets: list[Target] = Field(default_factory=list, description="Drug-protein Target relationships.")
    proteins: list[Protein] = Field(default_factory=list, description="Protein entities.")
    genes: list[Gene] = Field(default_factory=list, description="Gene entities.")
    pathways: list[Pathway] = Field(default_factory=list, description="Pathway entities.")
    evidence_records: list[Evidence] = Field(default_factory=list, description="Evidence records.")
    clinical_trials: list[ClinicalTrial] = Field(default_factory=list, description="ClinicalTrial records.")
    retrieval_confidence: str = Field(
        default="MEDIUM",
        pattern="^(HIGH|MEDIUM|LOW)$",
        description="Overall data completeness confidence.",
    )
    sources_queried: list[str] = Field(default_factory=list, description="Successfully queried sources.")
    sources_failed: list[str] = Field(default_factory=list, description="Failed data sources.")
    sealed_at: datetime = Field(default_factory=datetime.utcnow, description="UTC sealing timestamp.")
    approval_signal: ApprovalSignal | None = Field(
        default=None,
        description=(
            "Retrieved approval signal from ChEMBL indication data. "
            "None if ChEMBL indication retrieval failed or returned no results. "
            "Never hardcoded — always produced from live API data."
        ),
    )
    clinical_trial_retrieval_status: str = Field(
        default="NOT_ATTEMPTED",
        description=(
            "Clinical trial data retrieval outcome: "
            "RETRIEVED (trials found), NOT_FOUND (query ok, 0 results), "
            "API_FAILURE (endpoint error), NOT_ATTEMPTED."
        ),
    )
    validated_disease_genes: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Gene-disease association scores from Open Targets (primary) or "
            "DisGeNET (fallback). Keys are gene symbols (e.g. 'CRBN') and "
            "UniProt accessions (e.g. 'Q96SW2') — both are stored for flexible "
            "lookup by MultiHopReasoner. Values are association scores [0.0, 1.0], "
            "higher = stronger association. "
            "Empty dict when neither Open Targets nor DisGeNET returned data. "
            "This field populates the disease-relevance validation in trace_paths() "
            "and MUST NOT feed evidence_records or Support Score calculation."
        ),
    )
    identifier_mappings: list[BiologicalIdentifierMapping] = Field(
        default_factory=list,
        description="Preserved source-provided biological identifier mappings from Open Targets, Reactome, etc.",
    )
    reactome_reaction_evidence: list[ReactomeReactionEvidence] = Field(
        default_factory=list,
        description="Preserved target-specific Reactome reaction and event level evidence records.",
    )
    opentargets_doe_evidence: list[OpenTargetsDoEEvidence] = Field(
        default_factory=list,
        description="Open Targets Direction of Effect evidence records.",
    )
    datts_evidence: list[DATTsEvidence] = Field(
        default_factory=list,
        description="DATTs disease-associated therapeutic target evidence records.",
    )
    drugmechdb_evidence: list[DrugMechDBEvidence] = Field(
        default_factory=list,
        description="DrugMechDB curated mechanistic path validation records.",
    )
    therapeutic_direction_evidence: list[TherapeuticDirectionEvidence] = Field(
        default_factory=list,
        description="Normalized therapeutic direction evidence records with provenance and independence grouping.",
    )
    disease_gene_evidence: list[DiseaseGeneEvidence] = Field(
        default_factory=list,
        description="Structured, tiered disease-associated gene evidence records with explicit scope and provenance.",
    )


    @property
    def literature_evidence(self) -> list[Evidence]:
        """Filter to evidence records with abstract text (for claim extraction).

        Includes all literature-type evidence: META_ANALYSIS, RCT, OBSERVATIONAL,
        and LITERATURE (OpenAlex, EuropePMC, Semantic Scholar). Previously LITERATURE
        was excluded, silently dropping all OpenAlex/EuropePMC/S2 abstracts from
        claim extraction (Bug P3 fix).
        """
        from backend.core.enums.evidence_type import EvidenceType
        return [
            e for e in self.evidence_records
            if e.evidence_type in (
                EvidenceType.META_ANALYSIS,
                EvidenceType.RCT,
                EvidenceType.OBSERVATIONAL,
                EvidenceType.LITERATURE,   # OpenAlex / EuropePMC / Semantic Scholar
            ) and e.abstract
        ]
