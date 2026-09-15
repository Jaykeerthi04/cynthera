"""CYNTHERA — Final 100-Case Evaluation Runner.
Moment of Truth — Frozen System Evaluation.

Executes the production reasoning pipeline across the frozen 100-case dataset.
Strictly adheres to evaluation invariants:
- Zero reasoning system modifications
- Zero weight or threshold tuning
- Zero gold label alterations
- Live monitoring checkpoints
- Complete structured forensics per case
- Standard vs Epistemic evaluation
- Clinical trial attribution audit & opposition consistency check
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Path setup
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
logger = logging.getLogger("cynthera.eval_100_final")

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.core.enums.trial_attribution import TrialDrugRole, AttributionTextEvidence
from backend.infrastructure.cache.evaluation_cache import EvaluationCache

CASE_TIMEOUT_SECONDS = 180

RECOMMENDATION_TO_3CLASS: dict[str, str] = {
    "PROMISING": "SUPPORT",
    "NOT_RECOMMENDED": "OPPOSE",
    "UNCERTAIN": "UNCERTAIN",
    "INSUFFICIENT_DATA": "UNCERTAIN",
}


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
    return round(num / den, 4) if den > 0 else 0.0


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
    tp_counts: dict[str, int] = {}
    fp_counts: dict[str, int] = {}
    fn_counts: dict[str, int] = {}

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
        tp_counts[k] = tp
        fp_counts[k] = fp
        fn_counts[k] = fn

    macro_p = sum(precisions.values()) / 3.0
    macro_r = sum(recalls.values()) / 3.0
    macro_f1 = sum(f1s.values()) / 3.0

    # Balanced accuracy = average of recalls
    balanced_acc = macro_r

    support_counts = {k: sum(cm[k][p] for p in labels) for k in labels}
    weighted_f1 = sum(f1s[k] * support_counts[k] for k in labels) / total if total > 0 else 0.0
    mcc = compute_mcc_3x3(cm, labels)

    return {
        "total_cases": total,
        "correct_cases": correct,
        "accuracy": round(accuracy, 4),
        "balanced_accuracy": round(balanced_acc, 4),
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
                "tp": tp_counts[k],
                "fp": fp_counts[k],
                "fn": fn_counts[k],
                "support": support_counts[k],
            }
            for k in labels
        },
        "confusion_matrix": cm,
    }


def audit_clinical_trials(package: Any, candidate_drug: str) -> list[dict[str, Any]]:
    """Detailed audit of all clinical trials processed for the case."""
    trial_records = []
    trials = getattr(package, "clinical_trials", []) or []
    for t in trials:
        nct_id = getattr(t, "nct_id", "")
        phase = getattr(t, "phase", "")
        status = getattr(t, "status", "")
        study_design = getattr(t, "study_design", "")
        has_results = getattr(t, "has_results", False)
        
        # Trial attribution
        role = getattr(t, "candidate_drug_role", None)
        role_str = role.value if hasattr(role, "value") else (str(role) if role is not None else "OTHER_UNKNOWN")
        attr_rej = getattr(t, "attribution_rejected", False)
        attr_reason = getattr(t, "attribution_rejected_reason", None)
        attr_reason_str = attr_reason.value if hasattr(attr_reason, "value") else (str(attr_reason) if attr_reason is not None else "NONE")
        
        # Outcome / efficacy
        is_negative_efficacy = getattr(t, "negative_efficacy", False)
        neg_reason = getattr(t, "negative_efficacy_reason", "")
        endpoint_type = getattr(t, "endpoint_type", "UNKNOWN")
        direction = getattr(t, "direction", "UNKNOWN")
        
        # False attribution detection
        potential_false_attribution = False
        if is_negative_efficacy:
            if role in (
                TrialDrugRole.BACKGROUND_THERAPY,
                TrialDrugRole.BACKGROUND_CONSTANT_THERAPY,
                TrialDrugRole.ACTIVE_COMPARATOR,
                TrialDrugRole.COMPARATOR_ONLY,
                TrialDrugRole.PLACEBO_COMPARATOR,
                TrialDrugRole.CONCOMITANT_THERAPY,
            ):
                potential_false_attribution = True
            elif attr_rej:
                potential_false_attribution = True

        trial_records.append({
            "nct_id": nct_id,
            "phase": phase,
            "status": str(status),
            "study_design": str(study_design),
            "has_results": bool(has_results),
            "candidate_drug_role": role_str,
            "attribution_decision": "REJECTED" if attr_rej else "ATTRIBUTED",
            "attribution_rejection_reason": attr_reason_str,
            "endpoint_type": str(endpoint_type),
            "direction": str(direction),
            "negative_efficacy": bool(is_negative_efficacy),
            "negative_efficacy_reason": str(neg_reason),
            "potential_false_attribution": potential_false_attribution,
        })
    return trial_records


def verify_opposition_serialization(opp_assess: Any) -> tuple[bool, str]:
    """Check internal consistency of opposition assessment."""
    if opp_assess is None:
        return True, "None"
    
    score = float(getattr(opp_assess, "score", 0.0))
    level = getattr(opp_assess, "level", "NONE")
    qual_claims = int(getattr(opp_assess, "qualified_negative_claim_count", 0))
    groups = int(getattr(opp_assess, "independent_group_count", 0))
    rationale = getattr(opp_assess, "rationale", "")

    # Inconsistency checks
    if level in ("HIGH", "CRITICAL") and score == 0.0:
        return False, f"Inconsistency: level={level} but score=0.0"
    if level != "NONE" and qual_claims == 0 and score > 0.0:
        return False, f"Inconsistency: score={score} but qualified_claims=0"
    if score >= 0.40 and level == "NONE":
        return False, f"Inconsistency: score={score} but level=NONE"
    
    return True, "Consistent"


async def evaluate_case(
    case_manifest: dict[str, Any],
    orchestrator: MasterOrchestrator,
    timeout_seconds: int = CASE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Evaluate a single hypothesis through the full pipeline."""
    cid = case_manifest["case_id"]
    drug = case_manifest["drug"]
    disease = case_manifest["disease"]
    cat = case_manifest["category"]
    gold_label = case_manifest["gold_label"]
    std_gold = case_manifest["standard_gold"]
    epi_gold = case_manifest["epistemic_gold"]
    gold_source = case_manifest.get("gold_source", "")
    special_stress = case_manifest.get("special_stress_condition", "")

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
    qual_neg_claims = 0
    indep_groups = 0
    contra_level = "NONE"
    strong_conflict = False
    safety_veto = False
    has_high_quality_therapeutic = False
    decision_gate = "NONE"
    rec_reasons = []
    final_rationale = ""
    mech_qual = "UNKNOWN"
    target_count = 0
    targets = []
    primary_target = ""
    mech_paths = []
    path_count = 0
    molecular_polarity = "UNKNOWN"
    causal_grounding = "UNKNOWN"
    strongest_sup_path = ""
    strongest_opp_path = ""
    
    pos_claim_count = 0
    neg_claim_count = 0
    lit_claims_count = 0
    clinical_trial_count = 0
    trials_with_results_count = 0
    negative_trial_count = 0
    trial_records = []
    sources_attempted = ["chembl", "clinicaltrials_gov", "pubmed", "semantic_scholar", "reactome", "dgidb"]
    sources_successful = []
    sources_failed = []
    cache_hit = False
    
    drug_canonical_id = "UNKNOWN"
    disease_canonical_id = "UNKNOWN"
    serialization_consistent = True
    serialization_note = "OK"

    # Check cache status
    try:
        cached_res = orchestrator._cache.get(drug, disease, RetrievalPolicy.STANDARD.value)
        if cached_res is not None:
            cache_hit = True
    except Exception:
        pass

    try:
        eval_coro = orchestrator.evaluate(
            drug_name=drug,
            disease_name=disease,
            policy=RetrievalPolicy.STANDARD,
            bypass_cache=False,
        )
        hypothesis, package, result = await asyncio.wait_for(eval_coro, timeout=timeout_seconds)
        elapsed = time.time() - t0

        # Extract Canonical IDs
        drug_canonical_id = getattr(hypothesis, "drug_chembl_id", "UNKNOWN") or getattr(package.drug, "chembl_id", "UNKNOWN")
        disease_canonical_id = getattr(hypothesis, "disease_mesh_id", "UNKNOWN") or getattr(package.disease, "mesh_id", "UNKNOWN")

        # Recommendation & Predictions
        rec_status = result.recommendation_status
        rec_str = rec_status.value
        pred_class = RECOMMENDATION_TO_3CLASS.get(rec_str, "UNCERTAIN")

        # Scores
        ss = float(result.support_assessment.score)
        ms = float(result.mechanistic_assessment.score)
        rs = float(result.risk_assessment.score)

        # Opposition Forensics
        opp_assess = result.opposition_assessment
        opp_score = float(opp_assess.score)
        opp_level = opp_assess.level
        qual_neg_claims = int(opp_assess.qualified_negative_claim_count)
        indep_groups = int(opp_assess.independent_group_count)
        opp_rationale = getattr(opp_assess, "rationale", "")
        opp_claim_ids = getattr(opp_assess, "negative_claim_ids", [])
        opp_ev_types = [str(t) for t in getattr(opp_assess, "negative_evidence_types", [])]
        opp_strongest = getattr(opp_assess, "strongest_negative_evidence", "")

        serialization_consistent, serialization_note = verify_opposition_serialization(opp_assess)

        # Support Forensics
        has_high_quality_therapeutic = bool(getattr(result.support_assessment, "has_high_quality_therapeutic", False))
        support_rationale = getattr(result.support_assessment, "rationale", "")

        # Contradiction Forensics
        contra_sum = result.contradiction_summary
        if contra_sum:
            contra_level = getattr(contra_sum, "resolution", "NONE")
            strong_conflict = bool(getattr(contra_sum, "strong_conflict", False))

        # Safety Forensics
        safety_veto = bool(getattr(result.risk_assessment, "safety_veto", False))

        # Mechanistic Forensics
        ma = result.mechanistic_assessment
        sc = ma.score_components or {}
        mech_qual = sc.get("support_level", ma.level)
        target_count = len(package.targets)
        targets = [getattr(t, "name", "") or getattr(t, "gene_symbol", "") for t in package.targets]
        primary_target = sc.get("ranked_target", "") or (targets[0] if targets else "")
        mech_paths = [str(p) for p in getattr(ma, "candidate_mechanisms", [])]
        path_count = len(mech_paths)
        molecular_polarity = sc.get("directional_mechanism_state", "UNKNOWN")
        causal_grounding = sc.get("causal_grounding", "UNKNOWN")

        # Citations / Claims
        lit_claims = getattr(result.audit_report, "top_citations", []) or []
        lit_claims_count = len(lit_claims)

        # Clinical Trials Audit
        trial_records = audit_clinical_trials(package, drug)
        clinical_trial_count = len(trial_records)
        trials_with_results_count = sum(1 for tr in trial_records if tr["has_results"])
        negative_trial_count = sum(1 for tr in trial_records if tr["negative_efficacy"])

        # Sources
        sources_failed = list(getattr(package, "sources_failed", []) or [])
        sources_successful = [s for s in sources_attempted if s not in sources_failed]

        # Recommendation Reasons & Decision Gate
        rec_reasons = getattr(result, "recommendation_reasons", []) or []
        decision_gate = rec_reasons[0] if rec_reasons else "NONE"
        final_rationale = " | ".join(rec_reasons) if rec_reasons else getattr(result, "summary", "")

    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        status = "TIMEOUT"
        error_type = "TIMEOUT"
        error_msg = f"Execution exceeded {timeout_seconds}s timeout"
        rec_str = "UNCERTAIN"
        pred_class = "UNCERTAIN"
        decision_gate = "TIMEOUT"
        final_rationale = error_msg

    except Exception as exc:
        elapsed = time.time() - t0
        exc_str = str(exc)
        exc_type = type(exc).__name__
        rec_str = "UNCERTAIN"
        pred_class = "UNCERTAIN"
        decision_gate = "ERROR"

        if "DrugNotResolved" in exc_type or "DiseaseNotResolved" in exc_type:
            status = "RESOLUTION_FAILURE"
            error_type = "ENTITY_NORMALIZATION_FAILURE"
        elif "connect" in exc_str.lower() or "timeout" in exc_str.lower() or "http" in exc_str.lower():
            status = "RETRIEVAL_FAILURE"
            error_type = "RETRIEVAL_FAILURE"
        elif "json" in exc_str.lower() or "parsing" in exc_str.lower() or "validation" in exc_str.lower():
            status = "PARSING_FAILURE"
            error_type = "PARSING_FAILURE"
        else:
            status = "PIPELINE_ERROR"
            error_type = exc_type

        error_msg = f"{exc_type}: {exc_str}"
        final_rationale = error_msg

    # Epistemic Prediction
    epistemic_pred = pred_class

    # Evaluate Correctness
    is_correct_std = (pred_class == std_gold)
    is_correct_epi = (epistemic_pred == epi_gold)

    # Error Taxonomy Investigation
    failure_type = "NONE"
    primary_explanation = "Prediction matches ground truth."
    if not is_correct_std or not is_correct_epi:
        if status == "RESOLUTION_FAILURE":
            failure_type = "ENTITY_RESOLUTION"
            primary_explanation = f"Entity resolution failed: {error_msg}"
        elif status == "TIMEOUT":
            failure_type = "TIMEOUT"
            primary_explanation = f"Case exceeded timeout of {timeout_seconds}s"
        elif status == "RETRIEVAL_FAILURE":
            failure_type = "RETRIEVAL"
            primary_explanation = f"Critical retrieval upstream source failed: {error_msg}"
        elif pred_class == "SUPPORT" and std_gold in ("OPPOSE", "UNCERTAIN"):
            failure_type = "FALSE_PROMISING"
            primary_explanation = f"System predicted SUPPORT (SS={round(ss,3)}, Gate={decision_gate}) without sufficient evidentiary basis or despite negative evidence."
        elif pred_class == "OPPOSE" and std_gold == "SUPPORT":
            failure_type = "FALSE_OPPOSE"
            primary_explanation = f"System predicted OPPOSE (OppScore={round(opp_score,3)}, Level={opp_level}) against an established/approved indication."
        elif pred_class == "UNCERTAIN" and std_gold == "SUPPORT":
            failure_type = "FALSE_UNCERTAIN_ON_POSITIVE"
            primary_explanation = f"Approved or established therapy failed positive gate: SS={round(ss,3)}, Gate={decision_gate}"
        elif pred_class == "UNCERTAIN" and std_gold == "OPPOSE":
            failure_type = "FALSE_UNCERTAIN_ON_NEGATIVE"
            primary_explanation = f"Failed/futility clinical trial evidence was not converted to opposition (OppScore={round(opp_score,3)})"
        elif pred_class == "OPPOSE" and std_gold == "UNCERTAIN":
            failure_type = "OVERLY_AGGRESSIVE_OPPOSE"
            primary_explanation = f"Unverified hypothesis erroneously converted to OPPOSE without qualifying empirical evidence."

    return {
        # Identity
        "case_id": cid,
        "drug": drug,
        "disease": disease,
        "category": cat,
        "drug_canonical_id": drug_canonical_id,
        "disease_canonical_id": disease_canonical_id,

        # Labels & Provenance
        "gold_label": gold_label,
        "standard_gold": std_gold,
        "epistemic_gold": epi_gold,
        "gold_source": gold_source,
        "special_stress_condition": special_stress,

        # Execution Status
        "status": status,
        "runtime_seconds": round(elapsed, 2),
        "cache_hit": cache_hit,
        "error_type": error_type,
        "error_message": error_msg,

        # Prediction & Decisions
        "prediction": pred_class,
        "epistemic_prediction": epistemic_pred,
        "recommendation": rec_str,
        "decision_rule": decision_gate,
        "final_rationale": final_rationale,
        "recommendation_reasons": rec_reasons,

        # Evaluation Scores
        "support_score": round(ss, 4),
        "mechanistic_score": round(ms, 4),
        "risk_score": round(rs, 4),
        "opposition_score": round(opp_score, 4),
        "opposition_level": opp_level,
        "qualified_negative_claim_count": qual_neg_claims,
        "independent_negative_group_count": indep_groups,
        "contradiction_level": contra_level,
        "strong_conflict": strong_conflict,
        "safety_veto": safety_veto,
        "high_quality_therapeutic_evidence": has_high_quality_therapeutic,

        # Mechanistic Forensics
        "mechanistic_quality": mech_qual,
        "target_count": target_count,
        "primary_target": primary_target,
        "targets": targets,
        "mechanistic_path_count": path_count,
        "molecular_polarity": molecular_polarity,
        "causal_grounding": causal_grounding,

        # Therapeutic & Literature Evidence
        "literature_claims_count": lit_claims_count,
        "evidence_record_count": lit_claims_count + clinical_trial_count,

        # Clinical Trials Forensics
        "clinical_trial_count": clinical_trial_count,
        "trials_with_results": trials_with_results_count,
        "negative_trial_count": negative_trial_count,
        "clinical_trial_records": trial_records,

        # Retrieval Forensics
        "sources_attempted": sources_attempted,
        "sources_successful": sources_successful,
        "sources_failed": sources_failed,

        # Serialization Consistency
        "serialization_consistent": serialization_consistent,
        "serialization_note": serialization_note,

        # Correctness & Diagnostics
        "is_correct_standard": is_correct_std,
        "is_correct_epistemic": is_correct_epi,
        "failure_type": failure_type,
        "primary_explanation": primary_explanation,
    }


