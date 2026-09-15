"""Targeted deep inspection for Norepinephrine and Testosterone."""
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


async def inspect_cases():
    orchestrator = MasterOrchestrator()

    for drug, disease in [("Norepinephrine", "Heart Failure"), ("Testosterone", "Prostate Cancer")]:
        print("=" * 80)
        print(f"CASE: {drug} -> {disease}")
        print("=" * 80)
        hyp, pkg, res = await orchestrator.evaluate(drug_name=drug, disease_name=disease, policy=RetrievalPolicy.STANDARD, bypass_cache=False)
        ta_report = getattr(res.audit_report, "therapeutic_alignment", {}) or {}

        print("OVERALL ALIGNMENT:", ta_report.get("overall_alignment"))
        print("EXPLANATION:", ta_report.get("explanation"))

        print("\n--- TARGETS RETRIEVED FROM CHEMBL ---")
        resolver = BiologicalIdentifierResolver(proteins=pkg.proteins, genes=pkg.genes, mappings=pkg.identifier_mappings)
        for t in pkg.targets:
            uni = (t.protein_uniprot or "").strip().upper()
            resolved = resolver.resolve(uni, source="ChEMBL")
            canon = resolved.canonical_symbol or resolved.canonical_identifier or uni
            print(f"  UniProt: {uni} -> Canonical: {canon} | Mechanism: {t.mechanism} -> Norm: {normalize_drug_action(t.mechanism).value}")

        print("\n--- OPEN TARGETS DoE RECORDS ---")
        print(f"Total DoE Records: {len(pkg.opentargets_doe_evidence)}")
        for doe in pkg.opentargets_doe_evidence:
            print(f"  Target: {doe.target_symbol} (ID: {doe.target_id}) | LoF/GoF: {doe.direction_on_target} | Trait: {doe.direction_on_trait} | Datasource: {doe.datasource_id}")

        print("\n--- DATTS RECORDS ---")
        print(f"Total DATTs Records: {len(pkg.datts_evidence)}")
        for d in pkg.datts_evidence:
            print(f"  Gene: {d.gene_symbol} | Req: {d.required_action.value} | Rel: {d.rel_type} | Cit: {d.literature}")

        print("\n--- DRUGMECHDB RECORDS ---")
        print(f"Total DrugMechDB Records: {len(pkg.drugmechdb_evidence)}")
        for dm in pkg.drugmechdb_evidence:
            print(f"  Path Available: {dm.is_curated_path_available} | Target UniProt: {dm.target_uniprot} | Summary: {dm.path_summary}")

        print("\n--- NORMALIZED THERAPEUTIC DIRECTION EVIDENCE (TDE) ---")
        print(f"Total TDE: {len(pkg.therapeutic_direction_evidence)}")
        for tde in pkg.therapeutic_direction_evidence:
            print(f"  Target: {tde.target_canonical_id} | Source: {tde.source} | TgtDir: {tde.target_direction} | TraitDir: {tde.trait_direction} | ReqAct: {tde.required_action} | Grounding: {tde.causal_grounding} | IndepGrp: {tde.independence_group}")

        print("\n--- TARGET ALIGNMENTS IN REPORT ---")
        for ta in ta_report.get("target_alignments", []):
            print(f"  Target: {ta.get('target_id')} | IsPrimary: {ta.get('is_primary')} | DrugAct: {ta.get('drug_action')} | Desired: {ta.get('desired_target_action')} | Alignment: {ta.get('alignment')} | Supp: {ta.get('supporting_groups')} | Opp: {ta.get('opposing_groups')}")
            print(f"    Explanation: {ta.get('explanation')}")
        print("\n")


if __name__ == "__main__":
    asyncio.run(inspect_cases())
