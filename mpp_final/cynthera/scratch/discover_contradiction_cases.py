"""Contradiction Candidate Discovery Script for Phase 4E.4.

Evaluates a controlled list of well-known pharmacological contradiction candidates
through the live Cynthera pipeline.

Identifies pairs where:
1. Both directional claims are machine-readable.
2. Both claims are canonically mapped to the same biological target/disease entities.
3. The polarity is genuinely opposite (e.g. Drug Action vs Disease Requirement,
   or Open Targets vs DATTs/Clinical directions, or opposing target requirements).
4. Genuine independence and traceable provenance.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver
from backend.reasoning.directional.therapeutic_alignment import normalize_drug_action


CONTRADICTION_CANDIDATES = [
    ("Propranolol", "Asthma"),               # ADRB2 antagonist vs bronchodilation requirement (contra-indicated)
    ("Dobutamine", "Heart Failure"),         # ADRB1 agonist vs chronic HF beta-blockade
    ("Rosiglitazone", "Heart Failure"),      # PPARG agonist vs fluid retention in HF
    ("Milrinone", "Heart Failure"),          # PDE3A inhibitor: acute inotrope vs chronic mortality
    ("Verapamil", "Heart Failure"),          # CACNA1C blocker (negative inotrope) in HFrEF
    ("Ibuprofen", "Chronic Kidney Disease"), # PTGS1/2 inhibitor vs renal hemodynamics
    ("Celecoxib", "Myocardial Infarction"),  # PTGS2 inhibitor vs CV risk
    ("Albuterol", "Hypertension"),           # ADRB2/ADRB1 agonist vs BP reduction
    ("Dopamine", "Heart Failure"),           # Adrenergic/dopaminergic agonist in HF
    ("Aspirin", "Asthma"),                   # COX inhibitor vs AERD bronchospasm
]


async def discover_contradictions():
    orchestrator = MasterOrchestrator()
    print("=" * 80)
    print("CYNTHERA PHASE 4E.4 — CONTRADICTION CANDIDATE DISCOVERY AUDIT")
    print("=" * 80)

    for drug, disease in CONTRADICTION_CANDIDATES:
        print(f"\n" + "-" * 70)
        print(f"CASE: {drug} -> {disease}")
        print("-" * 70)
        try:
            hyp, pkg, res = await orchestrator.evaluate(
                drug_name=drug,
                disease_name=disease,
                policy=RetrievalPolicy.STANDARD,
                bypass_cache=False,
            )
            ta = getattr(res.audit_report, "therapeutic_alignment", {}) or {}
            overall_al = ta.get("overall_alignment", "INSUFFICIENT")

            resolver = BiologicalIdentifierResolver(
                proteins=pkg.proteins,
                genes=pkg.genes,
                mappings=pkg.identifier_mappings,
            )

            print(f"  Overall Alignment: {overall_al}")
            print(f"  Supporting Groups: {ta.get('supporting_groups_count', 0)}")
            print(f"  Opposing Groups:   {ta.get('opposing_groups_count', 0)}")
            print(f"  Explanation:       {ta.get('explanation')}")

            # Inspect per-target alignments
            print(f"  Target Alignments ({len(ta.get('target_alignments', []))}):")
            for t_al in ta.get("target_alignments", []):
                tid = t_al.get("target_id")
                is_p = t_al.get("is_primary")
                drug_act = t_al.get("drug_action")
                des_act = t_al.get("desired_target_action")
                verdict = t_al.get("alignment")
                supp_g = t_al.get("supporting_groups", [])
                opp_g = t_al.get("opposing_groups", [])

                print(f"    Target: {tid} (Primary: {is_p})")
                print(f"      Drug Action:     {drug_act}")
                print(f"      Desired Action:  {des_act}")
                print(f"      Target Verdict:  {verdict}")
                print(f"      Support Groups:  {len(supp_g)} {supp_g}")
                print(f"      Oppose Groups:   {len(opp_g)} {opp_g}")
                print(f"      Explanation:     {t_al.get('explanation')}")

            # Check if Open Targets / DATTs evidence was retrieved
            ot_doe = [d for d in pkg.opentargets_doe_evidence if d.direction_on_target or d.direction_on_trait]
            datts = [d for d in pkg.datts_evidence]
            print(f"  Data Source Stats: OT DoE with direction={len(ot_doe)}, DATTs={len(datts)}, DrugMechDB={len(pkg.drugmechdb_evidence)}")

        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n" + "=" * 80)
    print("DISCOVERY AUDIT COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(discover_contradictions())
