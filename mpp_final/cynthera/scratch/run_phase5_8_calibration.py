"""Phase 5.8: Development calibration script for CYNTHERA evidence weighting.

Evaluates evidence-weighting configurations on DEVELOPMENT CASES ONLY.
Strictly zero test-set exposure.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from backend.evaluation.benchmark_dataset import BENCHMARK_DATASET_V1
from backend.evaluation.benchmark_models import BenchmarkClass, BenchmarkSplit
from backend.evaluation.benchmark_runner import BenchmarkRunner
from backend.evaluation.evaluation_runner import EvaluationRunner
from backend.evaluation.evaluation_config import EVALUATION_CONFIGS
from backend.evaluation.evidence_weights import WEIGHT_CONFIGS
from backend.evaluation.metrics import compute_benchmark_metrics


async def run_calibration():
    print("=" * 80)
    print("CYNTHERA PHASE 5.8 DEVELOPMENT CALIBRATION")
    print("=" * 80)

    # 1. Filter splits
    dev_cases = [c for c in BENCHMARK_DATASET_V1 if c.split == BenchmarkSplit.DEVELOPMENT]
    test_cases = [c for c in BENCHMARK_DATASET_V1 if c.split == BenchmarkSplit.TEST]

    print(f"Cases:")
    print(f"    DEVELOPMENT = {len(dev_cases)}")
    print(f"    TEST = {len(test_cases)}")
    print(f"Calibration Split: DEVELOPMENT ONLY (TEST cases strictly isolated)\n")

    runner = BenchmarkRunner()
    eval_runner = EvaluationRunner()

    # 2. Evaluate all DEV cases to populate package cache
    print("Retrieving & evaluating DEVELOPMENT cases...")
    dev_full_results = []
    for c in dev_cases:
        t0 = time.time()
        res = await runner.evaluate_case(c, bypass_cache=False)
        dt = (time.time() - t0) * 1000.0
        dev_full_results.append(res)
        print(f"  [{c.case_id}] {c.drug} -> {c.disease}: Pred={res.predicted_class.value}, Exp={c.expected_class.value} ({dt:.0f}ms)")

    # 3. Evaluate each weighting configuration on DEV packages
    configs_to_test = ["WEIGHTED_4D_A", "WEIGHTED_4D_B", "WEIGHTED_4D_C"]
    config_results = {}
    config_metrics = {}

    # Also compute EQUAL_VOTE baseline on DEV
    eq_metrics = compute_benchmark_metrics(dev_full_results)
    config_metrics["EQUAL_VOTE (FULL_4D)"] = eq_metrics

    for cfg_name in configs_to_test:
        cfg = EVALUATION_CONFIGS[cfg_name]
        wc_name = cfg.weight_config_name
        wc = WEIGHT_CONFIGS[wc_name]

        res_list = []
        for c in dev_cases:
            pkg = runner._package_cache.get(c.case_id)
            if pkg is None:
                raise RuntimeError(f"Package for {c.case_id} missing from cache!")
            res, _ = eval_runner.run_with_config(case=c, package=pkg, config=cfg)
            res_list.append(res)

        config_results[wc_name] = res_list
        config_metrics[wc_name] = compute_benchmark_metrics(res_list)

    # 4. Display calibration comparison table
    print("\n" + "-" * 80)
    print(f"{'Configuration':<20} {'MCC':<10} {'F1':<10} {'Accuracy':<10} {'Precision':<10} {'Recall':<10} {'Specificity':<12} {'P / N / U':<10}")
    print("-" * 80)

    for name, m in config_metrics.items():
        mcc_str = f"{m.mcc:.4f}" if m.mcc is not None else "N/A"
        f1_str = f"{m.f1_score:.4f}" if m.f1_score is not None else "N/A"
        acc_str = f"{m.accuracy:.4f}" if m.accuracy is not None else "N/A"
        prec_str = f"{m.precision:.4f}" if m.precision is not None else "N/A"
        rec_str = f"{m.recall:.4f}" if m.recall is not None else "N/A"
        spec_str = f"{m.specificity:.4f}" if m.specificity is not None else "N/A"
        cm = m.confusion_matrix
        pos_p = sum(cm.get(e, "POSITIVE") for e in ("POSITIVE", "NEGATIVE", "UNCERTAIN"))
        neg_p = sum(cm.get(e, "NEGATIVE") for e in ("POSITIVE", "NEGATIVE", "UNCERTAIN"))
        unc_p = sum(cm.get(e, "UNCERTAIN") for e in ("POSITIVE", "NEGATIVE", "UNCERTAIN"))
        pnu = f"{pos_p} / {neg_p} / {unc_p}"
        print(f"{name:<20} {mcc_str:<10} {f1_str:<10} {acc_str:<10} {prec_str:<10} {rec_str:<10} {spec_str:<12} {pnu:<10}")
    print("-" * 80)

    # 5. Determine best configuration by MCC, then F1, then standard tie-breaker
    # Exclude baseline EQUAL_VOTE from candidate selection
    candidates = ["CONFIG_A", "CONFIG_B", "CONFIG_C"]
    
    def score_key(c_name):
        m = config_metrics[c_name]
        mcc_val = m.mcc if m.mcc is not None else -1.0
        f1_val = m.f1_score if m.f1_score is not None else -1.0
        acc_val = m.accuracy if m.accuracy is not None else -1.0
        # CONFIG_A preferred as standard scientific prior tie-breaker
        pref = 1.0 if c_name == "CONFIG_A" else 0.5
        return (round(mcc_val, 4), round(f1_val, 4), round(acc_val, 4), pref)

    best_config_name = max(candidates, key=score_key)
    best_m = config_metrics[best_config_name]

    print("\n" + "=" * 80)
    print("CALIBRATION DECISION")
    print("=" * 80)
    print(f"Selected configuration:       {best_config_name}")
    print(f"Selection metric:             MCC (Primary), F1 (Secondary)")
    print(f"Selection split:              DEVELOPMENT ONLY")
    print(f"TEST DATA USED FOR SELECTION: NO")
    print(f"Calibration status:           FROZEN")
    print("=" * 80)

    # 6. Detailed per-case audit on DEV for selected configuration
    print("\n" + "=" * 80)
    print("PER-CASE DEVELOPMENT AUDIT (Selected Configuration: " + best_config_name + ")")
    print("=" * 80)

    selected_results = config_results[best_config_name]
    for r in selected_results:
        c = r.case
        pkg = runner._package_cache.get(c.case_id)
        # Check alignment and groups
        supp = r.supporting_group_count
        opp = r.opposing_group_count
        concordance = r.directional_concordance
        print(f"\nCase ID:               {c.case_id}")
        print(f"Drug -> Disease:       {c.drug} -> {c.disease}")
        print(f"Expected Class:        {c.expected_class.value}")
        print(f"Predicted Class:       {r.predicted_class.value} (Alignment: {r.predicted_alignment})")
        print(f"Primary Target:        {r.primary_target or 'N/A'}")
        print(f"Directional Evidence:  Supporting groups: {supp}, Opposing groups: {opp} (Concordance: {concordance:.2f})")
        print(f"Explanation:           {r.explanation}")

    return best_config_name, config_metrics


if __name__ == '__main__':
    asyncio.run(run_calibration())
