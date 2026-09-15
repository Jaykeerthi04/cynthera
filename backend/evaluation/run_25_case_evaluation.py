"""CYNTHERA — 25-Case Reliable End-to-End Evaluation Runner.

Executes the production reasoning pipeline across 25 curated benchmark cases:
- Category A: Established Positive (7)
- Category B: Hard Negative / Hallucination Traps (6)
- Category C: Contradictory / Negative Evidence (6)
- Category D: Weak / Indirect Evidence (6)

Key Features:
- Per-case timeout (180s default)
- Progressive persistence to results.jsonl after each case
- Resumability via --resume flag
- Granular failure classification
- Cache metrics and runtime profiling
- 3-class metrics, confusion matrices, bootstrap CIs
- Equal-Vote vs Production-Weighting comparison (INITIAL_HEURISTIC)
- Generates all artifacts in evaluation_outputs/25_case/
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
logger = logging.getLogger("cynthera.eval_25")

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.therapeutic_direction_evidence import (
    TherapeuticAction,
)
from backend.reasoning.directional.therapeutic_alignment import (
    group_evidence_by_independence,
)
from backend.reasoning.mechanistic.reaction_aggregator import aggregate_reaction_evidence
from backend.reasoning.evidence_weighting import (
    EvidenceWeightingEngine,
    ProductionWeightConfig,
)
from backend.infrastructure.cache.evaluation_cache import EvaluationCache

CASE_TIMEOUT_SECONDS = 180

# ─────────────────────────────────────────────────────────────────────────────
# EXACT 25 BENCHMARK CASES
# ─────────────────────────────────────────────────────────────────────────────

EVALUATION_CASES: list[dict[str, str]] = [
    # ── CATEGORY A: ESTABLISHED POSITIVE (7) ──
    {
        "case_id": "CYN-003",
        "category": "Established positive",
        "drug": "Lisinopril",
        "disease": "Hypertension",
        "expected_label": "Established/approved",
    },
    {
        "case_id": "CYN-013",
        "category": "Established positive",
        "drug": "Aspirin",
        "disease": "Secondary prevention of cardiovascular disease",
        "expected_label": "Established/approved",
    },
    {
        "case_id": "CYN-023",
        "category": "Established positive",
        "drug": "Budesonide",
        "disease": "Asthma",
        "expected_label": "Established/approved",
    },
    {
        "case_id": "CYN-026",
        "category": "Established positive",
        "drug": "Fluticasone",
        "disease": "Allergic rhinitis",
        "expected_label": "Established/approved",
    },
    {
        "case_id": "CYN-036",
        "category": "Established positive",
        "drug": "Etanercept",
        "disease": "Rheumatoid arthritis",
        "expected_label": "Established/approved",
    },
    {
        "case_id": "CYN-041",
        "category": "Established positive",
        "drug": "Tamoxifen",
        "disease": "ER-positive breast cancer",
        "expected_label": "Established/approved",
    },
    {
        "case_id": "CYN-044",
        "category": "Established positive",
        "drug": "Trastuzumab",
        "disease": "HER2-positive breast cancer",
        "expected_label": "Established/approved",
    },

    # ── CATEGORY B: HARD NEGATIVE / HALLUCINATION TRAPS (6) ──
    {
        "case_id": "CYN-251",
        "category": "Hard negative",
        "drug": "Metformin",
        "disease": "Pancreatic cancer",
        "expected_label": "unverified/no established indication",
    },
    {
        "case_id": "CYN-260",
        "category": "Hard negative",
        "drug": "Furosemide",
        "disease": "Depression",
        "expected_label": "unverified",
    },
    {
        "case_id": "CYN-261",
        "category": "Hard negative",
        "drug": "Warfarin",
        "disease": "Leishmaniasis",
        "expected_label": "unverified",
    },
    {
        "case_id": "CYN-277",
        "category": "Hard negative",
        "drug": "Pregabalin",
        "disease": "Breast cancer",
        "expected_label": "unverified",
    },
    {
        "case_id": "CYN-284",
        "category": "Hard negative",
        "drug": "Tamsulosin",
        "disease": "Liver cancer",
        "expected_label": "unverified",
    },
    {
        "case_id": "CYN-299",
        "category": "Hard negative",
        "drug": "Imatinib",
        "disease": "COVID-19",
        "expected_label": "unverified",
    },

    # ── CATEGORY C: CONTRADICTORY / NEGATIVE EVIDENCE (6) ──
    {
        "case_id": "CYN-103",
        "category": "Contradictory/negative",
        "drug": "Azithromycin",
        "disease": "COVID-19",
        "expected_label": "negative/contradictory",
    },
    {
        "case_id": "CYN-109",
        "category": "Contradictory/negative",
        "drug": "Fluvoxamine",
        "disease": "COVID-19",
        "expected_label": "negative/contradictory",
    },
    {
        "case_id": "CYN-111",
        "category": "Contradictory/negative",
        "drug": "Aspirin",
        "disease": "COVID-19",
        "expected_label": "negative/contradictory",
    },
    {
        "case_id": "CYN-117",
        "category": "Contradictory/negative",
        "drug": "Baricitinib",
        "disease": "COVID-19",
        "expected_label": "negative/contradictory",
    },
    {
        "case_id": "CYN-125",
        "category": "Contradictory/negative",
        "drug": "Atorvastatin",
        "disease": "Alzheimer disease",
        "expected_label": "negative/contradictory",
    },
    {
        "case_id": "CYN-137",
        "category": "Contradictory/negative",
        "drug": "Lithium",
        "disease": "Alzheimer disease",
        "expected_label": "negative/contradictory",
    },

    # ── CATEGORY D: WEAK / INDIRECT EVIDENCE (6) ──
    {
        "case_id": "CYN-179",
        "category": "Weak/indirect",
        "drug": "Propranolol",
        "disease": "Depression",
        "expected_label": "insufficient/weak evidence",
    },
    {
        "case_id": "CYN-186",
        "category": "Weak/indirect",
        "drug": "Colchicine",
        "disease": "Colorectal cancer",
        "expected_label": "insufficient/weak",
    },
    {
        "case_id": "CYN-200",
        "category": "Weak/indirect",
        "drug": "Escitalopram",
        "disease": "Neuropathic pain",
        "expected_label": "insufficient/weak",
    },
    {
        "case_id": "CYN-213",
        "category": "Weak/indirect",
        "drug": "Furosemide",
        "disease": "COPD",
        "expected_label": "insufficient/weak",
    },
    {
        "case_id": "CYN-221",
        "category": "Weak/indirect",
        "drug": "Baricitinib",
        "disease": "Influenza",
        "expected_label": "insufficient/weak",
    },
    {
        "case_id": "CYN-249",
        "category": "Weak/indirect",
        "drug": "Losartan",
        "disease": "Breast cancer",
        "expected_label": "insufficient/weak",
    },
]

LABEL_TO_3CLASS = {
    "Established/approved": "SUPPORT",
    "unverified/no established indication": "OPPOSE",
    "unverified": "OPPOSE",
    "negative/contradictory": "OPPOSE",
    "insufficient/weak evidence": "UNCERTAIN",
    "insufficient/weak": "UNCERTAIN",
}

RECOMMENDATION_TO_3CLASS = {
    "PROMISING": "SUPPORT",
    "NOT_RECOMMENDED": "OPPOSE",
    "UNCERTAIN": "UNCERTAIN",
    "INSUFFICIENT_DATA": "UNCERTAIN",
}


# ─────────────────────────────────────────────────────────────────────────────
# METRICS UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def compute_mcc_3x3(cm: dict[str, dict[str, int]], labels: list[str]) -> float:
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
    n_boot: int = 1000,
    seed: int = 20260902,
) -> dict[str, tuple[float, float]]:
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


# ─────────────────────────────────────────────────────────────────────────────
# CACHE TELEMETRY
# ─────────────────────────────────────────────────────────────────────────────

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
        cur.execute("SELECT count(*), coalesce(sum(hit_count), 0) FROM evaluation_cache")
        row = cur.fetchone()
        if row:
            stats["evaluation_cache_rows"] = row[0]
            stats["evaluation_cache_hits"] = row[1]

        cur.execute("SELECT count(*), coalesce(sum(hit_count), 0) FROM raw_response_cache")
        row = cur.fetchone()
        if row:
            stats["raw_cache_rows"] = row[0]
            stats["raw_cache_hits"] = row[1]
        conn.close()
    except Exception as exc:
        logger.warning("Could not read cache stats: %s", exc)
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE CASE EVALUATION
# ─────────────────────────────────────────────────────────────────────────────

async def evaluate_single_case(
    case: dict[str, str],
    orchestrator: MasterOrchestrator,
    weight_engine: EvidenceWeightingEngine,
    timeout_seconds: int = CASE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    cid = case["case_id"]
    cat = case["category"]
    drug = case["drug"]
    disease = case["disease"]
    expected_label = case["expected_label"]
    expected_class = LABEL_TO_3CLASS[expected_label]

    t0 = time.time()
    status = "SUCCESS"
    error_type = None
    error_msg = None
    rec_str = "UNCERTAIN"
    pred_class = "UNCERTAIN"
    weighted_pred = "UNCERTAIN"

    ss = 0.0
    ms = 0.0
    opp_score = 0.0
    opp_level = "NONE"
    qualified_neg_claims = 0
    mech_qual = "UNKNOWN"
    dir_state = "UNKNOWN"
    contra_state = "NONE"
    strong_conflict = False

    target_count = 0
    cand_count = 0
    indep_groups = 0
    rxn_indep_groups = 0
    struct_edges = 0
    causal_edges = 0
    grounded_edges = 0
    rxn_ev_count = 0
    lit_claims = 0
    cache_hit = False
    sources_failed: list[str] = []
    primary_target = ""
    target_source = "none"
    has_high_quality_therapeutic = False
    therapeutic_evidence_audit: list[dict[str, Any]] = []
    approval_signal: dict[str, Any] | None = None
    decision_gate = "NONE"
    therapeutic_reasons = ""
    rec_reasons = []
    sc: dict[str, Any] = {}

    # Epistemic expected classification
    if cat == "Established positive":
        epistemic_expected = "SUPPORT"
    elif cat in ("Contradictory/negative", "Contradicted/negative", "Contraindicated"):
        epistemic_expected = "OPPOSE"
    elif cat == "Hard negative":
        epistemic_expected = "UNVERIFIED"
    else:
        epistemic_expected = "UNCERTAIN"

    # Check if this case is an evaluation cache hit before calling
    cached_res = orchestrator._cache.get(drug, disease, RetrievalPolicy.STANDARD.value)
    if cached_res is not None:
        cache_hit = True

    try:
        # Run with strict per-case timeout
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
        opp_assess = result.opposition_assessment
        opp_score = float(opp_assess.score)
        opp_level = opp_assess.level
        qualified_neg_claims = int(opp_assess.qualified_negative_claim_count)

        ma = result.mechanistic_assessment
        sc = ma.score_components or {}

        mech_qual = sc.get("support_level", ma.level)
        dir_state = sc.get("directional_mechanism_state", "UNKNOWN")
        contra_sum = result.contradiction_summary

        target_count = sc.get("target_count", len(package.targets))
        primary_target = sc.get("ranked_target", "")
        target_source = sc.get("target_source", "none")
        cand_count = sc.get("candidate_count", len(ma.candidate_mechanisms))

        # Reaction evidence aggregation
        raw_rxn_records = getattr(package, "reactome_reaction_evidence", []) or []
        rxn_ev_count = sc.get("curated_reaction_record_count", len(raw_rxn_records))
        rxn_indep_groups = sc.get("reaction_independent_groups", 0)
        if rxn_indep_groups == 0 and raw_rxn_records:
            try:
                agg_rxns = aggregate_reaction_evidence(raw_rxn_records)
                rxn_indep_groups = len({grp for a in agg_rxns for grp in a.independence_groups if grp != "UNKNOWN"})
            except Exception:
                rxn_indep_groups = 0

        # Fallback target resolution for observability if not already resolved
        if not primary_target and package.targets:
            t0 = package.targets[0]
            primary_target = (
                getattr(t0, "gene_symbol", None)
                or getattr(t0, "protein_uniprot", None)
                or getattr(t0, "name", None)
                or ""
            ).strip().upper()
            if primary_target and target_source == "none":
                target_source = "fallback_no_mechanistic_path"

        indep_groups = sc.get("independent_evidence_groups", 0)
        struct_edges = sc.get("structural_edge_count", 0)
        causal_edges = sc.get("causal_edge_count", 0)
        grounded_edges = sc.get("grounded_edge_count", 0)
        lit_claims = len(getattr(result.audit_report, "top_citations", []) or [])

        if contra_sum:
            contra_state = getattr(contra_sum, "resolution", "NONE")
            strong_conflict = bool(getattr(contra_sum, "strong_conflict", False))

        # Directional-weighting diagnostic only.  It intentionally does not
        # execute the final therapeutic gate, safety vetoes, or recommendation
        # rules, so it is not a second final classifier and must never be used
        # as the benchmark's primary prediction.
        dir_ev = getattr(package, "therapeutic_direction_evidence", []) or []
        groups = group_evidence_by_independence(dir_ev)
        weights_list = []
        for g in groups:
            is_pri = any(
                (getattr(t, "affinity_nm", None) or 9999.0) < 100.0
                for t in package.targets
                if getattr(t, "protein_uniprot", None) and t.protein_uniprot in g.target_id
            )
            w = weight_engine.compute_group_weight(
                group=g,
                target_id=g.target_id,
                drug_action=TherapeuticAction.INHIBITION if any("INHIBIT" in (getattr(t, "mechanism", "") or "").upper() for t in package.targets) else TherapeuticAction.ACTIVATION,
                is_primary_target=is_pri,
                mechanism_quality=mech_qual,
            )
            weights_list.append(w)

        weighted_agg = weight_engine.aggregate_weights(weights_list)
        if weighted_agg.verdict == "SUPPORTS":
            weighted_pred = "SUPPORT"
        elif weighted_agg.verdict == "OPPOSES":
            weighted_pred = "OPPOSE"
        else:
            weighted_pred = "UNCERTAIN"

        has_high_quality_therapeutic = bool(getattr(result.support_assessment, "has_high_quality_therapeutic", False))
        therapeutic_evidence_audit = list(
            getattr(result.support_assessment, "therapeutic_evidence_audit", []) or []
        )
        package_approval = getattr(package, "approval_signal", None)
        approval_signal = package_approval.model_dump() if package_approval is not None else None
        rec_reasons = getattr(result, "recommendation_reasons", []) or []
        decision_gate = rec_reasons[0] if rec_reasons else "NONE"
        therapeutic_reasons = getattr(result.support_assessment, "rationale", "")

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
        elif "graph" in exc_str.lower():
            status = "GRAPH_FAILURE"
            error_type = "GRAPH_FAILURE"
        elif "path" in exc_str.lower() or "reasoner" in exc_str.lower():
            status = "MECHANISM_FAILURE"
            error_type = "MECHANISM_FAILURE"
        elif "alignment" in exc_str.lower() or "direction" in exc_str.lower():
            status = "DIRECTION_FAILURE"
            error_type = "DIRECTION_FAILURE"
        elif "serializ" in exc_str.lower():
            status = "SERIALIZATION_FAILURE"
            error_type = "SERIALIZATION_FAILURE"
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
        "status": status,
        "prediction": pred_class,
        "recommendation": rec_str,
        "runtime_seconds": round(elapsed, 2),
        "mechanistic_score": round(ms, 4),
        "mechanistic_quality_tier": mech_qual,
        "mechanistic_direction": dir_state,
        "support_score": round(ss, 4),
        "opposition_level": opp_level,
        "qualified_negative_claim_count": qualified_neg_claims,
        "independent_opposition_group_count": int(opp_assess.independent_group_count),
        "opposition_score": round(opp_score, 4),
        "contradiction_state": contra_state,
        "strong_conflict": strong_conflict,
        "has_high_quality_therapeutic": has_high_quality_therapeutic,
        "therapeutic_evidence_audit": therapeutic_evidence_audit,
        "approval_signal": approval_signal,
        "decision_gate": decision_gate,
        "therapeutic_reasons": therapeutic_reasons,
        "recommendation_reasons": rec_reasons,
        "target_count": target_count,
        "mechanism_candidate_count": cand_count,
        "independent_evidence_groups": indep_groups,
        "reaction_independent_groups": rxn_indep_groups,
        "global_independent_evidence_groups": sc.get("global_independent_evidence_groups", 0),
        "curated_reaction_record_count": rxn_ev_count,
        "structural_edge_count": struct_edges,
        "causal_edge_count": causal_edges,
        "grounded_edge_count": grounded_edges,
        "reaction_evidence_count": rxn_ev_count,
        "literature_claims": lit_claims,
        "error_type": error_type,
        "error_message": error_msg,
        # Diagnostics
        "original_expected_label": expected_label,
        "expected_3class": expected_class,
        "epistemic_expected_class": epistemic_expected,
        "weighted_prediction": weighted_pred,
        "weighted_prediction_semantics": "DIRECTIONAL_WEIGHTING_DIAGNOSTIC_NOT_FINAL",
        "weighted_prediction_excluded_from_primary_evaluation": True,
        "weight_mode": "EQUAL_VOTE",
        "cache_hit": cache_hit,
        "sources_failed": sources_failed,
        "primary_target": primary_target,
        "target_source": target_source,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EVALUATION RUNNER ORCHESTRATION
# ─────────────────────────────────────────────────────────────────────────────

async def run_evaluation(
    output_dir: str = "evaluation_outputs/25_case",
    resume: bool = False,
    smoke_test: bool = False,
    timeout_seconds: int = CASE_TIMEOUT_SECONDS,
):
    start_time = datetime.now()
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    jsonl_path = out_path / "results.jsonl"
    json_path = out_path / "results.json"
    summary_path = out_path / "run_summary.json"
    runtime_path = out_path / "runtime.csv"
    errors_path = out_path / "error_cases.json"
    metrics_path = out_path / "metrics.json"
    cm_path = out_path / "confusion_matrix.json"

    print("=" * 75)
    print("CYNTHERA -- 25-CASE RELIABLE END-TO-END EVALUATION")
    print(f"Timestamp: {start_time.isoformat()}")
    print(f"Output Directory: {out_path.resolve()}")
    print(f"Cache Version Namespace: {EvaluationCache._CACHE_VERSION}")
    print(f"Per-case Timeout: {timeout_seconds}s | Resume: {resume} | Smoke Test: {smoke_test}")
    print("=" * 75)

    db_path = "data/cynthera.db"
    initial_cache_stats = get_cache_stats(db_path)
    print(f"Initial Cache State: evaluation_cache={initial_cache_stats['evaluation_cache_rows']} rows ({initial_cache_stats['evaluation_cache_hits']} hits), raw_cache={initial_cache_stats['raw_cache_rows']} rows ({initial_cache_stats['raw_cache_hits']} hits)")
    print("-" * 75)

    cases_to_run = EVALUATION_CASES[:1] if smoke_test else EVALUATION_CASES
    total_cases = len(cases_to_run)

    # Check existing progress if resume is enabled
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
        print(f"Resuming: found {len(existing_records)} existing records in {jsonl_path}")

    orchestrator = MasterOrchestrator(
        db_path=db_path,
        use_cache=True,
    )
    weight_engine = EvidenceWeightingEngine(ProductionWeightConfig(config_name="INITIAL_HEURISTIC_V1"))

    results: list[dict[str, Any]] = []

    # Open jsonl file in append mode
    # If not resuming and not smoke test, or if file doesn't exist, we start clean
    write_mode = "a" if (resume and jsonl_path.exists()) else "w"
    jsonl_file = open(jsonl_path, write_mode, encoding="utf-8")

    try:
        for idx, case in enumerate(cases_to_run, 1):
            cid = case["case_id"]
            drug = case["drug"]
            disease = case["disease"]
            expected = case["expected_label"]

            # A persisted terminal record (including a bounded timeout) is part of
            # this run.  Replaying it would make a resumed benchmark neither
            # reproducible nor a single evaluation pass.
            if resume and cid in existing_records:
                rec = existing_records[cid]
                results.append(rec)
                print(f"[{idx:02d}/{total_cases:02d}] {cid} {drug} -> {disease}")
                print(f"      reused from results.jsonl (runtime = {rec.get('runtime_seconds')}s, prediction = {rec.get('prediction')})")
                continue

            print(f"[{idx:02d}/{total_cases:02d}] {cid} {drug} -> {disease}")
            print(f"      started")

            rec = await evaluate_single_case(
                case=case,
                orchestrator=orchestrator,
                weight_engine=weight_engine,
                timeout_seconds=timeout_seconds,
            )

            # Progressive output: immediately append record to jsonl
            jsonl_file.write(json.dumps(rec) + "\n")
            jsonl_file.flush()

            results.append(rec)

            print(f"      completed in {rec['runtime_seconds']}s")
            print(f"      prediction = {rec['prediction']}")
            print(f"      expected = {expected}")
            print(f"      status = {rec['status']}")
            print(f"      saved")
            print()

    finally:
        jsonl_file.close()

    total_eval_duration = (datetime.now() - start_time).total_seconds()
    final_cache_stats = get_cache_stats(db_path)

    # ─────────────────────────────────────────────────────────────────────────
    # ANALYSIS & REPORT GENERATION
    # ─────────────────────────────────────────────────────────────────────────

    completed_count = len(results)
    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    timeout_count = sum(1 for r in results if r["status"] == "TIMEOUT")
    retrieval_fail_count = sum(1 for r in results if r["status"] == "RETRIEVAL_FAILURE")
    other_fail_count = completed_count - success_count - timeout_count - retrieval_fail_count

    runtimes = [r["runtime_seconds"] for r in results]
    mean_runtime = sum(runtimes) / len(runtimes) if runtimes else 0.0
    median_runtime = sorted(runtimes)[len(runtimes) // 2] if runtimes else 0.0
    max_runtime = max(runtimes) if runtimes else 0.0
    sorted_runtimes = sorted(runtimes)
    p90_idx = int(0.9 * len(sorted_runtimes))
    p90_runtime = sorted_runtimes[min(p90_idx, len(sorted_runtimes) - 1)] if sorted_runtimes else 0.0

    # Mechanistic coverage
    non_zero_ms = sum(1 for r in results if r["mechanistic_score"] > 0)
    zero_ms = sum(1 for r in results if r["mechanistic_score"] == 0)
    pct_non_zero = (non_zero_ms / completed_count * 100.0) if completed_count > 0 else 0.0

    zero_ms_causes = Counter()
    for r in results:
        if r["mechanistic_score"] == 0:
            if r["status"] == "RETRIEVAL_FAILURE":
                zero_ms_causes["retrieval_failure"] += 1
            elif r["target_count"] == 0:
                zero_ms_causes["no_target_evidence"] += 1
            elif r["structural_edge_count"] == 0 and r["causal_edge_count"] == 0:
                zero_ms_causes["no_pathway"] += 1
            elif r["category"] == "Hard negative":
                zero_ms_causes["unverified_disease_gap"] += 1
            else:
                zero_ms_causes["no_valid_mechanistic_path"] += 1

    # Mechanism quality distribution
    quality_dist = Counter(r["mechanistic_quality_tier"] for r in results)

    # Contradiction behavior (semantically accurate categorization)
    strong_conflict_cases = sum(1 for r in results if r.get("strong_conflict", False) or r["contradiction_state"] == "UNRESOLVED_CONFLICT")
    opposing_cases = sum(1 for r in results if r["contradiction_state"] == "OPPOSES")
    mixed_evidence_cases = sum(1 for r in results if r.get("has_conflict", False))
    supporting_cases = sum(1 for r in results if r["contradiction_state"] == "SUPPORTS")
    insufficient_evidence_cases = sum(1 for r in results if r["contradiction_state"] in ("NONE", "INSUFFICIENT"))
    genuine_contra_detected = strong_conflict_cases + opposing_cases

    strong_conflicts = strong_conflict_cases
    strong_conflict_to_uncertain = sum(1 for r in results if (r.get("strong_conflict", False) or r["contradiction_state"] == "UNRESOLVED_CONFLICT") and r["prediction"] == "UNCERTAIN")
    strong_conflict_to_support = sum(1 for r in results if (r.get("strong_conflict", False) or r["contradiction_state"] == "UNRESOLVED_CONFLICT") and r["prediction"] == "SUPPORT")
    strong_conflict_to_oppose = sum(1 for r in results if (r.get("strong_conflict", False) or r["contradiction_state"] == "UNRESOLVED_CONFLICT") and r["prediction"] == "OPPOSE")

    # Uncertainty behavior
    total_uncertain = sum(1 for r in results if r["prediction"] == "UNCERTAIN")
    contra_to_uncertain = sum(1 for r in results if r["contradiction_state"] == "UNRESOLVED_CONFLICT" and r["prediction"] == "UNCERTAIN")
    weak_to_uncertain = sum(1 for r in results if r["category"] == "Weak/indirect" and r["prediction"] == "UNCERTAIN")
    hard_neg_to_uncertain = sum(1 for r in results if r["category"] == "Hard negative" and r["prediction"] == "UNCERTAIN")
    estab_pos_to_uncertain = sum(1 for r in results if r["category"] == "Established positive" and r["prediction"] == "UNCERTAIN")

    # Evidence independence
    total_raw_evidence = sum(r["target_count"] + r["structural_edge_count"] + r["reaction_evidence_count"] + r["literature_claims"] for r in results)
    total_indep_groups = sum(r["independent_evidence_groups"] for r in results)
    independence_inflation_ratio = round(total_raw_evidence / total_indep_groups, 2) if total_indep_groups > 0 else 1.0

    # Reaction evidence
    total_raw_reactions = sum(r["reaction_evidence_count"] for r in results)
    total_rxn_indep_groups = sum(r["reaction_independent_groups"] for r in results)

    # Multi-target diagnostics
    cases_with_targets = [r for r in results if r["target_count"] > 0]
    multi_target_count = sum(1 for r in results if r["target_count"] > 1)

    # Weighting comparison: EQUAL_VOTE vs PRODUCTION_WEIGHTING
    weight_changes: list[dict[str, str]] = []
    weight_change_counts = Counter()
    for r in results:
        eq = r["prediction"]
        pw = r["weighted_prediction"]
        if eq != pw:
            trans = f"{eq} -> {pw}"
            weight_change_counts[trans] += 1
            weight_changes.append({"case_id": r["case_id"], "drug": r["drug"], "disease": r["disease"], "transition": trans})

    # Metrics computation:
    # 1. ORIGINAL BENCHMARK SCORING (Preserved verbatim)
    y_true_all = [r["expected_3class"] for r in results]
    y_pred_all = [r["prediction"] for r in results]
    metrics_all = compute_metrics(y_true_all, y_pred_all)
    ci_all = bootstrap_ci(y_true_all, y_pred_all)

    successful_results = [r for r in results if r["status"] == "SUCCESS"]
    y_true_succ = [r["expected_3class"] for r in successful_results]
    y_pred_succ = [r["prediction"] for r in successful_results]
    metrics_succ = compute_metrics(y_true_succ, y_pred_succ)
    ci_succ = bootstrap_ci(y_true_succ, y_pred_succ)

    # 2. EPISTEMICALLY CORRECTED SECONDARY SCORING
    # Unverified hard negatives (absence of evidence != evidence of opposition) mapped to sound expected UNCERTAIN
    y_true_epistemic_all = [
        "UNCERTAIN" if r["epistemic_expected_class"] == "UNVERIFIED" else r["epistemic_expected_class"]
        for r in results
    ]
    metrics_epistemic_all = compute_metrics(y_true_epistemic_all, y_pred_all)
    ci_epistemic_all = bootstrap_ci(y_true_epistemic_all, y_pred_all)

    y_true_epistemic_succ = [
        "UNCERTAIN" if r["epistemic_expected_class"] == "UNVERIFIED" else r["epistemic_expected_class"]
        for r in successful_results
    ]
    metrics_epistemic_succ = compute_metrics(y_true_epistemic_succ, y_pred_succ)
    ci_epistemic_succ = bootstrap_ci(y_true_epistemic_succ, y_pred_succ)

    # Category performance
    categories = ["Established positive", "Hard negative", "Contradictory/negative", "Weak/indirect"]
    category_summary: dict[str, Any] = {}
    for cat in categories:
        cat_cases = [r for r in results if r["category"] == cat]
        cat_succ = [r for r in cat_cases if r["status"] == "SUCCESS"]
        cat_fail = len(cat_cases) - len(cat_succ)
        cat_correct = sum(1 for r in cat_succ if r["prediction"] == r["expected_3class"])
        cat_incorrect = len(cat_succ) - cat_correct
        category_summary[cat] = {
            "total_cases": len(cat_cases),
            "successful_cases": len(cat_succ),
            "failures": cat_fail,
            "correct": cat_correct,
            "incorrect": cat_incorrect,
            "predictions": dict(Counter(r["prediction"] for r in cat_cases)),
        }

    # Error analysis
    incorrect_predictions = []
    failure_cases = []
    for r in results:
        if r["status"] != "SUCCESS":
            failure_cases.append(r)
        elif r["prediction"] != r["expected_3class"]:
            # Diagnostic reason for mismatch
            diag = "Mismatch between prediction and expected benchmark label"
            if r["category"] == "Established positive" and r["prediction"] == "UNCERTAIN":
                diag = f"Mechanistic/regulatory threshold not reached (MS={r['mechanistic_score']}, SS={r['support_score']}, Tier={r['mechanistic_quality_tier']})"
            elif r["category"] == "Hard negative" and r["prediction"] == "UNCERTAIN":
                diag = "Model predicted UNCERTAIN for unverified pair (missing evidence is not opposition)"
            elif r["category"] == "Contradictory/negative" and r["prediction"] == "UNCERTAIN":
                diag = f"Contradiction preserved as UNCERTAIN (state={r['contradiction_state']}, strong_conflict={r['strong_conflict']})"
            elif r["category"] == "Weak/indirect" and r["prediction"] == "SUPPORT":
                diag = "Weak evidence over-promoted to positive"
            incorrect_predictions.append({
                "case_id": r["case_id"],
                "drug": r["drug"],
                "disease": r["disease"],
                "category": r["category"],
                "expected": r["expected_3class"],
                "predicted": r["prediction"],
                "recommendation": r["recommendation"],
                "MS": r["mechanistic_score"],
                "mechanism_quality": r["mechanistic_quality_tier"],
                "direction": r["mechanistic_direction"],
                "contradiction": r["contradiction_state"],
                "target_count": r["target_count"],
                "evidence_groups": r["independent_evidence_groups"],
                "diagnostic_reason": diag,
            })

    # ─────────────────────────────────────────────────────────────────────────
    # WRITE RAW RESULTS FILES
    # ─────────────────────────────────────────────────────────────────────────

    # 1. results.json
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # 2. runtime.csv
    with open(runtime_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "drug", "disease", "category", "status", "prediction", "expected", "runtime_seconds", "mechanistic_score", "support_score", "cache_hit"])
        for r in results:
            writer.writerow([
                r["case_id"], r["drug"], r["disease"], r["category"], r["status"],
                r["prediction"], r["expected_3class"], r["runtime_seconds"],
                r["mechanistic_score"], r["support_score"], r["cache_hit"]
            ])

    # 3. metrics.json
    metrics_payload = {
        "evaluation_timestamp": start_time.isoformat(),
        "total_runtime_seconds": round(total_eval_duration, 2),
        "benchmark_scoring_original": {
            "all_cases_metrics": metrics_all,
            "all_cases_ci": ci_all,
            "successful_cases_metrics": metrics_succ,
            "successful_cases_ci": ci_succ,
        },
        "benchmark_scoring_epistemically_corrected": {
            "all_cases_metrics": metrics_epistemic_all,
            "all_cases_ci": ci_epistemic_all,
            "successful_cases_metrics": metrics_epistemic_succ,
            "successful_cases_ci": ci_epistemic_succ,
        },
        "all_cases_metrics": metrics_all,
        "all_cases_ci": ci_all,
        "successful_cases_metrics": metrics_succ,
        "successful_cases_ci": ci_succ,
        "category_performance": category_summary,
        "mechanistic_coverage": {
            "non_zero_count": non_zero_ms,
            "zero_count": zero_ms,
            "percentage_non_zero": round(pct_non_zero, 2),
            "zero_ms_root_causes": dict(zero_ms_causes),
            "quality_tier_distribution": dict(quality_dist),
        },
        "uncertainty_diagnostics": {
            "total_uncertain": total_uncertain,
            "unresolved_conflict_to_uncertain": contra_to_uncertain,
            "weak_indirect_to_uncertain": weak_to_uncertain,
            "hard_negative_to_uncertain": hard_neg_to_uncertain,
            "established_positive_to_uncertain": estab_pos_to_uncertain,
        },
        "contradiction_diagnostics": {
            "genuine_contradiction_cases": genuine_contra_detected,
            "strong_conflict_cases": strong_conflict_cases,
            "opposing_cases": opposing_cases,
            "mixed_evidence_cases": mixed_evidence_cases,
            "supporting_cases": supporting_cases,
            "insufficient_evidence_cases": insufficient_evidence_cases,
            "strong_conflict_to_uncertain": strong_conflict_to_uncertain,
            "strong_conflict_forced_to_support": strong_conflict_to_support,
            "strong_conflict_forced_to_oppose": strong_conflict_to_oppose,
        },
        "evidence_independence": {
            "total_raw_evidence": total_raw_evidence,
            "total_independent_groups": total_indep_groups,
            "independence_inflation_ratio": independence_inflation_ratio,
        },
        "reaction_evidence": {
            "total_raw_reaction_records": total_raw_reactions,
            "reaction_independent_groups": total_rxn_indep_groups,
        },
        "weighting_comparison": {
            "description": (
                "Evaluation-only directional-weighting diagnostic (INITIAL_HEURISTIC). "
                "It does not apply therapeutic-evidence gates, safety vetoes, or final decision synthesis "
                "and is excluded from all primary benchmark metrics."
            ),
            "primary_prediction_field": "prediction",
            "diagnostic_prediction_field": "weighted_prediction",
            "diagnostic_is_not_final": True,
            "changed_predictions_count": len(weight_changes),
            "transitions": dict(weight_change_counts),
            "changed_cases": weight_changes,
        },
    }
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2)

    # 4. confusion_matrix.json
    cm_payload = {
        "original_benchmark_all_3x3": metrics_all["confusion_matrix"],
        "original_benchmark_successful_3x3": metrics_succ["confusion_matrix"],
        "epistemically_corrected_all_3x3": metrics_epistemic_all["confusion_matrix"],
        "epistemically_corrected_successful_3x3": metrics_epistemic_succ["confusion_matrix"],
        "row_order": ["SUPPORT", "OPPOSE", "UNCERTAIN"],
        "col_order": ["SUPPORT", "OPPOSE", "UNCERTAIN"],
    }
    with open(cm_path, "w", encoding="utf-8") as f:
        json.dump(cm_payload, f, indent=2)

    # 5. error_cases.json
    error_payload = {
        "infrastructure_failures": failure_cases,
        "prediction_mismatches": incorrect_predictions,
    }
    with open(errors_path, "w", encoding="utf-8") as f:
        json.dump(error_payload, f, indent=2)

    # 6. run_summary.json
    summary_payload = {
        "eval_date": start_time.isoformat(),
        "total_cases": total_cases,
        "completed": completed_count,
        "success": success_count,
        "timeout": timeout_count,
        "retrieval_failure": retrieval_fail_count,
        "other_failure": other_fail_count,
        "runtimes": {
            "total_seconds": round(total_eval_duration, 2),
            "mean_seconds": round(mean_runtime, 2),
            "median_seconds": round(median_runtime, 2),
            "max_seconds": round(max_runtime, 2),
            "p90_seconds": round(p90_runtime, 2),
        },
        "caching": {
            "namespace_version": EvaluationCache._CACHE_VERSION,
            "initial": initial_cache_stats,
            "final": final_cache_stats,
            "cache_hits_during_run": (final_cache_stats["evaluation_cache_hits"] - initial_cache_stats["evaluation_cache_hits"]) + (final_cache_stats["raw_cache_hits"] - initial_cache_stats["raw_cache_hits"]),
        },
        "predictions": dict(Counter(r["prediction"] for r in results)),
        "metrics_all": metrics_all,
        "metrics_successful": metrics_succ,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    # Copy files to workspace root evaluation_outputs as well for convenience
    root_out_path = _workspace_dir / "evaluation_outputs" / "25_case"
    if root_out_path.resolve() != out_path.resolve():
        root_out_path.mkdir(parents=True, exist_ok=True)
        for p in (jsonl_path, json_path, summary_path, runtime_path, errors_path, metrics_path, cm_path):
            try:
                dest = root_out_path / p.name
                dest.write_bytes(p.read_bytes())
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # PRINT FINAL SUMMARY
    # ─────────────────────────────────────────────────────────────────────────

    print()
    print("=" * 52)
    print("CYNTHERA -- 25 CASE E2E EVALUATION")
    print("=" * 52)
    print()
    print("Cases:")
    print(total_cases)
    print()
    print("Completed:")
    print(completed_count)
    print()
    print("Timeout:")
    print(timeout_count)
    print()
    print("Retrieval failures:")
    print(retrieval_fail_count)
    print()
    print("Other failures:")
    print(other_fail_count)
    print()
    print("Successful predictions:")
    print(success_count)
    print()
    print("Runtime:")
    print(f"  total: {total_eval_duration:.1f}s")
    print(f"  mean/case: {mean_runtime:.1f}s")
    print(f"  median/case: {median_runtime:.1f}s")
    print(f"  max/case: {max_runtime:.1f}s")
    print()
    print("Mechanistic coverage:")
    print(f"  non-zero: {non_zero_ms}")
    print(f"  zero: {zero_ms}")
    print(f"  percentage: {pct_non_zero:.1f}%")
    print()
    pred_counts = Counter(r["prediction"] for r in results)
    print("Predictions:")
    print(f"  SUPPORT: {pred_counts.get('SUPPORT', 0)}")
    print(f"  OPPOSE: {pred_counts.get('OPPOSE', 0)}")
    print(f"  UNCERTAIN: {pred_counts.get('UNCERTAIN', 0)}")
    print()
    print("Original Benchmark 3-class metrics (All Cases):")
    print(f"  Accuracy: {metrics_all['accuracy']:.4f}")
    print(f"  Macro F1: {metrics_all['macro_f1']:.4f}")
    print(f"  MCC: {metrics_all['mcc']:.4f}")
    print()
    print("Original Benchmark 3-class metrics (Successful Cases Only):")
    print(f"  Accuracy: {metrics_succ['accuracy']:.4f}")
    print(f"  Macro F1: {metrics_succ['macro_f1']:.4f}")
    print(f"  MCC: {metrics_succ['mcc']:.4f}")
    print()
    print("Epistemically Corrected 3-class metrics (All Cases):")
    print(f"  Accuracy: {metrics_epistemic_all['accuracy']:.4f}")
    print(f"  Macro F1: {metrics_epistemic_all['macro_f1']:.4f}")
    print(f"  MCC: {metrics_epistemic_all['mcc']:.4f}")
    print()
    print("Epistemically Corrected 3-class metrics (Successful Cases Only):")
    print(f"  Accuracy: {metrics_epistemic_succ['accuracy']:.4f}")
    print(f"  Macro F1: {metrics_epistemic_succ['macro_f1']:.4f}")
    print(f"  MCC: {metrics_epistemic_succ['mcc']:.4f}")
    print()
    print("Contradiction Breakdown:")
    print(f"  Strong conflict cases: {strong_conflict_cases}")
    print(f"  Directional opposition cases: {opposing_cases}")
    print(f"  Mixed evidence cases: {mixed_evidence_cases}")
    print(f"  Supporting consensus cases: {supporting_cases}")
    print(f"  Insufficient evidence cases: {insufficient_evidence_cases}")
    print(f"  Genuine conflict cases (strong + opposing): {genuine_contra_detected}")
    print(f"  Strong conflict preserved as UNCERTAIN: {strong_conflict_to_uncertain}")
    print()
    print("=" * 52)
    print()
    print("Top 10 slowest cases:")
    slowest = sorted(results, key=lambda r: r["runtime_seconds"], reverse=True)[:10]
    for rank, r in enumerate(slowest, 1):
        print(f"{rank:2d}. {r['case_id']}: {r['drug']} -> {r['disease']} ({r['runtime_seconds']}s) [{r['status']}]")
    print()

    if failure_cases:
        print("Systematic Failures:")
        for fc in failure_cases:
            print(f"- {fc['case_id']} ({fc['drug']} -> {fc['disease']}): {fc['status']} - {fc['error_type']}: {fc['error_message']}")
        print()


def main():
    parser = argparse.ArgumentParser(description="CYNTHERA 25-case E2E Evaluation Runner")
    parser.add_argument("--output-dir", default="evaluation_outputs/25_case", help="Output directory")
    parser.add_argument("--resume", action="store_true", help="Resume previous run from results.jsonl")
    parser.add_argument("--smoke-test", action="store_true", help="Run only 1 case as a smoke test")
    parser.add_argument("--timeout", type=int, default=CASE_TIMEOUT_SECONDS, help="Per-case timeout seconds")
    args = parser.parse_args()

    asyncio.run(
        run_evaluation(
            output_dir=args.output_dir,
            resume=args.resume,
            smoke_test=args.smoke_test,
            timeout_seconds=args.timeout,
        )
    )


if __name__ == "__main__":
    main()
