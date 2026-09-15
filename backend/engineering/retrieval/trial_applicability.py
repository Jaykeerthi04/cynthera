"""Clinical-trial applicability gates for therapeutic evidence attribution.

This module is intentionally conservative. It does not decide whether a trial is
positive or negative; it decides whether a trial is sufficiently applicable to
contribute direct therapeutic evidence to the queried hypothesis. Mismatched
trials remain available to callers for contextual reporting, but must not create
direct opposition claims.
"""
from __future__ import annotations

from enum import Enum
import re

from pydantic import BaseModel, ConfigDict, Field

from backend.core.domain.clinical_trial import ClinicalTrial
from backend.engineering.retrieval.disease_relation import (
    _PARENT_CHILD,
    DiseaseRelation,
    classify_disease_relation,
    normalize_disease_term,
)


class TrialApplicabilityStatus(str, Enum):
    DIRECT = "DIRECT"
    PARENT_OR_BROAD_CONTEXT = "PARENT_OR_BROAD_CONTEXT"
    SUBTYPE_MISMATCH = "SUBTYPE_MISMATCH"
    POPULATION_MISMATCH = "POPULATION_MISMATCH"
    DOSE_MISMATCH = "DOSE_MISMATCH"
    ENDPOINT_MISMATCH = "ENDPOINT_MISMATCH"
    BACKGROUND_ONLY = "BACKGROUND_ONLY"
    COMPARATOR_ONLY = "COMPARATOR_ONLY"
    INSUFFICIENT_METADATA = "INSUFFICIENT_METADATA"


class TrialApplicability(BaseModel):
    """Auditable applicability decision for one trial/query pair."""

    model_config = ConfigDict(frozen=True)

    status: TrialApplicabilityStatus
    disease_relation: DiseaseRelation
    reasons: tuple[str, ...] = Field(default_factory=tuple)
    direct_therapeutic_evidence: bool = False


def _text(trial: ClinicalTrial) -> str:
    fields = [
        trial.title,
        *(getattr(trial, "condition_names", []) or []),
        *(getattr(trial, "outcome_measures", []) or []),
    ]
    return " ".join(
        item if isinstance(item, str) else " ".join(str(v) for v in item.values())
        for item in fields
    ).lower()


def _has_marker(term: str) -> bool:
    return bool(re.search(r"\b(?:egfr|alk|her2|her-2|braf|kras|pd-l1|brca|ros1|ntrk)[- ]?(?:positive|mutant|mutation|negative)\b", term.lower()))


def _marker_mismatch(query: str, text: str) -> bool:
    if not _has_marker(query):
        return False
    marker_tokens = re.findall(r"\b(?:egfr|alk|her2|her-2|braf|kras|pd-l1|brca|ros1|ntrk)\b", query.lower())
    return bool(marker_tokens) and not any(token in text for token in marker_tokens)


def _population_mismatch(query: str, text: str) -> bool:
    q = query.lower()
    explicit_query = re.search(r"\b(pediatric|paediatric|children|adult|adults)\b", q)
    if not explicit_query:
        return False
    requested = explicit_query.group(1)
    if requested in {"pediatric", "paediatric", "children"}:
        return bool(re.search(r"\badult|adults|elderly\b", text)) and not bool(re.search(r"pediatric|paediatric|children", text))
    return bool(re.search(r"pediatric|paediatric|children\b", text)) and not bool(re.search(r"adult|adults", text))


def _dose_mismatch(query: str, text: str) -> bool:
    q = query.lower()
    requested_high = bool(re.search(r"\b(high[- ]dose|supratherapeutic)\b", q))
    requested_low = bool(re.search(r"\b(low[- ]dose)\b", q))
    trial_high = bool(re.search(r"\b(high[- ]dose|supratherapeutic)\b", text))
    trial_low = bool(re.search(r"\b(low[- ]dose)\b", text))
    return (requested_high and trial_low) or (requested_low and trial_high)


