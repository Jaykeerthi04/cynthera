"""Directional Mechanism domain models.

Connects the directional evidence infrastructure to multi-hop mechanistic chains.
Evaluates whether molecular edges along a mechanistic path preserve, contradict,
or are neutral/unknown relative to the target-level therapeutic hypothesis.

SCIENTIFIC PRINCIPLES:
1. Strict semantic separation: Mechanistic plausibility != Therapeutic direction.
2. Reactome structural participation (CATALYST, INPUT, OUTPUT, PARTICIPANT) remains
   UNKNOWN polarity and never implies positive or negative causal effect.
3. Path contradictions are detected only on explicit, signed opposing edges.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.enums.causal_grounding import CausalGrounding


@dataclass(frozen=True)
class DirectionalMechanismAssessment:
    """Assessment of directional consistency for a multi-hop mechanistic path.

    Attributes:
        path_id: Unique identifier for the evaluated path.
        target_id: Canonical target identifier (e.g. "P12821" or "ACE").
        drug_action: Interaction classification from ChEMBL (e.g. "INHIBITOR", "AGONIST").
        disease_required_action: Desired disease target action (e.g. "INHIBITION", "ACTIVATION").
        mechanistic_polarity: Aggregate signed polarity propagated along the path.
        path_direction_status: "CONSISTENT" | "CONTRADICTORY" | "PARTIAL" | "UNKNOWN".
        causal_grounding: Best causal grounding tier across signed edges.
        directionally_consistent: True if path supports hypothesis, False if contradictory, None if partial/unknown.
        contradiction_detected: True if an explicit signed edge opposes the required direction.
        supporting_edges: List of human-readable edge descriptions supporting the direction.
        opposing_edges: List of human-readable edge descriptions opposing the direction.
        explanation: Clear narrative explanation of the directional mechanism assessment.
    """

    path_id: str
    target_id: str
    drug_action: str = "UNKNOWN"
    disease_required_action: str = "UNKNOWN"
    mechanistic_polarity: str = "UNKNOWN"
    path_direction_status: str = "UNKNOWN"
    causal_grounding: str = "STRUCTURAL"
    directionally_consistent: bool | None = None
    contradiction_detected: bool = False
    supporting_edges: list[str] = field(default_factory=list)
    opposing_edges: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_id": self.path_id,
            "target_id": self.target_id,
            "drug_action": self.drug_action,
            "disease_required_action": self.disease_required_action,
            "mechanistic_polarity": self.mechanistic_polarity,
            "path_direction_status": self.path_direction_status,
            "causal_grounding": self.causal_grounding,
            "directionally_consistent": self.directionally_consistent,
            "contradiction_detected": self.contradiction_detected,
            "supporting_edges": list(self.supporting_edges),
            "opposing_edges": list(self.opposing_edges),
            "explanation": self.explanation,
        }
