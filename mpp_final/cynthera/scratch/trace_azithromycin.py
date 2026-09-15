import asyncio
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy

async def main():
    orch = MasterOrchestrator()
    hyp, pkg, res = await orch.evaluate(
        drug_name="Azithromycin",
        disease_name="COVID-19",
        policy=RetrievalPolicy.STANDARD,
        bypass_cache=False,
    )
    print("Azithromycin -> COVID-19 with current code:")
    print("  Prediction:", res.prediction)
    print("  Recommendation:", res.recommendation)
    print("  Approval signal:", pkg.approval_signal)
    print("  Opposition assessment score:", res.opposition_assessment.score, "level:", res.opposition_assessment.level, "count:", res.opposition_assessment.qualified_negative_claim_count)
    print("  Recommendation reasons:")
    for r in res.recommendation_reasons:
        print("   *", r)

asyncio.run(main())
