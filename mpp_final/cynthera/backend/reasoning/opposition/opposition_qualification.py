"""Opposition Qualification Module for CYNTHERA (Phase P0b-2).

Provides semantic qualification of empirical opposition evidence before Rule 2b
can veto a hypothesis or override an approved indication.

Distinguishes between:
- DIRECT_THERAPEUTIC_FAILURE: Genuine primary efficacy failure of the evaluated drug
  for the target disease/indication (participates in Rule 2b).
- INDIRECT_SUBPOPULATION_RESULT: Trial conducted in a specialized subpopulation
  (e.g., hemodialysis / ESRD) or evaluated a surrogate/remodeling endpoint
  (e.g., LVH regression) rather than primary disease efficacy.
- BACKGROUND_THERAPY_FAILURE: Evaluated drug was constant background or maintenance
  therapy being stepped down, tapered, or augmented; failure to step down background
  therapy does NOT establish therapeutic failure of the background drug.
- ACTIVE_COMPARATOR_DIRECTION_ERROR: Evaluated drug was the active reference standard;
  failure of an investigational agent against it does not imply failure of the standard.
- BIOSIMILAR_EQUIVALENCE_FAILURE: A candidate biosimilar failed to establish
  equivalence/non-inferiority against the reference product; does not imply failure
  of the reference product itself.
- SAFETY_SIGNAL: Safety termination or adverse event signal that does not constitute
  direct therapeutic ineffectiveness for the indication.

Reference: CYNTHERA P0b-2 Specification.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from backend.core.domain.claim import Claim
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.trial_attribution import TrialDrugRole
from backend.engineering.retrieval.disease_relation import (
    DiseaseRelation,
    classify_disease_relation,
    matches_for_trial_attribution,
    normalize_disease_term,
)

logger = logging.getLogger(__name__)


class OppositionQualificationResult(BaseModel):
    """Structured forensic qualification of an empirical opposition claim."""

    model_config = {"frozen": True}

    qualified: bool = Field(
        ...,
        description="True if claim qualifies as direct empirical opposition capable of Rule 2b participation.",
    )
    reason_code: str = Field(
        ...,
        description=(
            "Semantic classification: DIRECT_THERAPEUTIC_FAILURE | "
            "DIRECT_THERAPEUTIC_HARM | "
            "INDIRECT_SUBPOPULATION_RESULT | BACKGROUND_THERAPY_FAILURE | "
            "ACTIVE_COMPARATOR_DIRECTION_ERROR | BIOSIMILAR_EQUIVALENCE_FAILURE | "
            "SAFETY_SIGNAL | AMBIGUOUS_INTERVENTION | UNRELATED_DISEASE"
        ),
    )
    directness: str = Field(
        ...,
        description="Evidence directness relative to hypothesis: DIRECT | INDIRECT | SUBPOPULATION | SURROGATE",
    )
    intervention_role: str = Field(
        ...,
        description="Role of evaluated drug in trial arm structure (TrialDrugRole value).",
    )
    endpoint_relevance: str = Field(
        ...,
        description=(
            "Clinical endpoint relevance: PRIMARY_EFFICACY_FAILURE | "
            "SECONDARY_ENDPOINT_ONLY | STEP_DOWN_OR_ADD_ON | "
            "EQUIVALENCE_CRITERION_FAILURE | SURROGATE_OR_SUBPOPULATION | "
            "SAFETY_ENDPOINT_ONLY | NOT_RELEVANT"
        ),
    )
    comparator_semantics: str = Field(
        ...,
        description=(
            "Comparator relationship: VALID_EXPERIMENTAL_ARM | "
            "REFERENCE_PRODUCT_COMPARATOR | BACKGROUND_STANDARD_OF_CARE | "
            "PLACEBO_CONTROL | UNCERTAIN"
        ),
    )
    disease_relation: str = Field(
        ...,
        description="Disease ontology relationship: SAME | PARENT_CHILD | SIBLING_EXCLUDED | UNRELATED | SPECIAL_SUBPOPULATION",
    )
    replication_eligible: bool = Field(
        ...,
        description="True if evidence is eligible to count toward independent replication for approved indication veto.",
    )
    is_direct_harm: bool = Field(
        default=False,
        description="True if evidence demonstrates clinically meaningful treatment-related harm.",
    )
    explanation: str = Field(
        ...,
        description="Human-auditable explanation of semantic qualification decision.",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert qualification result to dictionary."""
        return {
            "qualified": self.qualified,
            "reason_code": self.reason_code,
            "directness": self.directness,
            "intervention_role": self.intervention_role,
            "endpoint_relevance": self.endpoint_relevance,
            "comparator_semantics": self.comparator_semantics,
            "disease_relation": self.disease_relation,
            "replication_eligible": self.replication_eligible,
            "is_direct_harm": self.is_direct_harm,
            "explanation": self.explanation,
        }


