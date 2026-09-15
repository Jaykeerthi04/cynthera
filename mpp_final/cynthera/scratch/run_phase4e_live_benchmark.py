"""Live execution script for Phase 4E.4 Refined Benchmark & Comparative Evaluation."""
from __future__ import annotations

import asyncio
import os
import sys
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.abspath("."))

from backend.evaluation.benchmark_runner import BenchmarkRunner
from backend.evaluation.benchmark_models import BenchmarkClass
from backend.evaluation.benchmark_dataset import BENCHMARK_DATASET_V1, get_directionally_suitable_negatives, get_unsuitable_negatives
from backend.reporting.evaluation_pdf_exporter import EvaluationPDFExporter
from backend.evaluation.evaluation_config import EVALUATION_CONFIGS
from backend.evaluation.evidence_weights import WEIGHT_CONFIGS
from backend.evaluation.evaluation_runner import EvaluationRunner


async def main():
    print("=" * 85)
    print("CYNTHERA PHASE 4E.4 — REFINED BENCHMARK & COMPARATIVE EVALUATION")
    print("=" * 85)

    runner = BenchmarkRunner()
    report = await runner.run_benchmark(
        cases=BENCHMARK_DATASET_V1,
        bypass_cache=False,
        include_ablations=True,
        include_weighting_comparison=True,
    )

    print("\n" + "=" * 60)
    print("1. OVERALL PERFORMANCE METRICS (EQUAL-VOTE FULL 4D)")
    print("=" * 60)
    m = report.full_4d_metrics
    b = report.baseline_metrics
    print(f"Total Cases:     {m.total_cases} ({m.positive_cases}P / {m.negative_cases}N / {m.uncertain_cases}U)")
    print(f"Correct Preds:   {m.correct_predictions}/{m.total_cases}")
    acc_s = f"{m.accuracy:.1%}" if m.accuracy is not None else "N/A"
    b_acc_s = f"{b.accuracy:.1%}" if b.accuracy is not None else "N/A"
    print(f"Accuracy:        {acc_s} (Baseline: {b_acc_s})")
    prec_s = f"{m.precision:.1%}" if m.precision is not None else "N/A"
    b_prec_s = f"{b.precision:.1%}" if b.precision is not None else "N/A"
    print(f"Precision:       {prec_s} (Baseline: {b_prec_s})")
    rec_s = f"{m.recall:.1%}" if m.recall is not None else "N/A"
    b_rec_s = f"{b.recall:.1%}" if b.recall is not None else "N/A"
    print(f"Recall:          {rec_s} (Baseline: {b_rec_s})")
    spec_s = f"{m.specificity:.1%}" if m.specificity is not None else "N/A"
    b_spec_s = f"{b.specificity:.1%}" if b.specificity is not None else "N/A"
    print(f"Specificity:     {spec_s} (Baseline: {b_spec_s})")
    f1_s = f"{m.f1_score:.3f}" if m.f1_score is not None else "N/A"
    b_f1_s = f"{b.f1_score:.3f}" if b.f1_score is not None else "N/A"
    print(f"F1 Score:        {f1_s} (Baseline: {b_f1_s})")
    mcc_s = f"{m.mcc:.3f}" if m.mcc is not None else "N/A"
    b_mcc_s = f"{b.mcc:.3f}" if b.mcc is not None else "N/A"
    print(f"MCC:             {mcc_s} (Baseline: {b_mcc_s})")

    print("\n" + "=" * 60)
    print("2. 3x3 CONFUSION MATRIX")
    print("=" * 60)
    cm = m.confusion_matrix
    print(f"Exp POSITIVE -> Pred: P={cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.POSITIVE)}, N={cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.NEGATIVE)}, U={cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.UNCERTAIN)}")
    print(f"Exp NEGATIVE -> Pred: P={cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.POSITIVE)}, N={cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.NEGATIVE)}, U={cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.UNCERTAIN)}")
    print(f"Exp UNCERTAIN -> Pred: P={cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.POSITIVE)}, N={cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.NEGATIVE)}, U={cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.UNCERTAIN)}")

    print("\n" + "=" * 60)
    print("3. CONTRADICTION & CONFLICT RESOLUTION METRICS")
    print("=" * 60)
    cm_m = report.contradiction_metrics
    if cm_m:
        print(f"Contradiction Cases (Ground-truth Opposition): {cm_m.contradiction_cases}")
        print(f"Balanced Conflict Cases:                       {cm_m.balanced_conflict_cases}")
        print(f"Contradiction Detection Rate:                  {cm_m.contradiction_detection_rate:.1%}" if cm_m.contradiction_detection_rate is not None else "N/A")
        print(f"Contradiction Resolution Rate (to OPPOSES):    {cm_m.contradiction_resolution_rate:.1%}" if cm_m.contradiction_resolution_rate is not None else "N/A")
        print(f"Balanced Conflict -> INSUFFICIENT Rate:        {cm_m.balanced_conflict_insufficient_rate:.1%}" if cm_m.balanced_conflict_insufficient_rate is not None else "N/A")
        print(f"False Directional Resolution Rate (to SUPP):   {cm_m.false_directional_resolution_rate:.1%}" if cm_m.false_directional_resolution_rate is not None else "N/A")

    print("\n" + "=" * 60)
    print("4. PER-CASE EVALUATION RESULTS")
    print("=" * 60)
    for cr in report.case_results:
        is_pass = "PASS" if cr.is_correct else "FAIL"
        print(f"[{is_pass}] {cr.case.case_id}: {cr.case.drug} -> {cr.case.disease}")
        print(f"       Expected: {cr.case.expected_class.value} | Predicted: {cr.predicted_class.value} ({cr.predicted_alignment})")
        print(f"       Target: {cr.primary_target} | Concordance: {cr.directional_concordance:.2f} (Supp: {cr.supporting_group_count} / Opp: {cr.opposing_group_count})")
        print(f"       Explanation: {cr.explanation}")

    print("\n" + "=" * 60)
    print("5. ABLATION STUDY RESULTS")
    print("=" * 60)
    for ab in report.ablation_results:
        m_ab = ab.metrics
        acc_s = f"{m_ab.accuracy:.1%}" if m_ab.accuracy is not None else "N/A"
        prec_s = f"{m_ab.precision:.1%}" if m_ab.precision is not None else "N/A"
        rec_s = f"{m_ab.recall:.1%}" if m_ab.recall is not None else "N/A"
        f1_s = f"{m_ab.f1_score:.3f}" if m_ab.f1_score is not None else "N/A"
        print(f"{ab.config_name.value:25} | Acc: {acc_s:6} | Prec: {prec_s:6} | Rec: {rec_s:6} | F1: {f1_s:6} | Shifted: {len(ab.changed_cases_from_full)}")
        for ch in ab.changed_cases_from_full:
            print(f"   -> Shifted: {ch.get('drug')} -> {ch.get('disease')}: {ch.get('full_prediction')} -> {ch.get('ablated_prediction')}")

    print("\n" + "=" * 60)
    print("6. EVIDENCE WEIGHTING COMPARISONS (EVALUATION-ONLY)")
    print("=" * 60)
    ev_runner = EvaluationRunner()
    for cfg_name in ["WEIGHTED_4D_A", "WEIGHTED_4D_B", "WEIGHTED_4D_C"]:
        cfg = EVALUATION_CONFIGS.get(cfg_name)
        if not cfg:
            continue
        wc = WEIGHT_CONFIGS.get(cfg.weight_config_name)
        if not wc:
            continue
        print(f"\nConfiguration: {cfg_name} (direct={wc.direct}, curated={wc.curated}, inferred={wc.inferred})")
        agrees = 0
        total_w = 0
        for r in report.case_results:
            pkg = runner._package_cache.get(r.case.case_id)
            if not pkg:
                continue
            w_res, _ = ev_runner.run_with_config(r.case, pkg, cfg, full_result=r)
            total_w += 1
            if w_res.predicted_class == r.predicted_class:
                agrees += 1
            status = "AGREE" if w_res.predicted_class == r.predicted_class else f"DIFF ({r.predicted_class.value} -> {w_res.predicted_class.value})"
            print(f"  {r.case.case_id:<14} {r.case.drug:<16} {status:<20} Supp: {w_res.supporting_group_count} / Opp: {w_res.opposing_group_count}")
        if total_w > 0:
            print(f"  Agreement with Equal-Vote: {agrees}/{total_w} ({agrees/total_w:.1%})")

    print("\n" + "=" * 60)
    print("7. EXPORTING REFINED EVALUATION PDF")
    print("=" * 60)
    exporter = EvaluationPDFExporter(report)
    pdf_bytes = exporter.generate_pdf_bytes()
    pdf_path = "scratch/phase4e_refined_evaluation_report.pdf"
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"Wrote {len(pdf_bytes)} bytes to {pdf_path}")

    print("\n" + "=" * 85)
    print("PHASE 4E.4 BENCHMARK & COMPARATIVE EVALUATION COMPLETE!")
    print("=" * 85)


if __name__ == "__main__":
    asyncio.run(main())
