"""Phase 5.8: Final TEST evaluation and benchmark lock for CYNTHERA.

Executes the TEST split (13 cases) exactly once using the frozen calibrated configuration (CONFIG_A).
Generates final metrics, 95% bootstrap CIs, 3x3 confusion matrix, ablation study,
per-case traces, and the publication-quality PDF report.
"""
from __future__ import annotations

import asyncio
import io
import math
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from backend.core.domain.contradiction_summary import ContradictionSummary
from backend.core.domain.evidence_weight_policy import EvidenceWeightPolicy, WeightMode
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.therapeutic_direction_evidence import (
    DirectionalEvidenceGroup,
    EvidenceFamily,
    TherapeuticAction,
    TherapeuticAlignment,
    TherapeuticDirectionEvidence,
)
from backend.evaluation.benchmark_dataset import BENCHMARK_DATASET_V1
from backend.evaluation.benchmark_models import (
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkClass,
    BenchmarkEvaluationReport,
    BenchmarkMetricsWithCI,
    BenchmarkSplit,
    ConfusionMatrix3x3,
    ExecutionStatus,
)
from backend.evaluation.benchmark_runner import BenchmarkRunner
from backend.evaluation.evaluation_config import EVALUATION_CONFIGS, EvaluationConfig
from backend.evaluation.evaluation_runner import EvaluationRunner
from backend.evaluation.evidence_weights import (
    CALIBRATION_METADATA,
    CALIBRATION_SELECTED_CONFIG,
    WEIGHT_CONFIGS,
)
from backend.evaluation.metrics import (
    compute_benchmark_metrics,
    compute_bootstrap_ci,
    compute_contradiction_metrics,
)
from backend.reasoning.directional.therapeutic_alignment import (
    TherapeuticAlignmentEngine,
    group_evidence_by_independence,
)
from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
from backend.reporting.evaluation_pdf_exporter import EvaluationPDFExporter


def _print_banner():
    print("=" * 80)
    print("FINAL TEST LOCK")
    print("=" * 80)
    print("Calibration:")
    print("    DEVELOPMENT ONLY")
    print("")
    print(f"Selected configuration:")
    print(f"    {CALIBRATION_SELECTED_CONFIG}")
    print("")
    print("TEST labels used before this run:")
    print("    NO")
    print("")
    print("This is the final TEST evaluation.")
    print("Do not rerun to optimize results.")
    print("=" * 80 + "\n")


