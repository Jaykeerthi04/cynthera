"""EvaluationRunner — configurable evidence-source evaluation for benchmark ablation studies.

Applies EvaluationConfig to a RetrievalPackage, filtering evidence sources BEFORE
DirectionalEvidenceBuilder.build_all() is called, then running alignment.

This is NOT a replacement for the production pipeline. It is an evaluation-only
component used by the benchmark framework to measure the contribution of each
evidence source to the final alignment decision.

Evidence filtering scope:
    Filtering occurs at the RetrievalPackage evidence list level, BEFORE
    DirectionalEvidenceBuilder.build_all() processes the records. This means
    the filtered package contains genuinely different evidence, and the
    resulting TherapeuticDirectionEvidence records reflect the ablated state.

    This is equivalent to disabling the data source for DOWNSTREAM EVIDENCE
    CONTRIBUTION purposes only. It does not test retrieval behavior, connector
    error handling, caching behavior, or network latency.

Independence grouping ablation:
    When use_independence_grouping=False, raw evidence records are converted
    directly to one-vote-per-row groups (bypassing group_evidence_by_independence).
    This simulates what would happen with naive row counting — typically inflating
    multi-row evidence sources and revealing over-representation effects.

Ablation verification:
    Every EvaluationRunner run produces an AblationVerification record that
    documents whether the evidence representation actually changed. A correct
    ablation is one where the intended component was removed, regardless of
    whether the final prediction changed.
"""
from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING

from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.therapeutic_direction_evidence import (
    DirectionalEvidenceGroup,
    EvidenceFamily,
    TherapeuticAction,
    TherapeuticAlignment,
    TherapeuticDirectionEvidence,
)
from backend.evaluation.benchmark_models import (
    AblationVerification,
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkClass,
    ExecutionStatus,
    WeightedBenchmarkCaseResult,
    map_alignment_to_class,
)
from backend.evaluation.evaluation_config import EvaluationConfig, EVALUATION_CONFIGS
from backend.reasoning.directional.directional_evidence_builder import DirectionalEvidenceBuilder
from backend.reasoning.directional.therapeutic_alignment import TherapeuticAlignmentEngine

if TYPE_CHECKING:
    from backend.core.domain.retrieval_package import RetrievalPackage

logger = logging.getLogger(__name__)


def _filter_package(
    package: "RetrievalPackage",
    config: EvaluationConfig,
) -> "RetrievalPackage":
    """Filter a RetrievalPackage according to EvaluationConfig source flags.

    Returns a shallow copy of the package with the appropriate evidence lists
    replaced by filtered versions. The original package is NOT modified.

    Args:
        package: The fully-retrieved RetrievalPackage from the production pipeline.
        config: EvaluationConfig controlling which sources are included.

    Returns:
        A copy of the package with filtered evidence lists.
    """
    import copy as _copy

    # Build filtered lists
    doe_evidence = list(package.opentargets_doe_evidence) if config.use_open_targets else []
    datts_evidence = list(package.datts_evidence) if config.use_datts else []
    drugmechdb_evidence = list(package.drugmechdb_evidence) if config.use_drugmechdb else []

    # For therapeutic_direction_evidence, filter based on source string
    tde = list(package.therapeutic_direction_evidence)
    if not config.use_open_targets:
        tde = [r for r in tde if r.source != "OpenTargets"]
    if not config.use_datts:
        tde = [r for r in tde if r.source != "DATTs"]
    if not config.use_drugmechdb:
        tde = [r for r in tde if r.source != "DrugMechDB"]
    if not config.use_literature_direction:
        tde = [r for r in tde if r.source != "Literature"]

    # Create a copy of the package with filtered evidence
    # We use model_copy for Pydantic models
    filtered = package.model_copy(
        update={
            "opentargets_doe_evidence": doe_evidence,
            "datts_evidence": datts_evidence,
            "drugmechdb_evidence": drugmechdb_evidence,
            "therapeutic_direction_evidence": tde,
        }
    )
    return filtered


