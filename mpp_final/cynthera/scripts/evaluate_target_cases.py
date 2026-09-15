"""Evaluation of the 4 Phase 2 Target Cases (Sections 20, 21, 22).

Target Cases:
1. Ivermectin -> COVID-19
2. Celecoxib -> Alzheimer's disease
3. Simvastatin -> Sepsis
4. Interferon beta-1a -> COVID-19
"""
from __future__ import annotations

import asyncio
import json
from backend.infrastructure.cache.evaluation_cache import EvaluationCache
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.reasoning.opposition.therapeutic_opposition_assessor import evaluate_trial_attribution, matches_disease_condition

TARGET_CASES = [
    ("Ivermectin", "COVID-19"),
    ("Celecoxib", "Alzheimer's disease"),
    ("Simvastatin", "Sepsis"),
    ("Interferon beta-1a", "COVID-19"),
]


async def run_target_cases():
    cache = EvaluationCache()
    orch = MasterOrchestrator()

    all_traces = []

    for drug, disease in TARGET_CASES:
        print(f"\n{'='*70}\nEVALUATING TARGET CASE: {drug} -> {disease}\n{'='*70}")
        cache.invalidate(drug, disease)
        hyp, pkg, res = await orch.evaluate(drug, disease, bypass_cache=False)

        trials = pkg.clinical_trials
        trials_retrieved_count = len(trials)
        nct_ids = [t.nct_id for t in trials]
        trials_with_results = [t for t in trials if t.has_results or t.outcome_measures]
        trials_with_results_ncts = [t.nct_id for t in trials_with_results]

        # Detailed examination of outcome measures
        efficacy_outcomes_examined = 0
        primary_efficacy_outcomes = 0
        negative_candidates = []

        for t in trials:
            for om in getattr(t, "outcome_measures", []):
                if not om.get("is_safety", False):
                    efficacy_outcomes_examined += 1
                    if om.get("type") == "PRIMARY":
                        primary_efficacy_outcomes += 1
            if getattr(t, "is_negative_efficacy", False) or t.status.value in ("COMPLETED_FAILURE", "TERMINATED_LACK_OF_EFFICACY"):
                negative_candidates.append(t)

        # Attribution evaluation on negative candidates
        attribution_results = {}
        for t in negative_candidates:
            attr = evaluate_trial_attribution(t, drug)
            pair_match = matches_disease_condition(t, disease)
            attribution_results[t.nct_id] = {
                "drug_role": attr.drug_role.value,
                "is_differentiating": attr.is_differentiating_intervention,
                "text_evidence": attr.text_attribution_result.value,
                "decision": attr.final_attribution_decision,
                "pair_matched": pair_match,
                "reason": attr.attribution_reason,
            }

        opp = res.opposition_assessment
        opp_score = opp.score if opp else 0.0
        opp_level = opp.level if opp else "NONE"
        qualified_negative_claims = opp.qualified_negative_claim_count if opp else 0
        excluded_negative_claims = opp.excluded_negative_claim_count if opp else 0
        independent_studies = opp.independent_group_count if opp else 0
        final_recommendation = res.recommendation_status.value

        # Determine Root Cause Category (Prompt §20 A through I)
        if trials_retrieved_count == 0:
            root_cause = "A. no relevant trials retrieved"
        elif len(trials_with_results) == 0 and len(negative_candidates) == 0:
            root_cause = "B. no resultsSection (and no efficacy terminations)"
        elif len(trials_with_results) > 0 and efficacy_outcomes_examined == 0:
            root_cause = "C. results not parsed"
        elif len(negative_candidates) == 0:
            root_cause = "D. negative endpoint not classified (results inconclusive or non-negative)"
        elif all(not attribution_results[t.nct_id]["pair_matched"] for t in negative_candidates):
            root_cause = "G. qualification rejected (pair mismatch)"
        elif all(not attribution_results[t.nct_id]["decision"] for t in negative_candidates):
            root_cause = "F. attribution rejected"
        elif qualified_negative_claims > 0:
            root_cause = "QUALIFYING NEGATIVE EVIDENCE RECOVERED"
        else:
            root_cause = "NO QUALIFYING NEGATIVE EVIDENCE RECOVERED"

        trace = {
            "drug": drug,
            "disease": disease,
            "trials_retrieved_count": trials_retrieved_count,
            "nct_ids": nct_ids,
            "trials_with_results_count": len(trials_with_results),
            "trials_with_results_ncts": trials_with_results_ncts,
            "efficacy_outcomes_examined": efficacy_outcomes_examined,
            "primary_efficacy_outcomes": primary_efficacy_outcomes,
            "negative_candidates_count": len(negative_candidates),
            "negative_candidates_ncts": [t.nct_id for t in negative_candidates],
            "attribution_results": attribution_results,
            "qualified_negative_claims": qualified_negative_claims,
            "excluded_negative_claims": excluded_negative_claims,
            "independent_negative_studies": independent_studies,
            "opposition_score": opp_score,
            "opposition_level": opp_level,
            "final_recommendation": final_recommendation,
            "root_cause_determination": root_cause,
        }

        print(json.dumps(trace, indent=2))
        all_traces.append(trace)

    with open("target_cases_trace_results.json", "w", encoding="utf-8") as f:
        json.dump(all_traces, f, indent=2)
    print("\nSaved target cases trace to target_cases_trace_results.json")


if __name__ == "__main__":
    asyncio.run(run_target_cases())