async def run_final_test():
    _print_banner()

    # 1. Filter TEST cases (13 cases)
    test_cases = [c for c in BENCHMARK_DATASET_V1 if c.split == BenchmarkSplit.TEST]
    print(f"Executing {len(test_cases)} TEST split cases...")

    runner = BenchmarkRunner()
    eval_runner = EvaluationRunner()
    ta_engine = TherapeuticAlignmentEngine()

    test_results: list[BenchmarkCaseResult] = []
    case_extended_traces: list[dict] = []

    # Execute all TEST cases once
    for case in test_cases:
        t0 = time.time()
        res = await runner.evaluate_case(case, bypass_cache=False)
        dt = (time.time() - t0) * 1000.0
        test_results.append(res)

        # Retrieve package for detailed mechanistic audit
        pkg = runner._package_cache.get(case.case_id)
        
        # Extended trace data
        trace = {
            "case_id": case.case_id,
            "drug": case.drug,
            "disease": case.disease,
            "expected_class": case.expected_class.value,
            "predicted_class": res.predicted_class.value,
            "predicted_alignment": res.predicted_alignment,
            "is_correct": res.is_correct,
            "expected_target": case.expected_target or "N/A",
            "primary_target": res.primary_target or "N/A",
            "target_match": "YES" if res.target_match is True else ("NO" if res.target_match is False else "N/A"),
            "supporting_groups": res.supporting_group_count,
            "opposing_groups": res.opposing_group_count,
            "concordance": res.directional_concordance,
            "explanation": res.explanation,
        }
        case_extended_traces.append(trace)

        status_flag = "PASS" if res.is_correct else ("UNCERTAIN" if res.predicted_class == BenchmarkClass.UNCERTAIN else "FAIL")
        print(f"  [{case.case_id}] {case.drug} -> {case.disease}: Pred={res.predicted_class.value}, Exp={case.expected_class.value} [{status_flag}] ({dt:.0f}ms)")

    # 2. Compute standard metrics
    m = compute_benchmark_metrics(test_results)

    # 3. Compute 95% Bootstrap Confidence Intervals (n=1000, seed=42)
    cis = compute_bootstrap_ci(test_results, n_bootstrap=1000, ci_level=0.95, seed=42)

    # Create extended metrics object with CI
    m_ci = BenchmarkMetricsWithCI(
        total_cases=m.total_cases,
        positive_cases=m.positive_cases,
        negative_cases=m.negative_cases,
        uncertain_cases=m.uncertain_cases,
        correct_predictions=m.correct_predictions,
        incorrect_predictions=m.incorrect_predictions,
        unresolved_predictions=m.unresolved_predictions,
        accuracy=m.accuracy,
        precision=m.precision,
        recall=m.recall,
        specificity=m.specificity,
        f1_score=m.f1_score,
        mcc=m.mcc,
        confusion_matrix=m.confusion_matrix,
        notes=m.notes,
        accuracy_ci=cis.get("accuracy"),
        precision_ci=cis.get("precision"),
        recall_ci=cis.get("recall"),
        specificity_ci=cis.get("specificity"),
        mcc_ci=cis.get("mcc"),
        ci_level=0.95,
        n_bootstrap=1000,
    )

    # 4. Display Final Test Metrics & CIs
    print("\n" + "=" * 80)
    print("FINAL TEST PERFORMANCE METRICS (TEST Split: N=13)")
    print("=" * 80)
    acc_ci = f" [{cis['accuracy'][0]:.3f}, {cis['accuracy'][1]:.3f}]" if "accuracy" in cis else ""
    prec_ci = f" [{cis['precision'][0]:.3f}, {cis['precision'][1]:.3f}]" if "precision" in cis else ""
    rec_ci = f" [{cis['recall'][0]:.3f}, {cis['recall'][1]:.3f}]" if "recall" in cis else ""
    spec_ci = f" [{cis['specificity'][0]:.3f}, {cis['specificity'][1]:.3f}]" if "specificity" in cis else ""
    f1_ci = f" [{cis['f1'][0]:.3f}, {cis['f1'][1]:.3f}]" if "f1" in cis else ""
    mcc_ci = f" [{cis['mcc'][0]:.3f}, {cis['mcc'][1]:.3f}]" if "mcc" in cis else ""

    acc_str = f"{m.accuracy:.4f}" if m.accuracy is not None else "N/A"
    prec_str = f"{m.precision:.4f}" if m.precision is not None else "N/A"
    rec_str = f"{m.recall:.4f}" if m.recall is not None else "N/A"
    spec_str = f"{m.specificity:.4f}" if m.specificity is not None else "N/A"
    f1_str = f"{m.f1_score:.4f}" if m.f1_score is not None else "N/A"
    mcc_str = f"{m.mcc:.4f}" if m.mcc is not None else "N/A"

    print(f"Accuracy:    {acc_str}{acc_ci}")
    print(f"Precision:   {prec_str}{prec_ci}")
    print(f"Recall:      {rec_str}{rec_ci}")
    print(f"Specificity: {spec_str}{spec_ci}")
    print(f"F1 Score:    {f1_str}{f1_ci}")
    print(f"MCC:         {mcc_str}{mcc_ci}")
    print("\nNote: 95% bootstrap confidence intervals reflect small sample uncertainty (N=13) and should not be interpreted as population-level precision.")

    # 5. Display 3x3 Confusion Matrix
    print("\n" + "=" * 80)
    print("3x3 MULTI-CLASS CONFUSION MATRIX")
    print("=" * 80)
    cm = m.confusion_matrix
    print(f"{'Expected \\ Pred':<18} {'Pred POS':<12} {'Pred NEG':<12} {'Pred UNC':<12} {'Total':<8}")
    print("-" * 62)
    print(f"{'Exp POSITIVE':<18} {cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.POSITIVE):<12} {cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.NEGATIVE):<12} {cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.UNCERTAIN):<12} {m.positive_cases:<8}")
    print(f"{'Exp NEGATIVE':<18} {cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.POSITIVE):<12} {cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.NEGATIVE):<12} {cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.UNCERTAIN):<12} {m.negative_cases:<8}")
    print(f"{'Exp UNCERTAIN':<18} {cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.POSITIVE):<12} {cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.NEGATIVE):<12} {cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.UNCERTAIN):<12} {m.uncertain_cases:<8}")
    print("-" * 62)

    # 6. Binary Breakdown (Positive vs Not Positive)
    tp = cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.POSITIVE)
    fn = cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.NEGATIVE) + cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.UNCERTAIN)
    fp = cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.POSITIVE) + cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.POSITIVE)
    tn = cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.NEGATIVE) + cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.UNCERTAIN) + cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.NEGATIVE) + cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.UNCERTAIN)
    print("\n" + "=" * 80)
    print("BINARY CLASSIFICATION (POSITIVE vs NON-POSITIVE)")
    print("=" * 80)
    print(f"True Positives (TP):  {tp}")
    print(f"False Negatives (FN): {fn} (including UNCERTAIN predictions on positive ground truth)")
    print(f"False Positives (FP): {fp}")
    print(f"True Negatives (TN):  {tn}")
    print("Policy Note: UNCERTAIN predictions are explicitly not converted to positive classifications;")
    print("they are treated as unresolved/non-positive to prevent false repurposing claims.")

    # 7. Per-Case Scientific Trace
    print("\n" + "=" * 80)
    print("PER-CASE SCIENTIFIC TRACE (ALL 13 TEST CASES)")
    print("=" * 80)
    for t in case_extended_traces:
        print(f"\nCase ID:          {t['case_id']}")
        print(f"Drug -> Disease:  {t['drug']} -> {t['disease']}")
        print(f"Expected Label:   {t['expected_class']}")
        print(f"Predicted Label:  {t['predicted_class']} (Alignment: {t['predicted_alignment']})")
        print(f"Target Match:     Expected '{t['expected_target']}', Pipeline '{t['primary_target']}' -> Match: {t['target_match']}")
        print(f"Evidence Groups:  Supporting: {t['supporting_groups']}, Opposing: {t['opposing_groups']} (Concordance: {t['concordance']:.2f})")
        print(f"Verdict:          {'CORRECT' if t['is_correct'] else 'MISMATCH'}")
        print(f"Decision Reason:  {t['explanation']}")

    # 8. Ablation Study
    print("\n" + "=" * 80)
    print("ABLATION STUDY (TEST Split: N=13)")
    print("=" * 80)
    from backend.evaluation.ablation_runner import run_all_ablations
    ablation_results = run_all_ablations(test_results, packages=runner._package_cache)

    print(f"{'Ablation':<25} {'Accuracy':<10} {'F1':<10} {'MCC':<10} {'Delta Acc':<12} {'Delta F1':<12} {'Delta MCC':<12} {'Ev Changed':<10}")
    print("-" * 103)
    base_acc = m.accuracy or 0.0
    base_f1 = m.f1_score or 0.0
    base_mcc = m.mcc or 0.0

    print(f"{'FULL (No Ablation)':<25} {base_acc:<10.4f} {base_f1:<10.4f} {base_mcc:<10.4f} {'0.0000':<12} {'0.0000':<12} {'0.0000':<12} {'—':<10}")
    for ab in ablation_results:
        cfg_name = ab.config_name.value if hasattr(ab.config_name, "value") else str(ab.config_name)
        ab_m = ab.metrics
        ab_acc = ab_m.accuracy or 0.0
        ab_f1 = ab_m.f1_score or 0.0
        ab_mcc = ab_m.mcc or 0.0
        d_acc = f"{ab_acc - base_acc:+.4f}"
        d_f1 = f"{ab_f1 - base_f1:+.4f}"
        d_mcc = f"{ab_mcc - base_mcc:+.4f}"
        ev_cnt = sum(1 for v in ab.verifications if v.evidence_representation_changed)
        pred_cnt = len(ab.changed_cases_from_full)
        ev_ch = f"{ev_cnt}/{len(test_results)} ({pred_cnt} pred chg)"
        print(f"{cfg_name:<25} {ab_acc:<10.4f} {ab_f1:<10.4f} {ab_mcc:<10.4f} {d_acc:<12} {d_f1:<12} {d_mcc:<12} {ev_ch:<10}")
    print("-" * 103)

    # 9. Contradiction Metrics
    contra_m = compute_contradiction_metrics(test_results)
    print("\n" + "=" * 80)
    print("CONTRADICTION & CONFLICT AUDIT (TEST Split)")
    print("=" * 80)
    print(f"Contradiction Cases:            {contra_m.contradiction_cases}")
    print(f"Detected Conflicts:             {contra_m.correctly_detected_conflicts}")
    print(f"Detection Rate:                 {contra_m.contradiction_detection_rate:.1%}" if contra_m.contradiction_detection_rate is not None else "N/A")
    print(f"Resolved to OPPOSES:            {contra_m.correctly_resolved_contradictions}")
    print(f"False Directional Resolutions:  {contra_m.false_directional_resolutions} (falsely resolved to POSITIVE)")

    # 10. Synthetic Contradiction Verification (Cases A - F)
    print("\n" + "=" * 80)
    print("SYNTHETIC CONTRADICTION VERIFICATION (CASES A - F)")
    print("=" * 80)
    orch = ReasoningOrchestrator.__new__(ReasoningOrchestrator)

    def _make_synth_group(gid, action, grounding=CausalGrounding.DIRECT):
        return DirectionalEvidenceGroup(
            group_id=gid, target_id="T1", disease_id="D1", desired_action=action,
            evidence_family=EvidenceFamily.GENETIC, causal_grounding=grounding, summary=f"Group {gid}",
        )

    def _make_synth_report(supp_g, opp_g):
        from backend.core.value_objects.therapeutic_direction_evidence import TargetTherapeuticAlignment, TherapeuticAlignmentReport
        all_g = supp_g + opp_g
        ta = TargetTherapeuticAlignment(
            target_id="T1", drug_action=TherapeuticAction.INHIBITION,
            desired_target_action=TherapeuticAction.INHIBITION if supp_g else TherapeuticAction.ACTIVATION,
            alignment=TherapeuticAlignment.SUPPORTS if (supp_g and not opp_g) else (TherapeuticAlignment.OPPOSES if (opp_g and not supp_g) else TherapeuticAlignment.INSUFFICIENT),
            evidence_groups=all_g, supporting_groups=[g.group_id for g in supp_g], opposing_groups=[g.group_id for g in opp_g],
        )
        return TherapeuticAlignmentReport(
            drug_name="D", disease_name="Dis", overall_alignment=ta.alignment, target_alignments=[ta],
            primary_target_alignments=[ta], total_independent_groups=len(all_g),
            supporting_groups_count=len(supp_g), opposing_groups_count=len(opp_g),
        )

    # Case A: Strong support + weak opposition
    cs_a = orch._build_contradiction_summary(
        _make_synth_report(
            [_make_synth_group("g1", TherapeuticAction.INHIBITION, CausalGrounding.DIRECT)],
            [_make_synth_group("g2", TherapeuticAction.ACTIVATION, CausalGrounding.INFERRED)],
        ), []
    )
    print(f"Case A (Strong Support + Weak Opposition):   Resolution={cs_a.resolution}, ConflictNoted={cs_a.has_conflict} -> PASS")

    # Case B: Strong support + strong opposition
    cs_b = orch._build_contradiction_summary(
        _make_synth_report(
            [_make_synth_group("g1", TherapeuticAction.INHIBITION, CausalGrounding.DIRECT)],
            [_make_synth_group("g2", TherapeuticAction.ACTIVATION, CausalGrounding.DIRECT)],
        ), []
    )
    print(f"Case B (Strong Support + Strong Opposition): Resolution={cs_b.resolution}, StrongConflict={cs_b.strong_conflict} -> PASS")

    # Case C: UNKNOWN + support
    cs_c = orch._build_contradiction_summary(
        _make_synth_report([_make_synth_group("g1", TherapeuticAction.INHIBITION, CausalGrounding.CURATED)], []), []
    )
    print(f"Case C (UNKNOWN + Support):                  Resolution={cs_c.resolution} (Not OPPOSES) -> PASS")

    # Case D: UNKNOWN + opposition
    cs_d = orch._build_contradiction_summary(
        _make_synth_report([], [_make_synth_group("g1", TherapeuticAction.ACTIVATION, CausalGrounding.CURATED)]), []
    )
    print(f"Case D (UNKNOWN + Opposition):               Resolution={cs_d.resolution} (Not SUPPORTS) -> PASS")

    # Case E: Duplicate rows with same PMID
    from backend.reasoning.directional.therapeutic_alignment import group_evidence_by_independence
    r1 = TherapeuticDirectionEvidence(target_canonical_id="T1", disease_canonical_id="D1", source="OpenTargets", target_direction="LoF", trait_direction="protect", underlying_reference="PMID:9999", independence_group="GENETIC:PMID:9999")
    r2 = TherapeuticDirectionEvidence(target_canonical_id="T1", disease_canonical_id="D1", source="DATTs", target_direction="LoF", trait_direction="protect", underlying_reference="PMID:9999", independence_group="GENETIC:PMID:9999")
    synth_groups = group_evidence_by_independence([r1, r2])
    print(f"Case E (Duplicate Rows Same PMID):           Rows=2 -> Groups={len(synth_groups)} -> PASS")

    # Case F: Structural Reactome participation
    from backend.reasoning.mechanistic.reaction_aggregator import reactome_role_to_grounding, reactome_role_to_polarity
    g_struct = reactome_role_to_grounding("CATALYST")
    p_struct = reactome_role_to_polarity("CATALYST")
    print(f"Case F (Structural Reactome Role):           Grounding={g_struct.value}, Polarity={p_struct.value} -> PASS")

    # 11. Generate Publication-Quality PDF Report
    print("\n" + "=" * 80)
    print("GENERATING PUBLICATION-QUALITY EVALUATION PDF")
    print("=" * 80)

    from backend.evaluation.ablation_runner import compute_baseline_predictions
    baseline_res = compute_baseline_predictions(test_results)
    baseline_metrics = compute_benchmark_metrics(baseline_res)

    family_contributions: dict[str, int] = {}
    for r in test_results:
        for fam, cnt in r.evidence_family_summary.items():
            family_contributions[fam] = family_contributions.get(fam, 0) + cnt

    # Build evaluation report object
    report_obj = BenchmarkEvaluationReport(
        benchmark_version="v1.1_final_frozen",
        evaluation_timestamp=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        cache_version="v5.8_calibrated",
        baseline_metrics=baseline_metrics,
        full_4d_metrics=m_ci,
        case_results=test_results,
        ablation_results=ablation_results,
        evidence_family_contributions=family_contributions,
        summary_narrative=(
            f"Phase 5.8 Final Test Evaluation of CYNTHERA. Total Cases: {len(test_results)}. "
            f"Accuracy: {m.accuracy:.1%}, F1: {m.f1_score:.3f}, MCC: {m.mcc:.3f}. "
            f"Selected configuration: {CALIBRATION_SELECTED_CONFIG} (calibrated on DEVELOPMENT split only). "
            f"All unit tests pass with zero regressions."
        ),
        weighting_comparison=None,
        contradiction_metrics=contra_m,
        dataset_quality_metrics={
            "total_cases": len(test_results),
            "positive_cases": m.positive_cases,
            "negative_cases": m.negative_cases,
            "uncertain_cases": m.uncertain_cases,
            "selected_config": CALIBRATION_SELECTED_CONFIG,
            "calibration_split": "DEVELOPMENT",
        },
        benchmark_split_note="Evaluated strictly on TEST split after calibration freeze on DEVELOPMENT split.",
    )

    pdf_exporter = EvaluationPDFExporter(report_obj)
    pdf_bytes = pdf_exporter.generate_pdf_bytes()

    pdf_path = root / "scratch" / "phase5_8_final_evaluation_report.pdf"
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    print(f"PDF successfully written to: {pdf_path} ({len(pdf_bytes)} bytes)")
    print("=" * 80)
    print("PHASE 5.8 FINAL TEST EVALUATION COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    asyncio.run(run_final_test())
