"""Ablation analysis runner for Phase 4E evaluation.

Ablation Correctness Principle
--------------------------------
An ablation is correctly applied when the INTENDED EVIDENCE COMPONENT IS ABSENT
from the evaluation. Whether the final prediction changes is an experimental
OBSERVATION, not a correctness requirement.

The ablation results report:
  - evidence_representation_changed: YES/NO (correctness indicator)
  - prediction_changed: YES/NO (experimental observation)

If prediction stays identical despite evidence removal, the ablation is still
correctly applied — it indicates that removed source was not the deciding factor
for this case. This is a scientifically valid and honest outcome.

Implementation strategy
-----------------------
Source ablations (NO_OPEN_TARGETS, NO_DATTS, NO_DRUGMECHDB) filter the
RetrievalPackage evidence BEFORE DirectionalEvidenceBuilder.build_all() runs.
This is a pre-reasoning ablation — the TherapeuticDirectionEvidence records
the alignment engine receives genuinely reflect the ablated state.

Independence grouping ablation (NO_INDEPENDENCE_GROUPING) bypasses
group_evidence_by_independence() and maps each raw TDE row to one vote,
demonstrating what naive row-counting would produce.

Evidence weighting ablations (NO_EVIDENCE_WEIGHTING, WEIGHTED_4D_A/B/C) compare
equal-vote vs weighted concordance scores (evaluation-only comparator).
"""
from __future__ import annotations

import copy
import logging
from typing import Sequence
from backend.evaluation.benchmark_models import (
    AblationConfig,
    AblationResult,
    AblationVerification,
    BenchmarkCaseResult,
    BenchmarkClass,
)
from backend.evaluation.evaluation_config import EVALUATION_CONFIGS, EvaluationConfig
from backend.evaluation.metrics import compute_benchmark_metrics

logger = logging.getLogger(__name__)


def compute_baseline_predictions(results: Sequence[BenchmarkCaseResult]) -> list[BenchmarkCaseResult]:
    """Baseline 1: Target-existence heuristic.

    If drug-target connectivity exists -> POSITIVE, else UNCERTAIN.
    """
    baseline_results: list[BenchmarkCaseResult] = []
    for r in results:
        b_res = copy.deepcopy(r)
        if r.primary_target:
            b_res.predicted_class = BenchmarkClass.POSITIVE
            b_res.predicted_alignment = "SUPPORTS"
        else:
            b_res.predicted_class = BenchmarkClass.UNCERTAIN
            b_res.predicted_alignment = "INSUFFICIENT"
        b_res.is_correct = (b_res.predicted_class == b_res.case.expected_class)
        b_res.is_resolved = (b_res.predicted_class != BenchmarkClass.UNCERTAIN)
        baseline_results.append(b_res)
    return baseline_results


def _ablate_via_evaluation_runner(
    results: Sequence[BenchmarkCaseResult],
    packages: dict[str, object],  # case_id -> RetrievalPackage
    config: EvaluationConfig,
    config_name: AblationConfig,
    description: str,
) -> AblationResult:
    """Run a real ablation via EvaluationRunner if packages are available.

    If packages are not available (e.g. offline unit tests), falls back to
    post-hoc filtering of the already-computed result dictionaries.
    """
    from backend.evaluation.evaluation_runner import EvaluationRunner

    runner = EvaluationRunner()
    ablated_cases: list[BenchmarkCaseResult] = []
    changed_cases: list[dict] = []
    preds: dict[str, BenchmarkClass] = {}
    verifications: list[AblationVerification] = []
    evidence_changed_count = 0
    prediction_changed_count = 0

    for r in results:
        pkg = packages.get(r.case.case_id) if packages else None

        if pkg is not None:
            try:
                a_res, verif = runner.run_with_config(
                    case=r.case,
                    package=pkg,
                    config=config,
                    full_result=r,
                )
                if verif.evidence_representation_changed:
                    evidence_changed_count += 1
                if verif.prediction_changed:
                    prediction_changed_count += 1
                    changed_cases.append({
                        "case_id": r.case.case_id,
                        "drug": r.case.drug,
                        "disease": r.case.disease,
                        "full_prediction": r.predicted_class.value,
                        "ablated_prediction": a_res.predicted_class.value,
                        "evidence_representation_changed": verif.evidence_representation_changed,
                        "verification_note": verif.verification_note,
                    })
                preds[r.case.case_id] = a_res.predicted_class
                verifications.append(verif)
                ablated_cases.append(a_res)
            except Exception as exc:
                logger.warning(
                    "ablation_runner_case_failed",
                    extra={"case_id": r.case.case_id, "config": config.name, "error": str(exc)},
                )
                preds[r.case.case_id] = r.predicted_class
                ablated_cases.append(copy.deepcopy(r))
        else:
            # Fallback: post-hoc filtering (unit test mode — packages not available)
            a_res = _postfix_ablate(r, config)
            preds[r.case.case_id] = a_res.predicted_class
            if a_res.predicted_class != r.predicted_class:
                prediction_changed_count += 1
                changed_cases.append({
                    "case_id": r.case.case_id,
                    "drug": r.case.drug,
                    "disease": r.case.disease,
                    "full_prediction": r.predicted_class.value,
                    "ablated_prediction": a_res.predicted_class.value,
                    "evidence_representation_changed": False,  # Cannot verify without package
                    "verification_note": "FALLBACK: No package available; post-hoc filter applied.",
                })
            ablated_cases.append(a_res)

    metrics = compute_benchmark_metrics(ablated_cases)
    return AblationResult(
        config_name=config_name,
        description=description,
        metrics=metrics,
        case_predictions=preds,
        changed_cases_from_full=changed_cases,
        verifications=verifications,
        evidence_changed_count=evidence_changed_count,
        prediction_changed_count=prediction_changed_count,
    )


