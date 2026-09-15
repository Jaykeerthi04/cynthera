"""DirectionalMechanismEvaluator — evaluates directional consistency along mechanistic paths.

Bridges the directional evidence arm (Phase 4B/4C/4D) to multi-hop mechanistic chains (Phase 2/3)
without conflating mechanistic plausibility with therapeutic direction.

SCIENTIFIC PRINCIPLES:
1. Reactome structural roles (CATALYST, INPUT, OUTPUT, PARTICIPANT, COMPLEX_COMPONENT,
   ENTITY_SET_MEMBER) are non-directional (UNKNOWN polarity) and must NOT be fabricated
   into positive or negative regulators.
2. Only explicit regulatory edges (POSITIVE_REGULATOR, NEGATIVE_REGULATOR) or signed
   curated literature/database claims carry non-zero sign.
3. Path contradictions occur when an explicit signed edge opposes the required therapeutic direction.
4. If no signed contradictions exist, a structural path is CONSISTENT (or UNKNOWN if unpolarized),
   not automatically POSITIVE.
"""
from __future__ import annotations

import logging
from typing import Any, Sequence

from backend.core.domain.candidate_mechanism import CandidateMechanism, MechanismHop
from backend.core.domain.directional_mechanism import DirectionalMechanismAssessment
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.enums.molecular_polarity import MolecularPolarity

logger = logging.getLogger(__name__)

# Predicate sets for drug action normalization
_INHIBITORY_ACTIONS = {
    "INHIBITOR", "INHIBITION", "ANTAGONIST", "BLOCKER", "NEGATIVE_ALLOSTERIC_MODULATOR", "SUPPRESSOR"
}
_ACTIVATING_ACTIONS = {
    "ACTIVATOR", "ACTIVATION", "AGONIST", "OPENER", "POSITIVE_ALLOSTERIC_MODULATOR", "PARTIAL_AGONIST", "STIMULATOR"
}


