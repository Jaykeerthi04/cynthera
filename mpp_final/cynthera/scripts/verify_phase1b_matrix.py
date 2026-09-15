"""Verify Phase 1B Rule -1 Routing regression matrix and generate decision trace."""

import asyncio
import json
from backend.core.domain.hypothesis import Hypothesis
from backend.infrastructure.cache.evaluation_cache import EvaluationCache
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator

CASES = [
    ("Lisinopril", "hypertension"),
    ("Adalimumab", "Crohn's disease"),
    ("Metformin", "type 2 diabetes mellitus"),
    ("Omeprazole", "gastroesophageal reflux disease"),
    ("Rituximab", "non-Hodgkin lymphoma"),
    ("Insulin glargine", "type 1 diabetes mellitus"),
    ("Sertraline", "major depressive disorder"),
    ("Methotrexate", "rheumatoid arthritis"),
    ("Niacin", "cardiovascular disease"),
]


async def run_matrix():
    cache = EvaluationCache()
    orch = MasterOrchestrator()

    # Invalidate cache for Metformin and Niacin to ensure fresh re-computation under Phase 1A + 1B
    cache.invalidate("Metformin", "type 2 diabetes mellitus")
    cache.invalidate("Niacin", "cardiovascular disease")

    results = []
    print("Evaluating Phase 1B Regression Matrix...\n")
    for drug, disease in CASES:
        cache.invalidate(drug, disease)
        hyp, pkg, res = await orch.evaluate(drug, disease, bypass_cache=False)
        cache.set(drug, disease, res)

        audit = res.audit_report
        sci_ctx = audit.scientific_context if audit else {}
        reg = sci_ctx.get("regulatory", {})
        reg_status = reg.get("status", "UNKNOWN")
        
        opp = res.opposition_assessment
        opp_score = opp.score if opp else 0.0
        opp_level = opp.level if opp else "NONE"
        opp_claims = opp.qualified_negative_claim_count if opp else 0
        
        trace = getattr(audit, "rule_minus_one_trace", {}) if audit else {}
        rec = res.recommendation_status.value

        row = {
            "drug": drug,
            "disease": disease,
            "approval": reg_status,
            "opposition_score": opp_score,
            "opposition_level": opp_level,
            "qualified_negative_claim_count": opp_claims,
            "opposition_evaluated": trace.get("opposition_evaluated", opp is not None),
            "downstream_opposition_rules_reached": trace.get("downstream_opposition_rules_reached", False),
            "final_recommendation": rec,
            "trace": trace,
            "reasons": res.recommendation_reasons,
        }
        results.append(row)
        print(f"[{drug} -> {disease}] Approval: {reg_status} | Opp: {opp_level} ({opp_score:.4f}, {opp_claims} claims) | Rec: {rec}")

    with open("phase1b_regression_matrix_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\nPhase 1B Regression Table:")
    print("| Case | Approval | Opposition | Opposition Evaluated? | Final Recommendation |")
    print("|---|---|---|---|---|")
    for r in results:
        opp_str = f"{r['opposition_level']} ({r['opposition_score']:.4f})"
        eval_str = "YES" if r["opposition_evaluated"] else "NO"
        print(f"| {r['drug']} -> {r['disease']} | {r['approval']} | {opp_str} | {eval_str} | {r['final_recommendation']} |")


if __name__ == "__main__":
    asyncio.run(run_matrix())
