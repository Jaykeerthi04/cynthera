"""Evaluation metrics and confusion matrix computation for Phase 4E."""
from __future__ import annotations

import math
from typing import Sequence
from backend.evaluation.benchmark_models import (
    BenchmarkClass,
    BenchmarkMetrics,
    ConfusionMatrix3x3,
    BenchmarkCaseResult,
)


def compute_benchmark_metrics(results: Sequence[BenchmarkCaseResult]) -> BenchmarkMetrics:
    """Calculate comprehensive benchmark metrics across evaluation results.
    
    Handles missing class scenarios gracefully: unavailable metrics evaluate to None.
    """
    total = len(results)
    if total == 0:
        return BenchmarkMetrics(notes=["Empty benchmark results dataset."])

    cm = ConfusionMatrix3x3()
    pos_cases = 0
    neg_cases = 0
    unc_cases = 0
    correct = 0
    incorrect = 0
    unresolved = 0
    notes: list[str] = []

    for r in results:
        exp_raw = r.case.expected_class
        pred_raw = r.predicted_class
        exp = BenchmarkClass(exp_raw) if not isinstance(exp_raw, BenchmarkClass) else exp_raw
        pred = BenchmarkClass(pred_raw) if not isinstance(pred_raw, BenchmarkClass) else pred_raw
        cm.record(exp, pred)

        if exp == BenchmarkClass.POSITIVE:
            pos_cases += 1
        elif exp == BenchmarkClass.NEGATIVE:
            neg_cases += 1
        elif exp == BenchmarkClass.UNCERTAIN:
            unc_cases += 1

        if exp == pred:
            correct += 1
        else:
            if pred == BenchmarkClass.UNCERTAIN:
                unresolved += 1
            else:
                incorrect += 1

    accuracy = round(correct / total, 4) if total > 0 else None

    # Binary/Directional metrics over POSITIVE vs NEGATIVE
    tp = cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.POSITIVE)
    fp = cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.POSITIVE)
    fn = cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.NEGATIVE)
    tn = cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.NEGATIVE)

    # Precision: Positive Predictive Value
    if (tp + fp) > 0:
        precision = round(tp / (tp + fp), 4)
    else:
        precision = None
        notes.append("Precision unavailable (no positive predictions made).")

    # Recall / Sensitivity: True Positive Rate
    if pos_cases > 0:
        recall = round(tp / pos_cases, 4)
    else:
        recall = None
        notes.append("Recall unavailable (no positive ground-truth cases in benchmark).")

    # Specificity: True Negative Rate
    if neg_cases > 0:
        specificity = round(tn / neg_cases, 4)
    else:
        specificity = None
        notes.append("Specificity unavailable (no negative ground-truth cases in benchmark).")

    # F1 Score
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1_score = round(2 * (precision * recall) / (precision + recall), 4)
    else:
        f1_score = None

    # Matthews Correlation Coefficient (MCC)
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    if denom > 0:
        mcc = round(((tp * tn) - (fp * fn)) / denom, 4)
    else:
        mcc = None
        notes.append("MCC unavailable due to zero-variance in one or more marginal classes.")

    return BenchmarkMetrics(
        total_cases=total,
        positive_cases=pos_cases,
        negative_cases=neg_cases,
        uncertain_cases=unc_cases,
        correct_predictions=correct,
        incorrect_predictions=incorrect,
        unresolved_predictions=unresolved,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        specificity=specificity,
        f1_score=f1_score,
        mcc=mcc,
        confusion_matrix=cm,
        notes=notes,
    )


