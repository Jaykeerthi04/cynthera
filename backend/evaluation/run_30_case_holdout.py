"""CYNTHERA -- 30-Case Hold-Out Evaluation Runner.

Executes the production reasoning pipeline across a COMPLETELY NEW 30-case
hold-out benchmark that is disjoint from the existing 25-case regression set.

This is a research evaluation framework, NOT a regression test suite.
The 25-case set remains the regression/diagnostic benchmark.
This 30-case set is for publication-oriented research evaluation.

ABSOLUTE RULES:
- Benchmark labels NEVER enter the reasoning engine.
- No expected_class or expected_category is passed to any production function.
- Do not optimize the benchmark.
- Do not manipulate labels.
- Do not lower standards to obtain higher accuracy.
- "no indication found" != "negative therapeutic finding"
- "high SS" != "99% probability"
- "source unavailable" != "zero evidence"
- "Phase 3" != "approved"
- "structural pathway relationship" != "causal validation"
- "589 tests passed" != "scientific validation"

Key Features:
- Per-case timeout (180s default)
- Progressive persistence to results.jsonl after each case
- Resumability via --resume flag
- Dual scoring: Standard 3-class AND Epistemic 3-class
- Error taxonomy with diagnostic reasons
- Bootstrap 95% confidence intervals
- Confusion matrices for both scoring modes
- Category-level performance breakdown
- Research report generation
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import math
import os
import random
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Ensure root paths are in sys.path
_current_dir = Path(__file__).resolve().parent
_cynthera_dir = _current_dir.parent.parent
_workspace_dir = _cynthera_dir.parent.parent

if str(_workspace_dir) not in sys.path:
    sys.path.append(str(_workspace_dir))
if str(_cynthera_dir) in sys.path:
    sys.path.remove(str(_cynthera_dir))
sys.path.insert(0, str(_cynthera_dir))

load_dotenv(_cynthera_dir / ".env")
load_dotenv(_workspace_dir / ".env")

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("cynthera.eval_30_holdout")

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.infrastructure.cache.evaluation_cache import EvaluationCache
from backend.evaluation.holdout_30_case_dataset import (
    HOLDOUT_CASES,
    HoldoutCase,
    STANDARD_LABEL_TO_3CLASS,
    EPISTEMIC_LABEL_TO_3CLASS,
    RECOMMENDATION_TO_3CLASS,
    validate_dataset_integrity,
)

CASE_TIMEOUT_SECONDS = 180


# -----------------------------------------------------------------------------
# LABEL ISOLATION ASSERTION
# -----------------------------------------------------------------------------
# This check runs at import time. It verifies that the holdout dataset module
# does NOT import or reference any production reasoning code.

def _assert_label_isolation() -> None:
    """Verify that holdout labels are not importable from production modules."""
    import importlib
    prod_modules = [
        "backend.reasoning.orchestrator.reasoning_orchestrator",
        "backend.engineering.retrieval.pipeline",
        "backend.engineering.orchestrator.master_orchestrator",
        "backend.reasoning.context.scientific_context_builder",
    ]
    for mod_name in prod_modules:
        mod = importlib.import_module(mod_name)
        source_file = getattr(mod, "__file__", "")
        if source_file:
            with open(source_file, "r", encoding="utf-8", errors="ignore") as f:
                source = f.read()
            # No production module should reference the holdout dataset
            assert "holdout_30_case_dataset" not in source, (
                f"LABEL LEAKAGE: {mod_name} references holdout_30_case_dataset!"
            )
            assert "HOLDOUT_CASES" not in source, (
                f"LABEL LEAKAGE: {mod_name} references HOLDOUT_CASES!"
            )

_assert_label_isolation()


# -----------------------------------------------------------------------------
# METRICS UTILITIES
# -----------------------------------------------------------------------------

def compute_mcc_3x3(cm: dict[str, dict[str, int]], labels: list[str]) -> float:
    """Matthews Correlation Coefficient for 3x3 confusion matrix."""
    n = sum(cm[t][p] for t in labels for p in labels)
    if n == 0:
        return 0.0
    c = sum(cm[k][k] for k in labels)
    p_k = {k: sum(cm[t][k] for t in labels) for k in labels}
    t_k = {k: sum(cm[k][p] for p in labels) for k in labels}

    num = c * n - sum(p_k[k] * t_k[k] for k in labels)
    den1 = n**2 - sum(p_k[k] ** 2 for k in labels)
    den2 = n**2 - sum(t_k[k] ** 2 for k in labels)
    den = math.sqrt(den1 * den2)
    return num / den if den > 0 else 0.0


def compute_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    """Compute 3-class classification metrics."""
    labels = ["SUPPORT", "OPPOSE", "UNCERTAIN"]
    cm = {t: {p: 0 for p in labels} for t in labels}
    for t, p in zip(y_true, y_pred):
        if t in cm and p in cm[t]:
            cm[t][p] += 1

    total = len(y_true)
    correct = sum(cm[k][k] for k in labels)
    accuracy = correct / total if total > 0 else 0.0

    precisions: dict[str, float] = {}
    recalls: dict[str, float] = {}
    f1s: dict[str, float] = {}

    for k in labels:
        tp = cm[k][k]
        fp = sum(cm[t][k] for t in labels if t != k)
        fn = sum(cm[k][p] for p in labels if p != k)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        precisions[k] = prec
        recalls[k] = rec
        f1s[k] = f1

    macro_p = sum(precisions.values()) / 3.0
    macro_r = sum(recalls.values()) / 3.0
    macro_f1 = sum(f1s.values()) / 3.0

    support_counts = {k: sum(cm[k][p] for p in labels) for k in labels}
    weighted_f1 = sum(f1s[k] * support_counts[k] for k in labels) / total if total > 0 else 0.0
    mcc = compute_mcc_3x3(cm, labels)

    return {
        "total_cases": total,
        "correct_cases": correct,
        "accuracy": round(accuracy, 4),
        "macro_precision": round(macro_p, 4),
        "macro_recall": round(macro_r, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "mcc": round(mcc, 4),
        "per_class": {
            k: {
                "precision": round(precisions[k], 4),
                "recall": round(recalls[k], 4),
                "f1": round(f1s[k], 4),
                "support": support_counts[k],
            }
            for k in labels
        },
        "confusion_matrix": cm,
    }


def bootstrap_ci(
    y_true: list[str],
    y_pred: list[str],
    n_boot: int = 2000,
    seed: int = 20260906,
) -> dict[str, tuple[float, float]]:
    """Compute bootstrap 95% confidence intervals for accuracy, macro-F1, MCC."""
    if not y_true:
        return {}
    rng = random.Random(seed)
    n = len(y_true)
    boot_acc = []
    boot_f1 = []
    boot_mcc = []

    for _ in range(n_boot):
        indices = [rng.randint(0, n - 1) for _ in range(n)]
        samp_true = [y_true[i] for i in indices]
        samp_pred = [y_pred[i] for i in indices]
        m = compute_metrics(samp_true, samp_pred)
        boot_acc.append(m["accuracy"])
        boot_f1.append(m["macro_f1"])
        boot_mcc.append(m["mcc"])

    def get_ci(vals: list[float]) -> tuple[float, float]:
        vals_s = sorted(vals)
        low = vals_s[int(0.025 * len(vals_s))]
        high = vals_s[int(0.975 * len(vals_s))]
        return round(low, 4), round(high, 4)

    return {
        "accuracy_95ci": get_ci(boot_acc),
        "macro_f1_95ci": get_ci(boot_f1),
        "mcc_95ci": get_ci(boot_mcc),
    }


# -----------------------------------------------------------------------------
# CACHE TELEMETRY
# -----------------------------------------------------------------------------

def get_cache_stats(db_path: str) -> dict[str, int]:
    stats = {
        "evaluation_cache_rows": 0,
        "evaluation_cache_hits": 0,
        "raw_cache_rows": 0,
        "raw_cache_hits": 0,
    }
    if not os.path.exists(db_path):
        return stats
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        try:
            cur.execute("SELECT count(*), coalesce(sum(hit_count), 0) FROM evaluation_cache")
            row = cur.fetchone()
            if row:
                stats["evaluation_cache_rows"] = row[0]
                stats["evaluation_cache_hits"] = row[1]
        except Exception:
            pass
        try:
            cur.execute("SELECT count(*), coalesce(sum(hit_count), 0) FROM raw_response_cache")
            row = cur.fetchone()
            if row:
                stats["raw_cache_rows"] = row[0]
                stats["raw_cache_hits"] = row[1]
        except Exception:
            pass
        conn.close()
    except Exception as exc:
        logger.warning("Could not read cache stats: %s", exc)
    return stats


# -----------------------------------------------------------------------------
# SINGLE CASE EVALUATION
# -----------------------------------------------------------------------------

async def evaluate_single_case(
    case: HoldoutCase,
    orchestrator: MasterOrchestrator,
    timeout_seconds: int = CASE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Evaluate a single hold-out case through the production pipeline.

    CRITICAL: No expected_label or expected_class is passed to the orchestrator.
    The orchestrator receives ONLY (drug_name, disease_name, policy).
    Labels are attached to the result AFTER the reasoning pipeline returns.
    """
    cid = case.case_id
    cat = case.category
    drug = case.drug
    disease = case.disease

    # Labels are attached AFTER evaluation, never passed to reasoning
    expected_label = case.expected_label
    expected_3class_standard = STANDARD_LABEL_TO_3CLASS[expected_label]
    expected_3class_epistemic = EPISTEMIC_LABEL_TO_3CLASS[expected_label]

    t0 = time.time()
    status = "SUCCESS"
    error_type = None
    error_msg = None
    rec_str = "UNCERTAIN"
    pred_class = "UNCERTAIN"

    ss = 0.0
    ms = 0.0
    rs = 0.0
    opp_score = 0.0
    opp_level = "NONE"
    qualified_neg_claims = 0
    mech_qual = "UNKNOWN"
    has_high_quality_therapeutic = False
    approval_signal: dict[str, Any] | None = None
    decision_gate = "NONE"
    rec_reasons: list[str] = []
    target_count = 0
    primary_target = ""
    lit_claims = 0
    sources_failed: list[str] = []
    cache_hit = False

    # Check if this case is an evaluation cache hit
    try:
        cached_res = orchestrator._cache.get(drug, disease, RetrievalPolicy.STANDARD.value)
        if cached_res is not None:
            cache_hit = True
    except Exception:
        pass

    try:
        # Run the production pipeline -- NO LABELS PASSED
        eval_coro = orchestrator.evaluate(
            drug_name=drug,
            disease_name=disease,
            policy=RetrievalPolicy.STANDARD,
            bypass_cache=False,
        )
        hypothesis, package, result = await asyncio.wait_for(eval_coro, timeout=timeout_seconds)

        elapsed = time.time() - t0
        rec_status = result.recommendation_status
        rec_str = rec_status.value
        pred_class = RECOMMENDATION_TO_3CLASS.get(rec_str, "UNCERTAIN")

        ss = float(result.support_assessment.score)
        ms = float(result.mechanistic_assessment.score)
        rs = float(result.risk_assessment.score)
        opp_assess = result.opposition_assessment
        opp_score = float(opp_assess.score)
        opp_level = opp_assess.level
        qualified_neg_claims = int(opp_assess.qualified_negative_claim_count)

        ma = result.mechanistic_assessment
        sc = ma.score_components or {}
        mech_qual = sc.get("support_level", ma.level)

        target_count = sc.get("target_count", len(package.targets))
        primary_target = sc.get("ranked_target", "")
        if not primary_target and package.targets:
            t_obj = package.targets[0]
            primary_target = (
                getattr(t_obj, "gene_symbol", None)
                or getattr(t_obj, "protein_uniprot", None)
                or getattr(t_obj, "name", None)
                or ""
            )

        lit_claims = len(getattr(result.audit_report, "top_citations", []) or [])

        has_high_quality_therapeutic = bool(
            getattr(result.support_assessment, "has_high_quality_therapeutic", False)
        )
        package_approval = getattr(package, "approval_signal", None)
        approval_signal = package_approval.model_dump() if package_approval is not None else None
        rec_reasons = getattr(result, "recommendation_reasons", []) or []
        decision_gate = rec_reasons[0] if rec_reasons else "NONE"

        if package.sources_failed:
            sources_failed = list(package.sources_failed)
            if any(s.lower() in ("chembl", "uniprot") for s in sources_failed) and rec_str == "INSUFFICIENT_DATA":
                status = "RETRIEVAL_FAILURE"
                error_type = "RETRIEVAL_FAILURE"
                error_msg = f"Critical upstream source(s) failed: {sources_failed}"

    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        status = "TIMEOUT"
        error_type = "TIMEOUT"
        error_msg = f"Execution exceeded {timeout_seconds}s timeout"

    except Exception as exc:
        elapsed = time.time() - t0
        exc_str = str(exc)
        exc_type = type(exc).__name__

        if "connect" in exc_str.lower() or "timeout" in exc_str.lower() or "http" in exc_str.lower():
            status = "RETRIEVAL_FAILURE"
            error_type = "RETRIEVAL_FAILURE"
        elif "json" in exc_str.lower() or "parsing" in exc_str.lower() or "validation" in exc_str.lower():
            status = "PARSING_FAILURE"
            error_type = "PARSING_FAILURE"
        else:
            status = "UNKNOWN_FAILURE"
            error_type = "UNKNOWN_FAILURE"

        error_msg = f"{exc_type}: {exc_str}"

    return {
        "case_id": cid,
        "drug": drug,
        "disease": disease,
        "category": cat,
        "expected_label": expected_label,
        "expected_3class_standard": expected_3class_standard,
        "expected_3class_epistemic": expected_3class_epistemic,
        "status": status,
        "prediction": pred_class,
        "recommendation": rec_str,
        "runtime_seconds": round(elapsed, 2),
        "support_score": round(ss, 4),
        "mechanistic_score": round(ms, 4),
        "risk_score": round(rs, 4),
        "mechanistic_quality_tier": mech_qual,
        "opposition_score": round(opp_score, 4),
        "opposition_level": opp_level,
        "qualified_negative_claim_count": qualified_neg_claims,
        "independent_opposition_group_count": int(opp_assess.independent_group_count),
        "has_high_quality_therapeutic": has_high_quality_therapeutic,
        "approval_signal": approval_signal,
        "decision_gate": decision_gate,
        "recommendation_reasons": rec_reasons,
        "target_count": target_count,
        "primary_target": primary_target,
        "literature_claims": lit_claims,
        "error_type": error_type,
        "error_message": error_msg,
        "cache_hit": cache_hit,
        "sources_failed": sources_failed,
    }