def _raw_rows_to_groups(
    records: list[TherapeuticDirectionEvidence],
) -> list[DirectionalEvidenceGroup]:
    """Convert raw evidence rows to individual groups (no deduplication).

    Used when use_independence_grouping=False to simulate naive row counting.
    Each raw TherapeuticDirectionEvidence record becomes one vote.
    This reveals over-representation effects from multi-row evidence sources.

    The group_id is synthetic (row index based) to prevent any merging.
    """
    groups: list[DirectionalEvidenceGroup] = []
    for i, rec in enumerate(records):
        # Derive desired_action from this single record
        from backend.reasoning.directional.therapeutic_alignment import derive_desired_target_action
        action = derive_desired_target_action(
            rec.target_direction, rec.trait_direction, rec.required_action
        )
        groups.append(
            DirectionalEvidenceGroup(
                group_id=f"raw_row_{i}_{rec.source}",
                target_id=rec.target_canonical_id,
                disease_id=rec.disease_canonical_id,
                desired_action=action,
                evidence_family=rec.evidence_family,
                causal_grounding=rec.causal_grounding,
                references=[rec.underlying_reference] if rec.underlying_reference else [],
                member_record_count=1,
                sources=[rec.source],
                confidence=rec.confidence,
                summary=f"raw_row: {rec.source} -> {action.value}",
            )
        )
    return groups