def compute_contradiction_metrics(results: Sequence[BenchmarkCaseResult]) -> ContradictionMetrics:
    """Calculate contradiction and conflict detection metrics across benchmark results."""
    from backend.evaluation.benchmark_models import ContradictionMetrics

    total = len(results)
    if total == 0:
        return ContradictionMetrics(notes=["Empty results dataset."])

    contradiction_cases = 0
    balanced_cases = 0
    detected_conflicts = 0
    resolved_contradictions = 0
    resolved_balanced = 0
    false_resolutions = 0
    notes: list[str] = []

    for r in results:
        is_neg_expected = (r.case.expected_class == BenchmarkClass.NEGATIVE and not r.case.unsuitable_for_directional_negative)
        is_balanced_expected = (r.case.case_id == "BENCH-UNC-03" or ("balanced" in r.case.rationale.lower()))

        # Check if case has actual opposing or mixed evidence groups
        opp_cnt = r.opposing_group_count
        supp_cnt = r.supporting_group_count
        has_opposing_evidence = (opp_cnt > 0)
        has_balanced_evidence = (supp_cnt > 0 and opp_cnt > 0 and supp_cnt == opp_cnt)

        if is_neg_expected:
            contradiction_cases += 1
            if has_opposing_evidence or r.predicted_class == BenchmarkClass.NEGATIVE:
                detected_conflicts += 1
            if r.predicted_class == BenchmarkClass.NEGATIVE:
                resolved_contradictions += 1
            elif r.predicted_class == BenchmarkClass.POSITIVE:
                false_resolutions += 1

        if is_balanced_expected or has_balanced_evidence:
            balanced_cases += 1
            if r.predicted_class == BenchmarkClass.UNCERTAIN:
                resolved_balanced += 1

    det_rate = round(detected_conflicts / contradiction_cases, 4) if contradiction_cases > 0 else None
    res_rate = round(resolved_contradictions / contradiction_cases, 4) if contradiction_cases > 0 else None
    bal_rate = round(resolved_balanced / balanced_cases, 4) if balanced_cases > 0 else None
    false_rate = round(false_resolutions / contradiction_cases, 4) if contradiction_cases > 0 else None

    return ContradictionMetrics(
        total_cases=total,
        contradiction_cases=contradiction_cases,
        balanced_conflict_cases=balanced_cases,
        correctly_detected_conflicts=detected_conflicts,
        correctly_resolved_contradictions=resolved_contradictions,
        correctly_resolved_balanced_conflicts=resolved_balanced,
        false_directional_resolutions=false_resolutions,
        contradiction_detection_rate=det_rate,
        contradiction_resolution_rate=res_rate,
        balanced_conflict_insufficient_rate=bal_rate,
        false_directional_resolution_rate=false_rate,
        notes=notes,
    )


def compute_bootstrap_ci(
    results: Sequence[BenchmarkCaseResult],
    n_bootstrap: int = 1000,
    ci_level: float = 0.95,
    seed: int = 42,
) -> dict[str, tuple[float, float]]:
    """Compute bootstrap confidence intervals for key benchmark metrics.

    Uses random resampling with replacement (bootstrap) to estimate uncertainty
    in accuracy, precision, recall, specificity, and MCC.

    Args:
        results: Evaluated benchmark case results.
        n_bootstrap: Number of bootstrap resamples. Default 1000.
        ci_level: Confidence level. Default 0.95 (95% CI).
        seed: Random seed for reproducibility. Default 42.

    Returns:
        Dict mapping metric name to (lower_bound, upper_bound) tuple.
        Metric names: 'accuracy', 'precision', 'recall', 'specificity', 'mcc'.
        If a metric cannot be computed for a resample, that sample is skipped.

    Notes:
        Uses Python standard-library `random` module only (no numpy required).
        The CI is a percentile interval: lower = (1-ci_level)/2 quantile,
        upper = 1 - (1-ci_level)/2 quantile.
    """
    import random

    if len(results) == 0:
        return {}

    rng = random.Random(seed)
    n = len(results)
    alpha = 1.0 - ci_level
    lo_pct = alpha / 2.0
    hi_pct = 1.0 - alpha / 2.0

    bootstrapped: dict[str, list[float]] = {
        "accuracy": [], "precision": [], "recall": [],
        "specificity": [], "f1": [], "mcc": [],
    }

    result_list = list(results)

    for _ in range(n_bootstrap):
        sample = [rng.choice(result_list) for _ in range(n)]
        m = compute_benchmark_metrics(sample)
        if m.accuracy is not None:
            bootstrapped["accuracy"].append(m.accuracy)
        if m.precision is not None:
            bootstrapped["precision"].append(m.precision)
        if m.recall is not None:
            bootstrapped["recall"].append(m.recall)
        if m.specificity is not None:
            bootstrapped["specificity"].append(m.specificity)
        if m.f1_score is not None:
            bootstrapped["f1"].append(m.f1_score)
        if m.mcc is not None:
            bootstrapped["mcc"].append(m.mcc)

    ci: dict[str, tuple[float, float]] = {}
    for metric, values in bootstrapped.items():
        if not values:
            continue
        values_sorted = sorted(values)
        k = len(values_sorted)
        lo_idx = max(0, int(math.floor(lo_pct * k)))
        hi_idx = min(k - 1, int(math.floor(hi_pct * k)))
        ci[metric] = (round(values_sorted[lo_idx], 4), round(values_sorted[hi_idx], 4))

    return ci