# -----------------------------------------------------------------------------
# ERROR TAXONOMY
# -----------------------------------------------------------------------------

def classify_error(result: dict[str, Any]) -> str:
    """Classify the root cause of an incorrect prediction."""
    pred = result["prediction"]
    expected_std = result["expected_3class_standard"]
    expected_epi = result["expected_3class_epistemic"]
    cat = result["category"]
    rec = result["recommendation"]
    ss = result["support_score"]
    ms = result["mechanistic_score"]
    opp = result["opposition_score"]
    opp_lvl = result["opposition_level"]
    hqt = result["has_high_quality_therapeutic"]
    appr = result.get("approval_signal") or {}
    gate = result.get("decision_gate", "")

    # Infrastructure failures
    if result["status"] != "SUCCESS":
        return f"INFRASTRUCTURE: {result['status']}"

    # Established positive predicted UNCERTAIN
    if cat == "Established positive" and pred == "UNCERTAIN":
        if appr.get("is_approved") is True:
            return "RULE_GATE: Approved indication detected but downstream rule overrode to UNCERTAIN"
        if ms == 0 and ss == 0:
            return "RETRIEVAL_GAP: No mechanistic or support evidence retrieved for approved drug"
        if not hqt:
            return "THERAPEUTIC_ANCHOR: Rule 1c blocked -- no high-quality therapeutic evidence despite approval"
        return "THRESHOLD: Scores below PROMISING threshold despite established indication"

    # Established positive predicted OPPOSE
    if cat == "Established positive" and pred == "OPPOSE":
        return "FALSE_NEGATIVE: Established positive incorrectly classified as negative"

    # Verified negative predicted SUPPORT
    if cat == "Verified negative" and pred == "SUPPORT":
        if opp == 0:
            return "OPPOSITION_GAP: No opposition evidence retrieved for documented clinical failure"
        return "FALSE_POSITIVE: Verified negative incorrectly promoted to SUPPORT"

    # Verified negative predicted UNCERTAIN
    if cat == "Verified negative" and pred == "UNCERTAIN":
        if opp == 0:
            return "OPPOSITION_GAP: No opposition evidence retrieved -- opposition assessor missed clinical failure"
        return "OPPOSITION_THRESHOLD: Opposition detected but insufficient to trigger Rule 2b veto"

    # Unverified predicted SUPPORT
    if cat == "Unverified" and pred == "SUPPORT":
        if appr.get("is_approved"):
            return "INDICATION_LEAKAGE: Unrelated approved indication incorrectly matched to queried disease"
        return "FALSE_POSITIVE: Unverified pair incorrectly promoted to SUPPORT"

    # Unverified predicted OPPOSE
    if cat == "Unverified" and pred == "OPPOSE":
        return "OVER_NEGATION: Absence of evidence treated as opposition (epistemic error)"

    # Weak/indirect predicted SUPPORT
    if cat == "Weak/indirect" and pred == "SUPPORT":
        if hqt:
            return "HQT_FALSE_POSITIVE: Weak evidence incorrectly classified as high-quality therapeutic"
        return "FALSE_POSITIVE: Weak/indirect evidence over-promoted to SUPPORT"

    # Weak/indirect predicted OPPOSE
    if cat == "Weak/indirect" and pred == "OPPOSE":
        return "OVER_NEGATION: Weak evidence treated as negative rather than uncertain"

    return f"UNCLASSIFIED: {cat} expected={expected_std} got={pred}"