class EvaluationRunner:
    """Configurable evaluation engine for benchmark ablation studies.

    Given a RetrievalPackage (already retrieved from the production pipeline),
    applies an EvaluationConfig to:
    1. Filter evidence sources (Open Targets, DATTs, DrugMechDB, Literature)
    2. Optionally rebuild TherapeuticDirectionEvidence via DirectionalEvidenceBuilder
    3. Apply either independence-grouped or raw-row voting
    4. Run equal-vote or weighted alignment

    Produces both BenchmarkCaseResult and AblationVerification per case.
    """

    def __init__(self) -> None:
        self._engine = TherapeuticAlignmentEngine()

    def run_with_config(
        self,
        case: BenchmarkCase,
        package: "RetrievalPackage",
        config: EvaluationConfig,
        full_result: BenchmarkCaseResult | None = None,
    ) -> tuple[BenchmarkCaseResult, AblationVerification]:
        """Evaluate a benchmark case under a specific EvaluationConfig.

        Args:
            case: Benchmark case metadata.
            package: RetrievalPackage from the FULL production run for this case.
            config: EvaluationConfig controlling which sources/features are active.
            full_result: Optional full-run BenchmarkCaseResult for verification comparison.

        Returns:
            Tuple of (BenchmarkCaseResult, AblationVerification).
        """
        try:
            # Step 1: Filter the package based on config
            filtered_pkg = _filter_package(package, config)

            # Step 2: Rebuild TherapeuticDirectionEvidence from filtered package
            # This is where the ablation actually takes effect — the evidence builder
            # only sees what was NOT filtered out.
            builder = DirectionalEvidenceBuilder()
            filtered_tde = builder.build_all(filtered_pkg)

            # Track evidence counts for verification
            full_tde_count = len(package.therapeutic_direction_evidence)
            ablated_tde_count = len(filtered_tde)
            full_ig_count = len(set(r.independence_group for r in package.therapeutic_direction_evidence if r.independence_group))
            ablated_ig_count = len(set(r.independence_group for r in filtered_tde if r.independence_group))

            # Step 3: Determine component presence for verification
            component_in_full = self._has_component(package, config)
            component_in_ablated = self._has_component(filtered_pkg, config)

            # Rebuild the filtered package with updated TDE
            final_pkg = filtered_pkg.model_copy(
                update={"therapeutic_direction_evidence": filtered_tde}
            )

            # Step 4: Run alignment (with or without independence grouping)
            if config.use_independence_grouping:
                if config.use_evidence_weighting:
                    # Weighted alignment (evaluation-only comparator)
                    from backend.evaluation.evidence_weights import WEIGHT_CONFIGS
                    wc = WEIGHT_CONFIGS.get(config.weight_config_name, WEIGHT_CONFIGS["DEFAULT_HEURISTIC"])
                    report = self._engine.weighted_align_package(final_pkg, weight_config=wc)
                else:
                    # Standard production-equivalent alignment
                    report = self._engine.align_package(final_pkg)
            else:
                # Raw-row voting (no independence grouping)
                report = self._run_raw_row_alignment(final_pkg)

            # Step 5: Extract alignment result
            ta_dict = report.model_dump(mode="json")
            pred_al = ta_dict.get("overall_alignment", "INSUFFICIENT")
            if hasattr(pred_al, "value"):
                pred_al = pred_al.value
            pred_class = map_alignment_to_class(str(pred_al))

            target_aligns = ta_dict.get("target_alignments", [])
            primary_targets = [t for t in target_aligns if t.get("is_primary")]
            primary_target_id = (
                primary_targets[0].get("target_id") if primary_targets
                else (target_aligns[0].get("target_id") if target_aligns else None)
            )

            fam_counts: dict[str, int] = {}
            for t in target_aligns:
                for eg in t.get("evidence_groups", []):
                    fam = str(eg.get("evidence_family", "UNKNOWN"))
                    fam_counts[fam] = fam_counts.get(fam, 0) + 1

            supp_cnt = ta_dict.get("supporting_groups_count", 0)
            opp_cnt = ta_dict.get("opposing_groups_count", 0)
            tot = supp_cnt + opp_cnt
            concordance = round(supp_cnt / tot, 4) if tot > 0 else 0.0

            result = BenchmarkCaseResult(
                case=case,
                predicted_alignment=str(pred_al),
                predicted_class=pred_class,
                is_correct=(pred_class == case.expected_class),
                is_resolved=(pred_class != BenchmarkClass.UNCERTAIN),
                primary_target=primary_target_id,
                target_alignments=target_aligns,
                directional_concordance=concordance,
                supporting_group_count=supp_cnt,
                opposing_group_count=opp_cnt,
                evidence_family_summary=fam_counts,
                execution_status=ExecutionStatus.SUCCESS,
                explanation=ta_dict.get("explanation", ""),
            )

        except Exception as exc:
            logger.error(
                "evaluation_runner_failed",
                extra={"case_id": case.case_id, "config": config.name, "error": str(exc)},
                exc_info=True,
            )
            result = BenchmarkCaseResult(
                case=case,
                predicted_alignment="INSUFFICIENT",
                predicted_class=BenchmarkClass.UNCERTAIN,
                is_correct=(case.expected_class == BenchmarkClass.UNCERTAIN),
                is_resolved=False,
                execution_status=ExecutionStatus.FAILED,
                error_message=str(exc),
                explanation=f"EvaluationRunner error: {exc}",
            )
            full_tde_count = 0
            ablated_tde_count = 0
            full_ig_count = 0
            ablated_ig_count = 0
            component_in_full = False
            component_in_ablated = False

        # Step 6: Build AblationVerification
        ev_rep_changed = (
            full_tde_count != ablated_tde_count
            or full_ig_count != ablated_ig_count
            or (component_in_full and not component_in_ablated)
        )

        full_pred = full_result.predicted_class.value if full_result else "N/A"
        pred_changed = (full_result is not None and result.predicted_class != full_result.predicted_class)

        if ev_rep_changed:
            verif_note = (
                f"VERIFIED: Evidence removed. "
                f"TDE: {full_tde_count}→{ablated_tde_count}, "
                f"IndepGroups: {full_ig_count}→{ablated_ig_count}. "
                f"Prediction {'changed' if pred_changed else 'unchanged'} (observation only)."
            )
            verif_passed = True
        else:
            verif_note = (
                f"INCONCLUSIVE: No evidence representation change detected. "
                f"TDE: {full_tde_count}→{ablated_tde_count}. "
                f"Component may not have been present in the original data for this case."
            )
            verif_passed = False  # Not necessarily wrong, but cannot confirm ablation took effect

        verification = AblationVerification(
            case_id=case.case_id,
            ablation_config=config.name,
            full_evidence_count=full_tde_count,
            ablated_evidence_count=ablated_tde_count,
            full_independence_group_count=full_ig_count,
            ablated_independence_group_count=ablated_ig_count,
            component_present_in_full=component_in_full,
            component_present_in_ablated=component_in_ablated,
            evidence_representation_changed=ev_rep_changed,
            prediction_changed=pred_changed,
            full_prediction=full_pred,
            ablated_prediction=result.predicted_class.value,
            verification_passed=verif_passed,
            verification_note=verif_note,
        )

        return result, verification

    def _has_component(self, package: "RetrievalPackage", config: EvaluationConfig) -> bool:
        """Check if the ablated component was actually present in the package."""
        if not config.use_open_targets and len(package.opentargets_doe_evidence) > 0:
            return True
        if not config.use_datts and len(package.datts_evidence) > 0:
            return True
        if not config.use_drugmechdb and len(package.drugmechdb_evidence) > 0:
            return True
        if not config.use_independence_grouping:
            # Independence grouping — the component is "present" if there are multi-row groups
            ig_keys = [r.independence_group for r in package.therapeutic_direction_evidence if r.independence_group]
            from collections import Counter
            counts = Counter(ig_keys)
            return any(v > 1 for v in counts.values())
        return False

    def _run_raw_row_alignment(
        self,
        package: "RetrievalPackage",
    ):
        """Run alignment using raw row voting (no independence grouping).

        Bypasses group_evidence_by_independence() — each raw TDE record
        becomes one vote. Used for NO_INDEPENDENCE_GROUPING ablation.

        Returns TherapeuticAlignmentReport-compatible object (as dict then reconstructed).
        """
        from backend.core.value_objects.therapeutic_direction_evidence import (
            TherapeuticAlignmentReport,
            TargetTherapeuticAlignment,
        )
        from backend.reasoning.directional.therapeutic_alignment import (
            normalize_drug_action,
            derive_desired_target_action,
            compare_drug_action_to_target_direction,
        )
        from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver

        resolver = BiologicalIdentifierResolver(
            proteins=package.proteins,
            genes=package.genes,
            mappings=package.identifier_mappings,
        )

        # Map drug target actions
        drug_target_actions: dict = {}
        for target in package.targets:
            uni = (target.protein_uniprot or "").strip().upper()
            res = resolver.resolve(uni, source="ChEMBL")
            sym = res.canonical_symbol or res.canonical_identifier or uni
            action = normalize_drug_action(target.mechanism)
            if sym not in drug_target_actions:
                drug_target_actions[sym] = (action, target, uni)

        dm_validated = any(dm.is_curated_path_available for dm in package.drugmechdb_evidence)

        records_by_target: dict = {}
        for rec in package.therapeutic_direction_evidence:
            tid = rec.target_canonical_id
            if tid not in records_by_target:
                records_by_target[tid] = []
            records_by_target[tid].append(rec)

        all_target_ids = sorted(list(set(list(drug_target_actions.keys()) + list(records_by_target.keys()))))
        target_alignments = []
        primary_alignments = []
        secondary_alignments = []

        for tid in all_target_ids:
            is_primary = tid in drug_target_actions
            drug_action, _, uni = drug_target_actions.get(tid, (TherapeuticAction.UNKNOWN, None, None))
            recs = records_by_target.get(tid, [])

            # Raw row voting — no deduplication
            raw_groups = _raw_rows_to_groups(recs)
            supporting_groups = []
            opposing_groups = []

            for g in raw_groups:
                if g.desired_action == TherapeuticAction.UNKNOWN or drug_action == TherapeuticAction.UNKNOWN:
                    continue
                if g.desired_action == drug_action:
                    supporting_groups.append(g.group_id)
                else:
                    opposing_groups.append(g.group_id)

            # Determine alignment using raw counts
            if drug_action == TherapeuticAction.UNKNOWN:
                alignment = TherapeuticAlignment.INSUFFICIENT
                explanation = f"[RAW_ROW] Drug action unknown for {tid}."
            elif not raw_groups:
                alignment = TherapeuticAlignment.INSUFFICIENT
                explanation = f"[RAW_ROW] No evidence for {tid}."
            elif len(supporting_groups) > 0 and len(opposing_groups) == 0:
                alignment = TherapeuticAlignment.SUPPORTS
                explanation = f"[RAW_ROW] {len(supporting_groups)} raw rows support {tid}."
            elif len(opposing_groups) > 0 and len(supporting_groups) == 0:
                alignment = TherapeuticAlignment.OPPOSES
                explanation = f"[RAW_ROW] {len(opposing_groups)} raw rows oppose {tid}."
            else:
                alignment = TherapeuticAlignment.INSUFFICIENT
                explanation = f"[RAW_ROW] Conflicting raw rows for {tid}: {len(supporting_groups)} support, {len(opposing_groups)} oppose."

            total = len(supporting_groups) + len(opposing_groups)
            conf = round(len(supporting_groups) / total, 2) if total > 0 else 0.0

            desired_actions = [g.desired_action for g in raw_groups if g.desired_action != TherapeuticAction.UNKNOWN]
            consensus = desired_actions[0] if desired_actions and all(a == desired_actions[0] for a in desired_actions) else TherapeuticAction.UNKNOWN

            ta = TargetTherapeuticAlignment(
                target_id=tid,
                is_primary=is_primary,
                drug_action=drug_action,
                desired_target_action=consensus,
                alignment=alignment,
                evidence_groups=raw_groups,
                supporting_groups=supporting_groups,
                opposing_groups=opposing_groups,
                drugmechdb_validated=dm_validated,
                confidence=conf,
                explanation=explanation,
            )
            target_alignments.append(ta)
            if is_primary:
                primary_alignments.append(ta)
            else:
                secondary_alignments.append(ta)

        # Overall from primary targets
        if not primary_alignments:
            overall = TherapeuticAlignment.INSUFFICIENT
            overall_exp = "[RAW_ROW] No primary targets."
        else:
            pstatus = [a.alignment for a in primary_alignments if a.alignment != TherapeuticAlignment.INSUFFICIENT]
            if not pstatus:
                overall = TherapeuticAlignment.INSUFFICIENT
                overall_exp = "[RAW_ROW] Insufficient directional evidence."
            elif all(s == TherapeuticAlignment.SUPPORTS for s in pstatus):
                overall = TherapeuticAlignment.SUPPORTS
                overall_exp = "[RAW_ROW] Primary targets: SUPPORTS."
            elif all(s == TherapeuticAlignment.OPPOSES for s in pstatus):
                overall = TherapeuticAlignment.OPPOSES
                overall_exp = "[RAW_ROW] Primary targets: OPPOSES."
            else:
                overall = TherapeuticAlignment.MIXED
                overall_exp = "[RAW_ROW] Mixed."

        total_groups = sum(len(a.evidence_groups) for a in target_alignments)
        total_supp = sum(len(a.supporting_groups) for a in target_alignments)
        total_opp = sum(len(a.opposing_groups) for a in target_alignments)

        return TherapeuticAlignmentReport(
            drug_name=package.drug.name,
            disease_name=package.disease.name,
            overall_alignment=overall,
            target_alignments=target_alignments,
            primary_target_alignments=primary_alignments,
            secondary_target_alignments=secondary_alignments,
            total_independent_groups=total_groups,
            supporting_groups_count=total_supp,
            opposing_groups_count=total_opp,
            drugmechdb_validated=dm_validated,
            explanation=overall_exp,
        )