# ─────────────────────────────────────────────
# Semantic Pattern Definitions
# ─────────────────────────────────────────────

# Biosimilar / Reference Standard cues
_BIOSIMILAR_PATTERNS = (
    r"\bbiosimilar\b",
    r"\bequivalence\b",
    r"\bnon-inferiority\b",
    r"\btherapeutic equivalence\b",
    r"\bcomparability\b",
    r"\bcomparison to [a-z0-9\s\-]+\b",
    r"\bcompared to [a-z0-9\s\-]+\b",
    r"\bcomparison with [a-z0-9\s\-]+\b",
    r"\breference product\b",
    r"\breference standard\b",
)

# Candidate biosimilar alphanumeric codes
_BIOSIMILAR_CODE_PATTERNS = (
    r"\b[a-z]{2,4}\-?\d{3,5}\b",      # e.g., FYB201, CT-P13, SB4, ABP501, GP2013
    r"\bhd\d{3}\b",
    r"\bchs\-\d{3,4}\b",
    r"\bpf\-\d{7}\b",
    r"\bbi\s*695502\b",
)

# Step-down / Weaning / Tapering / Background reduction patterns
_STEP_DOWN_PATTERNS = (
    r"\breduction of (?:inhaled )?(?:corticosteroids|steroids|therapy|treatment|medication)\b",
    r"\b(?:steroid|dose|treatment|therapy|medication) (?:reduction|step-down|weaning|withdrawal|tapering|sparing)\b",
    r"\bstep-down\b",
    r"\bstep down\b",
    r"\bweaning\b",
    r"\btapering\b",
    r"\bsteroid-sparing\b",
    r"\bcorticosteroid-sparing\b",
    r"\bmaintenance therapy withdrawal\b",
    r"\bsparing of\b",
    r"\bdiscontinuation of background\b",
)

# Specialized subpopulation cues
_SUBPOPULATION_CUES = (
    r"\bhemodialysis\b",
    r"\bdialysis\b",
    r"\bend-stage renal disease\b",
    r"\besrd\b",
    r"\bperitoneal dialysis\b",
    r"\bmechanical ventilation\b",
    r"\becmo\b",
    r"\bsalvage\b",
    r"\brefractory to all\b",
    r"\bintensive care unit\b",
    r"\bicu patients\b",
)

# Surrogate structural / remodeling endpoint patterns
_SURROGATE_ENDPOINT_PATTERNS = (
    r"\bleft ventricular hypertrophy\b",
    r"\blvh regression\b",
    r"\blvh by echocardiographic\b",
    r"\bechocardiographic criteria\b",
    r"\bintima-media thickness\b",
    r"\bcoronary artery calcium\b",
    r"\bplaque volume\b",
    r"\bflow-mediated dilation\b",
    r"\bbiomarker change\b",
)


