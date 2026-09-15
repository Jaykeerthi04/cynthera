"""PredicateType enum — directional mechanism of a claim triplet.

Reference: 02_DOMAIN_MODEL.md §2.1
"""
from enum import Enum


class PredicateType(str, Enum):
    """Represents the directional mechanism of a claims triplet."""

    ACTIVATES = "ACTIVATES"
    """Increases the target protein's functional activity."""

    INHIBITS = "INHIBITS"
    """Decreases or blocks the target protein's functional activity."""

    BINDS = "BINDS"
    """Physically associates with the target without specified functional direction."""

    UPREGULATES = "UPREGULATES"
    """Increases the expression level (transcription/translation) of a gene or protein."""

    DOWNREGULATES = "DOWNREGULATES"
    """Decreases the expression level of a gene or protein."""

    CAUSES = "CAUSES"
    """Induces a downstream pathological state or process."""

    PREVENTS = "PREVENTS"
    """Halts or reverses a downstream pathological state or process."""

    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    """Statistically correlates with, but without implied direct physical causality."""

    NO_EFFECT = "NO_EFFECT"
    """Explicitly shown to have no directional, regulatory, or binding impact."""

    # ── Therapeutic opposition predicates (Phase 5.16) ──────────────────────────
    # These represent EXPLICIT negative therapeutic evidence — failure, futility,
    # or harm in a disease-specific clinical/experimental context.
    # They are DISTINCT from mechanistic predicates above and should only be
    # extracted when the text unambiguously describes a disease-specific outcome.

    FAILED_TO_IMPROVE = "FAILED_TO_IMPROVE"
    """Drug failed to improve the disease outcome in a clinical study."""

    NO_SIGNIFICANT_BENEFIT = "NO_SIGNIFICANT_BENEFIT"
    """No statistically significant benefit demonstrated for this disease."""

    TERMINATED_FOR_FUTILITY = "TERMINATED_FOR_FUTILITY"
    """Trial terminated for futility — pre-specified futility boundary crossed."""

    TERMINATED_FOR_SAFETY = "TERMINATED_FOR_SAFETY"
    """Trial terminated due to safety concerns in this disease context."""

    WORSENED_OUTCOME = "WORSENED_OUTCOME"
    """Drug was associated with worsening of disease outcome in this indication."""

    CONTRAINDICATED = "CONTRAINDICATED"
    """Drug is explicitly contraindicated for this disease."""
