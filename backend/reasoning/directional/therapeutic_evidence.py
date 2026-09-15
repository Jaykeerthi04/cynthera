"""Fail-closed semantic gates for therapeutic support evidence."""
from __future__ import annotations

import re
from typing import Any


_NON_THERAPEUTIC_PATTERNS = (
    r"\brisk factor\b",
    r"\bassociated with (?:an? )?(?:increased|higher|elevated) risk\b",
    r"\betiologic(?:al)?\b",
    r"\bcauses? (?:or )?(?:contributes to|increases)\b",
    r"\badverse event\b",
    r"\bdrug[- ]induced\b",
    r"\bcomplication of treatment\b",
    r"\bhemorrhagic stroke\b.*\b(bleed|bleeding|hemorrhage|risk)\b",
)

_THERAPEUTIC_CONTEXT_PATTERNS = (
    r"\btreat(?:ment|ed|s)?\b",
    r"\btherap(?:y|eutic|ies)\b",
    r"\befficacy\b",
    r"\bclinical trial\b",
    r"\bimprov(?:e|ed|ement|ing)\b",
    r"\bbenefit\b",
    r"\bresponse\b",
)


def is_therapeutically_eligible_evidence(evidence: Any) -> tuple[bool, str]:
    """Return whether a record can contribute direct therapeutic support.

    This intentionally rejects only unmistakable risk/etiology/adverse-event
    framing without treatment context. Ambiguous records remain eligible for
    the existing evidence pipeline and are not silently reclassified.
    """
    text = " ".join(
        str(value or "") for value in (
            getattr(evidence, "title", None),
            getattr(evidence, "abstract", None),
        )
    ).lower()
    if not text.strip():
        return True, "No text available for semantic exclusion; retained as contextual evidence."
    non_therapeutic = any(re.search(pattern, text) for pattern in _NON_THERAPEUTIC_PATTERNS)
    therapeutic_context = any(re.search(pattern, text) for pattern in _THERAPEUTIC_CONTEXT_PATTERNS)
    if non_therapeutic and not therapeutic_context:
        return False, "Risk, etiologic, or adverse-event framing without therapeutic treatment context."
    return True, "No exclusive non-therapeutic framing detected."
