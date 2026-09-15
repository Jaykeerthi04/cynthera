"""Therapeutic Alignment Engine — Phase 4D.

Evaluates directional compatibility between a drug's molecular action on its target(s)
and the biological direction-of-effect / clinical requirements associated with that target and disease.

Core Principles:
1. Target-State Model: Genetic direction (LoF/GoF + protect/risk) and pharmacological data
   are translated into an explicit desired therapeutic target action (INHIBITION / ACTIVATION / UNKNOWN).
2. Evidence Independence: Raw database rows are clustered by deterministic independence groups
   (PMID/DOI/trial). Multiple collinear rows count as 1 independent vote.
3. Multi-Target Protection: Primary targets and secondary targets are evaluated independently
   before synthesizing an overall alignment.
4. Auditable Explanations: Every alignment verdict is supported by structured trace evidence.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.value_objects.therapeutic_direction_evidence import (
    EvidenceFamily,
    TherapeuticAction,
    TherapeuticAlignment,
    TherapeuticDirectionEvidence,
    DirectionalEvidenceGroup,
    TargetDiseaseDirection,
    TargetTherapeuticAlignment,
    TherapeuticAlignmentReport,
)
from backend.reasoning.directional.chembl_polarity import CHEMBL_POLARITY_MAP
from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver
from backend.core.domain.evidence_weight_policy import EvidenceWeightPolicy, WeightMode

logger = logging.getLogger(__name__)


def derive_desired_target_action(
    target_direction: str | None = None,
    trait_direction: str | None = None,
    required_action: str | None = None,
) -> TherapeuticAction:
    """Translate genetic direction-of-effect or curated requirements into desired therapeutic target action.

    Rules:
    - Explicit required action (e.g. from DATTs):
      - INHIBITION -> TherapeuticAction.INHIBITION
      - ACTIVATION -> TherapeuticAction.ACTIVATION
      - TARGETING  -> TherapeuticAction.TARGETING
    - Direction of Effect pair (Open Targets LoF/GoF + protect/risk):
      - LoF + protect -> INHIBITION (reducing target function protects -> target inhibition desired)
      - LoF + risk    -> ACTIVATION (reducing target function increases risk -> target activation desired)
      - GoF + protect -> ACTIVATION (increasing target function protects -> target activation desired)
      - GoF + risk    -> INHIBITION (increasing target function increases risk -> target inhibition desired)
    - All ambiguous, uncharacterized, or UNKNOWN inputs -> TherapeuticAction.UNKNOWN.

    Args:
        target_direction: Perturbation on target (e.g. 'LoF', 'GoF', 'INHIBITED', 'ACTIVATED').
        trait_direction: Effect on disease trait (e.g. 'protect', 'risk', 'IMPROVED', 'WORSENED').
        required_action: Explicit therapeutic action string if provided.

    Returns:
        TherapeuticAction enum.
    """
    if required_action:
        norm_req = str(required_action).strip().upper()
        if "INHIBIT" in norm_req or "ANTAGON" in norm_req or "BLOCK" in norm_req:
            return TherapeuticAction.INHIBITION
        if "ACTIVAT" in norm_req or "AGONI" in norm_req or "OPEN" in norm_req:
            return TherapeuticAction.ACTIVATION
        if "TARGET" in norm_req:
            return TherapeuticAction.TARGETING

    if not target_direction or not trait_direction:
        return TherapeuticAction.UNKNOWN

    td = str(target_direction).strip().lower()
    tr = str(trait_direction).strip().lower()

    if td in ("unknown", "none", "") or tr in ("unknown", "none", ""):
        return TherapeuticAction.UNKNOWN

    is_lof = any(k in td for k in ["lof", "loss", "inhibit", "downregulat", "reduc", "suppress"])
    is_gof = any(k in td for k in ["gof", "gain", "activat", "upregulat", "increas", "stimulat", "overexpress"])

    is_protect = any(k in tr for k in ["protect", "improv", "benefit", "alleviat", "decreased risk", "decreased_risk"])
    is_risk = any(k in tr for k in ["risk", "worsen", "harm", "pathogen", "increased risk", "increased_risk"])

    if is_lof and is_protect:
        return TherapeuticAction.INHIBITION
    if is_lof and is_risk:
        return TherapeuticAction.ACTIVATION
    if is_gof and is_protect:
        return TherapeuticAction.ACTIVATION
    if is_gof and is_risk:
        return TherapeuticAction.INHIBITION

    return TherapeuticAction.UNKNOWN


def normalize_drug_action(target_or_mech: Any) -> TherapeuticAction:
    """Normalize a drug's target mechanism from ChEMBL into TherapeuticAction.

    Args:
        target_or_mech: Target domain object or raw mechanism string.

    Returns:
        TherapeuticAction.INHIBITION, .ACTIVATION, or .UNKNOWN.
    """
    if target_or_mech is None:
        return TherapeuticAction.UNKNOWN

    if isinstance(target_or_mech, Target):
        mech = target_or_mech.mechanism
    else:
        mech = str(target_or_mech)

    if not mech:
        return TherapeuticAction.UNKNOWN

    norm_mech = mech.strip().upper()
    polarity = CHEMBL_POLARITY_MAP.get(norm_mech, MolecularPolarity.UNKNOWN)

    if polarity == MolecularPolarity.NEGATIVE:
        return TherapeuticAction.INHIBITION
    if polarity == MolecularPolarity.POSITIVE:
        return TherapeuticAction.ACTIVATION

    # Fallback to keyword matching for compound mechanism descriptions
    lower_mech = norm_mech.lower()
    if any(k in lower_mech for k in ["inhibitor", "antagonist", "blocker", "negative allosteric", "inverse agonist", "inhibits"]):
        return TherapeuticAction.INHIBITION
    if any(k in lower_mech for k in ["agonist", "activator", "opener", "positive allosteric", "partial agonist", "full agonist", "activates"]):
        return TherapeuticAction.ACTIVATION

    return TherapeuticAction.UNKNOWN


def compare_drug_action_to_target_direction(
    drug_action: TherapeuticAction,
    desired_target_action: TherapeuticAction,
) -> TherapeuticAlignment:
    """Deterministic comparator between drug action and desired target therapeutic action.

    Args:
        drug_action: Drug's action on target (INHIBITION / ACTIVATION / UNKNOWN).
        desired_target_action: Desired target perturbation for disease (INHIBITION / ACTIVATION / UNKNOWN).

    Returns:
        TherapeuticAlignment.SUPPORTS, .OPPOSES, or .INSUFFICIENT.
    """
    if drug_action == TherapeuticAction.UNKNOWN or desired_target_action == TherapeuticAction.UNKNOWN:
        return TherapeuticAlignment.INSUFFICIENT

    if desired_target_action == TherapeuticAction.TARGETING:
        # Generic targeting without specified polarity is insufficient for polarity alignment
        return TherapeuticAlignment.INSUFFICIENT

    if drug_action == desired_target_action:
        return TherapeuticAlignment.SUPPORTS

    return TherapeuticAlignment.OPPOSES


def group_evidence_by_independence(
    records: list[TherapeuticDirectionEvidence],
) -> list[DirectionalEvidenceGroup]:
    """Group directional evidence records by their deterministic independence group.

    Prevents multiple database rows citing the same clinical trial, GWAS, or paper
    from multiplying votes.

    Args:
        records: List of TherapeuticDirectionEvidence records for a target.

    Returns:
        List of DirectionalEvidenceGroup objects representing independent evidence clusters.
    """
    groups_dict: dict[str, list[TherapeuticDirectionEvidence]] = {}

    for rec in records:
        group_key = rec.independence_group or f"{rec.evidence_family.value}:{rec.source.lower()}:unlinked"
        if group_key not in groups_dict:
            groups_dict[group_key] = []
        groups_dict[group_key].append(rec)

    out_groups: list[DirectionalEvidenceGroup] = []

    for group_id, member_recs in groups_dict.items():
        sample = member_recs[0]
        target_id = sample.target_canonical_id
        disease_id = sample.disease_canonical_id
        ev_family = sample.evidence_family

        # Determine consensus desired action among members
        actions = [
            derive_desired_target_action(
                r.target_direction, r.trait_direction, r.required_action
            )
            for r in member_recs
        ]
        valid_actions = [a for a in actions if a != TherapeuticAction.UNKNOWN]

        if not valid_actions:
            group_action = TherapeuticAction.UNKNOWN
        else:
            # Check if all valid actions agree
            if all(a == valid_actions[0] for a in valid_actions):
                group_action = valid_actions[0]
            else:
                group_action = TherapeuticAction.UNKNOWN

        # Collect unique references and sources
        refs: set[str] = set()
        sources: set[str] = set()
        for r in member_recs:
            if r.underlying_reference:
                refs.add(r.underlying_reference)
            sources.add(r.source)

        # Retain highest causal grounding tier
        grounding_priority = {
            CausalGrounding.DIRECT: 4,
            CausalGrounding.CURATED: 3,
            CausalGrounding.INFERRED: 2,
            CausalGrounding.STRUCTURAL: 1,
            CausalGrounding.NONE: 0,
        }
        best_grounding = max(
            (r.causal_grounding for r in member_recs),
            key=lambda g: grounding_priority.get(g, 0),
            default=CausalGrounding.CURATED,
        )

        ref_str = f" ({', '.join(sorted(refs))})" if refs else ""
        summary = f"{ev_family.value} evidence from {', '.join(sorted(sources))}{ref_str} -> desired {group_action.value}"

        out_groups.append(
            DirectionalEvidenceGroup(
                group_id=group_id,
                target_id=target_id,
                disease_id=disease_id,
                desired_action=group_action,
                evidence_family=ev_family,
                causal_grounding=best_grounding,
                references=sorted(list(refs)),
                member_record_count=len(member_recs),
                sources=sorted(list(sources)),
                confidence=sample.confidence,
                summary=summary,
            )
        )

    return sorted(out_groups, key=lambda g: g.group_id)


class TherapeuticAlignmentEngine:
    """Core reasoning engine for therapeutic direction alignment."""

    def align_target(
        self,
        target_id: str,
        drug_action: TherapeuticAction,
        evidence_records: list[TherapeuticDirectionEvidence],
        target_name: str | None = None,
        is_primary: bool = True,
        is_drugmechdb_validated: bool = False,
    ) -> TargetTherapeuticAlignment:
        """Evaluate therapeutic alignment for an individual target.

        Args:
            target_id: Canonical target identifier (e.g. 'SLC12A1').
            drug_action: Drug's action on target (INHIBITION / ACTIVATION / UNKNOWN).
            evidence_records: Directional evidence records matching target_id.
            target_name: Human-readable protein/target name.
            is_primary: True if primary binding target of the drug.
            is_drugmechdb_validated: True if DrugMechDB curated path validates this target.

        Returns:
            TargetTherapeuticAlignment assessment.
        """
        # Cluster evidence into independent groups
        groups = group_evidence_by_independence(evidence_records)

        supporting_groups: list[str] = []
        opposing_groups: list[str] = []

        for g in groups:
            if g.desired_action == TherapeuticAction.UNKNOWN:
                continue
            if drug_action == TherapeuticAction.UNKNOWN:
                continue

            if g.desired_action == drug_action:
                supporting_groups.append(g.group_id)
            else:
                opposing_groups.append(g.group_id)

        # Primary desired action consensus across independent groups
        desired_actions = [g.desired_action for g in groups if g.desired_action != TherapeuticAction.UNKNOWN]
        if desired_actions:
            if all(a == desired_actions[0] for a in desired_actions):
                consensus_desired_action = desired_actions[0]
            else:
                consensus_desired_action = TherapeuticAction.UNKNOWN
        else:
            consensus_desired_action = TherapeuticAction.UNKNOWN

        # Determine alignment
        if drug_action == TherapeuticAction.UNKNOWN:
            alignment = TherapeuticAlignment.INSUFFICIENT
            explanation = (
                f"Drug action on {target_id} is uncharacterized or ambiguous (MODULATOR/UNKNOWN). "
                f"Cannot establish therapeutic alignment despite {len(groups)} independent disease evidence groups."
            )
        elif not groups:
            alignment = TherapeuticAlignment.INSUFFICIENT
            explanation = f"No directional disease-target evidence found for {target_id}."
        elif len(supporting_groups) > 0 and len(opposing_groups) == 0:
            alignment = TherapeuticAlignment.SUPPORTS
            explanation = (
                f"Drug action ({drug_action.value}) aligns with {len(supporting_groups)} independent disease evidence groups "
                f"supporting target {consensus_desired_action.value}."
            )
        elif len(opposing_groups) > 0 and len(supporting_groups) == 0:
            alignment = TherapeuticAlignment.OPPOSES
            explanation = (
                f"Drug action ({drug_action.value}) opposes {len(opposing_groups)} independent disease evidence groups "
                f"requiring target {consensus_desired_action.value}."
            )
        elif len(supporting_groups) > 0 and len(opposing_groups) > 0:
            alignment = TherapeuticAlignment.INSUFFICIENT
            explanation = (
                f"Contradictory directional evidence for {target_id}: {len(supporting_groups)} supporting vs "
                f"{len(opposing_groups)} opposing independent groups."
            )
        else:
            alignment = TherapeuticAlignment.INSUFFICIENT
            explanation = (
                f"Uncharacterized disease directions across {len(groups)} independent evidence groups for {target_id}."
            )

        if is_drugmechdb_validated:
            explanation += " Curated mechanistic path validated in DrugMechDB."

        total_directional = len(supporting_groups) + len(opposing_groups)
        confidence = round(len(supporting_groups) / total_directional, 2) if total_directional > 0 else 0.0

        return TargetTherapeuticAlignment(
            target_id=target_id,
            target_name=target_name,
            is_primary=is_primary,
            drug_action=drug_action,
            desired_target_action=consensus_desired_action,
            alignment=alignment,
            evidence_groups=groups,
            supporting_groups=supporting_groups,
            opposing_groups=opposing_groups,
            drugmechdb_validated=is_drugmechdb_validated,
            confidence=confidence,
            explanation=explanation,
        )

    def align_package(
        self,
        package: RetrievalPackage,
        resolver: BiologicalIdentifierResolver | None = None,
        policy: EvidenceWeightPolicy | None = None,
    ) -> TherapeuticAlignmentReport:
        """Run complete Phase 4D/5.7 Therapeutic Alignment on a RetrievalPackage.

        Args:
            package: Sealed RetrievalPackage.
            resolver: BiologicalIdentifierResolver.
            policy: Optional EvidenceWeightPolicy. Defaults to EQUAL_VOTE (production default).
                    GROUNDING_WEIGHTED mode can be selected for evaluation or dev analysis.

        Returns:
            TherapeuticAlignmentReport domain model.
        """
        if resolver is None:
            resolver = BiologicalIdentifierResolver(
                proteins=package.proteins,
                genes=package.genes,
                mappings=package.identifier_mappings,
            )

        # 1. Map drug target actions from package.targets
        drug_target_actions: dict[str, tuple[TherapeuticAction, Target, str | None]] = {}
        for target in package.targets:
            uni = (target.protein_uniprot or "").strip().upper()
            res = resolver.resolve(uni, source="ChEMBL")
            sym = res.canonical_symbol or res.canonical_identifier or uni
            action = normalize_drug_action(target.mechanism)
            if sym not in drug_target_actions:
                drug_target_actions[sym] = (action, target, uni)

        # 2. Check DrugMechDB curated path availability
        dm_validated = any(dm.is_curated_path_available for dm in package.drugmechdb_evidence)

        # 3. Group directional evidence records by canonical target
        records_by_target: dict[str, list[TherapeuticDirectionEvidence]] = {}
        for rec in package.therapeutic_direction_evidence:
            tid = rec.target_canonical_id
            if tid not in records_by_target:
                records_by_target[tid] = []
            records_by_target[tid].append(rec)

        # 4. Identify all targets to evaluate
        all_target_ids = sorted(list(set(list(drug_target_actions.keys()) + list(records_by_target.keys()))))

        target_alignments: list[TargetTherapeuticAlignment] = []
        primary_alignments: list[TargetTherapeuticAlignment] = []
        secondary_alignments: list[TargetTherapeuticAlignment] = []

        is_weighted_mode = policy is not None and policy.mode == WeightMode.GROUNDING_WEIGHTED

        for tid in all_target_ids:
            is_primary = tid in drug_target_actions
            drug_action, target_obj, uni = drug_target_actions.get(
                tid, (TherapeuticAction.UNKNOWN, None, None)
            )

            recs = records_by_target.get(tid, [])

            # Target human name from package.proteins
            tname = None
            for p in package.proteins:
                if (p.gene_symbol and p.gene_symbol.upper() == tid) or (p.uniprot_accession and p.uniprot_accession.upper() == uni):
                    tname = p.name
                    break

            if is_weighted_mode and policy is not None:
                alignment = self.weighted_align_target(
                    target_id=tid,
                    drug_action=drug_action,
                    evidence_records=recs,
                    weight_config=policy.to_weight_config(),
                    target_name=tname,
                    is_primary=is_primary,
                    is_drugmechdb_validated=dm_validated,
                )
            else:
                alignment = self.align_target(
                    target_id=tid,
                    drug_action=drug_action,
                    evidence_records=recs,
                    target_name=tname,
                    is_primary=is_primary,
                    is_drugmechdb_validated=dm_validated,
                )

            target_alignments.append(alignment)
            if is_primary:
                primary_alignments.append(alignment)
            else:
                secondary_alignments.append(alignment)

        # 5. Determine Overall Alignment from primary targets
        if not primary_alignments:
            overall_alignment = TherapeuticAlignment.INSUFFICIENT
            overall_explanation = "No primary drug targets mapped to directional evidence."
        else:
            primary_statuses = [a.alignment for a in primary_alignments if a.alignment != TherapeuticAlignment.INSUFFICIENT]
            if not primary_statuses:
                overall_alignment = TherapeuticAlignment.INSUFFICIENT
                overall_explanation = (
                    f"Directional evidence for primary target(s) ({', '.join(a.target_id for a in primary_alignments)}) "
                    f"is insufficient or uncharacterized."
                )
            elif all(s == TherapeuticAlignment.SUPPORTS for s in primary_statuses):
                overall_alignment = TherapeuticAlignment.SUPPORTS
                supp_targets = [a.target_id for a in primary_alignments if a.alignment == TherapeuticAlignment.SUPPORTS]
                overall_explanation = (
                    f"Therapeutic alignment SUPPORTS hypothesis: Drug action on primary target(s) ({', '.join(supp_targets)}) "
                    f"is directionally concordant with disease-target therapeutic requirements."
                )
            elif all(s == TherapeuticAlignment.OPPOSES for s in primary_statuses):
                overall_alignment = TherapeuticAlignment.OPPOSES
                opp_targets = [a.target_id for a in primary_alignments if a.alignment == TherapeuticAlignment.OPPOSES]
                overall_explanation = (
                    f"Therapeutic alignment OPPOSES hypothesis: Drug action on primary target(s) ({', '.join(opp_targets)}) "
                    f"is directionally discordant with disease-target therapeutic requirements."
                )
            else:
                overall_alignment = TherapeuticAlignment.MIXED
                overall_explanation = (
                    "Mixed therapeutic alignment: Primary targets exhibit discordant directional support."
                )

        if dm_validated:
            overall_explanation += " Mechanistic chain independently validated in DrugMechDB."

        total_groups = sum(len(a.evidence_groups) for a in target_alignments)
        total_supp = sum(len(a.supporting_groups) for a in target_alignments)
        total_opp = sum(len(a.opposing_groups) for a in target_alignments)

        return TherapeuticAlignmentReport(
            drug_name=package.drug.name,
            disease_name=package.disease.name,
            overall_alignment=overall_alignment,
            target_alignments=target_alignments,
            primary_target_alignments=primary_alignments,
            secondary_target_alignments=secondary_alignments,
            total_independent_groups=total_groups,
            supporting_groups_count=total_supp,
            opposing_groups_count=total_opp,
            drugmechdb_validated=dm_validated,
            explanation=overall_explanation,
        )

    # ── Evaluation-Only: Weighted Alignment Comparator ────────────────────────
    # These methods are NOT used in the production pipeline.
    # They exist solely for Phase 4E evaluation comparison between equal-vote
    # and weighted evidence scoring. The production alignment path remains
    # align_target() / align_package() with equal independence-grouped votes.

    def weighted_align_target(
        self,
        target_id: str,
        drug_action: TherapeuticAction,
        evidence_records: list[TherapeuticDirectionEvidence],
        weight_config: "WeightConfig",
        target_name: str | None = None,
        is_primary: bool = True,
        is_drugmechdb_validated: bool = False,
    ) -> TargetTherapeuticAlignment:
        """EVALUATION-ONLY: Weighted therapeutic alignment for an individual target.

        Applies causal-grounding-tier weights from WeightConfig to independence-grouped
        evidence. Decision is based on cumulative weighted support vs weighted opposition.

        Decision rules:
            support_weight > 0 AND opposition_weight == 0 → SUPPORTS
            opposition_weight > 0 AND support_weight == 0 → OPPOSES
            Both > 0 AND support_weight > opposition_weight → SUPPORTS
              (only if neither weight exceeds min_effective_weight individually for opposition)
            Both > 0 AND opposition_weight > support_weight → OPPOSES
              (only if neither weight exceeds min_effective_weight individually for support)
            Both > min_effective_weight → INSUFFICIENT (strong conflict, weight-neutral)
            Total effective weight < min_effective_weight → INSUFFICIENT (too little evidence)
            drug_action == UNKNOWN → INSUFFICIENT (always)

        NOTE: This method does NOT replace or affect align_target().
        Production code must never call this method.

        Args:
            target_id: Canonical target identifier.
            drug_action: Drug's action on target.
            evidence_records: Directional evidence records matching target_id.
            weight_config: WeightConfig specifying tier weights.
            target_name: Human-readable protein/target name.
            is_primary: True if primary binding target.
            is_drugmechdb_validated: True if DrugMechDB path validates this target.

        Returns:
            TargetTherapeuticAlignment with weighted concordance in confidence field.
        """
        # Import here to avoid circular imports and keep evaluation concerns separate
        from backend.evaluation.evidence_weights import WeightConfig  # noqa: F401

        # Cluster evidence into independent groups (same grouping as production)
        groups = group_evidence_by_independence(evidence_records)

        supporting_groups: list[str] = []
        opposing_groups: list[str] = []
        support_weight: float = 0.0
        opposition_weight: float = 0.0

        for g in groups:
            if g.desired_action == TherapeuticAction.UNKNOWN:
                continue
            if drug_action == TherapeuticAction.UNKNOWN:
                continue

            grp_weight = weight_config.weight_for(g.causal_grounding)
            if grp_weight == 0.0:
                continue  # Structural / None — skip, no directional contribution

            if g.desired_action == drug_action:
                supporting_groups.append(g.group_id)
                support_weight += grp_weight
            else:
                opposing_groups.append(g.group_id)
                opposition_weight += grp_weight

        # Desired action consensus (same as production)
        desired_actions = [g.desired_action for g in groups if g.desired_action != TherapeuticAction.UNKNOWN]
        if desired_actions and all(a == desired_actions[0] for a in desired_actions):
            consensus_desired_action = desired_actions[0]
        else:
            consensus_desired_action = TherapeuticAction.UNKNOWN

        min_w = weight_config.min_effective_weight

        if drug_action == TherapeuticAction.UNKNOWN:
            alignment = TherapeuticAlignment.INSUFFICIENT
            explanation = (
                f"[WEIGHTED] Drug action on {target_id} is uncharacterized. "
                f"Cannot establish weighted alignment."
            )
        elif not groups:
            alignment = TherapeuticAlignment.INSUFFICIENT
            explanation = f"[WEIGHTED] No directional disease-target evidence found for {target_id}."
        elif (support_weight + opposition_weight) < min_w:
            # Total effective weight too low — not enough grounded evidence
            alignment = TherapeuticAlignment.INSUFFICIENT
            explanation = (
                f"[WEIGHTED] Insufficient grounded evidence for {target_id}: "
                f"total effective weight {support_weight + opposition_weight:.2f} < {min_w:.2f}."
            )
        elif support_weight > 0 and opposition_weight == 0:
            alignment = TherapeuticAlignment.SUPPORTS
            explanation = (
                f"[WEIGHTED] Drug action ({drug_action.value}) supported by weighted evidence "
                f"(support={support_weight:.2f}, opposition={opposition_weight:.2f}) for {target_id}."
            )
        elif opposition_weight > 0 and support_weight == 0:
            alignment = TherapeuticAlignment.OPPOSES
            explanation = (
                f"[WEIGHTED] Drug action ({drug_action.value}) opposed by weighted evidence "
                f"(support={support_weight:.2f}, opposition={opposition_weight:.2f}) for {target_id}."
            )
        elif support_weight > 0 and opposition_weight > 0:
            # Both sides have weight — strong conflict requires substantial curated/direct
            # evidence on both sides (>= curated weight), or equal weights. A weak inferred group
            # (w=0.5) must not cancel a direct clinical/curated group (w=1.0).
            has_strong_conflict = (
                support_weight >= weight_config.curated and opposition_weight >= weight_config.curated
            ) or (support_weight == opposition_weight)

            if has_strong_conflict:
                alignment = TherapeuticAlignment.INSUFFICIENT
                explanation = (
                    f"[WEIGHTED] Strong directional conflict for {target_id}: "
                    f"support={support_weight:.2f}, opposition={opposition_weight:.2f}. "
                    f"Both sides possess substantial grounded evidence."
                )
            elif support_weight > opposition_weight:
                alignment = TherapeuticAlignment.SUPPORTS
                explanation = (
                    f"[WEIGHTED] Drug action ({drug_action.value}) net-supported for {target_id}: "
                    f"support={support_weight:.2f} > opposition={opposition_weight:.2f}."
                )
            else:
                alignment = TherapeuticAlignment.OPPOSES
                explanation = (
                    f"[WEIGHTED] Drug action ({drug_action.value}) net-opposed for {target_id}: "
                    f"opposition={opposition_weight:.2f} > support={support_weight:.2f}."
                )
        else:
            alignment = TherapeuticAlignment.INSUFFICIENT
            explanation = (
                f"[WEIGHTED] Uncharacterized disease directions across {len(groups)} evidence groups for {target_id}."
            )

        if is_drugmechdb_validated:
            explanation += " Curated mechanistic path validated in DrugMechDB."

        total_w = support_weight + opposition_weight
        weighted_concordance = round(support_weight / total_w, 4) if total_w > 0 else 0.0

        return TargetTherapeuticAlignment(
            target_id=target_id,
            target_name=target_name,
            is_primary=is_primary,
            drug_action=drug_action,
            desired_target_action=consensus_desired_action,
            alignment=alignment,
            evidence_groups=groups,
            supporting_groups=supporting_groups,
            opposing_groups=opposing_groups,
            drugmechdb_validated=is_drugmechdb_validated,
            confidence=weighted_concordance,  # weighted concordance stored here
            explanation=explanation,
        )

    def weighted_align_package(
        self,
        package: RetrievalPackage,
        weight_config: "WeightConfig",
        resolver: BiologicalIdentifierResolver | None = None,
    ) -> TherapeuticAlignmentReport:
        """EVALUATION-ONLY: Weighted alignment across all targets in a RetrievalPackage.

        Mirrors align_package() structure but delegates to weighted_align_target().
        Production code must never call this method.

        Args:
            package: Sealed RetrievalPackage.
            weight_config: WeightConfig specifying tier weights.
            resolver: BiologicalIdentifierResolver.

        Returns:
            TherapeuticAlignmentReport with weighted per-target assessments.
        """
        from backend.evaluation.evidence_weights import WeightConfig  # noqa: F401

        if resolver is None:
            resolver = BiologicalIdentifierResolver(
                proteins=package.proteins,
                genes=package.genes,
                mappings=package.identifier_mappings,
            )

        drug_target_actions: dict[str, tuple[TherapeuticAction, Target, str | None]] = {}
        for target in package.targets:
            uni = (target.protein_uniprot or "").strip().upper()
            res = resolver.resolve(uni, source="ChEMBL")
            sym = res.canonical_symbol or res.canonical_identifier or uni
            action = normalize_drug_action(target.mechanism)
            if sym not in drug_target_actions:
                drug_target_actions[sym] = (action, target, uni)

        dm_validated = any(dm.is_curated_path_available for dm in package.drugmechdb_evidence)

        records_by_target: dict[str, list[TherapeuticDirectionEvidence]] = {}
        for rec in package.therapeutic_direction_evidence:
            tid = rec.target_canonical_id
            if tid not in records_by_target:
                records_by_target[tid] = []
            records_by_target[tid].append(rec)

        all_target_ids = sorted(list(set(list(drug_target_actions.keys()) + list(records_by_target.keys()))))
        target_alignments: list[TargetTherapeuticAlignment] = []
        primary_alignments: list[TargetTherapeuticAlignment] = []
        secondary_alignments: list[TargetTherapeuticAlignment] = []

        for tid in all_target_ids:
            is_primary = tid in drug_target_actions
            drug_action, target_obj, uni = drug_target_actions.get(
                tid, (TherapeuticAction.UNKNOWN, None, None)
            )
            recs = records_by_target.get(tid, [])
            tname = None
            for p in package.proteins:
                if (p.gene_symbol and p.gene_symbol.upper() == tid) or (
                    p.uniprot_accession and p.uniprot_accession.upper() == uni
                ):
                    tname = p.name
                    break

            alignment = self.weighted_align_target(
                target_id=tid,
                drug_action=drug_action,
                evidence_records=recs,
                weight_config=weight_config,
                target_name=tname,
                is_primary=is_primary,
                is_drugmechdb_validated=dm_validated,
            )
            target_alignments.append(alignment)
            if is_primary:
                primary_alignments.append(alignment)
            else:
                secondary_alignments.append(alignment)

        # Overall alignment from primary targets (same logic as production)
        if not primary_alignments:
            overall_alignment = TherapeuticAlignment.INSUFFICIENT
            overall_explanation = "[WEIGHTED] No primary drug targets mapped to directional evidence."
        else:
            primary_statuses = [a.alignment for a in primary_alignments if a.alignment != TherapeuticAlignment.INSUFFICIENT]
            if not primary_statuses:
                overall_alignment = TherapeuticAlignment.INSUFFICIENT
                overall_explanation = (
                    f"[WEIGHTED] Directional evidence for primary target(s) "
                    f"({', '.join(a.target_id for a in primary_alignments)}) is insufficient."
                )
            elif all(s == TherapeuticAlignment.SUPPORTS for s in primary_statuses):
                overall_alignment = TherapeuticAlignment.SUPPORTS
                supp_targets = [a.target_id for a in primary_alignments if a.alignment == TherapeuticAlignment.SUPPORTS]
                overall_explanation = (
                    f"[WEIGHTED] Alignment SUPPORTS: primary target(s) ({', '.join(supp_targets)}) "
                    f"show weighted directional concordance."
                )
            elif all(s == TherapeuticAlignment.OPPOSES for s in primary_statuses):
                overall_alignment = TherapeuticAlignment.OPPOSES
                opp_targets = [a.target_id for a in primary_alignments if a.alignment == TherapeuticAlignment.OPPOSES]
                overall_explanation = (
                    f"[WEIGHTED] Alignment OPPOSES: primary target(s) ({', '.join(opp_targets)}) "
                    f"show weighted directional discordance."
                )
            else:
                overall_alignment = TherapeuticAlignment.MIXED
                overall_explanation = (
                    "[WEIGHTED] Mixed alignment: primary targets exhibit discordant weighted directional support."
                )

        if dm_validated:
            overall_explanation += " Mechanistic chain independently validated in DrugMechDB."

        total_groups = sum(len(a.evidence_groups) for a in target_alignments)
        total_supp = sum(len(a.supporting_groups) for a in target_alignments)
        total_opp = sum(len(a.opposing_groups) for a in target_alignments)

        return TherapeuticAlignmentReport(
            drug_name=package.drug.name,
            disease_name=package.disease.name,
            overall_alignment=overall_alignment,
            target_alignments=target_alignments,
            primary_target_alignments=primary_alignments,
            secondary_target_alignments=secondary_alignments,
            total_independent_groups=total_groups,
            supporting_groups_count=total_supp,
            opposing_groups_count=total_opp,
            drugmechdb_validated=dm_validated,
            explanation=overall_explanation,
        )
