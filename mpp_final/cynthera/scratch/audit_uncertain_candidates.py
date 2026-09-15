"""Audit script to discover a genuine UNCERTAIN replacement candidate for BENCH-UNC-02.

Evaluates a controlled list of candidate drug-disease pairs through the live Cynthera pipeline.
Verifies that the candidate satisfies:
1. No strong therapeutic directional signal in integrated sources
2. No curated DrugMechDB path
3. No strong Open Targets DoE requirement (or insufficient/uncorrelated)
4. No strong DATTs action requirement
5. Emits INSUFFICIENT / UNCERTAIN
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
from backend.evaluation.benchmark_models import map_alignment_to_class
from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver
from backend.reasoning.directional.therapeutic_alignment import normalize_drug_action


CANDIDATES = [
    ("Methotrexate", "Osteoarthritis"),
    ("Metformin", "Alzheimer Disease"),
    ("Atorvastatin", "Major Depressive Disorder"),
    ("Aspirin", "Schizophrenia"),
    ("Furosemide", "Gout"),
    ("Propranolol", "Multiple Sclerosis"),
    ("Thalidomide", "Asthma"),
]


async def audit_uncertain_candidates():
    orchestrator = MasterOrchestrator()
    print("=" * 80)
    print("CYNTHERA PHASE 4E.4 — UNCERTAIN CANDIDATE AUDIT")
    print("=" * 80)

    for drug, disease in CANDIDATES:
        print(f"\nEvaluating: {drug} -> {disease}")
        try:
            hyp, pkg, res = await orchestrator.evaluate(
                drug_name=drug,
                disease_name=disease,
                policy=RetrievalPolicy.STANDARD,
                bypass_cache=False,
            )
            ta = getattr(res.audit_report, "therapeutic_alignment", {}) or {}
            al = ta.get("overall_alignment", "INSUFFICIENT")
            pred_class = map_alignment_to_class(al)

            resolver = BiologicalIdentifierResolver(
                proteins=pkg.proteins,
                genes=pkg.genes,
                mappings=pkg.identifier_mappings,
            )

            targets_info = []
            for t in pkg.targets:
                uni = (t.protein_uniprot or "").strip().upper()
                resolved = resolver.resolve(uni, source="ChEMBL")
                canon = resolved.canonical_symbol or resolved.canonical_identifier or uni
                act = normalize_drug_action(t.mechanism).value
                targets_info.append(f"{canon}({act})")

            dm_paths = [dm.path_id for dm in pkg.drugmechdb_evidence if dm.is_curated_path_available]
            ot_count = len(pkg.opentargets_doe_evidence)
            datts_count = len(pkg.datts_evidence)
            tde_count = len(pkg.therapeutic_direction_evidence)

            supp = ta.get("supporting_groups_count", 0)
            opp = ta.get("opposing_groups_count", 0)

            print(f"  Predicted Alignment: {al} -> Class: {pred_class.value}")
            print(f"  Targets ({len(pkg.targets)}): {', '.join(targets_info[:5])}")
            print(f"  Open Targets DoE Records: {ot_count}")
            print(f"  DATTs Records:            {datts_count}")
            print(f"  DrugMechDB Paths:         {len(dm_paths)} ({dm_paths})")
            print(f"  Total TDE Records:        {tde_count}")
            print(f"  Supporting Groups:        {supp}")
            print(f"  Opposing Groups:          {opp}")
            print(f"  Explanation:              {ta.get('explanation')}")

        except Exception as e:
            print(f"  ERROR evaluating {drug} -> {disease}: {e}")

    print("\n" + "=" * 80)
    print("AUDIT COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(audit_uncertain_candidates())
