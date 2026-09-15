"""ClinicalTrial entity — registered human-subject clinical study.

Reference: 02_DOMAIN_MODEL.md §4.13
"""
from __future__ import annotations

import re
import uuid
from typing import Any
from pydantic import BaseModel, Field, field_validator

from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.value_objects.provenance import ProvenanceReference


class ClinicalTrial(BaseModel):
    """A registered human-subject clinical study evaluating the drug on the disease.

    Immutable. Created by the Normalization Layer.
    NCT identifier must match format NCT\\d{8}.
    Status must map to TrialOutcomeStatus enum.

    Attributes:
        id: Internal UUID.
        nct_id: ClinicalTrials.gov identifier (e.g., 'NCT00398918').
        title: Official trial title.
        phase: Trial phase ('Phase I', 'Phase II', 'Phase III', 'Phase IV').
        status: Outcome status from TrialOutcomeStatus enum.
        drug_chembl_id: ChEMBL ID of the evaluated drug.
        disease_identifier: MeSH or UMLS identifier of the target disease.
        primary_outcome: Description of the primary outcome measure.
        enrollment: Number of enrolled participants.
        provenance: Citation to ClinicalTrials.gov record.
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Internal unique identifier.")
    nct_id: str = Field(..., description="ClinicalTrials.gov identifier (e.g., 'NCT00398918').")
    title: str = Field(..., description="Official trial title.")
    phase: str = Field(..., description="Trial phase ('Phase I', 'Phase II', 'Phase III', 'Phase IV').")
    status: TrialOutcomeStatus = Field(..., description="Outcome status.")
    drug_chembl_id: str | None = Field(None, description="ChEMBL ID of the evaluated drug.")
    disease_identifier: str | None = Field(None, description="MeSH or UMLS identifier of the disease.")
    primary_outcome: str | None = Field(None, description="Description of the primary outcome measure.")
    enrollment: int | None = Field(None, ge=0, description="Number of enrolled participants.")
    provenance: ProvenanceReference = Field(..., description="Citation to ClinicalTrials.gov record.")
    study_type: str | None = Field(None, description="Study type e.g. INTERVENTIONAL, OBSERVATIONAL.")
    design_allocation: str | None = Field(None, description="Design allocation e.g. RANDOMIZED, NON_RANDOMIZED.")
    intervention_names: list[str] = Field(default_factory=list, description="Names of experimental interventions.")
    comparator_names: list[str] = Field(default_factory=list, description="Names of comparator or control interventions.")
    why_stopped: str | None = Field(None, description="Reason why study was stopped.")
    has_results: bool = Field(default=False, description="Whether results were posted to ClinicalTrials.gov.")
    outcome_measures: list[dict[str, Any]] = Field(default_factory=list, description="Parsed outcome measures from resultsSection.")
    is_negative_efficacy: bool = Field(default=False, description="Whether a negative efficacy outcome was confirmed.")
    negative_efficacy_reason: str | None = Field(None, description="Detailed explanation of negative efficacy determination.")
    condition_names: list[str] = Field(default_factory=list, description="Conditions/diseases evaluated in the trial.")

    @field_validator("nct_id")
    @classmethod
    def validate_nct_id(cls, v: str) -> str:
        """Validate NCT identifier format: NCT followed by 8 digits."""
        pattern = r"^NCT\d{8}$"
        clean = v.strip().upper()
        if not re.match(pattern, clean):
            raise ValueError(
                f"Invalid NCT ID format: '{v}'. Expected format: 'NCT########' (8 digits)."
            )
        return clean

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v: str) -> str:
        """Validate trial phase string."""
        valid = {"Phase I", "Phase II", "Phase III", "Phase IV", "Phase I/II", "Phase II/III", "N/A"}
        clean = v.strip()
        if clean not in valid:
            raise ValueError(f"Invalid trial phase: '{clean}'. Valid values: {valid}.")
        return clean
