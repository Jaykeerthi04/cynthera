import asyncio
import sys
from pathlib import Path
sys.path.insert(0, ".")
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')

from backend.infrastructure.cache.evaluation_cache import EvaluationCache
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy

cache = EvaluationCache()
inv = cache.invalidate("Metformin", "Type 2 diabetes mellitus")
print(f"Invalidated Metformin from cache: {inv}")

async def test():
    orch = MasterOrchestrator()
    h, pkg, res = await orch.evaluate(
        drug_name="Metformin",
        disease_name="Type 2 diabetes mellitus",
        policy=RetrievalPolicy.STANDARD,
        bypass_cache=False,
    )
    print("=== METFORMIN THROUGH MASTER ORCHESTRATOR ===")
    print(f"Recommendation: {res.recommendation_status.value}")
    print(f"Opposition Score: {res.opposition_assessment.score}")
    print(f"Opposition Level: {res.opposition_assessment.level}")
    print(f"Qualified Neg Claims: {res.opposition_assessment.qualified_negative_claim_count}")
    print(f"Groups: {res.opposition_assessment.independent_group_count}")
    print(f"Rationale: {res.opposition_assessment.rationale}")

asyncio.run(test())
