"""Controlled vocabulary enumerations for clinical trial drug attribution.

Phase 1A: Dissecting trial arm structure and termination language to distinguish
evaluated interventions from background constant co-therapy and comparators.
"""
from __future__ import annotations

from enum import Enum


class TrialDrugRole(str, Enum):
    """Classification of the evaluated drug's structural role across trial arms."""

    EVALUATED_PRIMARY_INTERVENTION = "EVALUATED_PRIMARY_INTERVENTION"
    """The drug is the primary, sole, or differentiating investigational intervention."""

    EXPERIMENTAL = "EXPERIMENTAL"
    """The drug is the experimental intervention."""

    EVALUATED_COMBINATION_COMPONENT = "EVALUATED_COMBINATION_COMPONENT"
    """The drug is an active investigational component of a combination therapy arm."""

    BACKGROUND_CONSTANT_THERAPY = "BACKGROUND_CONSTANT_THERAPY"
    """The drug is administered identically across all relevant arms as constant background therapy."""

    BACKGROUND_THERAPY = "BACKGROUND_THERAPY"
    """The drug is background therapy across arms."""

    CONCOMITANT_THERAPY = "CONCOMITANT_THERAPY"
    """The drug is concomitant or constant therapy across device/formulation comparisons."""

    COMPARATOR_ONLY = "COMPARATOR_ONLY"
    """The drug is present only as a control/comparator, not in the experimental intervention arm."""

    ACTIVE_COMPARATOR = "ACTIVE_COMPARATOR"
    """The drug is an active comparator arm."""

    PLACEBO_COMPARATOR = "PLACEBO_COMPARATOR"
    """The comparator is a placebo."""

    UNCERTAIN = "UNCERTAIN"
    """The drug's structural role cannot be determined conclusively from trial metadata."""

    OTHER_UNKNOWN = "OTHER_UNKNOWN"
    """Other or unknown structural role."""


class AttributionTextEvidence(str, Enum):
    """Classification of textual attribution signals in trial termination rationale."""

    EXPLICIT_DRUG_ATTRIBUTION = "EXPLICIT_DRUG_ATTRIBUTION"
    """The drug is explicitly named in the termination reason (e.g. 'lack of efficacy of niacin')."""

    IMPLICIT_INTERVENTION_ATTRIBUTION = "IMPLICIT_INTERVENTION_ATTRIBUTION"
    """The study drug/investigational product is named generally without specifying the chemical entity."""

    GENERIC_FAILURE_REASON = "GENERIC_FAILURE_REASON"
    """A generic failure reason is stated (e.g. 'Lack of Efficacy', 'Futility') without drug attribution."""

    NO_ATTRIBUTION = "NO_ATTRIBUTION"
    """No termination reason is available or reason is purely administrative."""
