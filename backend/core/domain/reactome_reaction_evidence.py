"""ReactomeReactionEvidence domain model.

Represents target-specific molecular reaction and event participation derived from Reactome ContentService.
Preserves explicit reaction roles, hierarchy mapping, context, and provenance without assigning unsupported
causal activation/inhibition direction.
"""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ReactomeTargetRole(str, Enum):
    """Explicit biological/functional role of a target within a Reactome reaction."""
    CATALYST = "CATALYST"
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    PARTICIPANT = "PARTICIPANT"
    COMPLEX_COMPONENT = "COMPLEX_COMPONENT"
    ENTITY_SET_MEMBER = "ENTITY_SET_MEMBER"
    POSITIVE_REGULATOR = "POSITIVE_REGULATOR"
    NEGATIVE_REGULATOR = "NEGATIVE_REGULATOR"
    REQUIREMENT = "REQUIREMENT"
    UNKNOWN = "UNKNOWN"


class ReactomeReactionEvidence(BaseModel):
    """Evidence record for a target's participation in a Reactome reaction/event.

    Attributes:
        target_canonical_id: Canonical identifier for the target (e.g., gene symbol).
        target_original_id: Original identifier queried (e.g., UniProt accession).
        reaction_id: Reactome stable identifier for the reaction (e.g., 'R-HSA-379044').
        reaction_name: Display name of the reaction.
        schema_class: Reactome schema class (e.g., 'Reaction', 'FailedReaction', 'BlackBoxEvent').
        target_role: Target's role in the reaction (CATALYST, INPUT, OUTPUT, etc.).
        pathway_id: Reactome stable identifier for containing pathway (e.g., 'R-HSA-418555').
        pathway_name: Display name of the containing pathway.
        mapping_type: Relationship between reaction and pathway ('DIRECT_PATHWAY_MAPPING' or 'HIERARCHICAL_PATHWAY_MAPPING').
        direction: Direction of effect ('POSITIVE', 'NEGATIVE', or 'UNKNOWN').
                   Default 'UNKNOWN' for all structural/catalytic roles unless explicit Positive/Negative regulation exists.
        source: Primary data source ('REACTOME').
        source_id: Unique record ID from Reactome.
        evidence_type: Classification of evidence ('CURATED_REACTION').
        species: Taxon name (e.g., 'Homo sapiens').
        compartment: Subcellular location/compartment (e.g., 'plasma membrane', 'cytosol').
        disease_context: True if annotated in disease context (e.g., mutant/defective reaction), False if normal, None if unannotated.
        provenance: Structured provenance metadata.
    """

    model_config = {"frozen": True}

    target_canonical_id: str = Field(..., description="Canonical target identifier (e.g., gene symbol).")
    target_original_id: str = Field(..., description="Original target identifier (e.g., UniProt accession).")
    reaction_id: str = Field(..., description="Reactome reaction stable ID (e.g., 'R-HSA-379044').")
    reaction_name: str = Field(..., description="Display name of the reaction.")
    schema_class: str = Field(default="Reaction", description="Reactome schema class.")
    target_role: str = Field(default=ReactomeTargetRole.UNKNOWN.value, description="Role of the target in this reaction.")
    pathway_id: str | None = Field(default=None, description="Reactome pathway stable ID containing this reaction.")
    pathway_name: str | None = Field(default=None, description="Display name of the containing pathway.")
    mapping_type: str = Field(default="DIRECT_PATHWAY_MAPPING", description="DIRECT_PATHWAY_MAPPING or HIERARCHICAL_PATHWAY_MAPPING.")
    direction: str = Field(default="UNKNOWN", description="Directional polarity ('POSITIVE', 'NEGATIVE', or 'UNKNOWN').")
    source: str = Field(default="REACTOME", description="Source knowledgebase.")
    source_id: str | None = Field(default=None, description="Database record ID.")
    evidence_type: str = Field(default="CURATED_REACTION", description="Evidence classification.")
    species: str | None = Field(default="Homo sapiens", description="Taxonomic context.")
    compartment: str | None = Field(default=None, description="Subcellular compartment.")
    disease_context: bool | None = Field(default=None, description="Disease context flag.")
    provenance: dict[str, Any] = Field(default_factory=dict, description="Provenance metadata dictionary.")