class DirectionalMechanismEvaluator:
    """Evaluates directional consistency along individual candidate mechanism paths."""

    def evaluate_candidate(
        self,
        candidate: CandidateMechanism,
        package: RetrievalPackage | None = None,
        disease_required_action: str | None = None,
        drug_action: str | None = None,
    ) -> DirectionalMechanismAssessment:
        """Evaluate directional consistency and contradiction detection for a candidate mechanism.

        Args:
            candidate: The CandidateMechanism with ordered hops.
            package: Optional RetrievalPackage to look up target direction evidence.
            disease_required_action: Explicit required target action (e.g. "INHIBITION", "ACTIVATION").
            drug_action: Explicit drug action (e.g. "INHIBITOR", "AGONIST").

        Returns:
            DirectionalMechanismAssessment with consistency status, contradiction detection,
            and supporting/opposing edge breakdown.

        Path direction states:
            CONSISTENT:    Drug-target sign established AND no opposing intermediate signed edges.
            PARTIAL:       Drug-target sign is established, but critical intermediate edges have
                           unknown polarity (structural Reactome participation only). Full path
                           direction cannot be confirmed; partial information is available.
            CONTRADICTORY: An explicit signed edge opposes the required therapeutic direction.
            UNKNOWN:       Drug-target sign itself is indeterminate (MODULATOR or no action data).
        """
        path_id = str(candidate.candidate_index)
        hops = candidate.hops

        # 1. Identify primary target and drug action from hop 0
        target_id = "UNKNOWN"
        hop0_pred = ""
        if hops:
            hop0 = hops[0]
            hop0_pred = (hop0.predicate or "").upper()
            target_id = hop0.to_node.split(":")[-1].strip()

        # Resolve drug action
        if not drug_action:
            drug_action = hop0_pred if hop0_pred else "UNKNOWN"
        drug_action_norm = drug_action.upper()

        # 2. Resolve disease required target action
        if not disease_required_action and package:
            disease_required_action = self._resolve_disease_required_action(package, target_id)
        if not disease_required_action:
            disease_required_action = "UNKNOWN"
        disease_req_norm = disease_required_action.upper()

        # 3. Analyze per-hop polarity and causal grounding along the chain
        supporting_edges: list[str] = []
        opposing_edges: list[str] = []
        signed_hops: list[tuple[int, MechanismHop, MolecularPolarity]] = []
        best_grounding = CausalGrounding.STRUCTURAL

        _GROUNDING_RANKS = {
            CausalGrounding.DIRECT: 0,
            CausalGrounding.CURATED: 1,
            CausalGrounding.INFERRED: 2,
            CausalGrounding.STRUCTURAL: 3,
            CausalGrounding.NONE: 4,
        }

        for idx, hop in enumerate(hops):
            raw_pol = getattr(hop, "polarity", "UNKNOWN")
            pol = raw_pol if isinstance(raw_pol, MolecularPolarity) else MolecularPolarity(str(raw_pol))
            
            raw_g = getattr(hop, "causal_grounding", "STRUCTURAL")
            try:
                g = raw_g if isinstance(raw_g, CausalGrounding) else CausalGrounding(str(raw_g))
            except ValueError:
                g = CausalGrounding.STRUCTURAL

            # Track highest causal grounding
            if _GROUNDING_RANKS.get(g, 4) < _GROUNDING_RANKS.get(best_grounding, 4):
                best_grounding = g

            # Check for explicit signed intermediate edges
            if pol != MolecularPolarity.UNKNOWN:
                signed_hops.append((idx, hop, pol))


        # 4. Check for direct Drug-Target vs Disease Target Requirement alignment
        is_drug_inhibitory = drug_action_norm in _INHIBITORY_ACTIONS
        is_drug_activating = drug_action_norm in _ACTIVATING_ACTIONS
        is_req_inhibition = disease_req_norm in ("INHIBITION", "INHIBITOR", "LOSS_OF_FUNCTION_PROTECTIVE", "DOWNREGULATION")
        is_req_activation = disease_req_norm in ("ACTIVATION", "AGONIST", "GAIN_OF_FUNCTION_PROTECTIVE", "UPREGULATION")

        contradiction_detected = False
        direction_status = "UNKNOWN"
        directionally_consistent: bool | None = None
        explanation_parts: list[str] = []

        # Target-level baseline check
        if is_drug_inhibitory and is_req_inhibition:
            direction_status = "CONSISTENT"
            directionally_consistent = True
            supporting_edges.append(f"Drug {drug_action_norm} aligns with required target INHIBITION for {target_id}.")
        elif is_drug_activating and is_req_activation:
            direction_status = "CONSISTENT"
            directionally_consistent = True
            supporting_edges.append(f"Drug {drug_action_norm} aligns with required target ACTIVATION for {target_id}.")
        elif is_drug_inhibitory and is_req_activation:
            direction_status = "CONTRADICTORY"
            directionally_consistent = False
            contradiction_detected = True
            opposing_edges.append(f"Drug {drug_action_norm} opposes required target ACTIVATION for {target_id}.")
        elif is_drug_activating and is_req_inhibition:
            direction_status = "CONTRADICTORY"
            directionally_consistent = False
            contradiction_detected = True
            opposing_edges.append(f"Drug {drug_action_norm} opposes required target INHIBITION for {target_id}.")
        else:
            direction_status = "UNKNOWN"
            directionally_consistent = None
            explanation_parts.append(f"Target directional requirement is {disease_req_norm}; drug action is {drug_action_norm}.")

        # 5. Check intermediate path-level edges for contradictory regulatory mechanisms
        # Example: Drug inhibits Target, Disease requires inhibition, BUT Target NEGATIVE_REGULATES
        # a disease mediator or tumor suppressor, so inhibiting the target paradoxically activates the disease.
        for idx, hop, pol in signed_hops[1:]:  # skip hop 0 (drug-target)
            hop_desc = f"Hop {idx}: {hop.from_node} --[{hop.predicate}]--> {hop.to_node}"
            pred_u = (hop.predicate or "").upper()
            if is_req_inhibition and is_drug_inhibitory:
                if pol == MolecularPolarity.NEGATIVE or pred_u in ("NEGATIVE_REGULATOR", "NEGATIVE_REGULATES"):
                    opposing_edges.append(f"Path contradiction at {hop_desc}: drug inhibition of a negative regulator derepresses downstream disease progression.")
                    contradiction_detected = True
                    direction_status = "CONTRADICTORY"
                    directionally_consistent = False
                elif pol == MolecularPolarity.POSITIVE or pred_u in ("POSITIVE_REGULATOR", "POSITIVE_REGULATES"):
                    supporting_edges.append(f"{hop_desc}: positive regulation consistent with target cascade.")
            elif is_req_activation and is_drug_activating:
                if pol == MolecularPolarity.NEGATIVE or pred_u in ("NEGATIVE_REGULATOR", "NEGATIVE_REGULATES"):
                    opposing_edges.append(f"Path contradiction at {hop_desc}: drug activation of a negative regulator represses downstream therapeutic pathway.")
                    contradiction_detected = True
                    direction_status = "CONTRADICTORY"
                    directionally_consistent = False
                elif pol == MolecularPolarity.POSITIVE or pred_u in ("POSITIVE_REGULATOR", "POSITIVE_REGULATES"):
                    supporting_edges.append(f"{hop_desc}: positive regulation consistent with target cascade.")

        # Phase 5.3: PARTIAL state — drug-target sign is established (CONSISTENT baseline)
        # but critical intermediate edges have UNKNOWN polarity and STRUCTURAL grounding.
        # This is more informative than UNKNOWN (where even the drug-target sign is indeterminate).
        if direction_status == "CONSISTENT" and not contradiction_detected:
            if self._has_critical_unknown_intermediate(hops):
                direction_status = "PARTIAL"
                directionally_consistent = None
                explanation_parts.append(
                    f"Drug-target directional sign established ({drug_action_norm} → {target_id}), "
                    "but critical intermediate mechanistic edges have UNKNOWN polarity "
                    "(structural Reactome participation only). "
                    "Full path directional confirmation requires curated intermediate evidence."
                )

        # Determine overall mechanistic polarity
        path_polarity_val = getattr(candidate, "directional_polarity", "UNKNOWN")

        # Build explanation
        if contradiction_detected:
            explanation = (
                f"Directional mechanism contradiction detected: {'; '.join(opposing_edges)}. "
                f"Target: {target_id}, Drug action: {drug_action_norm}, Disease requirement: {disease_req_norm}."
            )
        elif direction_status == "PARTIAL":
            explanation = (
                f"Directional mechanism is PARTIAL: drug-target sign is known ({drug_action_norm} → {target_id}), "
                f"but {len(hops)} intermediate hop(s) have unresolved polarity. "
                f"{' '.join(explanation_parts)}"
            )
        elif directionally_consistent is True:
            explanation = (
                f"Directional mechanism is consistent: {'; '.join(supporting_edges)}. "
                f"No signed path-level contradictions found along {len(hops)} hops."
            )
        else:
            explanation = (
                f"Directional mechanism status is {direction_status}. "
                f"Intermediate hops contain {len(hops)} structural edges with {len(signed_hops)} signed regulatory roles. "
                f"{' '.join(explanation_parts)}"
            )

        return DirectionalMechanismAssessment(
            path_id=path_id,
            target_id=target_id,
            drug_action=drug_action_norm,
            disease_required_action=disease_req_norm,
            mechanistic_polarity=path_polarity_val,
            path_direction_status=direction_status,
            causal_grounding=best_grounding.value,
            directionally_consistent=directionally_consistent,
            contradiction_detected=contradiction_detected,
            supporting_edges=supporting_edges,
            opposing_edges=opposing_edges,
            explanation=explanation,
        )

    def _has_critical_unknown_intermediate(self, hops: Sequence[MechanismHop]) -> bool:
        """Return True if any intermediate hop (between drug-target and disease terminal)
        has UNKNOWN polarity with STRUCTURAL grounding.

        This identifies paths where the drug-target sign is known but the downstream
        mechanistic edges cannot propagate direction (structural Reactome participation only).
        Such paths should be classified as PARTIAL rather than CONSISTENT or UNKNOWN.

        Args:
            hops: Ordered hops of a CandidateMechanism (index 0 = drug-target).

        Returns:
            True if any intermediate hop (index 1..n-2) has UNKNOWN polarity + STRUCTURAL grounding.
        """
        if len(hops) <= 2:
            # Only drug-target and disease terminal — no intermediate hops possible
            return False
        for idx, hop in enumerate(hops):
            if idx == 0:
                # Drug-target hop — already evaluated in baseline check
                continue
            if idx == len(hops) - 1:
                # Disease terminal hop — not a mechanistic intermediate
                continue
            raw_pol = getattr(hop, "polarity", "UNKNOWN")
            try:
                pol = raw_pol if isinstance(raw_pol, MolecularPolarity) else MolecularPolarity(str(raw_pol))
            except ValueError:
                pol = MolecularPolarity.UNKNOWN
            raw_g = getattr(hop, "causal_grounding", "STRUCTURAL")
            try:
                g = raw_g if isinstance(raw_g, CausalGrounding) else CausalGrounding(str(raw_g))
            except ValueError:
                g = CausalGrounding.STRUCTURAL
            if pol == MolecularPolarity.UNKNOWN and g == CausalGrounding.STRUCTURAL:
                return True
        return False


    def _resolve_disease_required_action(self, package: RetrievalPackage, target_id: str) -> str:
        """Resolve the disease required action for a given target from package evidence."""
        # Check Open Targets DoE evidence
        target_norm = target_id.upper().strip()
        for doe in getattr(package, "opentargets_doe_evidence", []):
            doe_tgt = getattr(doe, "target_symbol", "") or getattr(doe, "target_id", "")
            if doe_tgt.upper() == target_norm or target_norm in doe_tgt.upper():
                action = getattr(doe, "required_action", None) or getattr(doe, "disease_target_direction", None)
                if action and action != "UNKNOWN":
                    return str(action)

        # Check DATTs evidence
        for datts in getattr(package, "datts_evidence", []):
            datts_tgt = getattr(datts, "target_symbol", "") or getattr(datts, "target_id", "")
            if datts_tgt.upper() == target_norm or target_norm in datts_tgt.upper():
                action = getattr(datts, "required_action", None)
                if action and action != "UNKNOWN":
                    return str(action)

        return "UNKNOWN"
