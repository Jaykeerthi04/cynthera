"""ReasoningResult entity — complete output of the reasoning subsystem.

Reference: 04_REASONING_SPECIFICATION.md, 02_DOMAIN_MODEL.md §4.16, §4.17
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field

from backend.core.enums.recommendation import RecommendationStatus
from backend.core.domain.contradiction import Contradiction
from backend.core.domain.contradiction_summary import ContradictionSummary


class SupportAssessment(BaseModel):
    """Support Score assessment from the SupportAssessmentAgent.

    Attributes:
        score: Support Score (SS) float [0.0, 1.0].
        level: Categorical level ('HIGH', 'MEDIUM', 'LOW').
        evidence_count: Number of evidence records contributing to the score.
        weighted_sum: Sum of all ERW values contributing.
        rationale: Human-readable explanation.
        supporting_claim_ids: UUIDs of Claims contributing positively.
    """

    model_config = {"frozen": True}

    score: float = Field(..., ge=0.0, le=1.0, description="Support Score [0.0, 1.0].")
    level: str = Field(..., pattern="^(HIGH|MEDIUM|LOW|NONE)$", description="Categorical level.")
    evidence_count: int = Field(default=0, ge=0)
    weighted_sum: float = Field(default=0.0, ge=0.0)
    rationale: str = Field(default="", description="Human-readable explanation.")
    supporting_claim_ids: list[str] = Field(default_factory=list)
    evidence_family_counts: dict[str, int] = Field(default_factory=dict, description="Counts by evidence family.")
    clinical_trial_success_count: int = Field(default=0, ge=0, description="Count of completed successful clinical trials.")
    has_high_quality_therapeutic: bool = Field(default=False, description="True only for authoritative, pair-scoped therapeutic evidence.")
    regulatory_approved: bool = Field(default=False, description="True if approved for this indication.")
    therapeutic_evidence_audit: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Provenance decisions for records considered by the high-quality therapeutic gate.",
    )


class MechanisticAssessment(BaseModel):
    """Mechanistic Score assessment from the MechanisticExpertAgent.

    Attributes:
        score: Mechanistic Score (MS) float [0.0, 1.0].
        level: Categorical level ('HIGH', 'MEDIUM', 'LOW', 'NONE').
        pathway_count: Number of overlapping pathways traced.
        mechanistic_chain: List of nodes in the primary traced chain (Drug→Target→Pathway→Disease).
        candidate_mechanisms: Discovered CandidateMechanism domain objects with hop evidence & URLs.
        evidence_status: 'SOURCE_UNAVAILABLE' | 'IDENTITY_RESOLUTION_FAILED' | 'INSUFFICIENT_EVIDENCE' | 'MECHANISTICALLY_UNSUPPORTED' | 'CONTRADICTED' | 'MECHANISTICALLY_PLAUSIBLE'
        literature_grounding_level: 'STRONG' | 'MODERATE' | 'NONE' | 'UNAVAILABLE'
        rationale: Human-readable explanation.
        score_components: Dictionary of weighted sub-scores contributing to the total score.
    """

    model_config = {"frozen": True}

    score: float = Field(..., ge=0.0, le=1.0, description="Mechanistic Score [0.0, 1.0].")
    level: str = Field(..., pattern="^(HIGH|MEDIUM|LOW|NONE)$", description="Categorical level.")
    pathway_count: int = Field(default=0, ge=0)
    mechanistic_chain: list[str] = Field(
        default_factory=list,
        description="Nodes in the primary mechanistic chain.",
    )
    candidate_mechanisms: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Serialized list of discovered CandidateMechanism objects.",
    )
    evidence_status: str = Field(
        default="MECHANISTICALLY_PLAUSIBLE",
        description="Data state: SOURCE_UNAVAILABLE | IDENTITY_RESOLUTION_FAILED | INSUFFICIENT_EVIDENCE | MECHANISTICALLY_UNSUPPORTED | CONTRADICTED | MECHANISTICALLY_PLAUSIBLE",
    )
    literature_grounding_level: str = Field(
        default="MODERATE",
        description="Literature grounding state: STRONG | MODERATE | NONE | UNAVAILABLE",
    )
    rationale: str = Field(default="", description="Human-readable explanation.")
    score_components: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Phase 5.1 mechanistic quality audit breakdown. "
            "Keys: raw_confidence (float), support_level (str), structural_edge_count (int), "
            "causal_edge_count (int), grounded_edge_count (int), "
            "independent_evidence_groups (int), reaction_enriched (bool). "
            "MS remains the raw mechanistic confidence score. Quality is exposed here separately "
            "so recommendation gating can use support_level without altering the numeric score."
        ),
    )


class RiskAssessment(BaseModel):
    """Risk Score assessment from the RiskAssessmentAgent.

    Attributes:
        score: Risk Score (RS) float [0.0, 1.0] where 1.0 = maximum risk.
        level: Categorical level ('HIGH', 'MEDIUM', 'LOW').
        failed_trial_count: Number of failed/terminated clinical trials found.
        contradiction_count: Number of contradictions detected.
        rationale: Human-readable explanation.
        risk_claim_ids: UUIDs of Claims contributing to risk.
    """

    model_config = {"frozen": True}

    score: float = Field(..., ge=0.0, le=1.0, description="Risk Score [0.0, 1.0].")
    level: str = Field(..., pattern="^(HIGH|MEDIUM|LOW|NONE)$", description="Categorical level.")
    failed_trial_count: int = Field(default=0, ge=0)
    contradiction_count: int = Field(default=0, ge=0)
    rationale: str = Field(default="", description="Human-readable explanation.")
    risk_claim_ids: list[str] = Field(default_factory=list)


def level_from_score(score: float) -> str:
    """Canonical derivation of opposition level from opposition score.

    Thresholds align with Rule 2b and Phase 5.16 specification:
    - >= 0.45: HIGH (Rule 2b veto threshold)
    - >= 0.25: MODERATE
    - > 0.0: LOW
    - == 0.0: NONE
    """
    if score >= 0.45:
        return "HIGH"
    elif score >= 0.25:
        return "MODERATE"
    elif score > 0.0:
        return "LOW"
    return "NONE"


class OppositionAssessment(BaseModel):
    """Therapeutic opposition evidence assessment (Phase 5.16).

    Captures explicit negative therapeutic evidence for the queried drug-disease pair.
    A score of 0.0 means no explicit negative evidence was found — it does NOT imply
    that the drug is safe or effective for this indication.

    Attributes:
        score: Aggregate opposition score [0.0, 1.0].
        level: Categorical level — NONE | LOW | MODERATE | HIGH.
        independent_group_count: Number of independent study groups with negative evidence.
        key_claim_ids: UUIDs of the highest-weight negative claims.
        rationale: Human-readable explanation.
        qualified_negative_claim_count: Claims that passed drug + disease relevance gates.
        qualified_claim_count: Alias for qualified_negative_claim_count matching canonical spec.
        excluded_negative_claim_count: Negative-predicate claims excluded by relevance gates.
        strongest_group_weight: Weight of the highest-weight evidence group.
        qualified_claims: Serialized list of qualified negative claims.
        independent_groups: Clustered independent study groups and weights.
        rejected_claims: Serialized list of excluded negative claims.
        rejection_reasons: Mapping of claim/trial ID to rejection reason.
    """

    model_config = {"frozen": True}

    score: float = Field(..., ge=0.0, le=1.0, description="Aggregate opposition score [0.0, 1.0].")
    level: str = Field(..., pattern="^(HIGH|MODERATE|LOW|NONE)$", description="Opposition level.")
    independent_group_count: int = Field(default=0, ge=0)
    key_claim_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(default="")
    qualified_negative_claim_count: int = Field(default=0, ge=0)
    qualified_claim_count: int = Field(default=0, ge=0)
    excluded_negative_claim_count: int = Field(default=0, ge=0)
    strongest_group_weight: float = Field(default=0.0, ge=0.0)
    has_direct_harm: bool = Field(default=False, description="True if evidence demonstrates clinically meaningful treatment-related harm.")
    qualified_claims: list[dict[str, Any]] = Field(default_factory=list)
    independent_groups: list[dict[str, Any]] = Field(default_factory=list)
    rejected_claims: list[dict[str, Any]] = Field(default_factory=list)
    rejection_reasons: dict[str, str] = Field(default_factory=dict)

    def __init__(self, **data: Any):
        # Synchronize claim counts if only one is specified or list is provided
        q_claims = data.get("qualified_claims", [])
        q_count = data.get("qualified_claim_count")
        q_neg_count = data.get("qualified_negative_claim_count")
        effective_q = max(
            len(q_claims),
            q_count if q_count is not None else 0,
            q_neg_count if q_neg_count is not None else 0,
        )
        if q_count is None:
            data["qualified_claim_count"] = effective_q
        if q_neg_count is None:
            data["qualified_negative_claim_count"] = effective_q

        indep_groups = data.get("independent_groups", [])
        indep_count = data.get("independent_group_count")
        if indep_count is None or (len(indep_groups) > (indep_count or 0)):
            data["independent_group_count"] = max(len(indep_groups), indep_count or 0)

        super().__init__(**data)

    @classmethod
    def empty(cls) -> "OppositionAssessment":
        """Return a zero-score assessment (no negative evidence detected)."""
        return cls(
            score=0.0,
            level="NONE",
            rationale="No explicit negative therapeutic evidence detected for this drug-disease pair.",
            independent_group_count=0,
            qualified_negative_claim_count=0,
            qualified_claim_count=0,
            excluded_negative_claim_count=0,
            strongest_group_weight=0.0,
            qualified_claims=[],
            independent_groups=[],
            rejected_claims=[],
            rejection_reasons={},
        )


class ScientificAuditReport(BaseModel):
    """Complete audit trail of the reasoning process.

    Attributes:
        summary: Executive summary of the evaluation.
        key_supporting_claim_ids: Claim IDs supporting the recommendation.
        key_contradicting_claim_ids: Claim IDs contradicting the hypothesis.
        data_gaps: Identified gaps in evidence.
        confidence_narrative: Text explaining the confidence calculation.
        recommendation_rationale: Step-by-step rule application trace.
        agent_verdicts: Per-agent assessment verdicts (typed dict, not buried in text).
        evaluation_pathway: Drug-disease relationship classification from retrieved data.
        clinical_trial_status: Retrieval outcome — RETRIEVED, NOT_FOUND, or API_FAILURE.
        top_citations: Formatted citation strings with PMID/DOI, title, type, ERW.
        safety_breakdown: Safety signals by category (adverse events, interactions, etc.).
        positive_factors: Explicit factors supporting the recommendation.
        negative_factors: Explicit factors against or limiting the recommendation.
    """

    model_config = {"frozen": True}

    summary: str = Field(..., description="Executive summary of the evaluation.")
    key_supporting_claim_ids: list[str] = Field(default_factory=list)
    key_contradicting_claim_ids: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    confidence_narrative: str = Field(default="")
    recommendation_rationale: str = Field(default="")
    mechanistic_narrative: str = Field(
        default="",
        description="Explicit narrative of biological candidate mechanisms and graph evidence.",
    )
    clinical_narrative: str = Field(
        default="",
        description="Explicit narrative of clinical trial findings with trial termination WHY analysis.",
    )
    safety_narrative: str = Field(
        default="",
        description="Explicit narrative of safety profile, adverse events, boxed warnings, and safety grade.",
    )
    final_synthesis: str = Field(
        default="",
        description="Integrated synthesis connecting mechanistic, clinical, and safety dimensions.",
    )
    agent_verdicts: dict[str, str] = Field(
        default_factory=dict,
        description="Per-agent assessment verdicts keyed by agent name.",
    )
    evaluation_pathway: str = Field(
        default="NOVEL_HYPOTHESIS",
        description=(
            "Classification inferred from retrieved ChEMBL indication data: "
            "APPROVED_INDICATION | PHASE_III_INVESTIGATION | "
            "PHASE_II_INVESTIGATION | PHASE_I_INVESTIGATION | NOVEL_HYPOTHESIS"
        ),
    )
    clinical_trial_status: str = Field(
        default="NOT_ATTEMPTED",
        description=(
            "Clinical trial data retrieval outcome: "
            "RETRIEVED (trials found), NOT_FOUND (query succeeded, 0 results), "
            "API_FAILURE (endpoint error), NOT_ATTEMPTED."
        ),
    )
    top_citations: list[str] = Field(
        default_factory=list,
        description="Formatted citation strings: PMID/DOI, title, evidence type, ERW.",
    )
    claims_by_source: dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown of extracted claims by literature source name (e.g. pubmed, europepmc).",
    )
    safety_breakdown: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Safety signals by category from ClinicalSafetyAgent: "
            "adverse_events, drug_interactions, population_restrictions, "
            "hepatotoxicity, cardiotoxicity, nephrotoxicity signals."
        ),
    )
    positive_factors: list[str] = Field(
        default_factory=list,
        description="Factors explicitly supporting the recommendation.",
    )
    negative_factors: list[str] = Field(
        default_factory=list,
        description="Factors against or limiting the recommendation.",
    )
    scientific_context: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Dimensional prior-knowledge context assembled by ScientificContextBuilder: "
            "regulatory, repurposing, mechanistic, clinical, and knowledge_maturity "
            "statuses, each with confidence and evidence provenance, plus related "
            "prior-knowledge pairs. Descriptive only — Rule -1 uses the regulatory "
            "dimension (== APPROVED) exclusively."
        ),
    )
    claim_citations: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Maps each Claim UUID (str) to its supporting PMID/DOI citation keys. "
            "Built at report-assembly time from Claim.evidence_ids → Evidence.citation_key. "
            "Enables per-claim traceability in JSON exports and audit UI."
        ),
    )
    candidate_mechanisms: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Discovered candidate biological mechanisms with hop evidence and clickable links.",
    )
    sources_accessed: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of queried database sources with status and direct portal links.",
    )
    therapeutic_alignment: dict[str, Any] = Field(
        default_factory=dict,
        description="Phase 4D Therapeutic Alignment report capturing target-level and overall directional compatibility.",
    )
    contradiction_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Phase 5.6 structured contradiction and uncertainty summary dict.",
    )
    rule_minus_one_trace: dict[str, Any] = Field(
        default_factory=dict,
        description="Phase 1B Rule -1 routing and opposition evaluation trace.",
    )




class ReasoningResult(BaseModel):
    """Complete output of the reasoning pipeline for a Hypothesis evaluation.

    Immutable. The final artifact produced by the ReasoningOrchestrator.

    Attributes:
        id: Internal UUID.
        hypothesis_id: UUID of the evaluated Hypothesis.
        support_assessment: Full SupportAssessmentAgent output.
        mechanistic_assessment: Full MechanisticExpertAgent output.
        risk_assessment: Full RiskAssessmentAgent output.
        contradictions: All Contradiction objects detected.
        recommendation_status: Final RecommendationStatus.
        recommendation_reasons: Ordered list of rule-based reasons.
        audit_report: Full ScientificAuditReport.
        rule_set_version: Version of the RuleEngine rule set used.
        reasoning_duration_ms: Total reasoning pipeline duration.
        completed_at: UTC timestamp of completion.
        data_source_failures: Explicit list of named retrieval failures propagated
            from the retrieval package. Each entry is a human-readable statement of
            what failed and what data it would have contributed. These are displayed
            verbatim in the frontend report — they are NOT absorbed into scores.
        claim_extraction_method: The extraction method used for all claims:
            'llm' (full LLM extraction), 'rule_based_fallback' (keyword-matching
            because LLM was unavailable), or 'mixed' (some records used LLM,
            some used fallback). Displayed in the report so the user knows the
            claim quality.
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Internal unique identifier.")
    hypothesis_id: uuid.UUID = Field(..., description="UUID of the evaluated Hypothesis.")
    support_assessment: SupportAssessment = Field(..., description="Support assessment output.")
    mechanistic_assessment: MechanisticAssessment = Field(..., description="Mechanistic assessment output.")
    risk_assessment: RiskAssessment = Field(..., description="Risk assessment output.")
    contradictions: list[Contradiction] = Field(default_factory=list, description="Detected contradictions.")
    recommendation_status: RecommendationStatus = Field(..., description="Final recommendation status.")
    recommendation_reasons: list[str] = Field(
        default_factory=list,
        description="Ordered list of rule-based reasons for the recommendation.",
    )
    audit_report: ScientificAuditReport = Field(..., description="Full scientific audit report.")
    rule_set_version: str = Field(default="3.2", description="RuleEngine rule set version used.")
    reasoning_duration_ms: float = Field(default=0.0, ge=0.0, description="Total reasoning duration ms.")
    completed_at: datetime = Field(default_factory=datetime.utcnow, description="UTC completion timestamp.")
    data_source_failures: list[str] = Field(
        default_factory=list,
        description=(
            "Explicit retrieval failure statements propagated from the retrieval package. "
            "Each entry names the source, what it would have contributed, and the impact "
            "on scoring. Displayed verbatim in the frontend — not absorbed into scores."
        ),
    )
    claim_extraction_method: str = Field(
        default="unknown",
        description=(
            "Extraction method for all claims: 'llm' | 'rule_based_fallback' | 'mixed' | 'none'. "
            "'rule_based_fallback' means LLM was unavailable; claims are keyword-matched, "
            "not scientifically extracted. Displayed in the report."
        ),
    )
    contradiction_summary: ContradictionSummary | None = Field(
        default=None,
        description="Phase 5.6 structured contradiction and epistemic uncertainty summary.",
    )
    opposition_assessment: OppositionAssessment = Field(
        default_factory=OppositionAssessment.empty,
        description="Phase 5.16 therapeutic opposition evidence assessment.",
    )

    @property
    def opposition_score(self) -> float:
        """Canonical opposition score directly from opposition assessment."""
        return self.opposition_assessment.score

    @property
    def opposition_level(self) -> str:
        """Canonical opposition level directly from opposition assessment."""
        return self.opposition_assessment.level

    @property
    def qualified_negative_claim_count(self) -> int:
        """Canonical count of qualified negative claims."""
        return self.opposition_assessment.qualified_negative_claim_count

    @property
    def independent_opposition_group_count(self) -> int:
        """Canonical count of independent study groups with negative evidence."""
        return self.opposition_assessment.independent_group_count

    @classmethod
    def resolution_failed(
        cls,
        hypothesis_id: uuid.UUID,
        drug_name: str,
        disease_name: str,
        reasons: list[str] | None = None,
    ) -> "ReasoningResult":
        """Factory method for creating a RESOLUTION_FAILED ReasoningResult when
        identity resolution fails for both drug and disease.

        Suppresses misleading scores (SS=0.0, MS=0.0, RS=0.0) and sets status
        to RESOLUTION_FAILED with explicit diagnostic summary.
        """
        summary_msg = (
            f"Identifier resolution failed for '{drug_name}' and/or '{disease_name}'. "
            "Neither entity could be mapped to canonical ontology identifiers (ChEMBL, MeSH, MONDO). "
            "No scientific conclusion can be drawn from this run — a retry or synonym query is recommended."
        )
        fail_reasons = reasons or [
            f"Failed to map drug '{drug_name}' to a ChEMBL compound ID.",
            f"Failed to map disease '{disease_name}' to a MeSH or MONDO ID.",
        ]
        return cls(
            hypothesis_id=hypothesis_id,
            support_assessment=SupportAssessment(
                score=0.0, level="NONE", rationale="Resolution failed — support score not computed."
            ),
            mechanistic_assessment=MechanisticAssessment(
                score=0.0, level="NONE", rationale="Resolution failed — mechanistic score not computed."
            ),
            risk_assessment=RiskAssessment(
                score=0.0, level="NONE", rationale="Resolution failed — risk score not computed."
            ),
            opposition_assessment=OppositionAssessment.empty(),
            recommendation_status=RecommendationStatus.RESOLUTION_FAILED,
            recommendation_reasons=fail_reasons,
            audit_report=ScientificAuditReport(
                summary=summary_msg,
                confidence_narrative="Confidence is 0.0 because entity identity could not be established.",
                recommendation_rationale="Identifier resolution hard gate triggered.",
                data_gaps=["Drug ChEMBL ID unmapped", "Disease MeSH/MONDO ID unmapped"],
            ),
            completed_at=datetime.utcnow(),
        )
