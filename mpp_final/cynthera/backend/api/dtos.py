"""CYNTHERA DTOs — Typed data transfer objects for research-grade frontend and report export."""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class AnalysisRequestDTO(BaseModel):
    """Request payload for POST /api/analyze."""
    drug: str = Field(..., min_length=1, max_length=200, description="Common or generic drug name.")
    disease: str = Field(..., min_length=1, max_length=200, description="Disease or indication name.")
    policy: str = Field(default="STANDARD", description="Retrieval policy: STANDARD | FAST | COMPREHENSIVE.")
    bypass_cache: bool = Field(default=False, description="Whether to bypass evaluation cache.")


class DrugDTO(BaseModel):
    name: str
    chembl_id: Optional[str] = None
    canonical_smiles: Optional[str] = None
    synonyms: list[str] = Field(default_factory=list)
    global_approval_phase: int = 0
    matched_indication_phase: int = 0


class DiseaseDTO(BaseModel):
    name: str
    mesh_id: Optional[str] = None
    mondo_id: Optional[str] = None
    efo_id: Optional[str] = None
    synonyms: list[str] = Field(default_factory=list)


class DecisionDTO(BaseModel):
    verdict: str = Field(..., description="Authoritative 3-class decision: SUPPORT | OPPOSE | UNCERTAIN")
    recommendation: str = Field(..., description="Authoritative recommendation: PROMISING | NOT_RECOMMENDED | UNCERTAIN")
    hypothesis_status: str = "INVESTIGATIONAL / NOVEL HYPOTHESIS"
    repurposing_novelty: str = "NOVEL"
    evidence_support_score: float = 0.0
    evidence_support_tier: str = "NONE"
    risk_score: float = 0.0
    opposition_score: float = 0.0
    rationale: str
    therapeutic_anchor: bool = False
    mechanistic_evidence: str = "NONE"   # HIGH | MODERATE | LOW | NONE
    therapeutic_evidence: str = "LOW"    # HIGH | MODERATE | LOW
    opposition: str = "NONE"             # NONE | LOW | MODERATE | HIGH
    contradiction: str = "NONE"          # NONE | MINOR | MODERATE | STRONG
    safety_grade: str = "B"              # A | B | C | D | HIGH_RISK
    safety_summary: str = ""
    structured_why: list[dict[str, str]] = Field(default_factory=list)


class TargetDTO(BaseModel):
    symbol: str
    uniprot_id: str
    name: str
    chembl_id: Optional[str] = None
    mechanism_count: int = 0
    disease_relevance: float = 0.0
    evidence_count: int = 0
    affinity_nm: Optional[float] = None
    source: str = "ChEMBL / Open Targets"
    source_url: Optional[str] = None


class MechanismHopDTO(BaseModel):
    from_node: str
    to_node: str
    predicate: str
    status: str
    evidence_strength: float
    source_database: str
    provenance_note: str = ""
    polarity: str = "UNKNOWN"          # POSITIVE | NEGATIVE | UNKNOWN
    causal_grounding: str = "STRUCTURAL"  # DIRECT | CURATED | INFERRED | STRUCTURAL | NONE
    evidence_type: str = "STRUCTURAL"     # DIRECT | CURATED | STRUCTURAL | LITERATURE
    source_url: Optional[str] = None


class CandidateMechanismDTO(BaseModel):
    candidate_id: str
    target: str
    pathway: str
    biological_process: str
    hops: list[MechanismHopDTO] = Field(default_factory=list)
    support_level: str = "UNKNOWN"
    overall_confidence: float = 0.0
    rationale: str = ""


class MechanismDTO(BaseModel):
    score: float = 0.0
    level: str = "NONE"
    primary_chain: list[str] = Field(default_factory=list)
    pathway_count: int = 0
    candidate_mechanisms: list[CandidateMechanismDTO] = Field(default_factory=list)
    targets: list[TargetDTO] = Field(default_factory=list)
    evidence_status: str = "INSUFFICIENT_EVIDENCE"
    literature_grounding_level: str = "NONE"
    rationale: str = ""


