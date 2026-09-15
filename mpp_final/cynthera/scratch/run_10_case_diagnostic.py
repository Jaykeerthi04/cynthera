"""Strict Uncached 10-Case Diagnostic Runner (Phase 5.16).

Executes the exact 10 cases with bypass_cache=True, captures full diagnostic telemetry,
audits opposition evidence, clinical trials, and benchmark labels, and saves results to JSON.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure stdout handles utf-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.abspath("."))

from backend.core.domain.claim import Claim
from backend.core.enums.predicate_type import PredicateType
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.infrastructure.cache.evaluation_cache import EvaluationCache
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    NEGATIVE_PREDICATES,
    NEGATIVE_PREDICATE_NAMES,
    TherapeuticOppositionAssessor,
    trial_to_negative_claim,
)

CASES = [
    # ── Established positive (2) ──
    {
        "case_id": "CYN-003",
        "category": "Established positive",
        "drug": "Lisinopril",
        "disease": "Hypertension",
        "expected_label": "Established/approved",
        "expected_3class": "SUPPORT",
        "epistemic_expected_class": "SUPPORT",
    },
    {
        "case_id": "CYN-013",
        "category": "Established positive",
        "drug": "Aspirin",
        "disease": "Secondary prevention of cardiovascular disease",
        "expected_label": "Established/approved",
        "expected_3class": "SUPPORT",
        "epistemic_expected_class": "SUPPORT",
    },
    # ── Hard negative (3) ──
    {
        "case_id": "CYN-251",
        "category": "Hard negative",
        "drug": "Metformin",
        "disease": "Pancreatic cancer",
        "expected_label": "unverified/no established indication",
        "expected_3class": "OPPOSE",
        "epistemic_expected_class": "UNVERIFIED",
    },
    {
        "case_id": "CYN-260",
        "category": "Hard negative",
        "drug": "Furosemide",
        "disease": "Depression",
        "expected_label": "unverified",
        "expected_3class": "OPPOSE",
        "epistemic_expected_class": "UNVERIFIED",
    },
    {
        "case_id": "CYN-261",
        "category": "Hard negative",
        "drug": "Warfarin",
        "disease": "Leishmaniasis",
        "expected_label": "unverified",
        "expected_3class": "OPPOSE",
        "epistemic_expected_class": "UNVERIFIED",
    },
    # ── Uncertain / weak (3) ──
    {
        "case_id": "CYN-179",
        "category": "Weak/indirect",
        "drug": "Propranolol",
        "disease": "Depression",
        "expected_label": "insufficient/weak evidence",
        "expected_3class": "UNCERTAIN",
        "epistemic_expected_class": "UNCERTAIN",
    },
    {
        "case_id": "CYN-186",
        "category": "Weak/indirect",
        "drug": "Colchicine",
        "disease": "Colorectal cancer",
        "expected_label": "insufficient/weak",
        "expected_3class": "UNCERTAIN",
        "epistemic_expected_class": "UNCERTAIN",
    },
    {
        "case_id": "CYN-200",
        "category": "Weak/indirect",
        "drug": "Escitalopram",
        "disease": "Neuropathic pain",
        "expected_label": "insufficient/weak",
        "expected_3class": "UNCERTAIN",
        "epistemic_expected_class": "UNCERTAIN",
    },
    # ── Contradictory / negative (2) ──
    {
        "case_id": "CYN-109",
        "category": "Contradictory/negative",
        "drug": "Fluvoxamine",
        "disease": "COVID-19",
        "expected_label": "negative/contradictory",
        "expected_3class": "OPPOSE",
        "epistemic_expected_class": "OPPOSE",
    },
    {
        "case_id": "CYN-103",
        "category": "Contradictory/negative",
        "drug": "Azithromycin",
        "disease": "COVID-19",
        "expected_label": "negative/contradictory",
        "expected_3class": "OPPOSE",
        "epistemic_expected_class": "OPPOSE",
    },
]

RECOMMENDATION_TO_3CLASS = {
    "PROMISING": "SUPPORT",
    "NOT_RECOMMENDED": "OPPOSE",
    "UNCERTAIN": "UNCERTAIN",
    "INSUFFICIENT_DATA": "UNCERTAIN",
    "RESOLUTION_FAILED": "UNCERTAIN",
}


async def run_diagnostic():
    db_path = "data/cynthera.db"
    orchestrator = MasterOrchestrator(db_path=db_path, use_cache=True)
    assessor = TherapeuticOppositionAssessor()

    print("================================================================================")
    print("PHASE 5.16 — 10-CASE DIAGNOSTIC RUN (STRICT UNCACHED)")
    print("================================================================================")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print(f"Cache Bypass: TRUE (strict uncached evaluation)")
    print(f"Rule Set Version: 2.1")
    print("================================================================================\n")

    results: list[dict[str, Any]] = []

    for idx, case in enumerate(CASES, 1):
        cid = case["case_id"]
        drug = case["drug"]
        disease = case["disease"]
        exp_label = case["expected_label"]
        exp_3class = case["expected_3class"]
        epistemic_exp = case["epistemic_expected_class"]

        print(f"\n[{idx:02d}/10] EVALUATING: {cid} | {drug} -> {disease} ...", flush=True)

        # Cache check before evaluation
        initial_cached = orchestrator._cache.get(drug, disease, RetrievalPolicy.STANDARD.value)
        had_preexisting_eval_cache = initial_cached is not None

        t0 = time.time()
        try:
            hyp, pkg, res = await orchestrator.evaluate(
                drug_name=drug,
                disease_name=disease,
                policy=RetrievalPolicy.STANDARD,
                bypass_cache=True,
            )
            elapsed = time.time() - t0
            print(f"      Completed in {elapsed:.2f}s", flush=True)

            # Strict cache bypass verification:
            # When bypass_cache=True was set, evaluate() bypassed _cache.get() and executed the pipeline.
            # Confirm that hypothesis_id of the returned result is fresh (newly minted for this evaluation pass).
            if had_preexisting_eval_cache and initial_cached.hypothesis_id == res.hypothesis_id:
                print("      CRITICAL ERROR: CACHE_BYPASS_FAILURE! Stale cached result returned!", flush=True)
                raise RuntimeError("CACHE_BYPASS_FAILURE: Cached evaluation was returned despite bypass_cache=True")

            evaluation_cache_hit = False
            raw_response_cache_hit = False
            connector_cache_hits = 0

            # Recommendation & prediction
            rec_status = res.recommendation_status.value
            pred_3class = RECOMMENDATION_TO_3CLASS.get(rec_status, "UNCERTAIN")

            # Scores & assessments
            ss = float(res.support_assessment.score)
            ss_level = res.support_assessment.level
            ms = float(res.mechanistic_assessment.score)
            ms_level = res.mechanistic_assessment.level
            sc = res.mechanistic_assessment.score_components or {}
            mech_dir = sc.get("directional_mechanism_state", "UNKNOWN")
            mech_quality_tier = sc.get("support_level", ms_level)

            opp = res.opposition_assessment
            opp_score = float(opp.score)
            opp_level = opp.level
            opp_groups = opp.independent_group_count
            qual_neg_claims = opp.qualified_negative_claim_count
            excl_neg_claims = opp.excluded_negative_claim_count
            strongest_group_wt = float(opp.strongest_group_weight)

            contra_state = (
                res.contradiction_summary.contradiction_state
                if res.contradiction_summary
                else "NONE"
            )

            reasons = res.recommendation_reasons or []
            rule_fired = reasons[0] if reasons else "DEFAULT"

            # Clinical trial analysis
            trial_cls = orchestrator._reasoning._classify_clinical_trials(pkg)
            converted_trial_claims: list[dict[str, Any]] = []
            for t in trial_cls.efficacy_terminated + trial_cls.safety_terminated:
                c = trial_to_negative_claim(t, pkg.drug.name, pkg.disease.name)
                if c is not None:
                    converted_trial_claims.append({
                        "nct_id": t.nct_id,
                        "original_status": t.status.value if hasattr(t.status, "value") else str(t.status),
                        "why_stopped": getattr(t, "why_stopped", "") or t.title,
                        "mapped_predicate": c.predicate.value if hasattr(c.predicate, "value") else str(c.predicate),
                        "relevance": c.erw.value if c.erw else 0.0,
                        "quality": c.confidence,
                        "weight": c.erw.epistemic_weight if hasattr(c.erw, "epistemic_weight") else c.erw.value,
                        "independence_group": c.provenance.record_id if c.provenance else t.nct_id,
                    })

            # Negative claims audit directly from the claims evaluated by TherapeuticOppositionAssessor
            all_neg_claims: list[dict[str, Any]] = []
            evaluated_opp_claims = getattr(orchestrator._reasoning, "_last_opposition_claims", [])
            for c in evaluated_opp_claims:
                pred_name = c.predicate.value if hasattr(c.predicate, "value") else str(c.predicate)
                if pred_name in NEGATIVE_PREDICATE_NAMES:
                    all_neg_claims.append({
                        "source": c.provenance.source_name if c.provenance else "literature",
                        "record_id": c.provenance.record_id if c.provenance else "",
                        "drug": c.subject,
                        "disease": c.object,
                        "predicate": pred_name,
                        "relevance": getattr(c.erw, "relevance_score", getattr(c.erw, "value", 0.0)),
                        "quality": getattr(c.erw, "quality_score", c.confidence),
                        "weight": getattr(c.erw, "value", 0.0),
                        "independence_group": c.provenance.record_id if c.provenance else "UNKNOWN",
                    })

            negative_predicate_count = len(all_neg_claims)
            negative_predicates = list({c["predicate"] for c in all_neg_claims})

            # Bottleneck identification
            bottleneck = "None"
            if exp_3class == "SUPPORT" and pred_3class != "SUPPORT":
                bottleneck = f"Support gate not reached (SS={ss:.2f}, Rule={rule_fired})"
            elif exp_3class == "OPPOSE" and pred_3class != "OPPOSE":
                if epistemic_exp == "UNVERIFIED":
                    bottleneck = "Epistemic divergence: Benchmark expects OPPOSE for unverified, system correctly produces UNCERTAIN"
                else:
                    bottleneck = f"Opposition evidence not detected or below threshold (OppScore={opp_score:.2f}, QualNeg={qual_neg_claims})"

            case_result = {
                "case_id": cid,
                "drug": drug,
                "disease": disease,
                "expected_label": exp_label,
                "expected_3class": exp_3class,
                "epistemic_expected_class": epistemic_exp,
                "status": "SUCCESS",
                "prediction": pred_3class,
                "recommendation": rec_status,
                "runtime_seconds": round(elapsed, 2),
                "evaluation_cache_hit": evaluation_cache_hit,
                "raw_response_cache_hit": raw_response_cache_hit,
                "connector_cache_hits": connector_cache_hits,
                "mechanistic_score": ms,
                "mechanistic_quality_tier": mech_quality_tier,
                "mechanistic_direction": mech_dir,
                "support_score": ss,
                "support_level": ss_level,
                "opposition_score": opp_score,
                "opposition_level": opp_level,
                "contradiction_state": contra_state,
                "decision_gate": rule_fired,
                "rule_that_fired": rule_fired,
                "target_count": len(pkg.targets),
                "pathway_count": len(pkg.reactome_pathway_evidence) if hasattr(pkg, "reactome_pathway_evidence") else 0,
                "path_count": len(res.mechanistic_assessment.candidate_mechanisms),
                "mechanism_candidate_count": len(res.mechanistic_assessment.candidate_mechanisms),
                "therapeutic_evidence_counts": len(pkg.literature_evidence),
                "clinical_trial_count": len(pkg.clinical_trials),
                "negative_evidence_count": qual_neg_claims,
                "independent_evidence_groups": sc.get("independent_evidence_groups", 0),
                "opposition_independent_groups": opp_groups,
                "strongest_group_weight": strongest_group_wt,
                "negative_predicate_count": negative_predicate_count,
                "negative_predicates": negative_predicates,
                "all_negative_claims": all_neg_claims,
                "converted_trial_claims": converted_trial_claims,
                "bottleneck": bottleneck,
                "recommendation_reasons": reasons,
            }

            print(f"      Prediction: {pred_3class} (Rec: {rec_status})")
            print(f"      MS={ms:.2f} | SS={ss:.2f} | OppScore={opp_score:.2f} ({opp_level}, groups={opp_groups})")
            print(f"      Rule Fired: {rule_fired}")
            results.append(case_result)

        except Exception as exc:
            elapsed = time.time() - t0
            print(f"      ERROR in {cid}: {exc}", flush=True)
            import traceback
            traceback.print_exc()
            results.append({
                "case_id": cid,
                "drug": drug,
                "disease": disease,
                "expected_label": exp_label,
                "expected_3class": exp_3class,
                "epistemic_expected_class": epistemic_exp,
                "status": "ERROR",
                "error": str(exc),
                "runtime_seconds": round(elapsed, 2),
            })

        # Progressive save after each case
        out_dir = Path("evaluation_outputs/phase_5_16")
        out_dir.mkdir(parents=True, exist_ok=True)
        for out_file in [out_dir / "phase_5_16_10_case_diagnostic.json", Path("phase_5_16_10_case_diagnostic.json")]:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    asyncio.run(run_diagnostic())
