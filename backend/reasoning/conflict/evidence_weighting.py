"""Shared claim-level evidence weighting utilities (Phase 5.16).

Provides canonical weighting, group-key computation, and independence clustering
for claim-level evidence.  Used by both AdvancedConflictResolver and
TherapeuticOppositionAssessor so that quality judgements are consistent across
the conflict-detection and opposition-detection pathways.

Design decisions:
- claim.provenance.record_id (PMID/DOI/NCT) is the canonical deduplication anchor.
- Abstract text fingerprint is the fallback when record_id is absent.
- group_weight uses max-of-group (not sum) so that redundant records do not inflate.
- Recency factors are read-only constants — do NOT tune against test data.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.core.domain.claim import Claim

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Evidence type quality multipliers
# Source: same as AdvancedConflictResolver (Phase 2)
# These are the CANONICAL weights — conflict_resolver.py imports from here.
# ─────────────────────────────────────────────

EVIDENCE_TYPE_WEIGHTS: dict[str, float] = {
    "META_ANALYSIS": 1.0,
    "SYSTEMATIC_REVIEW": 0.95,
    "RCT": 0.9,
    "INTERVENTIONAL": 0.75,
    "NON_RCT": 0.75,
    "COHORT_STUDY": 0.75,
    "CASE_CONTROL": 0.65,
    "CASE_REPORT": 0.4,
    "EXPERT_OPINION": 0.3,
    "IN_VITRO": 0.5,
    "IN_VIVO": 0.55,
    "COMPUTATIONAL": 0.35,
    "OBSERVATIONAL": 0.65,  # matches EvidenceType.OBSERVATIONAL
    "UNKNOWN": 0.5,
}

_CURRENT_YEAR: int = datetime.utcnow().year


# ─────────────────────────────────────────────
# Claim weight
# ─────────────────────────────────────────────

def compute_claim_weight(claim: "Claim") -> float:
    """Compute a single quality score for a claim.

    Formula: ERW × evidence_type_weight × recency_factor

    ERW comes directly from claim.erw.value (inherited from parent Evidence).
    Evidence type is read from claim.evidence_type if present (Claim has no
    evidence_type field in the canonical model, so this is a safe getattr).
    Recency uses claim.publication_year when available.

    Returns:
        float [0.0, 1.0] — higher is higher quality.
    """
    erw: float = claim.erw.value

    # evidence_type is not a Claim attribute in the canonical model.
    # It may be present on subclasses or populated via extra fields.
    ev_type_raw = getattr(claim, "evidence_type", None)
    if ev_type_raw is not None:
        ev_type = str(ev_type_raw).upper().replace(" ", "_")
    else:
        ev_type = "UNKNOWN"
    type_weight = EVIDENCE_TYPE_WEIGHTS.get(ev_type, 0.5)

    # Recency factor: more recent evidence is slightly preferred
    recency_factor = 1.0
    pub_year = getattr(claim, "publication_year", None)
    if pub_year is not None:
        try:
            age = _CURRENT_YEAR - int(pub_year)
            if age <= 2:
                recency_factor = 1.2
            elif age <= 5:
                recency_factor = 1.1
            elif age <= 10:
                recency_factor = 1.0
            else:
                recency_factor = max(0.7, 1.0 - (age - 10) * 0.02)
        except (ValueError, TypeError):
            recency_factor = 1.0

    return round(min(1.0, erw * type_weight * recency_factor), 4)


# ─────────────────────────────────────────────
# Evidence group key
# ─────────────────────────────────────────────

def evidence_group_key(claim: "Claim") -> str:
    """Return a string key identifying the underlying study this claim came from.

    Priority:
    1. claim.provenance.record_id  — PMID / DOI / NCT (canonical study identity)
    2. SHA-256 prefix of claim.raw_text — text fingerprint fallback
    3. str(claim.id) — unique per-claim fallback (no grouping possible)

    The returned key is used to cluster claims by the same underlying study so
    that redundant records do not inflate opposition scores linearly.
    """
    record_id = getattr(claim.provenance, "record_id", None)
    if record_id and record_id not in ("", "unknown", "unlinked", "mock_citation_key"):
        return f"record:{record_id}"

    # Try citation_key as encoded in evidence_ids — not directly available on Claim.
    # Fall back to raw_text fingerprint.
    raw_text = claim.raw_text
    if raw_text and len(raw_text.strip()) >= 20:
        fingerprint = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:16]
        return f"text:{fingerprint}"

    # Last resort — each claim is its own group (no deduplication)
    return f"claim:{claim.id}"


# ─────────────────────────────────────────────
# Independence clustering
# ─────────────────────────────────────────────

def cluster_into_evidence_groups(
    claims: list["Claim"],
) -> dict[str, list["Claim"]]:
    """Cluster claims by underlying study identity.

    Returns:
        Dict mapping group_key → list of claims in that group.
        Each group represents one independent study/source.
    """
    groups: dict[str, list["Claim"]] = {}
    for claim in claims:
        key = evidence_group_key(claim)
        groups.setdefault(key, []).append(claim)
    return groups


def group_weight(claims_in_group: list["Claim"]) -> float:
    """Return the effective weight for an independence group.

    Uses max-of-group: multiple records from the same study do NOT multiply.
    The highest-quality record in the group represents the study's contribution.

    Args:
        claims_in_group: All claims with the same group key.

    Returns:
        float — maximum compute_claim_weight in the group, or 0.0 if empty.
    """
    if not claims_in_group:
        return 0.0
    return max(compute_claim_weight(c) for c in claims_in_group)
