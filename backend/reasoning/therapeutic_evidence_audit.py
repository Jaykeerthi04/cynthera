"""Auditable classification of evidence used for therapeutic decisions.

This module intentionally distinguishes *retrieved biomedical evidence* from
*authoritative therapeutic evidence for the queried drug--disease pair*.
The former can contribute to the heuristic Support Score; the latter is the
only kind of evidence allowed to bypass the mechanistic-path requirement in
the final decision synthesis.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backend.core.enums.evidence_type import EvidenceType
from backend.core.enums.trial_outcome import TrialOutcomeStatus


@dataclass(frozen=True)
class TherapeuticEvidenceAudit:
    """One provenance decision for a possible therapeutic-evidence source."""

    source: str
    evidence_type: str
    pair_specific: bool
    therapeutic_relevance: bool
    direction: str
    quality: str
    provenance_id: str | None
    allowed_for_high_quality_therapeutic: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_high_quality_therapeutic_evidence(package: Any) -> list[TherapeuticEvidenceAudit]:
    """Return the provenance audit behind the high-quality-therapeutic gate.

    A registry ``COMPLETED`` status is not an efficacy result, and an Evidence
    record typed as RCT or META_ANALYSIS has no structured direction/outcome in
    the current domain model.  Those records remain useful, traceable inputs to
    SS, but cannot by themselves establish a therapeutic indication.
    """
    records: list[TherapeuticEvidenceAudit] = []

    approval = getattr(package, "approval_signal", None)
    if approval is not None:
        is_pair_approved = bool(
            getattr(approval, "is_approved", False)
            and getattr(approval, "matched_indication_term", "")
            and float(getattr(approval, "match_confidence", 0.0)) > 0.0
        )
        records.append(
            TherapeuticEvidenceAudit(
                source=str(getattr(approval, "source", "chembl")),
                evidence_type="REGULATORY_INDICATION",
                pair_specific=bool(getattr(approval, "matched_indication_term", "")),
                therapeutic_relevance=is_pair_approved,
                direction="SUPPORTS" if is_pair_approved else "UNKNOWN",
                quality="REGULATORY",
                provenance_id=getattr(approval, "matched_indication_term", None) or None,
                allowed_for_high_quality_therapeutic=is_pair_approved,
                reason=(
                    "Disease-matched regulatory indication retrieved from ChEMBL."
                    if is_pair_approved
                    else "No disease-matched approved indication was established by the approval signal."
                ),
            )
        )

    for trial in getattr(package, "clinical_trials", []) or []:
        pair_scoped = bool(
            getattr(trial, "drug_chembl_id", None)
            and getattr(trial, "disease_identifier", None)
        )
        explicit_success = getattr(trial, "status", None) == TrialOutcomeStatus.COMPLETED_SUCCESS
        explicit_failure = bool(
            getattr(trial, "status", None) in (
                TrialOutcomeStatus.COMPLETED_FAILURE,
                TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
                TrialOutcomeStatus.TERMINATED_SAFETY,
            )
            or getattr(trial, "is_negative_efficacy", False)
        )

        if explicit_failure:
            direction = "OPPOSES"
            quality = "CLINICAL_HUMAN_FAILURE"
            relevance = True
            allowed = False
            reason = f"Clinical trial outcome opposes therapeutic hypothesis: {getattr(trial, 'negative_efficacy_reason', None) or getattr(trial, 'why_stopped', None) or 'Documented trial failure or early termination.'}"
        elif explicit_success:
            direction = "SUPPORTS"
            quality = "CLINICAL_HUMAN"
            relevance = True
            allowed = pair_scoped
            reason = "Pair-scoped trial has an explicit successful therapeutic outcome." if pair_scoped else "Registry status alone does not establish a successful therapeutic outcome."
        else:
            direction = "UNKNOWN"
            quality = "REGISTERED_STATUS_ONLY"
            relevance = False
            allowed = False
            reason = "Registry status alone does not establish a successful therapeutic outcome."

        records.append(
            TherapeuticEvidenceAudit(
                source=getattr(getattr(trial, "provenance", None), "source_name", "ClinicalTrials.gov"),
                evidence_type="REGISTERED_CLINICAL_TRIAL",
                pair_specific=pair_scoped,
                therapeutic_relevance=relevance,
                direction=direction,
                quality=quality,
                provenance_id=getattr(trial, "nct_id", None),
                allowed_for_high_quality_therapeutic=allowed,
                reason=reason,
            )
        )

    for evidence in getattr(package, "evidence_records", []) or []:
        evidence_type = getattr(evidence, "evidence_type", None)
        if evidence_type not in {EvidenceType.RCT, EvidenceType.META_ANALYSIS}:
            continue
        records.append(
            TherapeuticEvidenceAudit(
                source=getattr(getattr(evidence, "provenance", None), "source_name", "Unknown"),
                evidence_type=evidence_type.value,
                pair_specific=bool(
                    getattr(evidence, "drug_chembl_id", None)
                    and getattr(evidence, "disease_identifier", None)
                ),
                therapeutic_relevance=False,
                direction="UNKNOWN",
                quality="CLINICAL_RECORD_UNINTERPRETED",
                provenance_id=getattr(evidence, "citation_key", None),
                allowed_for_high_quality_therapeutic=False,
                reason=(
                    "The Evidence model records study type and provenance but no structured "
                    "drug--disease efficacy outcome or therapeutic direction. It may contribute "
                    "to SS but cannot certify high-quality therapeutic support."
                ),
            )
        )

    return records


def has_high_quality_therapeutic_evidence(package: Any) -> tuple[bool, list[TherapeuticEvidenceAudit]]:
    """Return the strict decision gate and its complete audit trail."""
    audit = audit_high_quality_therapeutic_evidence(package)
    return any(item.allowed_for_high_quality_therapeutic for item in audit), audit