# -----------------------------------------------------------------------------
# RESEARCH REPORT GENERATION
# -----------------------------------------------------------------------------

def generate_research_report(
    results: list[dict[str, Any]],
    metrics_std: dict[str, Any],
    metrics_epi: dict[str, Any],
    ci_std: dict[str, Any],
    ci_epi: dict[str, Any],
    category_summary: dict[str, Any],
    error_taxonomy: list[dict[str, Any]],
    output_path: Path,
    total_runtime: float,
) -> None:
    """Generate a publication-oriented research evaluation report."""
    report_lines = []

    def w(line: str = "") -> None:
        report_lines.append(line)

    w("=" * 78)
    w("CYNTHERA -- 30-Case Hold-Out Research Evaluation Report")
    w("=" * 78)
    w()
    w(f"Generated: {datetime.now().isoformat()}")
    w(f"Engine Version: CYNTHERA v2.0")
    w(f"Rule Set: 3.2")
    w(f"Cache Version: {EvaluationCache._CACHE_VERSION}")
    w(f"Total Runtime: {total_runtime:.1f}s")
    w(f"Total Cases: {len(results)}")
    w()

    # -- EXECUTIVE SUMMARY --
    w("-" * 78)
    w("1. EXECUTIVE SUMMARY")
    w("-" * 78)
    w()
    w(f"  Standard Accuracy:       {metrics_std['accuracy']:.1%} ({metrics_std['correct_cases']}/{metrics_std['total_cases']})")
    w(f"  Epistemic Accuracy:      {metrics_epi['accuracy']:.1%} ({metrics_epi['correct_cases']}/{metrics_epi['total_cases']})")
    w(f"  Standard Macro-F1:       {metrics_std['macro_f1']:.4f}")
    w(f"  Epistemic Macro-F1:      {metrics_epi['macro_f1']:.4f}")
    w(f"  Standard MCC:            {metrics_std['mcc']:.4f}")
    w(f"  Epistemic MCC:           {metrics_epi['mcc']:.4f}")
    w()
    if ci_std:
        w(f"  Standard Accuracy 95% CI:  [{ci_std['accuracy_95ci'][0]:.1%}, {ci_std['accuracy_95ci'][1]:.1%}]")
        w(f"  Epistemic Accuracy 95% CI: [{ci_epi['accuracy_95ci'][0]:.1%}, {ci_epi['accuracy_95ci'][1]:.1%}]")
        w(f"  Standard Macro-F1 95% CI:  [{ci_std['macro_f1_95ci'][0]:.4f}, {ci_std['macro_f1_95ci'][1]:.4f}]")
        w(f"  Epistemic Macro-F1 95% CI: [{ci_epi['macro_f1_95ci'][0]:.4f}, {ci_epi['macro_f1_95ci'][1]:.4f}]")
        w()

    w("  Scoring Philosophy:")
    w("    Standard: unverified pairs -> OPPOSE (benchmark convention)")
    w("    Epistemic: unverified pairs -> UNCERTAIN (UNKNOWN != NEGATIVE)")
    w()

    # -- CATEGORY PERFORMANCE --
    w("-" * 78)
    w("2. CATEGORY PERFORMANCE")
    w("-" * 78)
    w()
    for cat_name, cat_data in category_summary.items():
        total = cat_data["total_cases"]
        correct_std = cat_data["correct_standard"]
        correct_epi = cat_data["correct_epistemic"]
        w(f"  {cat_name}:")
        w(f"    Cases: {total}")
        w(f"    Standard Accuracy: {correct_std}/{total} = {correct_std/total:.1%}" if total > 0 else "    Standard Accuracy: N/A")
        w(f"    Epistemic Accuracy: {correct_epi}/{total} = {correct_epi/total:.1%}" if total > 0 else "    Epistemic Accuracy: N/A")
        w(f"    Prediction Distribution: {cat_data['predictions']}")
        w()

    # -- CONFUSION MATRICES --
    w("-" * 78)
    w("3. CONFUSION MATRICES")
    w("-" * 78)
    w()
    labels = ["SUPPORT", "OPPOSE", "UNCERTAIN"]

    w("  3a. Standard 3-Class Confusion Matrix")
    w("       (rows = expected, columns = predicted)")
    w()
    cm_std = metrics_std["confusion_matrix"]
    w(f"  {'':>12s}  {'SUPPORT':>8s}  {'OPPOSE':>8s}  {'UNCERTAIN':>10s}")
    for row_label in labels:
        vals = [str(cm_std[row_label][col]) for col in labels]
        w(f"  {row_label:>12s}  {vals[0]:>8s}  {vals[1]:>8s}  {vals[2]:>10s}")
    w()

    w("  3b. Epistemic 3-Class Confusion Matrix")
    w("       (rows = expected, columns = predicted)")
    w()
    cm_epi = metrics_epi["confusion_matrix"]
    w(f"  {'':>12s}  {'SUPPORT':>8s}  {'OPPOSE':>8s}  {'UNCERTAIN':>10s}")
    for row_label in labels:
        vals = [str(cm_epi[row_label][col]) for col in labels]
        w(f"  {row_label:>12s}  {vals[0]:>8s}  {vals[1]:>8s}  {vals[2]:>10s}")
    w()

    # -- PER-CLASS METRICS --
    w("-" * 78)
    w("4. PER-CLASS METRICS")
    w("-" * 78)
    w()
    w("  4a. Standard Scoring:")
    w(f"  {'Class':>12s}  {'Precision':>10s}  {'Recall':>8s}  {'F1':>8s}  {'Support':>8s}")
    for k in labels:
        pc = metrics_std["per_class"][k]
        w(f"  {k:>12s}  {pc['precision']:>10.4f}  {pc['recall']:>8.4f}  {pc['f1']:>8.4f}  {pc['support']:>8d}")
    w()
    w("  4b. Epistemic Scoring:")
    w(f"  {'Class':>12s}  {'Precision':>10s}  {'Recall':>8s}  {'F1':>8s}  {'Support':>8s}")
    for k in labels:
        pc = metrics_epi["per_class"][k]
        w(f"  {k:>12s}  {pc['precision']:>10.4f}  {pc['recall']:>8.4f}  {pc['f1']:>8.4f}  {pc['support']:>8d}")
    w()

    # -- DERIVED DIAGNOSTIC METRICS --
    w("-" * 78)
    w("5. DERIVED DIAGNOSTIC METRICS")
    w("-" * 78)
    w()
    cat_e_cases = [r for r in results if r["category"] == "Established positive"]
    cat_f_cases = [r for r in results if r["category"] == "Verified negative"]
    cat_g_cases = [r for r in results if r["category"] == "Unverified"]
    cat_h_cases = [r for r in results if r["category"] == "Weak/indirect"]

    cat_e_correct = sum(1 for r in cat_e_cases if r["prediction"] == "SUPPORT")
    cat_f_oppose = sum(1 for r in cat_f_cases if r["prediction"] == "OPPOSE")
    false_promising = sum(1 for r in results if r["expected_3class_standard"] != "SUPPORT" and r["prediction"] == "SUPPORT")
    total_non_support = sum(1 for r in results if r["expected_3class_standard"] != "SUPPORT")

    w(f"  Category E Recovery (Established -> SUPPORT): {cat_e_correct}/{len(cat_e_cases)}")
    w(f"  Category F Recall (Verified Negative -> OPPOSE): {cat_f_oppose}/{len(cat_f_cases)}")
    w(f"  False-PROMISING Rate: {false_promising}/{total_non_support} = {false_promising/total_non_support:.1%}" if total_non_support > 0 else "  False-PROMISING Rate: N/A")
    w()

    # -- ERROR TAXONOMY --
    w("-" * 78)
    w("6. ERROR TAXONOMY")
    w("-" * 78)
    w()
    if error_taxonomy:
        taxonomy_counts = Counter(e["error_class"] for e in error_taxonomy)
        for error_class, count in taxonomy_counts.most_common():
            w(f"  {error_class}: {count}")
        w()
        w("  Detailed Errors:")
        for err in error_taxonomy:
            w(f"    {err['case_id']} {err['drug']} -> {err['disease']}")
            w(f"      Category: {err['category']}")
            w(f"      Expected (std): {err['expected_standard']} | Expected (epi): {err['expected_epistemic']}")
            w(f"      Predicted: {err['predicted']} ({err['recommendation']})")
            w(f"      Error Class: {err['error_class']}")
            w(f"      SS={err['support_score']:.3f} MS={err['mechanistic_score']:.3f} RS={err['risk_score']:.3f} Opp={err['opposition_score']:.3f}")
            w()
    else:
        w("  No errors detected.")
        w()

    # -- PER-CASE RESULTS --
    w("-" * 78)
    w("7. PER-CASE RESULTS")
    w("-" * 78)
    w()
    for r in results:
        std_match = "OK" if r["prediction"] == r["expected_3class_standard"] else "XX"
        epi_match = "OK" if r["prediction"] == r["expected_3class_epistemic"] else "XX"
        w(f"  {r['case_id']} {r['drug']} -> {r['disease']}")
        w(f"    Category: {r['category']} | Status: {r['status']} | Runtime: {r['runtime_seconds']}s")
        w(f"    Prediction: {r['prediction']} ({r['recommendation']})")
        w(f"    Expected (std): {r['expected_3class_standard']} {std_match} | Expected (epi): {r['expected_3class_epistemic']} {epi_match}")
        w(f"    SS={r['support_score']:.3f} MS={r['mechanistic_score']:.3f} RS={r['risk_score']:.3f} Opp={r['opposition_score']:.3f} ({r['opposition_level']})")
        w(f"    HQT={r['has_high_quality_therapeutic']} | Targets={r['target_count']} | Primary={r['primary_target']}")
        if r.get("decision_gate") and r["decision_gate"] != "NONE":
            gate_text = r["decision_gate"][:120]
            w(f"    Gate: {gate_text}")
        w()

    # -- METHODOLOGY --
    w("-" * 78)
    w("8. METHODOLOGY")
    w("-" * 78)
    w()
    w("  This evaluation uses a hold-out benchmark of 30 drug-disease pairs")
    w("  that are completely disjoint from the 25-case regression benchmark.")
    w("  Labels are evaluation-only ground truth and are never passed to the")
    w("  reasoning engine. The production pipeline receives only (drug, disease)")
    w("  and returns a recommendation independently of any benchmark label.")
    w()
    w("  Dual scoring addresses a fundamental epistemic question:")
    w("  Should 'no evidence found' count as a correct negative or as uncertainty?")
    w()
    w("  Standard scoring (UNKNOWN = NEGATIVE): Penalizes the system for not")
    w("  detecting that a pair is therapeutically invalid. This is the harsher metric.")
    w()
    w("  Epistemic scoring (UNKNOWN != NEGATIVE): Rewards the system for correctly")
    w("  expressing uncertainty about pairs where evidence simply does not exist.")
    w("  This reflects CYNTHERA's core epistemic principle: absence of evidence")
    w("  is not evidence of absence.")
    w()

    report_text = "\n".join(report_lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"\nResearch report written to: {output_path}")