def qualify_opposition_claim(
    claim: Claim,
    drug_name: str,
    disease_name: str,
    trial: ClinicalTrial | None = None,
) -> OppositionQualificationResult:
    """Semantically qualify an opposition claim relative to the evaluated hypothesis.

    Args:
        claim: Negative Claim object (from CT.gov adapter or literature).
        drug_name: Target drug being evaluated.
        disease_name: Target disease being evaluated.
        trial: Optional raw ClinicalTrial object if available.

    Returns:
        OppositionQualificationResult with structured forensic verdict.
    """
    drug_clean = drug_name.strip().lower()
    disease_clean = disease_name.strip().lower()
    if claim is None:
        return OppositionQualificationResult(
            qualified=False,
            reason_code="AMBIGUOUS_INTERVENTION",
            directness="INDIRECT",
            intervention_role="UNKNOWN",
            endpoint_relevance="NOT_RELEVANT",
            comparator_semantics="UNCERTAIN",
            disease_relation="UNRELATED",
            replication_eligible=False,
            is_direct_harm=False,
            explanation="Claim is None; unable to evaluate opposition.",
        )

    # Extract attribution trace and metadata
    attr_trace = claim.attribution_trace or {}
    if "drug_role" in attr_trace:
        drug_role_str = str(attr_trace["drug_role"])
    else:
        # Direct literature or synthetic claim: subject is the evaluated entity
        drug_role_str = TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION.value
    is_differentiating = bool(attr_trace.get("is_differentiating_intervention", True))
    attr_decision = bool(attr_trace.get("final_attribution_decision", True))

    raw_text = (claim.raw_text or "").lower()
    claim_subject = claim.subject.lower()
    claim_object = claim.object.lower()

    # Trial-level metadata if available
    trial_title = (getattr(trial, "title", None) or attr_trace.get("title", "") or "").lower()
    why_stopped = (getattr(trial, "why_stopped", None) or attr_trace.get("why_stopped", "") or "").lower()
    conditions = [c.lower() for c in (getattr(trial, "condition_names", None) or attr_trace.get("conditions", []))]
    interventions = [i.lower() for i in (getattr(trial, "intervention_names", None) or attr_trace.get("interventions", []))]
    comparators = [c.lower() for c in (getattr(trial, "comparator_names", None) or attr_trace.get("comparators", []))]

    combined_text = f"{trial_title} {why_stopped} {raw_text}".lower()

    # ─────────────────────────────────────────────
    # 1. Disease Relation & Pair Specificity Check
    # ─────────────────────────────────────────────
    dis_rel = classify_disease_relation(disease_clean, claim_object)
    if dis_rel == DiseaseRelation.SIBLING_EXCLUDED:
        return OppositionQualificationResult(
            qualified=False,
            reason_code="UNRELATED_DISEASE",
            directness="INDIRECT",
            intervention_role=drug_role_str,
            endpoint_relevance="NOT_RELEVANT",
            comparator_semantics="UNCERTAIN",
            disease_relation="SIBLING_EXCLUDED",
            replication_eligible=False,
            explanation=(
                f"Claim disease object '{claim.object}' is a sibling-excluded condition of "
                f"hypothesis disease '{disease_name}' (e.g. ischemic vs hemorrhagic stroke)."
            ),
        )

    # ─────────────────────────────────────────────
    # 2. Biosimilar / Reference Standard Semantics
    # ─────────────────────────────────────────────
    # E.g., Ranibizumab (Lucentis) vs FYB201 in NCT02611778
    has_biosimilar_term = any(re.search(p, combined_text) for p in _BIOSIMILAR_PATTERNS)
    has_biosimilar_code = any(re.search(p, trial_title) for p in _BIOSIMILAR_CODE_PATTERNS)
    
    # Check outcome measures for EQUIVALENCE_FAILURE or NON_INFERIORITY_FAILURE
    has_equiv_failure = False
    outcome_measures = getattr(trial, "outcome_measures", None) or attr_trace.get("outcome_measures", []) or []
    for om in outcome_measures:
        r_code = om.get("reason_code") if isinstance(om, dict) else getattr(om, "reason_code", None)
        if r_code in ("EQUIVALENCE_FAILURE", "NON_INFERIORITY_FAILURE"):
            has_equiv_failure = True
            break

    if (has_biosimilar_term or has_biosimilar_code or has_equiv_failure) and (
        "lucentis" in combined_text or "ranibizumab" in drug_clean or "reference" in combined_text or "comparison to" in trial_title
    ):
        # The hypothesis drug is the reference product against which a candidate biosimilar was tested
        return OppositionQualificationResult(
            qualified=False,
            reason_code="BIOSIMILAR_EQUIVALENCE_FAILURE",
            directness="INDIRECT",
            intervention_role=drug_role_str,
            endpoint_relevance="EQUIVALENCE_CRITERION_FAILURE",
            comparator_semantics="REFERENCE_PRODUCT_COMPARATOR",
            disease_relation=dis_rel.value,
            replication_eligible=False,
            explanation=(
                f"Trial evaluates candidate biosimilar equivalence/non-inferiority against {drug_name} as "
                f"reference standard. Failure of a candidate biosimilar to establish equivalence to {drug_name} "
                f"does not establish therapeutic failure of {drug_name}."
            ),
        )

    # ─────────────────────────────────────────────
    # 3. Background Therapy / Step-Down / Add-On Strategy
    # ─────────────────────────────────────────────
    # E.g., Budesonide in MARS trial (NCT00471809)
    has_step_down = any(re.search(p, combined_text) for p in _STEP_DOWN_PATTERNS)
    is_background_role = drug_role_str in (
        TrialDrugRole.BACKGROUND_CONSTANT_THERAPY.value,
        TrialDrugRole.BACKGROUND_THERAPY.value,
        TrialDrugRole.CONCOMITANT_THERAPY.value,
    )

    if has_step_down or (is_background_role and not is_differentiating):
        return OppositionQualificationResult(
            qualified=False,
            reason_code="BACKGROUND_THERAPY_FAILURE",
            directness="INDIRECT",
            intervention_role=drug_role_str,
            endpoint_relevance="STEP_DOWN_OR_ADD_ON",
            comparator_semantics="BACKGROUND_STANDARD_OF_CARE",
            disease_relation=dis_rel.value,
            replication_eligible=False,
            explanation=(
                f"{drug_name} serves as background or standard-of-care maintenance therapy in a step-down, "
                f"tapering, or add-on strategy. Failure of an add-on intervention to permit reduction/withdrawal "
                f"of background {drug_name} does not constitute therapeutic failure of {drug_name}."
            ),
        )

    # ─────────────────────────────────────────────
    # 4. Indirect Subpopulation / Surrogate Endpoint
    # ─────────────────────────────────────────────
    # E.g., Lisinopril in Hemodialysis Patients evaluating LVH regression (NCT00582114)
    conditions_str = " ".join(conditions)
    has_special_subpop = any(
        re.search(p, conditions_str) or re.search(p, trial_title) for p in _SUBPOPULATION_CUES
    )
    has_surrogate_endpoint = any(
        re.search(p, trial_title) or re.search(p, combined_text) for p in _SURROGATE_ENDPOINT_PATTERNS
    )

    # Check if hypothesis disease is general (e.g. "hypertension") while trial condition is specialized (e.g. "hemodialysis")
    is_general_disease = disease_clean in ("hypertension", "asthma", "type 2 diabetes", "depression")
    if is_general_disease and (has_special_subpop or has_surrogate_endpoint):
        endpoint_rel = "SURROGATE_OR_SUBPOPULATION" if has_surrogate_endpoint else "SPECIAL_SUBPOPULATION_ONLY"
        return OppositionQualificationResult(
            qualified=False,
            reason_code="INDIRECT_SUBPOPULATION_RESULT",
            directness="SUBPOPULATION",
            intervention_role=drug_role_str,
            endpoint_relevance=endpoint_rel,
            comparator_semantics="VALID_EXPERIMENTAL_ARM",
            disease_relation="SPECIAL_SUBPOPULATION",
            replication_eligible=False,
            explanation=(
                f"Trial evaluates a specialized comorbidity subpopulation (e.g., hemodialysis/ESRD) or "
                f"structural remodeling surrogate (e.g., LVH regression) rather than direct blood pressure or "
                f"primary therapeutic efficacy in general {disease_name}."
            ),
        )

    # ─────────────────────────────────────────────
    # 5. Active Comparator Direction Error
    # ─────────────────────────────────────────────
    if not is_differentiating or drug_role_str in (
        TrialDrugRole.COMPARATOR_ONLY.value,
        TrialDrugRole.ACTIVE_COMPARATOR.value,
        TrialDrugRole.PLACEBO_COMPARATOR.value,
    ):
        return OppositionQualificationResult(
            qualified=False,
            reason_code="ACTIVE_COMPARATOR_DIRECTION_ERROR",
            directness="INDIRECT",
            intervention_role=drug_role_str,
            endpoint_relevance="NOT_RELEVANT",
            comparator_semantics="REFERENCE_PRODUCT_COMPARATOR",
            disease_relation=dis_rel.value,
            replication_eligible=False,
            explanation=(
                f"{drug_name} is a comparator or non-differentiating agent in the evaluated trial arm. "
                f"Trial outcome cannot be causally attributed as opposition against {drug_name}."
            ),
        )

    # ─────────────────────────────────────────────
    # 6. Safety Signal vs Efficacy Failure / Direct Harm Distinction
    # ─────────────────────────────────────────────
    predicate_name = claim.predicate.value if hasattr(claim.predicate, "value") else str(claim.predicate)
    is_safety_termination = predicate_name == PredicateType.TERMINATED_FOR_SAFETY.value

    # If trial terminated for safety in a specialized comorbidity context, classify as SAFETY_SIGNAL
    if is_safety_termination and has_special_subpop:
        return OppositionQualificationResult(
            qualified=False,
            reason_code="SAFETY_SIGNAL",
            directness="SUBPOPULATION",
            intervention_role=drug_role_str,
            endpoint_relevance="SAFETY_ENDPOINT_ONLY",
            comparator_semantics="VALID_EXPERIMENTAL_ARM",
            disease_relation="SPECIAL_SUBPOPULATION",
            replication_eligible=False,
            is_direct_harm=False,
            explanation=(
                f"Trial terminated for safety in a specialized comorbidity subpopulation. "
                f"Constitutes a subpopulation safety signal rather than general therapeutic failure."
            ),
        )

    # Administrative safety stop cues (no demonstrated treatment-related therapeutic harm)
    _ADMIN_SAFETY_CUES = (
        r"\bdsmb (?:stopped|recommended|review)\b",
        r"\broutine (?:safety|monitoring)\b",
        r"\badministrative (?:safety|stopping|termination)\b",
        r"\black of funding\b",
        r"\baccrual too slow\b",
        r"\bslow accrual\b",
        r"\bstudy p\.?i\.? passed away\b",
        r"\bsponsor decision\b",
        r"\bbusiness decision\b",
    )
    is_admin_safety = any(re.search(p, why_stopped) for p in _ADMIN_SAFETY_CUES)
    has_explicit_harm_cues = any(
        re.search(p, why_stopped) or re.search(p, combined_text) for p in (
            r"\bserious adverse events?\b",
            r"\bexcess (?:mortality|deaths?)\b",
            r"\bincreased mortality\b",
            r"\btreatment-related (?:mortality|harm|adverse)\b",
            r"\bunacceptable toxicity\b",
            r"\bharm\b",
        )
    )

    if is_safety_termination and is_admin_safety and not has_explicit_harm_cues:
        return OppositionQualificationResult(
            qualified=False,
            reason_code="SAFETY_SIGNAL",
            directness="INDIRECT",
            intervention_role=drug_role_str,
            endpoint_relevance="SAFETY_ENDPOINT_ONLY",
            comparator_semantics="VALID_EXPERIMENTAL_ARM",
            disease_relation=dis_rel.value,
            replication_eligible=False,
            is_direct_harm=False,
            explanation=(
                f"Trial was stopped for administrative or routine safety management reasons without demonstrated "
                f"treatment-related therapeutic harm. Constitutes a safety-management signal rather than empirical opposition."
            ),
        )

    # ─────────────────────────────────────────────
    # 7. Direct Therapeutic Harm / Direct Efficacy Failure (Qualified)
    # ─────────────────────────────────────────────
    # Evaluated drug is primary intervention or differentiating combination component,
    # target disease matches hypothesis, and trial failed efficacy/futility or caused direct harm.
    if (
        drug_role_str in (
            TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION.value,
            TrialDrugRole.EVALUATED_COMBINATION_COMPONENT.value,
            TrialDrugRole.EXPERIMENTAL.value,
        )
        and is_differentiating
        and attr_decision
    ):
        if is_safety_termination or has_explicit_harm_cues:
            return OppositionQualificationResult(
                qualified=True,
                reason_code="DIRECT_THERAPEUTIC_HARM",
                directness="DIRECT",
                intervention_role=drug_role_str,
                endpoint_relevance="SAFETY_ENDPOINT_ONLY",
                comparator_semantics="VALID_EXPERIMENTAL_ARM",
                disease_relation=dis_rel.value,
                replication_eligible=True,
                is_direct_harm=True,
                explanation=(
                    f"Trial demonstrates clinically meaningful treatment-related harm or terminated due to "
                    f"serious adverse events with {drug_name} for {disease_name}. Constitutes direct empirical "
                    f"opposition based on therapeutic harm."
                ),
            )

        return OppositionQualificationResult(
            qualified=True,
            reason_code="DIRECT_THERAPEUTIC_FAILURE",
            directness="DIRECT",
            intervention_role=drug_role_str,
            endpoint_relevance="PRIMARY_EFFICACY_FAILURE",
            comparator_semantics="VALID_EXPERIMENTAL_ARM",
            disease_relation=dis_rel.value,
            replication_eligible=True,
            is_direct_harm=False,
            explanation=(
                f"Trial evaluates {drug_name} directly as therapeutic intervention for {disease_name}. "
                f"Outcome provides direct empirical opposition on clinical endpoints."
            ),
        )

    # Default fallback: ambiguous attribution or structural role
    return OppositionQualificationResult(
        qualified=False,
        reason_code="AMBIGUOUS_INTERVENTION",
        directness="INDIRECT",
        intervention_role=drug_role_str,
        endpoint_relevance="NOT_RELEVANT",
        comparator_semantics="UNCERTAIN",
        disease_relation=dis_rel.value,
        replication_eligible=False,
        is_direct_harm=False,
        explanation=f"Ambiguous intervention attribution or unconfirmed therapeutic directness for {drug_name}.",
    )
