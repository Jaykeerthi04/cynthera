"""MultiTargetSynthesizer Engine (Phase 5.13).

Synthesizes therapeutic evidence across multiple targets of a drug:
1. Evaluates each target independently first.
2. Preserves all target-level provenance without silently dropping secondary targets.
3. Protects primary therapeutic targets from being overpowered by weak off-targets.
4. Synthesizes drug-level direction, conflicts, and evidence weights.
"""
from __future__ import annotations

from typing import Sequence

from backend.core.domain.candidate_mechanism import CandidateMechanism
from backend.core.domain.multitarget_synthesis import MultiTargetSynthesis
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.target import Target
from backend.core.domain.target_evidence_summary import TargetEvidenceSummary
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.therapeutic_direction_evidence import (
    TherapeuticAction,
    TherapeuticAlignment,
    TherapeuticDirectionEvidence,
)
from backend.reasoning.directional.therapeutic_alignment import (
    TherapeuticAlignmentEngine,
    group_evidence_by_independence,
    normalize_drug_action,
)
from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver


_QUALITY_FACTORS: dict[str, float] = {
    "INDEPENDENTLY_VALIDATED": 1.0,
    "LITERATURE_GROUNDED": 0.9,
    "CAUSAL": 0.85,
    "CURATED": 0.75,
    "STRUCTURAL": 0.30,
    "WEAK_SPECULATIVE": 0.30,
}

_GROUNDING_FACTORS: dict[CausalGrounding, float] = {
    CausalGrounding.DIRECT: 1.0,
    CausalGrounding.CURATED: 0.9,
    CausalGrounding.INFERRED: 0.5,
    CausalGrounding.STRUCTURAL: 0.0,
    CausalGrounding.NONE: 0.0,
}