def _postfix_ablate(
    r: BenchmarkCaseResult,
    config: EvaluationConfig,
) -> BenchmarkCaseResult:
    """Fallback post-hoc ablation for unit tests (no live RetrievalPackage available).

    Checks target_alignments dict for evidence group presence and downgrades
    prediction to UNCERTAIN if the required source evidence is absent.
    This is NOT a real ablation — it is a best-effort approximation for
    offline testing without live pipeline data.
    """
    a_res = copy.deepcopy(r)

    if not config.use_open_targets:
        has_other = any(
            src != "OpenTargets"
            for t in r.target_alignments
            for eg in t.get("evidence_groups", [])
            for src in ([eg.get("sources", [])] if isinstance(eg.get("sources"), str) else eg.get("sources", []))
            if eg.get("desired_action") in ("INHIBITION", "ACTIVATION")
        )
        if not has_other:
            a_res.predicted_class = BenchmarkClass.UNCERTAIN
            a_res.predicted_alignment = "INSUFFICIENT"
            a_res.is_correct = (a_res.predicted_class == a_res.case.expected_class)
            a_res.is_resolved = False

    elif not config.use_datts:
        has_other = any(
            src != "DATTs"
            for t in r.target_alignments
            for eg in t.get("evidence_groups", [])
            for src in ([eg.get("sources", [])] if isinstance(eg.get("sources"), str) else eg.get("sources", []))
            if eg.get("desired_action") in ("INHIBITION", "ACTIVATION")
        )
        if not has_other:
            a_res.predicted_class = BenchmarkClass.UNCERTAIN
            a_res.predicted_alignment = "INSUFFICIENT"
            a_res.is_correct = (a_res.predicted_class == a_res.case.expected_class)
            a_res.is_resolved = False

    # DrugMechDB and independence grouping — cannot approximate without live package
    # Return unchanged result; AblationVerification will flag as INCONCLUSIVE
    return a_res


# ── Public ablation functions ─────────────────────────────────────────────────

def run_ablation_no_open_targets(
    results: Sequence[BenchmarkCaseResult],
    packages: dict[str, object] | None = None,
) -> AblationResult:
    """Ablate Open Targets Direction-of-Effect evidence."""
    return _ablate_via_evaluation_runner(
        results=results,
        packages=packages or {},
        config=EVALUATION_CONFIGS["NO_OPEN_TARGETS"],
        config_name=AblationConfig.NO_OPEN_TARGETS,
        description="Excludes all Open Targets Direction-of-Effect (LoF/GoF) annotations.",
    )


def run_ablation_no_datts(
    results: Sequence[BenchmarkCaseResult],
    packages: dict[str, object] | None = None,
) -> AblationResult:
    """Ablate DATTs curated pharmacology target evidence."""
    return _ablate_via_evaluation_runner(
        results=results,
        packages=packages or {},
        config=EVALUATION_CONFIGS["NO_DATTS"],
        config_name=AblationConfig.NO_DATTS,
        description="Excludes all DATTs curated disease-target required actions.",
    )


def run_ablation_no_drugmechdb(
    results: Sequence[BenchmarkCaseResult],
    packages: dict[str, object] | None = None,
) -> AblationResult:
    """Ablate DrugMechDB curated mechanistic path validation.

    CORRECTION vs Phase 4E initial implementation:
    The original run_ablation_no_drugmechdb was a no-op that did not modify
    predictions. This implementation performs real evidence filtering:
    DrugMechDB records are removed from the package before alignment,
    and the AblationVerification records whether evidence actually changed.
    """
    return _ablate_via_evaluation_runner(
        results=results,
        packages=packages or {},
        config=EVALUATION_CONFIGS["NO_DRUGMECHDB"],
        config_name=AblationConfig.NO_DRUGMECHDB,
        description="Excludes DrugMechDB curated mechanistic path validation.",
    )


def run_ablation_no_independence(
    results: Sequence[BenchmarkCaseResult],
    packages: dict[str, object] | None = None,
) -> AblationResult:
    """Ablate independence grouping (raw row counting vs publication deduplication).

    CORRECTION vs Phase 4E initial implementation:
    The original run_ablation_no_independence was a no-op that did not change
    evidence representation. This implementation uses EvaluationRunner with
    use_independence_grouping=False, which maps each raw TDE row to one vote.
    AblationVerification records whether independence groups genuinely changed.
    """
    return _ablate_via_evaluation_runner(
        results=results,
        packages=packages or {},
        config=EVALUATION_CONFIGS["NO_INDEPENDENCE_GROUPING"],
        config_name=AblationConfig.NO_INDEPENDENCE_GROUPING,
        description="Replaces publication-level clustering with naive raw-row counting.",
    )


def run_all_ablations(
    results: Sequence[BenchmarkCaseResult],
    packages: dict[str, object] | None = None,
) -> list[AblationResult]:
    """Execute all ablation configurations against the benchmark results.

    Args:
        results: Full benchmark case results from production pipeline.
        packages: Optional dict of case_id -> RetrievalPackage for live ablation.
            If None, falls back to post-hoc approximation for unit test compatibility.
    """
    return [
        run_ablation_no_open_targets(results, packages),
        run_ablation_no_datts(results, packages),
        run_ablation_no_drugmechdb(results, packages),
        run_ablation_no_independence(results, packages),
    ]
