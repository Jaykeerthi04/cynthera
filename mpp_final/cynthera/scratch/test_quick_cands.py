"""Quick test on more potential contradiction cases."""
import asyncio
import io
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator


CANDS = [
    ("Terbutaline", "Hypertension"),
    ("Pilocarpine", "Asthma"),
    ("Clonidine", "Hypotension"),
    ("Metoprolol", "Asthma"),
]


async def test_cands():
    orchestrator = MasterOrchestrator()
    for drug, disease in CANDS:
        try:
            hyp, pkg, res = await orchestrator.evaluate(drug_name=drug, disease_name=disease, policy=RetrievalPolicy.STANDARD, bypass_cache=False)
            ta = getattr(res.audit_report, "therapeutic_alignment", {}) or {}
            print(f"{drug} -> {disease}: {ta.get('overall_alignment')} (Supp: {ta.get('supporting_groups_count', 0)}, Opp: {ta.get('opposing_groups_count', 0)})")
            for t_al in ta.get("target_alignments", []):
                if t_al.get("is_primary"):
                    print(f"  Target {t_al.get('target_id')}: Drug={t_al.get('drug_action')}, Desired={t_al.get('desired_target_action')}, Alignment={t_al.get('alignment')}, Supp={len(t_al.get('supporting_groups', []))}, Opp={len(t_al.get('opposing_groups', []))}")
        except Exception as e:
            print(f"Error {drug}->{disease}: {e}")


if __name__ == "__main__":
    asyncio.run(test_cands())
