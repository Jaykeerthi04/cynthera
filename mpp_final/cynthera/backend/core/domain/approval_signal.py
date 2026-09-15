"""ApprovalSignal — retrieved evidence of a drug's approval status for a disease.

This object is populated entirely from live biomedical database retrieval
(ChEMBL drug_indication endpoint) and carries no hardcoded biomedical facts.

Reference: 04_REASONING_SPECIFICATION.md, 02_DOMAIN_MODEL.md
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# Phase descriptions — these describe ChEMBL clinical development phases,
# not drug-specific knowledge. Safe to define as constants.
_PHASE_LABELS: dict[int, str] = {
    4: "FDA/EMA Approved",
    3: "Phase III Clinical Trial",
    2: "Phase II Clinical Trial",
    1: "Phase I Clinical Trial",
    0: "Preclinical / Not in Clinical Development",
}

_EVALUATION_PATHWAY_BY_PHASE: dict[int, str] = {
    4: "APPROVED_INDICATION",
    3: "PHASE_III_INVESTIGATION",
    2: "PHASE_II_INVESTIGATION",
    1: "PHASE_I_INVESTIGATION",
    0: "NOVEL_HYPOTHESIS",
}


class ApprovalSignal(BaseModel):
    """Evidence of a drug's regulatory approval status for a specific disease.

    Populated from ChEMBL drug_indication data retrieved live.
    Contains NO hardcoded drug-disease facts — all fields are set from
    API responses during the retrieval pipeline execution.

    Attributes:
        is_approved: True if max_phase_for_ind == 4 (FDA/EMA approved).
        max_phase: Highest clinical phase reached for this specific indication.
        matched_indication_term: The EFO/MeSH term that matched the queried disease.
        match_confidence: Fuzzy string match confidence [0.0, 1.0].
        evaluation_pathway: Classification string for the rule engine.
        phase_label: Human-readable phase description.
        source: Data source that produced this signal.
        approved_indications_count: Total number of approved indications for this drug.
    """

    model_config = {"frozen": True}

    is_approved: bool = Field(
        default=False,
        description="True if max_phase_for_ind == 4 for this disease.",
    )
    max_phase: int = Field(
        default=0,
        ge=0,
        le=4,
        description="Highest clinical phase reached for this indication (0-4).",
    )
    matched_indication_term: str = Field(
        default="",
        description="The indication term (EFO/MeSH) that best matched the queried disease.",
    )
    match_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fuzzy match confidence between queried disease and matched indication term.",
    )
    evaluation_pathway: str = Field(
        default="NOVEL_HYPOTHESIS",
        description=(
            "Classification for the rule engine: "
            "APPROVED_INDICATION | PHASE_III_INVESTIGATION | "
            "PHASE_II_INVESTIGATION | PHASE_I_INVESTIGATION | NOVEL_HYPOTHESIS"
        ),
    )
    phase_label: str = Field(
        default="Preclinical / Not in Clinical Development",
        description="Human-readable regulatory phase description.",
    )
    source: str = Field(
        default="chembl",
        description="Data source that produced this signal.",
    )
    approved_indications_count: int = Field(
        default=0,
        ge=0,
        description="Total number of approved indications recorded for this drug across all diseases.",
    )
    global_approval_phase: int = Field(
        default=0,
        ge=0,
        le=4,
        description="Highest regulatory approval phase achieved globally across any indication for this drug.",
    )
    matched_indication_phase: int = Field(
        default=0,
        ge=0,
        le=4,
        description="Highest clinical phase reached for this specific matched indication in ChEMBL.",
    )
    late_stage_investigational_phase: int = Field(
        default=0,
        ge=0,
        le=4,
        description="Phase if in late-stage investigational development (Phase 2 or 3), else 0.",
    )
    requested_disease: str = Field(
        default="",
        description="The queried disease name.",
    )
    matching_rationale: str = Field(
        default="",
        description="Explanation of how the indication matched or did not match.",
    )
    disease_relation: str = Field(
        default="",
        description="Disease relation classification for indication match (e.g. SAME, SIBLING_EXCLUDED).",
    )
    disease_relation_policy: str = Field(
        default="APPROVAL_ANCHOR",
        description="Policy governing indication matching.",
    )

    @property
    def matched_indication(self) -> str:
        """Alias for matched_indication_term."""
        return self.matched_indication_term

    @classmethod
    def from_chembl_indication_match(
        cls,
        max_phase: int,
        matched_term: str,
        match_confidence: float,
        approved_count: int,
        source: str = "chembl",
        global_approval_phase: int = 0,
        requested_disease: str = "",
        matching_rationale: str = "",
        disease_relation: str = "SAME",
        disease_relation_policy: str = "APPROVAL_ANCHOR",
    ) -> "ApprovalSignal":
        """Build an ApprovalSignal from a ChEMBL indication match result.

        Args:
            max_phase: The max_phase_for_ind value from ChEMBL for the matched indication.
            matched_term: The EFO/MeSH term that best matched the query.
            match_confidence: Fuzzy match confidence [0.0, 1.0].
            approved_count: Total approved indications for this drug.
            source: Provenance source string for this signal.
            global_approval_phase: Global max phase for molecule (e.g. 4 if approved for any disease).
            requested_disease: The queried disease name.
            matching_rationale: Explanation of how indication matched.
            disease_relation: Disease relation classification string.
            disease_relation_policy: Governing policy string.

        Returns:
            A populated ApprovalSignal.
        """
        clamped = max(0, min(4, int(max_phase)))
        clamped_global = max(0, min(4, int(global_approval_phase)))
        late_stage = clamped if clamped in (2, 3) else 0

        return cls(
            is_approved=(clamped == 4),
            max_phase=clamped,
            matched_indication_term=matched_term,
            match_confidence=round(match_confidence, 4),
            evaluation_pathway=_EVALUATION_PATHWAY_BY_PHASE.get(
                clamped, "NOVEL_HYPOTHESIS"
            ),
            phase_label=_PHASE_LABELS.get(clamped, "Unknown"),
            source=source,
            approved_indications_count=approved_count,
            global_approval_phase=clamped_global,
            matched_indication_phase=clamped,
            late_stage_investigational_phase=late_stage,
            requested_disease=requested_disease,
            matching_rationale=matching_rationale,
            disease_relation=disease_relation,
            disease_relation_policy=disease_relation_policy,
        )

    @classmethod
    def no_data(
        cls,
        requested_disease: str = "",
        matching_rationale: str = "No indication data found.",
    ) -> "ApprovalSignal":
        """Return a default signal when no ChEMBL indication data is available."""
        return cls(
            is_approved=False,
            max_phase=0,
            matched_indication_term="",
            match_confidence=0.0,
            evaluation_pathway="NOVEL_HYPOTHESIS",
            phase_label="Preclinical / Not in Clinical Development",
            source="none",
            approved_indications_count=0,
            global_approval_phase=0,
            matched_indication_phase=0,
            late_stage_investigational_phase=0,
            requested_disease=requested_disease,
            matching_rationale=matching_rationale,
        )