def assess_trial_applicability(trial: ClinicalTrial, queried_disease: str) -> TrialApplicability:
    """Classify direct applicability without silently treating missing metadata as a match."""
    conditions = list(getattr(trial, "condition_names", []) or [])
    relation = DiseaseRelation.UNRELATED
    for condition in conditions:
        candidate = classify_disease_relation(queried_disease, condition)
        if candidate == DiseaseRelation.SIBLING_EXCLUDED:
            relation = candidate
            break
        if candidate == DiseaseRelation.SAME:
            relation = candidate
            break
        if candidate == DiseaseRelation.PARENT_CHILD and relation == DiseaseRelation.UNRELATED:
            relation = candidate
    if relation == DiseaseRelation.UNRELATED:
        relation = classify_disease_relation(queried_disease, trial.title or "")

    text = _text(trial)
    reasons: list[str] = []
    if relation == DiseaseRelation.SIBLING_EXCLUDED:
        return TrialApplicability(
            status=TrialApplicabilityStatus.SUBTYPE_MISMATCH,
            disease_relation=relation,
            reasons=("Sibling disease is explicitly excluded by disease-relation policy.",),
        )
    # Explicit query qualifiers are safety-critical even when the disease
    # ontology cannot establish a broader relation.
    if _marker_mismatch(queried_disease, text):
        return TrialApplicability(
            status=TrialApplicabilityStatus.SUBTYPE_MISMATCH,
            disease_relation=relation,
            reasons=("Query is biomarker-defined but the trial record lacks the requested biomarker.",),
        )
    if _population_mismatch(queried_disease, text):
        return TrialApplicability(
            status=TrialApplicabilityStatus.POPULATION_MISMATCH,
            disease_relation=relation,
            reasons=("Trial population conflicts with the explicit age population in the query.",),
        )
    if _dose_mismatch(queried_disease, text):
        return TrialApplicability(
            status=TrialApplicabilityStatus.DOSE_MISMATCH,
            disease_relation=relation,
            reasons=("Trial dose/intensity conflicts with the explicit dose qualifier in the query.",),
        )
    if relation == DiseaseRelation.UNRELATED:
        query_norm = normalize_disease_term(queried_disease)
        title_norm = normalize_disease_term(trial.title or "")
        if query_norm and (
            query_norm == title_norm
            or re.search(r"\b" + re.escape(query_norm) + r"\b", title_norm)
        ):
            relation = DiseaseRelation.SAME

    # Match the legacy title fallback for curated parent-child disease terms.
    # This preserves established cases such as secondary prevention of stroke
    # queried under the broader cardiovascular-disease concept.
    if relation == DiseaseRelation.UNRELATED:
        query_norm = normalize_disease_term(queried_disease)
        title_lower = (trial.title or "").lower()
        for child in _PARENT_CHILD.get(query_norm, frozenset()):
            if re.search(r"\b" + re.escape(child) + r"\b", title_lower):
                relation = DiseaseRelation.PARENT_CHILD
                break
        if relation == DiseaseRelation.UNRELATED:
            for parent, children in _PARENT_CHILD.items():
                if query_norm in children and re.search(r"\b" + re.escape(parent) + r"\b", title_lower):
                    relation = DiseaseRelation.PARENT_CHILD
                    break

    if relation == DiseaseRelation.UNRELATED:
        return TrialApplicability(
            status=TrialApplicabilityStatus.INSUFFICIENT_METADATA,
            disease_relation=relation,
            reasons=("No exact or curated parent-child disease relation was established.",),
        )
    if _marker_mismatch(queried_disease, text):
        reasons.append("Query is biomarker-defined but the trial record lacks the requested biomarker.")
        return TrialApplicability(
            status=TrialApplicabilityStatus.SUBTYPE_MISMATCH,
            disease_relation=relation,
            reasons=tuple(reasons),
        )
    if _population_mismatch(queried_disease, text):
        reasons.append("Trial population conflicts with the explicit age population in the query.")
        return TrialApplicability(
            status=TrialApplicabilityStatus.POPULATION_MISMATCH,
            disease_relation=relation,
            reasons=tuple(reasons),
        )
    if _dose_mismatch(queried_disease, text):
        reasons.append("Trial dose/intensity conflicts with the explicit dose qualifier in the query.")
        return TrialApplicability(
            status=TrialApplicabilityStatus.DOSE_MISMATCH,
            disease_relation=relation,
            reasons=tuple(reasons),
        )

    if relation == DiseaseRelation.PARENT_CHILD:
        return TrialApplicability(
            status=TrialApplicabilityStatus.PARENT_OR_BROAD_CONTEXT,
            disease_relation=relation,
            reasons=("Curated parent-child disease relation; retain as contextual evidence.",),
            direct_therapeutic_evidence=True,
        )
    return TrialApplicability(
        status=TrialApplicabilityStatus.DIRECT,
        disease_relation=relation,
        reasons=("Exact disease relation established.",),
        direct_therapeutic_evidence=True,
    )