class MultiTargetSynthesizer:
    """Orchestrates multi-target reasoning and synthesis."""

    def __init__(self, alignment_engine: TherapeuticAlignmentEngine | None = None) -> None:
        self._alignment_engine = alignment_engine or TherapeuticAlignmentEngine()

    def synthesize(
        self,
        package: RetrievalPackage,
        candidates: Sequence[CandidateMechanism] | None = None,
        resolver: BiologicalIdentifierResolver | None = None,
    ) -> MultiTargetSynthesis:
        """Synthesize evidence across all drug targets in the package.

        Args:
            package: Sealed RetrievalPackage with drug, targets, proteins, and evidence.
            candidates: Discovered CandidateMechanism objects for target-mechanism linkage.
            resolver: BiologicalIdentifierResolver for alias resolution.

        Returns:
            MultiTargetSynthesis domain model.
        """
        if resolver is None:
            resolver = BiologicalIdentifierResolver(
                proteins=package.proteins,
                genes=package.genes,
                mappings=package.identifier_mappings,
            )

        # 1. Map all targets (primary from bioactivity, secondary from direction evidence)
        target_meta: dict[str, dict] = {}
        for idx, t in enumerate(package.targets):
            uni = (t.protein_uniprot or "").strip().upper()
            res = resolver.resolve(uni, source="ChEMBL")
            sym = res.canonical_symbol or res.canonical_identifier or uni
            action = normalize_drug_action(t.mechanism)
            if sym not in target_meta:
                target_meta[sym] = {
                    "is_primary": idx == 0 or t.affinity_nm < 100.0,
                    "drug_action": action,
                    "uniprot": uni,
                    "target_obj": t,
                    "symbol": sym,
                    "affinity_nm": t.affinity_nm,
                }

        # Also register any target appearing in therapeutic direction evidence
        dir_recs_by_target: dict[str, list[TherapeuticDirectionEvidence]] = {}
        for rec in package.therapeutic_direction_evidence:
            tid = rec.target_canonical_id
            if tid not in dir_recs_by_target:
                dir_recs_by_target[tid] = []
            dir_recs_by_target[tid].append(rec)
            if tid not in target_meta:
                target_meta[tid] = {
                    "is_primary": False,
                    "drug_action": TherapeuticAction.UNKNOWN,
                    "uniprot": None,
                    "target_obj": None,
                    "symbol": tid,
                    "affinity_nm": None,
                }

        # 2. Map candidate mechanisms to targets
        candidates_by_target: dict[str, list[CandidateMechanism]] = {}
        if candidates:
            for cand in candidates:
                for hop in cand.hops:
                    for tid in target_meta:
                        if tid.upper() in hop.to_node.upper() or tid.upper() in hop.from_node.upper():
                            if tid not in candidates_by_target:
                                candidates_by_target[tid] = []
                            candidates_by_target[tid].append(cand)
                            break

        # 3. Evaluate each target independently
        target_summaries: list[TargetEvidenceSummary] = []
        supp_targets: list[str] = []
        opp_targets: list[str] = []
        unres_targets: list[str] = []

        total_supp_weight = 0.0
        total_opp_weight = 0.0
        total_unres_weight = 0.0

        for tid, meta in target_meta.items():
            recs = dir_recs_by_target.get(tid, [])
            groups = group_evidence_by_independence(recs)
            drug_action = meta["drug_action"]
            is_primary = meta["is_primary"]

            # Associated mechanisms
            target_cands = candidates_by_target.get(tid, [])
            best_ms = max([c.confidence_score for c in target_cands], default=0.0)
            best_quality = (
                max(target_cands, key=lambda c: _QUALITY_FACTORS.get(c.quality_tier, 0.0)).quality_tier
                if target_cands
                else "STRUCTURAL"
            )

            supp_groups: list[str] = []
            opp_groups: list[str] = []
            unres_groups: list[str] = []
            target_supp_w = 0.0
            target_opp_w = 0.0

            # Target weighting:
            target_role_multiplier = 1.0 if is_primary else 0.40
            quality_mult = _QUALITY_FACTORS.get(best_quality, 0.85) if target_cands else 1.0

            for g in groups:
                gw = _GROUNDING_FACTORS.get(g.causal_grounding, 0.0)
                if gw == 0.0:
                    continue  # Structural / None: zero directional weight

                if g.desired_action == TherapeuticAction.UNKNOWN or drug_action == TherapeuticAction.UNKNOWN:
                    unres_groups.append(g.group_id)
                elif g.desired_action == drug_action:
                    supp_groups.append(g.group_id)
                    target_supp_w += gw * target_role_multiplier * quality_mult
                else:
                    opp_groups.append(g.group_id)
                    target_opp_w += gw * target_role_multiplier * quality_mult

            # Target alignment
            if drug_action == TherapeuticAction.UNKNOWN or not groups:
                alignment = "INSUFFICIENT"
                dir_state = "UNKNOWN"
                unres_targets.append(tid)
                total_unres_weight += 0.50 * target_role_multiplier
            elif len(supp_groups) > 0 and len(opp_groups) == 0:
                alignment = "SUPPORTS"
                dir_state = "CONSISTENT"
                supp_targets.append(tid)
                total_supp_weight += target_supp_w
            elif len(opp_groups) > 0 and len(supp_groups) == 0:
                alignment = "OPPOSES"
                dir_state = "CONTRADICTORY"
                opp_targets.append(tid)
                total_opp_weight += target_opp_w
            else:
                alignment = "MIXED"
                dir_state = "CONTRADICTORY"
                if target_supp_w >= target_opp_w:
                    supp_targets.append(tid)
                else:
                    opp_targets.append(tid)
                total_supp_weight += target_supp_w
                total_opp_weight += target_opp_w

            # Desired action consensus
            req_action = TherapeuticAction.UNKNOWN
            for g in groups:
                if g.desired_action != TherapeuticAction.UNKNOWN:
                    req_action = g.desired_action
                    break

            relevance = {
                "canonical_match": True,
                "direct_drug_target": meta["target_obj"] is not None,
                "is_primary": is_primary,
                "affinity_nm": meta["affinity_nm"],
                "mechanism_quality": best_quality,
                "directional_support": alignment == "SUPPORTS",
                "role_multiplier": target_role_multiplier,
            }

            confidence = round(min(1.0, (target_supp_w + target_opp_w) / max(1.0, len(groups))), 4)

            summary = TargetEvidenceSummary(
                target_id=tid,
                target_symbol=meta["symbol"],
                drug_action=drug_action,
                required_action=req_action,
                alignment=alignment,
                mechanistic_score=best_ms,
                mechanism_quality=best_quality,
                supporting_evidence_groups=len(supp_groups),
                opposing_evidence_groups=len(opp_groups),
                independent_evidence_groups=len(groups),
                directional_state=dir_state,
                confidence=confidence,
                is_primary=is_primary,
                target_relevance=relevance,
            )
            target_summaries.append(summary)

        # 4. Drug-level synthesis
        conflict_detected = bool(supp_targets and opp_targets)
        strong_conflict = conflict_detected and (
            (total_supp_weight >= 0.50 and total_opp_weight >= 0.50)
            or (abs(total_supp_weight - total_opp_weight) < 1e-4 and total_supp_weight > 0.0)
        )

        effective_count = len(supp_targets) + len(opp_targets)

        if strong_conflict:
            synthesis_state = "MIXED"
            rationale = (
                f"Multi-target conflict detected: Supporting targets ({', '.join(supp_targets)}, weight={total_supp_weight:.2f}) "
                f"conflict with opposing targets ({', '.join(opp_targets)}, weight={total_opp_weight:.2f}). "
                "Both directions have substantial grounded evidence."
            )
        elif total_supp_weight > total_opp_weight and total_supp_weight >= 0.25:
            synthesis_state = "SUPPORTS"
            rationale = (
                f"Multi-target alignment SUPPORTS hypothesis: Key target(s) ({', '.join(supp_targets)}) "
                f"exhibit concordant directional action (net weight {total_supp_weight:.2f} vs {total_opp_weight:.2f})."
            )
        elif total_opp_weight > total_supp_weight and total_opp_weight >= 0.25:
            synthesis_state = "OPPOSES"
            rationale = (
                f"Multi-target alignment OPPOSES hypothesis: Target(s) ({', '.join(opp_targets)}) "
                f"exhibit discordant directional action (net weight {total_opp_weight:.2f} vs {total_supp_weight:.2f})."
            )
        else:
            synthesis_state = "INSUFFICIENT"
            rationale = "Insufficient directional evidence across evaluated targets to establish robust drug-level synthesis."

        return MultiTargetSynthesis(
            target_summaries=target_summaries,
            supporting_targets=supp_targets,
            opposing_targets=opp_targets,
            unresolved_targets=unres_targets,
            supporting_weight=total_supp_weight,
            opposing_weight=total_opp_weight,
            unresolved_weight=total_unres_weight,
            conflict_detected=conflict_detected,
            strong_conflict=strong_conflict,
            synthesis_state=synthesis_state,
            effective_target_count=effective_count,
            rationale=rationale,
        )