# -----------------------------------------------------------------------------
# EVALUATION RUNNER ORCHESTRATION
# -----------------------------------------------------------------------------

async def run_evaluation(
    output_dir: str = "evaluation_outputs/30_case_holdout",
    resume: bool = False,
    smoke_test: bool = False,
    timeout_seconds: int = CASE_TIMEOUT_SECONDS,
):
    """Run the complete 30-case hold-out evaluation."""
    # Validate dataset integrity first
    validate_dataset_integrity()

    start_time = datetime.now()
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    jsonl_path = out_path / "results.jsonl"
    json_path = out_path / "results.json"
    metrics_path = out_path / "metrics.json"
    report_path = out_path / "research_report.txt"
    errors_path = out_path / "error_taxonomy.json"
    runtime_path = out_path / "runtime.csv"

    print("=" * 78)
    print("CYNTHERA -- 30-CASE HOLD-OUT RESEARCH EVALUATION")
    print(f"Timestamp: {start_time.isoformat()}")
    print(f"Output Directory: {out_path.resolve()}")
    print(f"Cache Version: {EvaluationCache._CACHE_VERSION}")
    print(f"Per-case Timeout: {timeout_seconds}s | Resume: {resume} | Smoke Test: {smoke_test}")
    print("=" * 78)

    db_path = "data/cynthera.db"
    initial_cache = get_cache_stats(db_path)
    print(f"Initial Cache: eval={initial_cache['evaluation_cache_rows']} rows, raw={initial_cache['raw_cache_rows']} rows")
    print("-" * 78)

    cases_to_run = HOLDOUT_CASES[:2] if smoke_test else HOLDOUT_CASES
    total_cases = len(cases_to_run)

    # Resume support
    existing_records: dict[str, dict[str, Any]] = {}
    if resume and jsonl_path.exists():
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    existing_records[rec["case_id"]] = rec
                except json.JSONDecodeError:
                    pass
        print(f"Resuming: found {len(existing_records)} existing records")

    orchestrator = MasterOrchestrator(
        db_path=db_path,
        use_cache=True,
    )

    results: list[dict[str, Any]] = []
    write_mode = "a" if (resume and jsonl_path.exists()) else "w"
    jsonl_file = open(jsonl_path, write_mode, encoding="utf-8")

    try:
        for idx, case in enumerate(cases_to_run, 1):
            cid = case.case_id
            drug = case.drug
            disease = case.disease

            if resume and cid in existing_records:
                rec = existing_records[cid]
                results.append(rec)
                print(f"[{idx:02d}/{total_cases:02d}] {cid} {drug} -> {disease}")
                print(f"      => reused (prediction={rec.get('prediction')}, {rec.get('runtime_seconds')}s)")
                continue

            print(f"[{idx:02d}/{total_cases:02d}] {cid} {drug} -> {disease}")

            rec = await evaluate_single_case(
                case=case,
                orchestrator=orchestrator,
                timeout_seconds=timeout_seconds,
            )

            jsonl_file.write(json.dumps(rec) + "\n")
            jsonl_file.flush()

            results.append(rec)

            std_match = "OK" if rec["prediction"] == rec["expected_3class_standard"] else "XX"
            epi_match = "OK" if rec["prediction"] == rec["expected_3class_epistemic"] else "XX"
            print(f"      => {rec['runtime_seconds']}s | {rec['prediction']} | std:{std_match} epi:{epi_match} | {rec['status']}")
            print()

    finally:
        jsonl_file.close()

    total_eval_duration = (datetime.now() - start_time).total_seconds()

    # -------------------------------------------------------------------------
    # ANALYSIS & METRICS
    # -------------------------------------------------------------------------

    # Standard scoring
    y_true_std = [r["expected_3class_standard"] for r in results]
    y_pred_all = [r["prediction"] for r in results]
    metrics_std = compute_metrics(y_true_std, y_pred_all)
    ci_std = bootstrap_ci(y_true_std, y_pred_all)

    # Epistemic scoring
    y_true_epi = [r["expected_3class_epistemic"] for r in results]
    metrics_epi = compute_metrics(y_true_epi, y_pred_all)
    ci_epi = bootstrap_ci(y_true_epi, y_pred_all)

    # Category performance
    categories = ["Established positive", "Verified negative", "Unverified", "Weak/indirect"]
    category_summary: dict[str, Any] = {}
    for cat in categories:
        cat_cases = [r for r in results if r["category"] == cat]
        correct_std = sum(1 for r in cat_cases if r["prediction"] == r["expected_3class_standard"])
        correct_epi = sum(1 for r in cat_cases if r["prediction"] == r["expected_3class_epistemic"])
        category_summary[cat] = {
            "total_cases": len(cat_cases),
            "correct_standard": correct_std,
            "correct_epistemic": correct_epi,
            "predictions": dict(Counter(r["prediction"] for r in cat_cases)),
        }

    # Error taxonomy
    error_taxonomy: list[dict[str, Any]] = []
    for r in results:
        is_std_error = r["prediction"] != r["expected_3class_standard"]
        is_epi_error = r["prediction"] != r["expected_3class_epistemic"]
        if is_std_error or is_epi_error:
            error_taxonomy.append({
                "case_id": r["case_id"],
                "drug": r["drug"],
                "disease": r["disease"],
                "category": r["category"],
                "expected_standard": r["expected_3class_standard"],
                "expected_epistemic": r["expected_3class_epistemic"],
                "predicted": r["prediction"],
                "recommendation": r["recommendation"],
                "support_score": r["support_score"],
                "mechanistic_score": r["mechanistic_score"],
                "risk_score": r["risk_score"],
                "opposition_score": r["opposition_score"],
                "has_high_quality_therapeutic": r["has_high_quality_therapeutic"],
                "error_class": classify_error(r),
                "is_standard_error": is_std_error,
                "is_epistemic_error": is_epi_error,
            })

    # -------------------------------------------------------------------------
    # WRITE OUTPUT FILES
    # -------------------------------------------------------------------------

    # 1. results.json
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # 2. runtime.csv
    with open(runtime_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "case_id", "drug", "disease", "category", "status", "prediction",
            "expected_std", "expected_epi", "runtime_seconds",
            "support_score", "mechanistic_score", "risk_score", "opposition_score",
            "has_hqt", "cache_hit",
        ])
        for r in results:
            writer.writerow([
                r["case_id"], r["drug"], r["disease"], r["category"], r["status"],
                r["prediction"], r["expected_3class_standard"], r["expected_3class_epistemic"],
                r["runtime_seconds"], r["support_score"], r["mechanistic_score"],
                r["risk_score"], r["opposition_score"], r["has_high_quality_therapeutic"],
                r["cache_hit"],
            ])

    # 3. metrics.json
    metrics_payload = {
        "evaluation_timestamp": start_time.isoformat(),
        "total_runtime_seconds": round(total_eval_duration, 2),
        "total_cases": len(results),
        "engine_version": "CYNTHERA v2.0",
        "rule_set_version": "3.2",
        "cache_version": EvaluationCache._CACHE_VERSION,
        "standard_scoring": {
            **metrics_std,
            **ci_std,
        },
        "epistemic_scoring": {
            **metrics_epi,
            **ci_epi,
        },
        "category_performance": category_summary,
        "error_count_standard": sum(1 for e in error_taxonomy if e["is_standard_error"]),
        "error_count_epistemic": sum(1 for e in error_taxonomy if e["is_epistemic_error"]),
    }
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2)

    # 4. error_taxonomy.json
    with open(errors_path, "w", encoding="utf-8") as f:
        json.dump(error_taxonomy, f, indent=2)

    # 5. Research report
    generate_research_report(
        results=results,
        metrics_std=metrics_std,
        metrics_epi=metrics_epi,
        ci_std=ci_std,
        ci_epi=ci_epi,
        category_summary=category_summary,
        error_taxonomy=error_taxonomy,
        output_path=report_path,
        total_runtime=total_eval_duration,
    )

    # -------------------------------------------------------------------------
    # CONSOLE SUMMARY
    # -------------------------------------------------------------------------

    print()
    print("=" * 78)
    print("30-CASE HOLD-OUT EVALUATION COMPLETE")
    print("=" * 78)
    print()
    print(f"  Standard Accuracy:    {metrics_std['accuracy']:.1%} ({metrics_std['correct_cases']}/{metrics_std['total_cases']})")
    print(f"  Epistemic Accuracy:   {metrics_epi['accuracy']:.1%} ({metrics_epi['correct_cases']}/{metrics_epi['total_cases']})")
    print(f"  Standard Macro-F1:    {metrics_std['macro_f1']:.4f}")
    print(f"  Epistemic Macro-F1:   {metrics_epi['macro_f1']:.4f}")
    print(f"  Standard MCC:         {metrics_std['mcc']:.4f}")
    print(f"  Epistemic MCC:        {metrics_epi['mcc']:.4f}")
    print()
    print("  Category Performance:")
    for cat_name, cat_data in category_summary.items():
        total = cat_data["total_cases"]
        cs = cat_data["correct_standard"]
        ce = cat_data["correct_epistemic"]
        print(f"    {cat_name}: std={cs}/{total} epi={ce}/{total}")
    print()
    print(f"  Total Runtime: {total_eval_duration:.1f}s")
    print(f"  Outputs: {out_path.resolve()}")
    print()


# -----------------------------------------------------------------------------
# CLI ENTRY POINT
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CYNTHERA 30-Case Hold-Out Research Evaluation"
    )
    parser.add_argument(
        "--output-dir",
        default="evaluation_outputs/30_case_holdout",
        help="Output directory for evaluation artifacts",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing results.jsonl",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run only 2 cases for smoke testing",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=CASE_TIMEOUT_SECONDS,
        help=f"Per-case timeout in seconds (default: {CASE_TIMEOUT_SECONDS})",
    )
    args = parser.parse_args()

    asyncio.run(run_evaluation(
        output_dir=args.output_dir,
        resume=args.resume,
        smoke_test=args.smoke_test,
        timeout_seconds=args.timeout,
    ))


if __name__ == "__main__":
    main()