class TherapeuticEvidenceItemDTO(BaseModel):
    id: str
    evidence_type: str            # REGULATORY_INDICATION | CLINICAL_TRIAL | RCT | OBSERVATIONAL | REVIEW | LITERATURE_CLAIM | CELL_LINE
    source: str
    citation_key: str
    title: Optional[str] = None
    abstract: Optional[str] = None
    direction: str = "UNKNOWN"    # SUPPORTS | OPPOSES | UNCERTAIN | UNKNOWN
    quality_tier: str = "MODERATE"  # HIGH | MODERATE | LOW | UNVERIFIED
    pair_specificity: bool = False
    independent_group: str = "group:unknown"
    extracted_claim: Optional[str] = None
    study_type: Optional[str] = None
    outcome: Optional[str] = None
    why_stopped: Optional[str] = None
    target: Optional[str] = None
    pathway: Optional[str] = None
    source_url: Optional[str] = None
    provenance_id: Optional[str] = None
    retrieved_at: Optional[str] = None
    drug_name: Optional[str] = None
    disease_name: Optional[str] = None


class OppositionDTO(BaseModel):
    score: float = 0.0
    level: str = "NONE"           # NONE | LOW | MODERATE | HIGH
    qualified_negative_claim_count: int = 0
    excluded_negative_claim_count: int = 0
    independent_group_count: int = 0
    key_claims: list[TherapeuticEvidenceItemDTO] = Field(default_factory=list)
    rationale: str = ""


class ContradictionItemDTO(BaseModel):
    id: str
    conflict_type: str            # DIRECT_OPPOSITION | OUTCOME_DISCORDANCE | POTENCY_MISMATCH | DIRECTIONAL_MISMATCH
    severity: str                 # MINOR | MODERATE | STRONG
    supporting_records: list[str] = Field(default_factory=list)
    opposing_records: list[str] = Field(default_factory=list)
    explanation: str
    resolution: str = "UNRESOLVED"


class SafetyDTO(BaseModel):
    risk_score: float = 0.0
    risk_level: str = "LOW"
    safety_grade: str = "B"
    failed_trial_count: int = 0
    adverse_event_count: int = 0
    summary: str = ""
    signals: dict[str, Any] = Field(default_factory=dict)


class SourceStatusDTO(BaseModel):
    name: str
    status: str                   # "available" | "unavailable" | "partial"
    retrieved_count: int = 0
    used_count: int = 0
    excluded_count: int = 0
    reason_for_exclusion: Optional[str] = None
    impact: Optional[str] = None
    canonical_portal_url: Optional[str] = None


class ProvenanceDTO(BaseModel):
    raw_record_count: int = 0
    deduplicated_record_count: int = 0
    independent_group_count: int = 0
    retrieval_timestamp: str = ""
    sources: list[SourceStatusDTO] = Field(default_factory=list)


class AnalysisResultDTO(BaseModel):
    """Complete analysis response payload for researcher-facing frontend."""
    analysis_id: str
    hypothesis_id: str
    status: str                   # "completed" | "partial" | "failed"
    duration_ms: float = 0.0
    rule_set_version: str = "3.2"
    drug: DrugDTO
    disease: DiseaseDTO
    decision: DecisionDTO
    mechanism: MechanismDTO
    therapeutic_evidence: list[TherapeuticEvidenceItemDTO] = Field(default_factory=list)
    opposition: OppositionDTO
    contradictions: list[ContradictionItemDTO] = Field(default_factory=list)
    safety: SafetyDTO
    provenance: ProvenanceDTO
    sources: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    audit_trace: dict[str, Any] = Field(default_factory=dict)


class ReportModelDTO(BaseModel):
    """Structured 15-section scientific report model."""
    report_version: str = "1.0"
    generated_at: str
    analysis_id: str
    drug: DrugDTO
    disease: DiseaseDTO
    evaluated_hypothesis: str
    executive_summary: str
    decision: DecisionDTO
    evidence_overview: dict[str, Any]
    entity_resolution: dict[str, Any]
    regulatory_evidence: dict[str, Any]
    mechanistic_evidence: MechanismDTO
    therapeutic_evidence: list[TherapeuticEvidenceItemDTO]
    opposing_evidence: OppositionDTO
    contradictions: list[ContradictionItemDTO]
    evidence_independence: dict[str, Any]
    safety_analysis: SafetyDTO
    final_reasoning: dict[str, Any]
    limitations: list[str]
    evidence_ledger: list[TherapeuticEvidenceItemDTO]
    references: list[dict[str, str]]