async def run_evaluation(
    manifest_path: str = "scratch/manifest_100_cases.json",
    output_dir: str = "evaluation_outputs/100_case_final",
    resume: bool = True,
    timeout: int = CASE_TIMEOUT_SECONDS,
) -> None:
    """Run full 100-case evaluation with progressive logging and live progress tracking."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    jsonl_file = out_path / "results.jsonl"
    progress_file = out_path / "progress.json"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest: list[dict[str, Any]] = json.load(f)

    # Resume handling
    completed_results: dict[str, dict[str, Any]] = {}
    if resume and jsonl_file.exists():
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        completed_results[record["case_id"]] = record
                    except Exception:
                        pass
        print(f"Resuming: Loaded {len(completed_results)} previously completed cases from {jsonl_file}")

    orchestrator = MasterOrchestrator(use_cache=True)
    print(f"MasterOrchestrator initialized. Starting evaluation of {len(manifest)} cases...")
    print(f"Output directory: {output_dir}")
    print(f"Timeout per case: {timeout}s")

    all_results: list[dict[str, Any]] = []
    start_time = time.time()

    for idx, case in enumerate(manifest, 1):
        cid = case["case_id"]
        drug = case["drug"]
        disease = case["disease"]

        # Check if already completed
        if cid in completed_results:
            res = completed_results[cid]
            all_results.append(res)
            print(f"[{idx}/100] [CACHED_RUN] {cid}: {drug} -> {disease} | Pred: {res['prediction']} (Gold Std: {res['standard_gold']}, Epi: {res['epistemic_gold']})")
            continue

        # Run Case
        print(f"\n=======================================================")
        print(f"[{idx}/100] STARTING: {cid} | {drug} -> {disease}")
        print(f"Category: {case['category']} | Stress: {case.get('special_stress_condition')}")
        case_start = time.time()

        res = await evaluate_case(case, orchestrator, timeout_seconds=timeout)
        case_elapsed = round(time.time() - case_start, 2)
        all_results.append(res)

        # Write progressive JSONL
        with open(jsonl_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(res) + "\n")

        # Update progress file
        progress_data = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_cases": len(manifest),
            "completed_cases": len(all_results),
            "remaining_cases": len(manifest) - len(all_results),
            "current_case": f"{cid} ({drug} -> {disease})",
            "runtime_seconds_total": round(time.time() - start_time, 1),
            "successful_cases": sum(1 for r in all_results if r["status"] == "SUCCESS"),
            "failed_cases": sum(1 for r in all_results if r["status"] not in ("SUCCESS", "TIMEOUT")),
            "timeout_cases": sum(1 for r in all_results if r["status"] == "TIMEOUT"),
            "cache_hits": sum(1 for r in all_results if r.get("cache_hit", False)),
        }
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(progress_data, f, indent=2)

        try:
            print(f"[{idx}/100] COMPLETED: {cid} in {case_elapsed}s | Status: {res['status']}")
            print(f"  Prediction: {res['prediction']} (Recommendation: {res['recommendation']})")
            print(f"  Standard Gold: {res['standard_gold']} | Correct: {res['is_correct_standard']}")
            print(f"  Epistemic Gold: {res['epistemic_gold']} | Correct: {res['is_correct_epistemic']}")
            gate_clean = str(res['decision_rule']).encode('ascii', 'replace').decode('ascii')
            print(f"  Decision Gate: {gate_clean}")
            print(f"  Scores: SS={res['support_score']}, MS={res['mechanistic_score']}, RS={res['risk_score']}, OppScore={res['opposition_score']} ({res['opposition_level']})")
        except Exception as p_err:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    # FINAL METRICS COMPUTATION
    # ══════════════════════════════════════════════════════════════════════════
    print("\nAll 100 cases evaluated! Computing final comprehensive metrics...")

    # Standard vs Epistemic Lists
    std_true = [r["standard_gold"] for r in all_results]
    std_pred = [r["prediction"] for r in all_results]
    epi_true = [r["epistemic_gold"] for r in all_results]
    epi_pred = [r["epistemic_prediction"] for r in all_results]

    std_metrics = compute_metrics(std_true, std_pred)
    epi_metrics = compute_metrics(epi_true, epi_pred)

    # High Value Metrics
    # 1. False Promising Rate: SUPPORT when std_gold != SUPPORT
    false_promising_cases = [r["case_id"] for r in all_results if r["prediction"] == "SUPPORT" and r["standard_gold"] != "SUPPORT"]
    false_promising_rate = round(len(false_promising_cases) / len(all_results), 4)

    # 2. False Oppose Rate: OPPOSE when std_gold != OPPOSE
    false_oppose_cases = [r["case_id"] for r in all_results if r["prediction"] == "OPPOSE" and r["standard_gold"] != "OPPOSE"]
    false_oppose_rate = round(len(false_oppose_cases) / len(all_results), 4)

    # 3. Verified Negative Recall: Among true OPPOSE, how many predicted OPPOSE
    true_oppose_cases = [r for r in all_results if r["standard_gold"] == "OPPOSE"]
    oppose_tp = sum(1 for r in true_oppose_cases if r["prediction"] == "OPPOSE")
    oppose_fn = len(true_oppose_cases) - oppose_tp
    verified_negative_recall = round(oppose_tp / len(true_oppose_cases), 4) if true_oppose_cases else 0.0

    # 4. Hard-Negative Uncertainty Rate: Among unverified cases, how many remain UNCERTAIN
    unverified_cases = [r for r in all_results if r["gold_label"] == "unverified"]
    unverified_unc = sum(1 for r in unverified_cases if r["prediction"] == "UNCERTAIN")
    unverified_sup = sum(1 for r in unverified_cases if r["prediction"] == "SUPPORT")
    unverified_opp = sum(1 for r in unverified_cases if r["prediction"] == "OPPOSE")
    hard_negative_uncertainty_rate = round(unverified_unc / len(unverified_cases), 4) if unverified_cases else 0.0

    # 5. Support Recall: Among true SUPPORT, how many predicted SUPPORT
    true_support_cases = [r for r in all_results if r["standard_gold"] == "SUPPORT"]
    support_tp = sum(1 for r in true_support_cases if r["prediction"] == "SUPPORT")
    support_recall = round(support_tp / len(true_support_cases), 4) if true_support_cases else 0.0

    # 6. Opposition Precision: When CYNTHERA says OPPOSE, how many are true OPPOSE
    pred_oppose_cases = [r for r in all_results if r["prediction"] == "OPPOSE"]
    opposition_precision = round(sum(1 for r in pred_oppose_cases if r["standard_gold"] == "OPPOSE") / len(pred_oppose_cases), 4) if pred_oppose_cases else 0.0

    # 7. Uncertainty Precision: When CYNTHERA says UNCERTAIN, how often is it unverified/uncertain
    pred_uncertain_cases = [r for r in all_results if r["prediction"] == "UNCERTAIN"]
    uncertainty_precision_epi = round(sum(1 for r in pred_uncertain_cases if r["epistemic_gold"] == "UNCERTAIN") / len(pred_uncertain_cases), 4) if pred_uncertain_cases else 0.0

    # 8. Contradiction Detection
    contradiction_category_cases = [r for r in all_results if "Category C" in r["category"]]

    # 9. Clinical Attribution Precision & False Clinical Attribution Rate
    all_clinical_trials = []
    potential_false_attributions = []
    for r in all_results:
        for tr in r.get("clinical_trial_records", []):
            all_clinical_trials.append(tr)
            if tr.get("potential_false_attribution"):
                potential_false_attributions.append({
                    "case_id": r["case_id"],
                    "drug": r["drug"],
                    "trial": tr,
                })

    # 10. Serialization Consistency
    consistent_cases = sum(1 for r in all_results if r.get("serialization_consistent", False))
    serialization_consistency_rate = round(consistent_cases / len(all_results), 4)

    # Category Performance Breakdown
    categories = sorted(list({r["category"] for r in all_results}))
    category_metrics = {}
    for c in categories:
        c_results = [r for r in all_results if r["category"] == c]
        c_true = [r["standard_gold"] for r in c_results]
        c_pred = [r["prediction"] for r in c_results]
        c_m = compute_metrics(c_true, c_pred)
        category_metrics[c] = {
            "total": len(c_results),
            "accuracy": c_m["accuracy"],
            "macro_f1": c_m["macro_f1"],
            "support_recall": c_m["per_class"]["SUPPORT"]["recall"],
            "oppose_recall": c_m["per_class"]["OPPOSE"]["recall"],
            "uncertain_recall": c_m["per_class"]["UNCERTAIN"]["recall"],
            "false_promising": sum(1 for r in c_results if r["prediction"] == "SUPPORT" and r["standard_gold"] != "SUPPORT"),
            "false_oppose": sum(1 for r in c_results if r["prediction"] == "OPPOSE" and r["standard_gold"] != "OPPOSE"),
        }

    high_value_metrics = {
        "false_promising_count": len(false_promising_cases),
        "false_promising_rate": false_promising_rate,
        "false_promising_case_ids": false_promising_cases,
        "false_oppose_count": len(false_oppose_cases),
        "false_oppose_rate": false_oppose_rate,
        "false_oppose_case_ids": false_oppose_cases,
        "verified_negative_recall": verified_negative_recall,
        "verified_negative_tp": oppose_tp,
        "verified_negative_fn": oppose_fn,
        "hard_negative_uncertainty_rate": hard_negative_uncertainty_rate,
        "hard_negative_correct_uncertain": unverified_unc,
        "hard_negative_incorrect_support": unverified_sup,
        "hard_negative_incorrect_oppose": unverified_opp,
        "support_recall": support_recall,
        "opposition_precision": opposition_precision,
        "uncertainty_precision_epistemic": uncertainty_precision_epi,
        "serialization_consistency_count": consistent_cases,
        "serialization_consistency_rate": serialization_consistency_rate,
        "total_clinical_trials_processed": len(all_clinical_trials),
        "potential_false_attributions_count": len(potential_false_attributions),
    }

    full_evaluation_payload = {
        "metadata": {
            "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_cases": len(all_results),
            "manifest_file": manifest_path,
            "timeout_seconds": timeout,
        },
        "standard_metrics": std_metrics,
        "epistemic_metrics": epi_metrics,
        "high_value_metrics": high_value_metrics,
        "category_metrics": category_metrics,
        "potential_false_attributions": potential_false_attributions,
    }

    # Save metrics.json
    with open(out_path / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(full_evaluation_payload, f, indent=2)

    # Save full results.json
    with open(out_path / "results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    # Save runtime.csv
    csv_fields = [
        "case_id", "drug", "disease", "category", "standard_gold", "epistemic_gold",
        "prediction", "epistemic_prediction", "recommendation", "is_correct_standard",
        "is_correct_epistemic", "runtime_seconds", "support_score", "opposition_score",
        "opposition_level", "decision_rule", "qualified_negative_claim_count",
        "failure_type", "primary_explanation"
    ]
    with open(out_path / "runtime.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        for r in all_results:
            writer.writerow(r)

    # Save dedicated clinical trials audit
    with open(out_path / "clinical_trials_attribution_audit.json", "w", encoding="utf-8") as f:
        json.dump({
            "total_trials": len(all_clinical_trials),
            "trials": all_clinical_trials,
            "potential_false_attributions": potential_false_attributions,
        }, f, indent=2)

    # Save dedicated opposition serialization audit
    serialization_audit = [
        {
            "case_id": r["case_id"],
            "drug": r["drug"],
            "disease": r["disease"],
            "opposition_score": r["opposition_score"],
            "opposition_level": r["opposition_level"],
            "qualified_negative_claim_count": r["qualified_negative_claim_count"],
            "independent_negative_group_count": r["independent_negative_group_count"],
            "serialization_consistent": r["serialization_consistent"],
            "serialization_note": r["serialization_note"],
        }
        for r in all_results
    ]
    with open(out_path / "opposition_serialization_audit.json", "w", encoding="utf-8") as f:
        json.dump(serialization_audit, f, indent=2)

    print("\n=======================================================")
    print("EVALUATION FINISHED SUCCESSFULLY!")
    print(f"Standard Accuracy:  {std_metrics['accuracy']} | Macro F1: {std_metrics['macro_f1']} | MCC: {std_metrics['mcc']}")
    print(f"Epistemic Accuracy: {epi_metrics['accuracy']} | Macro F1: {epi_metrics['macro_f1']} | MCC: {epi_metrics['mcc']}")
    print(f"False-Promising Rate: {false_promising_rate} ({len(false_promising_cases)} cases)")
    print(f"False-Oppose Rate:    {false_oppose_rate} ({len(false_oppose_cases)} cases)")
    print(f"Hard-Neg Uncertainty: {hard_negative_uncertainty_rate}")
    print(f"Serialization Consistency: {consistent_cases}/100 ({serialization_consistency_rate * 100}%)")
    print(f"Results saved in: {output_dir}")
    print("=======================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run CYNTHERA 100-Case Final Evaluation.")
    parser.add_argument("--manifest", default="scratch/manifest_100_cases.json", help="Path to 100-case manifest JSON")
    parser.add_argument("--output-dir", default="evaluation_outputs/100_case_final", help="Directory for output files")
    parser.add_argument("--resume", action="store_true", default=True, help="Resume from existing results.jsonl")
    parser.add_argument("--timeout", type=int, default=CASE_TIMEOUT_SECONDS, help="Timeout in seconds per case")
    args = parser.parse_args()

    asyncio.run(run_evaluation(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        resume=args.resume,
        timeout=args.timeout,
    ))
