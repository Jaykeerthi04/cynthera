"""TherapeuticOppositionAssessor — Phase 5.16.

Detects explicit negative therapeutic evidence in extracted Claims and produces
a scored OppositionAssessment indicating whether sufficient, disease-specific,
high-quality evidence exists to conclude the drug is OPPOSED for the queried
indication.

IMPORTANT EPISTEMIC CONSTRAINTS:
  1. Absence of evidence ≠ OPPOSE.  Score is 0.0 when no negative predicates found.
  2. Only claims with NEGATIVE_PREDICATE_NAMES predicates are considered.
  3. Disease relevance is required: disease_name must appear in claim.object or raw_text.
  4. Drug relevance is required: drug_name must appear in claim.subject or raw_text.
  5. Independence: claims from the same underlying study (same provenance.record_id)
     are merged into one group — max-weight used, not sum.
  6. The assessor does NOT replace AdvancedConflictResolver (pairwise mechanistic
     contradiction detector). They are parallel, independent pathways.

Reference: Phase 5.16 implementation plan.
"""
from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from backend.core.domain.claim import Claim
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.reasoning_result import OppositionAssessment, level_from_score
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.enums.trial_attribution import TrialDrugRole, AttributionTextEvidence
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.reasoning.conflict.evidence_weighting import (
    cluster_into_evidence_groups,
    group_weight,
)
from backend.reasoning.opposition.opposition_qualification import qualify_opposition_claim
from backend.engineering.retrieval.disease_relation import (
    DiseaseRelation,
    classify_disease_relation,
    matches_for_trial_attribution,
    normalize_disease_term,
    _PARENT_CHILD,
    _SIBLING_EXCLUSIONS,
    _CANONICAL_SYNONYMS,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Negative predicate membership set
# Strictly the real five empirical opposition predicates from PredicateType
# ─────────────────────────────────────────────

NEGATIVE_PREDICATES: frozenset[PredicateType] = frozenset({
    PredicateType.FAILED_TO_IMPROVE,
    PredicateType.TERMINATED_FOR_FUTILITY,
    PredicateType.TERMINATED_FOR_SAFETY,
    PredicateType.WORSENED_OUTCOME,
    PredicateType.CONTRAINDICATED,
})

NEGATIVE_PREDICATE_NAMES: frozenset[str] = frozenset({
    p.value for p in NEGATIVE_PREDICATES
})

# ─────────────────────────────────────────────
# Named thresholds — NOT to be tuned against test data
# ─────────────────────────────────────────────

_HIGH_QUALITY_THRESHOLD: float = 0.75       # minimum group weight for HIGH level
_MODERATE_QUALITY_THRESHOLD: float = 0.50   # minimum group weight for MODERATE level
_OPPOSE_THRESHOLD: float = 0.45             # minimum opposition score for Rule 2b OPPOSE
_STRONG_EVIDENCE_THRESHOLD: float = 0.60    # boundary for "strong support/opposition" (Rule 1b UNCERTAIN)

_HIGH_QUALITY_WEIGHT: float = _HIGH_QUALITY_THRESHOLD
_MODERATE_QUALITY_WEIGHT: float = _MODERATE_QUALITY_THRESHOLD
_OPPOSE_SCORE_THRESHOLD: float = _OPPOSE_THRESHOLD
_CONFLICT_THRESHOLD: float = _STRONG_EVIDENCE_THRESHOLD


# ─────────────────────────────────────────────
# Trial to Negative Claim Adapter
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# Trial Attribution Data Models & Sub-Fixes
# Phase 1A: Dissecting arm structure & explicit termination language
# ─────────────────────────────────────────────

DRUG_SYNONYMS: dict[str, list[str]] = {
    "metformin": ["metformin", "metformin hydrochloride", "metformin hcl", "metformin er", "metformin xr", "glucophage"],
    "niacin": ["niacin", "nicotinic acid", "extended release niacin", "er niacin", "niacin er", "niaspan"],
    "aspirin": ["aspirin", "acetylsalicylic acid", "asa", "bay1019036"],
    "hydroxychloroquine": ["hydroxychloroquine", "hcq", "apo-hydroxychloroquine", "plaquenil"],
    "methotrexate": ["methotrexate", "mtx"],
    "azithromycin": ["azithromycin"],
    "baricitinib": ["baricitinib"],
    "dexamethasone": ["dexamethasone"],
    "valproic acid": ["valproic acid", "valproate", "sodium valproate", "depakote"],
    "imatinib": ["imatinib", "imatinib mesylate", "gleevec"],
    "propranolol": ["propranolol", "inderal"],
    "rapamycin": ["rapamycin", "sirolimus"],
}


def _levenshtein_le_1(s1: str, s2: str) -> bool:
    """Check if edit distance between two strings is at most 1."""
    if abs(len(s1) - len(s2)) > 1:
        return False
    if s1 == s2:
        return True
    if len(s1) == len(s2):
        return sum(c1 != c2 for c1, c2 in zip(s1, s2)) <= 1
    if len(s1) > len(s2):
        s1, s2 = s2, s1
    i = j = diffs = 0
    while i < len(s1) and j < len(s2):
        if s1[i] != s2[j]:
            diffs += 1
            if diffs > 1:
                return False
            j += 1
        else:
            i += 1
            j += 1
    return True


def is_placebo_component(name: str) -> bool:
    """Detect whether an intervention string represents a placebo/vehicle/sham/dummy control (§11)."""
    n_lower = name.strip().lower()
    placebo_patterns = (
        r"\bplacebo\b",
        r"\bvehicle\b",
        r"\bsham\b",
        r"\bdummy\b",
        r"\bmatching\s+placebo\b",
        r"\bmatched\s+placebo\b",
        r"\bcontrol\s+placebo\b",
    )
    return any(re.search(p, n_lower) for p in placebo_patterns)


def matches_drug(candidate_name: str, drug_name: str) -> bool:
    """Determine if a trial intervention string references the evaluated drug as an active intervention.

    Fix 2 (§11): Prevents drug placebos (e.g. 'Nivolumab Placebo') from matching
    the actual administered drug, while recognizing combinations like 'Nivolumab + Radiation'.
    """
    c_lower = candidate_name.strip().lower()
    d_lower = drug_name.strip().lower()
    if not c_lower or not d_lower:
        return False

    # Extract component parts: e.g. "Nivolumab + Radiation" -> ["Nivolumab", "Radiation"]
    # or "Temozolomide + Nivolumab Placebo" -> ["Temozolomide", "Nivolumab Placebo"]
    parts = [p.strip() for p in re.split(r"[/+&]|\band\b|;", candidate_name) if p.strip()]
    if not parts:
        parts = [candidate_name]

    for part in parts:
        part_lower = part.strip().lower()
        if not part_lower:
            continue

        matches_part = False
        syns = DRUG_SYNONYMS.get(d_lower, [d_lower])
        for s in syns:
            if s == part_lower:
                matches_part = True
                break
            if re.search(r"\b" + re.escape(s) + r"\b", part_lower):
                matches_part = True
                break
            if len(s) >= 5 and s in part_lower:
                matches_part = True
                break

        if not matches_part and len(d_lower) >= 6:
            tokens = re.findall(r"[a-z0-9\-]+", part_lower)
            for tok in tokens:
                if abs(len(tok) - len(d_lower)) <= 1 and _levenshtein_le_1(tok, d_lower):
                    matches_part = True
                    break

        if matches_part:
            # Placebo check (§11): "Nivolumab Placebo" must NOT match actual administered "Nivolumab"
            if is_placebo_component(part):
                continue
            return True

    return False


def extract_dosage(name: str) -> str | None:
    """Extract dosage, schedule, or intensity specifications from an intervention name."""
    m = re.search(r"\b\d+(?:\.\d+)?\s*(?:mg|g|mcg|ug|ml|%|iu|units|mg/kg)\b", name.lower())
    if m:
        return m.group(0).strip()
    if "high dose" in name.lower() or "high-dose" in name.lower():
        return "high-dose"
    if "low dose" in name.lower() or "low-dose" in name.lower():
        return "low-dose"
    return None


class TrialAttributionResult(BaseModel):
    """Structured attribution audit trace for clinical trial negative outcomes."""

    model_config = {"frozen": True}

    trial_id: str = Field(..., description="NCT identifier.")
    evaluated_drug: str = Field(..., description="Drug being evaluated.")
    drug_role: TrialDrugRole = Field(..., description="Inferred structural role of the drug.")
    intervention_match: bool = Field(..., description="True if drug matched in experimental arms.")
    comparator_match: bool = Field(..., description="True if drug matched in comparator arms.")
    is_differentiating_intervention: bool = Field(..., description="True if drug differentiates experimental arm.")
    arm_attribution_result: TrialDrugRole = Field(..., description="Independent result of arm/role analysis.")
    text_attribution_result: AttributionTextEvidence = Field(..., description="Independent result of text attribution analysis.")
    final_attribution_decision: bool = Field(..., description="True if trial outcome is attributed to evaluated drug.")
    attribution_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in attribution decision.")
    attribution_reason: str = Field(..., description="Human-auditable explanation of attribution decision.")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary matching Section 7 & 12 specification."""
        return {
            "trial_id": self.trial_id,
            "evaluated_drug": self.evaluated_drug,
            "drug_role": self.drug_role.value,
            "intervention_match": self.intervention_match,
            "comparator_match": self.comparator_match,
            "is_differentiating_intervention": self.is_differentiating_intervention,
            "arm_attribution_result": self.arm_attribution_result.value,
            "text_attribution_result": self.text_attribution_result.value,
            "final_attribution_decision": self.final_attribution_decision,
            "attribution_confidence": self.attribution_confidence,
            "attribution_reason": self.attribution_reason,
        }


def _extract_arm_components(names: list[str]) -> list[str]:
    """Expand co-interventions and combination strings into distinct agent components (§11 & §12)."""
    components: list[str] = []
    for n in names:
        parts = re.split(r"[/+&]|\band\b|;", n)
        if len(parts) > 1:
            for p in parts:
                p_clean = p.strip()
                if p_clean and not is_placebo_component(p_clean):
                    components.append(p_clean)
        else:
            n_clean = n.strip()
            if n_clean and not is_placebo_component(n_clean):
                components.append(n_clean)
    return components


def analyze_trial_drug_role(
    trial: ClinicalTrial,
    drug_name: str,
) -> tuple[TrialDrugRole, bool, bool, bool, str]:
    """Sub-fix A: Analyze trial arm structure and determine the evaluated drug's role.

    Distinguishes:
        Structure A (Background / Constant Co-therapy across arms):
            e.g. LY3053102 + Metformin vs Placebo + Metformin -> Metformin is background.
        Structure B (Differentiating experimental contrast):
            e.g. Drug X alone vs Placebo, or Drug X + standard vs standard alone.

    Returns:
        (drug_role, intervention_match, comparator_match, is_differentiating, reason)
    """
    clean_drug = drug_name.strip().lower()
    intrs = getattr(trial, "intervention_names", None) or []
    comps = getattr(trial, "comparator_names", None) or []

    intr_matched = [i for i in intrs if matches_drug(i, clean_drug)]
    comp_matched = [c for c in comps if matches_drug(c, clean_drug)]

    has_intr = len(intr_matched) > 0
    has_comp = len(comp_matched) > 0

    # Textual comparative pattern in title / text (e.g. "X Versus Y in...")
    text = f"{trial.title} {getattr(trial, 'why_stopped', '') or ''}".lower()
    comp_patterns = (
        r"(?P<exp>[a-z0-9\-\s]+?)\s+(?:versus|vs\.?|compared\s+(?:to|with))\s+(?P<comp>[a-z0-9\-\s]+?)(?:\s+(?:in|for|among|with|to|as|after)\b|\s*$)",
    )
    for pat in comp_patterns:
        m = re.search(pat, text)
        if m:
            exp_part = m.group("exp").strip()
            comp_part = m.group("comp").strip()
            if matches_drug(comp_part, clean_drug) and not matches_drug(exp_part, clean_drug):
                has_comp = True
                if not intr_matched:
                    has_intr = False
            elif matches_drug(exp_part, clean_drug) and not matches_drug(comp_part, clean_drug):
                has_intr = True

    # 1. Comparator Only
    if has_comp and not has_intr:
        return (
            TrialDrugRole.COMPARATOR_ONLY,
            False,
            True,
            False,
            f"Drug appears only in comparator/control arm(s) ({comp_matched}).",
        )

    # 2. Both Intervention and Comparator Arms
    if has_intr and has_comp:
        # Check for dose / intensity differentiation (Test D)
        intr_doses = {extract_dosage(i) for i in intr_matched if extract_dosage(i)}
        comp_doses = {extract_dosage(c) for c in comp_matched if extract_dosage(c)}
        if intr_doses and comp_doses and intr_doses != comp_doses:
            return (
                TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION,
                True,
                True,
                True,
                f"Drug appears across arms with different doses/intensities ({intr_doses} vs {comp_doses}), representing an evaluated dose-response contrast.",
            )

        # Check if other interventions differentiate the experimental arm (Structure A)
        exp_comp_names = _extract_arm_components(intrs)
        ctl_comp_names = _extract_arm_components(comps)
        other_intrs = [i for i in exp_comp_names if not matches_drug(i, clean_drug)]
        other_comps = [c for c in ctl_comp_names if not matches_drug(c, clean_drug)]
        if other_intrs or other_comps:
            return (
                TrialDrugRole.BACKGROUND_CONSTANT_THERAPY,
                True,
                True,
                False,
                f"Drug appears identically across experimental and comparator arms as constant background therapy; experimental contrast is provided by {other_intrs} vs {other_comps}.",
            )

        # If no other interventions and no dose difference, check if title names drug
        if matches_drug(trial.title, clean_drug):
            return (
                TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION,
                True,
                True,
                True,
                f"Drug is the sole agent named in the trial title across arms.",
            )

        return (
            TrialDrugRole.UNCERTAIN,
            True,
            True,
            False,
            f"Drug appears in both arms without distinct dosage or contrasting agent metadata.",
        )

    # 3. Intervention Arms Only (Structure B)
    if has_intr and not has_comp:
        exp_comp_names = _extract_arm_components(intrs)
        ctl_comp_names = _extract_arm_components(comps)

        def in_comparator(agent: str) -> bool:
            return any(
                matches_drug(c, agent) or matches_drug(agent, c) or c.lower() == agent.lower()
                for c in ctl_comp_names
            )

        other_exp_agents = [i for i in exp_comp_names if not matches_drug(i, clean_drug)]
        diff_other_exp = [i for i in other_exp_agents if not in_comparator(i)]
        common_background = [i for i in other_exp_agents if in_comparator(i)]

        if diff_other_exp:
            diff_ctl_agents = [
                c for c in ctl_comp_names
                if not is_placebo_component(c) and not any(matches_drug(i, c) for i in exp_comp_names)
            ]
            if diff_ctl_agents:
                return (
                    TrialDrugRole.EVALUATED_COMBINATION_COMPONENT,
                    True,
                    False,
                    False,
                    f"Drug is an active investigational component of an unresolved multi-agent contrast ({intrs} vs {comps}) with active comparator agents ({diff_ctl_agents}).",
                )
            return (
                TrialDrugRole.EVALUATED_COMBINATION_COMPONENT,
                True,
                False,
                False,
                f"Drug is an active investigational component of a combination therapy arm ({intrs}) with additional differentiating agents ({diff_other_exp}) absent from comparator ({comps}).",
            )

        # Check if multiple arms all receive the drug and contrast delivery device/formulation
        if len(intrs) >= 2:
            device_cues = ("autoinjector", "injector", "pen", "syringe", "device", "formulation")
            if any(any(c in i.lower() for c in device_cues) for i in intrs):
                return (
                    TrialDrugRole.CONCOMITANT_THERAPY,
                    True,
                    False,
                    False,
                    f"Drug is constant across study arms ({intrs}) comparing delivery devices/methods; contrast is the device, not the drug.",
                )
            # If all arms are identical drug names without contrast
            if all(matches_drug(i, clean_drug) for i in intrs) and len({i.strip().lower() for i in intrs}) <= 1:
                return (
                    TrialDrugRole.CONCOMITANT_THERAPY,
                    True,
                    False,
                    False,
                    f"Drug appears identically across arms ({intrs}) without comparator or dose contrast; cannot establish comparative failure.",
                )

        if common_background:
            return (
                TrialDrugRole.EVALUATED_COMBINATION_COMPONENT,
                True,
                False,
                True,
                f"Drug is the differentiating experimental contrast in a combination therapy arm ({intrs}) against comparator ({comps}); co-medications ({common_background}) are constant background.",
            )

        return (
            TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION,
            True,
            False,
            True,
            f"Drug is the primary/sole experimental intervention evaluated against control/comparator.",
        )

    # 4. Neither arm matched
    # Case 4a: Arm metadata is completely unpopulated (both intrs and comps are empty)
    if not intrs and not comps:
        if matches_drug(trial.title, clean_drug):
            return (
                TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION,
                True,
                False,
                True,
                f"Drug is named as study intervention in title; arm metadata unpopulated.",
            )
        return (
            TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION,
            True,
            False,
            True,
            f"Arm metadata unpopulated; evaluated drug assumed primary intervention from retrieval context in absence of comparator arms.",
        )

    # Case 4b: Arm metadata is populated, but drug did not match either arm
    if matches_drug(trial.title, clean_drug):
        return (
            TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION,
            True,
            False,
            True,
            f"Drug is named as the study intervention in the trial title despite absence from arm metadata.",
        )

    return (
        TrialDrugRole.UNCERTAIN,
        False,
        False,
        False,
        f"Drug was not found in trial arms ({intrs} vs {comps}) or title.",
    )


def analyze_failure_attribution_text(
    why_stopped: str | None,
    title: str,
    drug_name: str,
) -> tuple[AttributionTextEvidence, str]:
    """Sub-fix B: Analyze termination rationale for explicit or implicit drug attribution.

    Distinguishes:
        EXPLICIT_DRUG_ATTRIBUTION: Explicit attribution to the drug (e.g. 'lack of efficacy of niacin').
        IMPLICIT_INTERVENTION_ATTRIBUTION: Attribution to 'study drug' or 'active arm'.
        GENERIC_FAILURE_REASON: Generic 'Lack of Efficacy' / 'Futility' without drug attribution.
        NO_ATTRIBUTION: No clinical rationale provided or purely administrative.

    Returns:
        (attribution_text_evidence, reason)
    """
    if not why_stopped or not why_stopped.strip():
        return (AttributionTextEvidence.NO_ATTRIBUTION, "No termination reason provided.")

    text = why_stopped.strip()
    clean_drug = drug_name.strip().lower()

    # Check for explicit mention of drug in why_stopped
    if matches_drug(text, clean_drug):
        failure_verbs = (
            "lack of efficacy", "futility", "ineffective", "no benefit", "failure",
            "harm", "toxicity", "adverse", "risk", "stopped",
        )
        if any(v in text.lower() for v in failure_verbs):
            return (
                AttributionTextEvidence.EXPLICIT_DRUG_ATTRIBUTION,
                f"Termination reason explicitly attributes failure/stopping to {drug_name} ('{text}').",
            )
        return (
            AttributionTextEvidence.EXPLICIT_DRUG_ATTRIBUTION,
            f"Termination reason explicitly mentions {drug_name} ('{text}').",
        )

    # Check for implicit intervention attribution
    implicit_cues = (
        "investigational product", "study drug", "active treatment", "active arm",
        "experimental drug", "study treatment", "experimental arm",
    )
    if any(c in text.lower() for c in implicit_cues):
        return (
            AttributionTextEvidence.IMPLICIT_INTERVENTION_ATTRIBUTION,
            f"Termination reason attributes failure to the investigational product/active arm generally ('{text}').",
        )

    # Check for generic failure reasons
    generic_cues = (
        "lack of efficacy", "futility", "ineffective", "no benefit", "primary endpoint",
        "interim analysis", "dsmb", "dmcb", "adverse events", "safety", "harm", "results",
    )
    if any(c in text.lower() for c in generic_cues):
        return (
            AttributionTextEvidence.GENERIC_FAILURE_REASON,
            f"Termination reason states generic clinical outcome ('{text}') without specific drug attribution.",
        )

    return (
        AttributionTextEvidence.NO_ATTRIBUTION,
        f"Termination reason ('{text}') contains no clinical failure attribution.",
    )


def evaluate_trial_attribution(
    trial: ClinicalTrial,
    drug_name: str,
) -> TrialAttributionResult:
    """Evaluate whether a clinical trial outcome is genuinely attributable to the evaluated drug.

    Combines independent Sub-Fix A (arm/role attribution) and Sub-Fix B (text attribution)
    into a structured, auditable attribution verdict.
    """
    role, intr_match, comp_match, is_diff, arm_reason = analyze_trial_drug_role(trial, drug_name)
    failure_text = trial.why_stopped or getattr(trial, "negative_efficacy_reason", None)
    text_ev, text_reason = analyze_failure_attribution_text(failure_text, trial.title, drug_name)

    if role in (TrialDrugRole.COMPARATOR_ONLY, TrialDrugRole.ACTIVE_COMPARATOR):
        final_decision = False
        confidence = 0.95
        combined_reason = f"REJECT: Evaluated drug is comparator/control only. {arm_reason}"

    elif role in (TrialDrugRole.BACKGROUND_CONSTANT_THERAPY, TrialDrugRole.BACKGROUND_THERAPY):
        if text_ev == AttributionTextEvidence.EXPLICIT_DRUG_ATTRIBUTION:
            final_decision = True
            confidence = 0.85
            combined_reason = f"ATTRIBUTED: Drug is background therapy, but termination text explicitly attributes failure to it: {text_reason}"
        else:
            final_decision = False
            confidence = 0.95
            combined_reason = (
                f"REJECT: Drug is constant background therapy across arms; investigational failure of the "
                f"added agent cannot be attributed to the background standard-of-care. ({text_reason})"
            )

    elif role == TrialDrugRole.CONCOMITANT_THERAPY:
        if text_ev == AttributionTextEvidence.EXPLICIT_DRUG_ATTRIBUTION:
            final_decision = True
            confidence = 0.85
            combined_reason = f"ATTRIBUTED: Drug is concomitant/delivery-tested, but explicit failure attribution present: {text_reason}"
        else:
            final_decision = False
            confidence = 0.95
            combined_reason = f"REJECT: Drug is constant across delivery device/usability contrast arms; trial does not test therapeutic drug efficacy. {arm_reason}"

    elif role == TrialDrugRole.EVALUATED_COMBINATION_COMPONENT:
        if not is_diff:
            if "unresolved multi-agent contrast" in arm_reason:
                # Unresolved multi-agent contrast (e.g. A+B vs C+D): candidate drug is NOT independently
                # attributable even if whyStopped mentions the drug (§3).
                final_decision = False
                confidence = 0.90
                combined_reason = (
                    f"REJECT: Evaluated drug is part of an unresolved combination contrast ({arm_reason}); "
                    f"outcome cannot be causally attributed to {drug_name} without a differentiating arm contrast."
                )
            elif text_ev == AttributionTextEvidence.EXPLICIT_DRUG_ATTRIBUTION:
                final_decision = True
                confidence = 0.85
                combined_reason = f"ATTRIBUTED: Explicit failure attribution for combination component: {text_reason} ({arm_reason})"
            else:
                final_decision = False
                confidence = 0.90
                combined_reason = (
                    f"REJECT: Evaluated drug is part of a combination therapy arm ({arm_reason}); "
                    f"generic outcome cannot be attributed to {drug_name} alone without explicit drug attribution."
                )
        elif text_ev == AttributionTextEvidence.EXPLICIT_DRUG_ATTRIBUTION:
            final_decision = True
            confidence = 0.90
            combined_reason = f"ATTRIBUTED: Differentiating combination component with explicit drug attribution: {text_reason} ({arm_reason})"
        else:
            final_decision = True
            confidence = 0.85
            combined_reason = f"ATTRIBUTED: Differentiating evaluated intervention in combination contrast against standard background: {text_reason} ({arm_reason})"

    elif role in (TrialDrugRole.EVALUATED_PRIMARY_INTERVENTION, TrialDrugRole.EXPERIMENTAL):
        if is_diff:
            if text_ev == AttributionTextEvidence.EXPLICIT_DRUG_ATTRIBUTION:
                final_decision = True
                confidence = 0.95
                combined_reason = f"ATTRIBUTED: Differentiating evaluated intervention with explicit failure attribution: {text_reason} ({arm_reason})"
            elif text_ev in (AttributionTextEvidence.IMPLICIT_INTERVENTION_ATTRIBUTION, AttributionTextEvidence.GENERIC_FAILURE_REASON):
                final_decision = True
                confidence = 0.85
                combined_reason = f"ATTRIBUTED: Differentiating evaluated intervention with {text_ev.value.lower()}: {text_reason} ({arm_reason})"
            else:
                final_decision = True
                confidence = 0.75
                combined_reason = f"ATTRIBUTED: Evaluated intervention in trial terminated for clinical outcome. ({arm_reason})"
        else:
            final_decision = False
            confidence = 0.70
            combined_reason = f"REJECT: Drug is not differentiating in trial contrast. {arm_reason}"

    else:  # UNCERTAIN
        if text_ev == AttributionTextEvidence.EXPLICIT_DRUG_ATTRIBUTION:
            final_decision = True
            confidence = 0.80
            combined_reason = f"ATTRIBUTED: Structural role uncertain, but explicit termination attribution present: {text_reason}"
        else:
            final_decision = False
            confidence = 0.30
            combined_reason = f"REJECT: Structural role uncertain and no explicit failure attribution."

    return TrialAttributionResult(
        trial_id=trial.nct_id,
        evaluated_drug=drug_name,
        drug_role=role,
        intervention_match=intr_match,
        comparator_match=comp_match,
        is_differentiating_intervention=is_diff,
        arm_attribution_result=role,
        text_attribution_result=text_ev,
        final_attribution_decision=final_decision,
        attribution_confidence=confidence,
        attribution_reason=combined_reason,
    )


def is_trial_comparator(trial: ClinicalTrial, drug_name: str) -> bool:
    """Determine whether the evaluated drug is a comparator/control rather than the investigational intervention.

    Semantic invariant:
        A negative result against intervention A MUST NOT become opposition against comparator B.
    """
    attr = evaluate_trial_attribution(trial, drug_name)
    return attr.drug_role == TrialDrugRole.COMPARATOR_ONLY or not attr.is_differentiating_intervention


def determine_trial_evidence_type(trial: ClinicalTrial) -> str:
    """Determine evidence type from clinical trial study design metadata.

    Classification:
        - RCT: randomized controlled clinical trial (when metadata supports it)
        - INTERVENTIONAL: interventional non-randomized trial
        - OBSERVATIONAL: observational / registry / cohort study
        - UNKNOWN: when study design cannot be confirmed from metadata
    """
    allocation = (getattr(trial, "design_allocation", None) or "").upper()
    study_type = (getattr(trial, "study_type", None) or "").upper()
    title_lower = (trial.title or "").lower()

    # 1. Explicit metadata checks from designModule
    if allocation == "RANDOMIZED":
        return "RCT"
    elif allocation in ("NON_RANDOMIZED", "NA") and study_type == "INTERVENTIONAL":
        return "INTERVENTIONAL"
    elif study_type == "OBSERVATIONAL":
        return "OBSERVATIONAL"

    # 2. Text cues in title / description
    rct_cues = ("randomized", "randomised", "double-blind", "placebo-controlled", " rct ")
    if any(c in title_lower for c in rct_cues):
        return "RCT"
    obs_cues = ("observational", "registry", "cohort", "epidemiological", "retrospective")
    if any(c in title_lower for c in obs_cues):
        return "OBSERVATIONAL"
    interv_cues = ("open-label", "single-arm", "non-randomized", "non-randomised")
    if any(c in title_lower for c in interv_cues):
        return "INTERVENTIONAL"

    # If study_type is explicitly INTERVENTIONAL but no randomization is confirmed:
    if study_type == "INTERVENTIONAL":
        return "INTERVENTIONAL"

    # Unknown must remain UNKNOWN
    return "UNKNOWN"


def matches_disease_condition(trial: ClinicalTrial, disease_name: str) -> bool:
    """Pair Specificity Gate (§17): verify that trial condition matches evaluated disease.

    Uses shared disease_relation module (§9):
    - Accepts SAME and PARENT_CHILD relations (matches_for_trial_attribution).
    - Strictly rejects SIBLING_EXCLUDED relations (e.g. ischemic vs hemorrhagic stroke).
    """
    d_clean = disease_name.strip().lower()
    if not d_clean:
        return True

    norm_d = normalize_disease_term(d_clean)
    conditions = getattr(trial, "condition_names", []) or []

    # 1. Check conditions with shared disease_relation policy if populated
    if conditions:
        for c in conditions:
            rel = classify_disease_relation(d_clean, c)
            if rel == DiseaseRelation.SIBLING_EXCLUDED:
                logger.info(
                    "trial_disease_condition_sibling_excluded",
                    extra={
                        "nct_id": trial.nct_id,
                        "query_disease": d_clean,
                        "candidate_condition": c,
                        "relation": "SIBLING_EXCLUDED",
                        "policy": "TRIAL_ATTRIBUTION",
                        "matched": False,
                    },
                )
                return False

            if matches_for_trial_attribution(d_clean, c):
                logger.info(
                    "trial_disease_condition_matched",
                    extra={
                        "nct_id": trial.nct_id,
                        "query_disease": d_clean,
                        "candidate_condition": c,
                        "relation": rel.value,
                        "policy": "TRIAL_ATTRIBUTION",
                        "matched": True,
                    },
                )
                return True

    # 2. Title fallback (used when conditions is empty OR no condition matched)
    # Empty conditions MUST NOT automatically return True (§1).
    title = trial.title or ""
    if title:
        title_lower = title.lower()

        # SIBLING EXCLUSION GATE ON TITLE:
        # SIBLING_EXCLUDED must NEVER be bypassed!
        for sib in _SIBLING_EXCLUSIONS.get(norm_d, frozenset()):
            if re.search(r"\b" + re.escape(sib) + r"\b", title_lower):
                logger.info(
                    "trial_title_sibling_excluded",
                    extra={
                        "nct_id": trial.nct_id,
                        "query_disease": d_clean,
                        "sibling_term": sib,
                        "title": title,
                    },
                )
                return False

        # Bidirectional check across all registered sibling exclusions
        for term_x, ex_set in _SIBLING_EXCLUSIONS.items():
            if term_x == norm_d:
                for ex in ex_set:
                    if re.search(r"\b" + re.escape(ex) + r"\b", title_lower):
                        return False
            elif norm_d in ex_set:
                if re.search(r"\b" + re.escape(term_x) + r"\b", title_lower):
                    return False

        rel_title = classify_disease_relation(d_clean, title)
        if rel_title == DiseaseRelation.SIBLING_EXCLUDED:
            return False
        if matches_for_trial_attribution(d_clean, title):
            return True

        # Recognized entity checks in title:
        # PARENT_CHILD terms from curated ontology (e.g. query="traumatic brain injury", child="subdural hematoma")
        children = _PARENT_CHILD.get(norm_d, frozenset())
        for child in children:
            if len(child) >= 4 and re.search(r"\b" + re.escape(child) + r"\b", title_lower):
                if matches_for_trial_attribution(d_clean, child):
                    return True

        # Parent terms from curated ontology (e.g. query="glioblastoma", parent="brain neoplasms")
        for parent_term, child_set in _PARENT_CHILD.items():
            if norm_d in child_set:
                if len(parent_term) >= 4 and re.search(r"\b" + re.escape(parent_term) + r"\b", title_lower):
                    if matches_for_trial_attribution(d_clean, parent_term):
                        return True

        # Exact SAME query term (word-bounded)
        if norm_d and len(norm_d) >= 4 and re.search(r"\b" + re.escape(norm_d) + r"\b", title_lower):
            return True
        if d_clean and len(d_clean) >= 4 and re.search(r"\b" + re.escape(d_clean) + r"\b", title_lower):
            return True

        # Canonical synonyms of norm_d (e.g. "gbm" for "glioblastoma")
        for syn, canon in _CANONICAL_SYNONYMS.items():
            if canon == norm_d and len(syn) >= 4:
                if re.search(r"\b" + re.escape(syn) + r"\b", title_lower):
                    if matches_for_trial_attribution(d_clean, syn):
                        return True

    return False


def trial_to_negative_claim(
    trial: ClinicalTrial,
    drug_name: str,
    disease_name: str,
) -> Claim | None:
    """Convert an efficacy- or safety-terminated clinical trial or negative-outcome trial into an empirical opposition Claim.

    Handles:
    - TERMINATED_LACK_OF_EFFICACY -> FAILED_TO_IMPROVE
    - COMPLETED_FAILURE (or is_negative_efficacy) -> FAILED_TO_IMPROVE (Phase 2 / Issue 5)
    - TERMINATED_SAFETY -> TERMINATED_FOR_SAFETY

    Pair Specificity Gate (§17):
        Verifies that trial conditions or title match the evaluated disease.
    Attribution Gate (§18):
        Distinguishes evaluated intervention vs background therapy vs comparator/control.
    """
    if (
        trial.status in (TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY, TrialOutcomeStatus.COMPLETED_FAILURE)
        or getattr(trial, "is_negative_efficacy", False)
    ):
        predicate = PredicateType.FAILED_TO_IMPROVE
    elif trial.status == TrialOutcomeStatus.TERMINATED_SAFETY:
        predicate = PredicateType.TERMINATED_FOR_SAFETY
    else:
        return None

    # PAIR SPECIFICITY GATE (§17):
    if not matches_disease_condition(trial, disease_name):
        logger.info(
            "trial_pair_specificity_rejected",
            extra={
                "nct_id": trial.nct_id,
                "drug": drug_name,
                "disease": disease_name,
                "conditions": getattr(trial, "condition_names", []),
            },
        )
        return None

    # ATTRIBUTION GATE:
    attr_result = evaluate_trial_attribution(trial, drug_name)
    if not attr_result.final_attribution_decision:
        logger.info(
            "trial_attribution_gate_rejected",
            extra={
                "nct_id": trial.nct_id,
                "drug": drug_name,
                "drug_role": attr_result.drug_role.value,
                "is_differentiating": attr_result.is_differentiating_intervention,
                "text_attribution": attr_result.text_attribution_result.value,
                "reason": attr_result.attribution_reason,
            },
        )
        return None

    # ── Stage 1: Negative Evidence Strength Classification (Step 5) ───────────
    # A. Explicit futility / explicit lack of efficacy: ERW = 0.90, conf = 0.95
    # B. Significant harmful primary endpoint / safety termination: ERW = 0.90, conf = 0.95
    # C. Primary endpoint failure: ERW = 0.90, conf = 0.90
    # D. Secondary endpoint failure: ERW = 0.55, conf = 0.65 (weaker, context-dependent)
    # E. Subgroup failure: ERW = 0.40, conf = 0.50 (weak/non-opposing)
    # F. Neutral result: rejected (return None, zero therapeutic opposition)
    why_stopped = (getattr(trial, "why_stopped", "") or "").lower()
    neg_reason = (getattr(trial, "negative_efficacy_reason", "") or "").lower()
    title_text = (getattr(trial, "title", "") or "").lower()
    combined_notes = f"{why_stopped} {neg_reason} {title_text}".lower()

    futility_kw = (
        "futility", "futility boundary", "lack of efficacy", "ineffective",
        "dsmb", "no evidence of efficacy", "failed to demonstrate superiority"
    )
    has_explicit_futility = (
        trial.status == TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY
        or any(kw in combined_notes for kw in futility_kw)
    )

    harm_kw = ("serious adverse", "toxicity", "adverse event", "safety concern", "mortality", "excess death")
    has_harm = (
        trial.status == TrialOutcomeStatus.TERMINATED_SAFETY
        or any(kw in combined_notes for kw in harm_kw)
    )

    for om in getattr(trial, "outcome_measures", []) or []:
        r_code = om.get("reason_code")
        if r_code in ("EXPLICIT_FUTILITY", "EXPLICIT_LACK_OF_EFFICACY"):
            has_explicit_futility = True
        elif r_code in ("STATISTICALLY_SIGNIFICANT_HARM",) or om.get("direction") == "SAFETY_HARM":
            has_harm = True

    is_secondary_only = False
    if not (trial.status in (TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY, TrialOutcomeStatus.TERMINATED_SAFETY)):
        outcomes = getattr(trial, "outcome_measures", []) or []
        primary_negs = [om for om in outcomes if str(om.get("type", "")).upper() == "PRIMARY" and om.get("direction") == "NEGATIVE"]
        sec_negs = [om for om in outcomes if str(om.get("type", "")).upper() == "SECONDARY" and om.get("direction") == "NEGATIVE"]
        if not primary_negs and sec_negs:
            is_secondary_only = True

    is_subgroup = any("subgroup" in (om.get("title", "") + om.get("description", "")).lower() for om in getattr(trial, "outcome_measures", []) or [])

    if trial.status == TrialOutcomeStatus.TERMINATED_SAFETY:
        erw_val = 0.90
        conf_val = 0.95
        predicate = PredicateType.TERMINATED_FOR_SAFETY
    elif has_explicit_futility or trial.status == TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY:
        erw_val = 0.90
        conf_val = 0.95
        predicate = PredicateType.FAILED_TO_IMPROVE
    elif has_harm:
        erw_val = 0.90
        conf_val = 0.95
        predicate = PredicateType.FAILED_TO_IMPROVE
    elif is_secondary_only:
        erw_val = 0.55
        conf_val = 0.65
        predicate = PredicateType.FAILED_TO_IMPROVE
    elif is_subgroup:
        erw_val = 0.40
        conf_val = 0.50
        predicate = PredicateType.FAILED_TO_IMPROVE
    else:
        erw_val = 0.90
        conf_val = 0.90
        predicate = PredicateType.FAILED_TO_IMPROVE

    evidence_type = determine_trial_evidence_type(trial)
    raw_text = (
        getattr(trial, "why_stopped", None)
        or getattr(trial, "negative_efficacy_reason", None)
        or trial.title
    )

    prov = ProvenanceReference(
        source_name="ClinicalTrials.gov",
        source_version="2024",
        record_id=trial.nct_id,
        url=f"https://clinicaltrials.gov/study/{trial.nct_id}",
    )

    trace_dict = attr_result.to_dict()
    trace_dict["title"] = trial.title or ""
    trace_dict["why_stopped"] = trial.why_stopped or getattr(trial, "negative_efficacy_reason", None) or ""
    trace_dict["conditions"] = list(getattr(trial, "condition_names", []) or [])
    trace_dict["interventions"] = list(getattr(trial, "intervention_names", []) or [])
    trace_dict["comparators"] = list(getattr(trial, "comparator_names", []) or [])
    trace_dict["outcome_measures"] = [
        {
            "title": om.get("title") if isinstance(om, dict) else getattr(om, "title", ""),
            "type": om.get("type") if isinstance(om, dict) else getattr(om, "type", ""),
            "direction": om.get("direction") if isinstance(om, dict) else getattr(om, "direction", ""),
            "reason_code": om.get("reason_code") if isinstance(om, dict) else getattr(om, "reason_code", ""),
        }
        for om in (getattr(trial, "outcome_measures", []) or [])
    ]

    return Claim(
        subject=drug_name,
        predicate=predicate,
        object=disease_name,
        confidence=conf_val,
        erw=ERW(value=erw_val, base_weight=erw_val),
        provenance=prov,
        raw_text=raw_text,
        is_validated=True,
        evidence_type=evidence_type,
        attribution_trace=trace_dict,
    )



# ─────────────────────────────────────────────
# Assessor
# ─────────────────────────────────────────────

class TherapeuticOppositionAssessor:
    """Detect and score explicit negative therapeutic evidence.

    Pipeline:
    1. Filter claims by negative predicate (real 5 PredicateType members)
    2. Filter by drug relevance (drug_name in subject or raw_text)
    3. Filter by disease relevance (disease_name in object or raw_text)
    4. Cluster remaining claims by evidence_group_key (provenance.record_id anchor)
    5. Compute max-weight per group
    6. Aggregate: score = best_weight × (1 - exp(-0.5 × n_groups))
    7. Level classification from score and best_weight
    """

    def assess(
        self,
        claims: list[Claim],
        drug_name: str,
        disease_name: str,
    ) -> OppositionAssessment:
        """Assess negative therapeutic evidence across all extracted claims.

        Args:
            claims: All Claim objects produced by ClaimExtractionAgent and trial adapter.
            drug_name: Drug name from the hypothesis (case-insensitive matching).
            disease_name: Disease name from the hypothesis (case-insensitive matching).

        Returns:
            OppositionAssessment — score=0.0 when no qualifying evidence found.
        """
        drug_lower = drug_name.lower().strip()
        disease_lower = disease_name.lower().strip()

        # ── Stage 1: Filter by negative predicate ─────────────────────────────
        negative_claims: list[Claim] = []
        for claim in claims:
            pred = claim.predicate
            if pred in NEGATIVE_PREDICATES or (hasattr(pred, "value") and pred.value in NEGATIVE_PREDICATE_NAMES) or str(pred) in NEGATIVE_PREDICATE_NAMES:
                negative_claims.append(claim)

        if not negative_claims:
            logger.debug(
                "therapeutic_opposition_no_negative_claims",
                extra={"drug": drug_name, "disease": disease_name, "total_claims": len(claims)},
            )
            return OppositionAssessment.empty()

        # ── Stage 2 & 3: Drug + disease relevance gates ───────────────────────
        relevance_passed: list[Claim] = []
        excluded_count = 0

        for claim in negative_claims:
            raw = (claim.raw_text or "").lower()
            subject_lower = claim.subject.lower()
            object_lower = claim.object.lower()

            # Drug relevance: drug_name in subject OR raw_text
            drug_relevant = (
                drug_lower in subject_lower
                or (len(drug_lower) >= 4 and drug_lower in raw)
            )
            # Disease relevance: disease_name in object OR raw_text
            disease_relevant = (
                disease_lower in object_lower
                or (len(disease_lower) >= 4 and disease_lower in raw)
            )

            if drug_relevant and disease_relevant:
                relevance_passed.append(claim)
            else:
                excluded_count += 1
                logger.debug(
                    "therapeutic_opposition_claim_excluded",
                    extra={
                        "claim_id": str(claim.id),
                        "predicate": claim.predicate.value,
                        "subject": claim.subject,
                        "object": claim.object,
                        "drug_relevant": drug_relevant,
                        "disease_relevant": disease_relevant,
                    },
                )

        # Collect rejected claims and reasons
        rejection_reasons: dict[str, str] = {}
        serialized_rejected: list[dict[str, Any]] = []

        # ── Stage 3b: Semantic opposition qualification gate ──────────────────
        qualified: list[Claim] = []
        has_direct_harm = False
        for claim in relevance_passed:
            qual_res = qualify_opposition_claim(claim, drug_name, disease_name)
            cid = str(claim.id)
            if qual_res.qualified:
                qualified.append(claim)
                if qual_res.is_direct_harm:
                    has_direct_harm = True
            else:
                excluded_count += 1
                reason = f"Rejected [{qual_res.reason_code}]: {qual_res.explanation}"
                rejection_reasons[cid] = reason
                serialized_rejected.append({
                    "id": cid,
                    "subject": claim.subject,
                    "predicate": claim.predicate.value if hasattr(claim.predicate, "value") else str(claim.predicate),
                    "object": claim.object,
                    "reason": reason,
                    "qualification": qual_res.to_dict(),
                })

        for claim in negative_claims:
            cid = str(claim.id)
            if claim not in qualified and cid not in rejection_reasons:
                raw = (claim.raw_text or "").lower()
                subj = claim.subject.lower()
                obj = claim.object.lower()
                d_rel = (drug_lower in subj) or (len(drug_lower) >= 4 and drug_lower in raw)
                dis_rel = (disease_lower in obj) or (len(disease_lower) >= 4 and disease_lower in raw)
                if not d_rel and not dis_rel:
                    reason = f"Rejected: Neither drug '{drug_name}' nor disease '{disease_name}' matched claim."
                elif not d_rel:
                    reason = f"Rejected: Drug '{drug_name}' not matched in claim subject '{claim.subject}' or text."
                else:
                    reason = f"Rejected: Disease '{disease_name}' not matched in claim object '{claim.object}' or text."
                rejection_reasons[cid] = reason
                serialized_rejected.append({
                    "id": cid,
                    "subject": claim.subject,
                    "predicate": claim.predicate.value if hasattr(claim.predicate, "value") else str(claim.predicate),
                    "object": claim.object,
                    "reason": reason,
                })

        if not qualified:
            logger.info(
                "therapeutic_opposition_all_excluded",
                extra={
                    "drug": drug_name,
                    "disease": disease_name,
                    "negative_claim_count": len(negative_claims),
                    "excluded": excluded_count,
                },
            )
            return OppositionAssessment(
                score=0.0,
                level="NONE",
                rationale=(
                    f"{len(negative_claims)} negative-predicate claim(s) found but none passed "
                    f"drug ({drug_name!r}) + disease ({disease_name!r}) relevance gates."
                ),
                qualified_negative_claim_count=0,
                qualified_claim_count=0,
                excluded_negative_claim_count=excluded_count,
                strongest_group_weight=0.0,
                qualified_claims=[],
                independent_groups=[],
                rejected_claims=serialized_rejected,
                rejection_reasons=rejection_reasons,
            )

        # ── Stage 4: Cluster by independent study ────────────────────────────
        groups = cluster_into_evidence_groups(qualified)
        n_groups = len(groups)

        # ── Stage 5: Score per group (max-weight) ─────────────────────────────
        group_weights: list[tuple[str, float, list[str]]] = []  # (group_key, weight, claim_ids)
        for group_key, group_claims in groups.items():
            w = group_weight(group_claims)
            ids = [str(c.id) for c in group_claims]
            group_weights.append((group_key, w, ids))

        group_weights.sort(key=lambda x: x[1], reverse=True)
        best_w = group_weights[0][1] if group_weights else 0.0

        # ── Stage 6: Aggregate ─────────────────────────────────────────────────
        # Formula: score = best_weight × (1.0 - 0.30 / n_groups)
        # Scientific Semantics:
        # - A single definitive landmark trial (n=1) retains 70% of its intrinsic quality
        #   weight (e.g. Phase III RCT best_w = 0.810 -> score = 0.567 >= 0.45), sufficient
        #   to trigger Rule 2b veto when evidence strength warrants it.
        # - Weaker single evidence units (e.g. secondary endpoints best_w = 0.495 -> score = 0.347,
        #   or observational best_w = 0.585 -> score = 0.410, or case reports best_w = 0.360 -> score = 0.252)
        #   remain strictly below the 0.45 Rule 2b threshold when n=1.
        # - At n=2: score = best_weight × 0.850 (independent replication bonus).
        # - At n=3: score = best_weight × 0.900.
        # - At n=4+: score approaches best_weight (asymptotic saturation).
        aggregate_factor = 1.0 - (0.30 / n_groups) if n_groups > 0 else 0.0
        raw_score = best_w * aggregate_factor
        score = round(min(1.0, raw_score), 4)

        # ── Stage 7: Canonical level classification from score ─────────────────
        level = level_from_score(score)

        # Collect key claim IDs from the top 3 groups
        key_ids: list[str] = []
        for _, _, ids in group_weights[:3]:
            key_ids.extend(ids[:2])

        rationale = (
            f"Therapeutic opposition score: {score:.3f} ({level}). "
            f"{len(qualified)} qualifying negative claim(s) across {n_groups} independent study group(s). "
            f"Strongest group weight: {best_w:.3f}. "
            f"Groups: {[gk for gk, _, _ in group_weights[:3]]}."
        )

        serialized_qualified: list[dict[str, Any]] = [
            {
                "id": str(c.id),
                "subject": c.subject,
                "predicate": c.predicate.value if hasattr(c.predicate, "value") else str(c.predicate),
                "object": c.object,
                "confidence": c.confidence,
                "erw": c.erw.value if hasattr(c.erw, "value") else float(c.erw or 0.0),
                "provenance_id": c.provenance.record_id if c.provenance else "",
                "source": c.provenance.source_name if c.provenance else "",
                "qualification": qualify_opposition_claim(c, drug_name, disease_name).to_dict(),
            }
            for c in qualified
        ]

        serialized_groups: list[dict[str, Any]] = [
            {"group_key": gk, "weight": round(w, 4), "claim_ids": ids}
            for gk, w, ids in group_weights
        ]

        logger.info(
            "therapeutic_opposition_assessed",
            extra={
                "drug": drug_name,
                "disease": disease_name,
                "score": score,
                "level": level,
                "n_groups": n_groups,
                "best_weight": best_w,
                "qualified": len(qualified),
                "excluded": excluded_count,
            },
        )

        return OppositionAssessment(
            score=score,
            level=level,
            independent_group_count=n_groups,
            key_claim_ids=key_ids,
            rationale=rationale,
            has_direct_harm=has_direct_harm,
            qualified_negative_claim_count=len(qualified),
            qualified_claim_count=len(qualified),
            excluded_negative_claim_count=excluded_count,
            strongest_group_weight=best_w,
            qualified_claims=serialized_qualified,
            independent_groups=serialized_groups,
            rejected_claims=serialized_rejected,
            rejection_reasons=rejection_reasons,
        )
