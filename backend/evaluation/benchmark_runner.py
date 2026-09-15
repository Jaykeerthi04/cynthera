"""Benchmark evaluation runner for executing benchmark datasets through CYNTHERA."""
from __future__ import annotations

import time
import logging
from typing import Sequence

from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.evaluation.benchmark_models import (
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkClass,
    BenchmarkEvaluationReport,
    ExecutionStatus,
    map_alignment_to_class,
    map_recommendation_to_class,
    WeightedBenchmarkCaseResult,
    WeightingComparisonResult,
)
from backend.evaluation.benchmark_dataset import BENCHMARK_DATASET_V1
from backend.evaluation.metrics import compute_benchmark_metrics
from backend.evaluation.ablation_runner import run_all_ablations, compute_baseline_predictions

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """Executes benchmark cases through the production reasoning pipeline.

    For each case, stores the RetrievalPackage so that downstream ablation
    runs can re-use already-retrieved data without additional API calls.
    """

    def __init__(self, orchestrator: MasterOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator or MasterOrchestrator()
        # Cache of case_id -> RetrievalPackage for ablation re-use
        self._package_cache: dict[str, object] = {}

    async def evaluate_case(self, case: BenchmarkCase, bypass_cache: bool = True) -> BenchmarkCaseResult:
        """Evaluate a single benchmark case through the full production pipeline."""
        start_time = time.time()
        try:
            hyp, pkg, res = await self._orchestrator.evaluate(
                drug_name=case.drug,
                disease_name=case.disease,
                policy=RetrievalPolicy.STANDARD,
                bypass_cache=bypass_cache,
            )
            exec_time_ms = (time.time() - start_time) * 1000.0

            # Store package for ablation re-use
            self._package_cache[case.case_id] = pkg

            ta_dict = getattr(res.audit_report, "therapeutic_alignment", {}) or {}
            # Analytical intermediate alignment (Phase 4D)
            pred_al = ta_dict.get("overall_alignment", "INSUFFICIENT")
            # Canonical production recommendation verdict (Rule Set v3.2)
            rec_status = getattr(res, "recommendation_status", None)
            pred_class = map_recommendation_to_class(rec_status)

            # Determine primary target and all pipeline targets
            target_aligns = ta_dict.get("target_alignments", [])
            primary_targets = [t for t in target_aligns if t.get("is_primary")]
            primary_target_id = primary_targets[0].get("target_id") if primary_targets else (target_aligns[0].get("target_id") if target_aligns else None)

            # Collect all target IDs seen by the pipeline for this case
            all_tids = [t.get("target_id") for t in target_aligns if t.get("target_id")]

            # Check if expected target appears anywhere in the pipeline's returned targets
            exp_target = case.expected_target
            if exp_target:
                target_match = any(tid.upper() == exp_target.upper() for tid in all_tids)
            else:
                target_match = None

            # Evidence family breakdown
            fam_counts: dict[str, int] = {}
            for t in target_aligns:
                for eg in t.get("evidence_groups", []):
                    fam = str(eg.get("evidence_family", "UNKNOWN"))
                    fam_counts[fam] = fam_counts.get(fam, 0) + 1

            # Directional concordance
            concordance = float(ta_dict.get("confidence", 0.0)) if "confidence" in ta_dict else 0.0
            if concordance == 0.0 and pred_al == "SUPPORTS":
                supp_cnt = ta_dict.get("supporting_groups_count", 0)
                opp_cnt = ta_dict.get("opposing_groups_count", 0)
                tot = supp_cnt + opp_cnt
                concordance = round(supp_cnt / tot, 4) if tot > 0 else 1.0

            return BenchmarkCaseResult(
                case=case,
                predicted_alignment=pred_al,
                predicted_class=pred_class,
                is_correct=(pred_class == case.expected_class),
                is_resolved=(pred_class != BenchmarkClass.UNCERTAIN),
                primary_target=primary_target_id,
                all_pipeline_targets=all_tids,
                target_match=target_match,
                target_alignments=target_aligns,
                directional_concordance=concordance,
                supporting_group_count=ta_dict.get("supporting_groups_count", 0),
                opposing_group_count=ta_dict.get("opposing_groups_count", 0),
                evidence_family_summary=fam_counts,
                execution_status=ExecutionStatus.SUCCESS,
                execution_time_ms=round(exec_time_ms, 2),
                explanation=ta_dict.get("explanation", ""),
            )
        except Exception as exc:
            exec_time_ms = (time.time() - start_time) * 1000.0
            logger.error("benchmark_case_evaluation_failed", extra={"case_id": case.case_id, "error": str(exc)})
            return BenchmarkCaseResult(
                case=case,
                predicted_alignment="INSUFFICIENT",
                predicted_class=BenchmarkClass.UNCERTAIN,
                is_correct=(case.expected_class == BenchmarkClass.UNCERTAIN),
                is_resolved=False,
                execution_status=ExecutionStatus.FAILED,
                error_message=str(exc),
                execution_time_ms=round(exec_time_ms, 2),
                explanation=f"Execution error: {exc}",
            )

    def evaluate_case_with_config(
        self,
        case: BenchmarkCase,
        config_name: str,
    ) -> tuple[BenchmarkCaseResult, object] | None:
        """Evaluate a benchmark case under a specific EvaluationConfig.

        Requires that evaluate_case() has already been called for this case_id
        (to populate self._package_cache). If the package is not cached, returns None.

        Args:
            case: Benchmark case metadata.
            config_name: Name of evaluation config (key in EVALUATION_CONFIGS).

        Returns:
            Tuple of (BenchmarkCaseResult, AblationVerification) or None if no package.
        """
        from backend.evaluation.evaluation_config import EVALUATION_CONFIGS
        from backend.evaluation.evaluation_runner import EvaluationRunner

        pkg = self._package_cache.get(case.case_id)
        if pkg is None:
            logger.warning(
                "evaluate_case_with_config_no_package",
                extra={"case_id": case.case_id, "config": config_name},
            )
            return None

        cfg = EVALUATION_CONFIGS.get(config_name)
        if cfg is None:
            raise ValueError(f"Unknown EvaluationConfig: {config_name!r}")

        runner = EvaluationRunner()
        return runner.run_with_config(case=case, package=pkg, config=cfg)

    async def run_benchmark(
        self,
        cases: Sequence[BenchmarkCase] | None = None,
        bypass_cache: bool = True,
        include_ablations: bool = True,
        include_weighting_comparison: bool = False,
    ) -> BenchmarkEvaluationReport:
        """Run complete benchmark evaluation across all dataset cases.

        Args:
            cases: Benchmark cases to evaluate. Defaults to BENCHMARK_DATASET_V1.
            bypass_cache: If True, force fresh evaluation (skip EvaluationCache).
            include_ablations: Whether to run ablation study.
            include_weighting_comparison: Whether to run equal-vote vs weighted comparison.
        """
        eval_cases = list(cases) if cases is not None else BENCHMARK_DATASET_V1
        results: list[BenchmarkCaseResult] = []

        for case in eval_cases:
            res = await self.evaluate_case(case, bypass_cache=bypass_cache)
            results.append(res)

        full_metrics = compute_benchmark_metrics(results)

        # Baseline evaluation (target existence heuristic)
        baseline_res = compute_baseline_predictions(results)
        baseline_metrics = compute_benchmark_metrics(baseline_res)

        # Ablations with stored packages
        ablation_results = []
        if include_ablations:
            ablation_results = run_all_ablations(results, packages=self._package_cache)

        # Aggregate evidence family contributions
        family_contributions: dict[str, int] = {}
        for r in results:
            for fam, cnt in r.evidence_family_summary.items():
                family_contributions[fam] = family_contributions.get(fam, 0) + cnt

        # Optional: weighting comparison (evaluation-only)
        weighting_comparison: WeightingComparisonResult | None = None
        if include_weighting_comparison:
            weighting_comparison = self._run_weighting_comparison(results, eval_cases)

        # Summary narrative
        acc_str = f"{full_metrics.accuracy:.1%}" if full_metrics.accuracy is not None else "N/A"
        base_acc_str = f"{baseline_metrics.accuracy:.1%}" if baseline_metrics.accuracy is not None else "N/A"
        n_pos = sum(1 for r in results if r.case.expected_class == BenchmarkClass.POSITIVE)
        n_neg = sum(1 for r in results if r.case.expected_class == BenchmarkClass.NEGATIVE)
        n_unc = sum(1 for r in results if r.case.expected_class == BenchmarkClass.UNCERTAIN)
        summary = (
            f"Phase 4E Benchmark evaluated {len(results)} cases "
            f"({n_pos} POSITIVE, {n_neg} NEGATIVE, {n_unc} UNCERTAIN) "
            f"with overall accuracy {acc_str}. "
            f"Directional alignment correctly identified {full_metrics.correct_predictions}/{len(results)} cases. "
            f"Baseline target existence achieved {base_acc_str} accuracy."
        )

        # Contradiction metrics
        from backend.evaluation.metrics import compute_contradiction_metrics
        contradiction_metrics = compute_contradiction_metrics(results)

        # Dataset quality metrics
        from backend.evaluation.benchmark_dataset import get_directionally_suitable_negatives, get_unsuitable_negatives, get_contradiction_cases
        suitable_neg = len(get_directionally_suitable_negatives())
        unsuitable_neg = len(get_unsuitable_negatives())
        contradiction_cnt = len(get_contradiction_cases())
        dataset_quality = {
            "total_cases": len(eval_cases),
            "positive_cases": n_pos,
            "negative_cases": n_neg,
            "uncertain_cases": n_unc,
            "contradiction_cases": contradiction_cnt,
            "directionally_suitable_negatives": suitable_neg,
            "unsuitable_flagged_negatives": unsuitable_neg,
            "label_provenance_coverage": sum(
                1 for c in eval_cases if c.label_source and c.label_reference
            ),
        }

        return BenchmarkEvaluationReport(
            benchmark_version="v1.1_refined",
            evaluation_timestamp=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            cache_version="v4.2_phase4e_benchmark",
            baseline_metrics=baseline_metrics,
            full_4d_metrics=full_metrics,
            case_results=results,
            ablation_results=ablation_results,
            evidence_family_contributions=family_contributions,
            summary_narrative=summary,
            weighting_comparison=weighting_comparison,
            contradiction_metrics=contradiction_metrics,
            dataset_quality_metrics=dataset_quality,
            benchmark_split_note=(
                "All cases in BENCHMARK_DATASET_V1 are labeled as TEST split. "
                "Do not tune WeightConfig values against these cases."
            ),
        )

    def _run_weighting_comparison(
        self,
        results: list[BenchmarkCaseResult],
        cases: list[BenchmarkCase],
    ) -> WeightingComparisonResult:
        """Compare equal-vote and weighted alignment across all benchmark cases."""
        from backend.evaluation.evidence_weights import WEIGHT_CONFIGS
        from backend.evaluation.evaluation_runner import EvaluationRunner
        from backend.evaluation.evaluation_config import EVALUATION_CONFIGS

        # Use Config A (default heuristic) for comparison
        wc = WEIGHT_CONFIGS.get("CONFIG_A", WEIGHT_CONFIGS["DEFAULT_HEURISTIC"])
        config = EVALUATION_CONFIGS.get("WEIGHTED_4D_A")
        runner = EvaluationRunner()

        comparisons: list[WeightedBenchmarkCaseResult] = []
        agreement_count = 0

        for r in results:
            pkg = self._package_cache.get(r.case.case_id)
            if pkg is None:
                continue
            try:
                w_res, _ = runner.run_with_config(r.case, pkg, config)
                agrees = (w_res.predicted_class == r.predicted_class)
                if agrees:
                    agreement_count += 1
                comparisons.append(
                    WeightedBenchmarkCaseResult(
                        case=r.case,
                        equal_vote_class=r.predicted_class,
                        equal_vote_alignment=r.predicted_alignment,
                        weighted_class=w_res.predicted_class,
                        weighted_alignment=w_res.predicted_alignment,
                        weight_config_name=wc.name,
                        weighted_support=float(w_res.supporting_group_count),
                        weighted_opposition=float(w_res.opposing_group_count),
                        weighted_concordance=w_res.directional_concordance,
                        equal_vote_concordance=r.directional_concordance,
                        prediction_agrees=agrees,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "weighting_comparison_failed",
                    extra={"case_id": r.case.case_id, "error": str(exc)},
                )

        total = len(comparisons)
        disagreement = total - agreement_count
        agreement_rate = round(agreement_count / total, 4) if total > 0 else None

        return WeightingComparisonResult(
            weight_config_name=wc.name,
            total_cases=total,
            agreement_count=agreement_count,
            disagreement_count=disagreement,
            agreement_rate=agreement_rate,
            case_comparisons=comparisons,
            interpretation=(
                f"Equal-vote and weighted (Config A: direct=1.0, curated=0.9, inferred=0.5) "
                f"agree on {agreement_count}/{total} cases ({agreement_rate:.1%} if agreement_rate else 'N/A'). "
                f"Weights are INITIAL HEURISTIC — not calibrated. "
                f"Disagreements indicate cases that are weight-sensitive."
            ),
        )
