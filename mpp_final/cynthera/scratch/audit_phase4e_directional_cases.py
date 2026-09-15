"""Phase 4E Deep Diagnostic Audit Script: Norepinephrine, Methotrexate, Testosterone.

Runs the live Cynthera pipeline on three key cases:
1. Testosterone -> Prostate Cancer (Control)
2. Norepinephrine -> Heart Failure (Missed Negative)
3. Methotrexate -> Rheumatoid Arthritis (Over-aggregated Positive vs Expected Uncertain)

Traces every stage from Retrieval, Canonicalization, DoE/DATTs/ChEMBL/DrugMechDB/Lit,
to TherapeuticDirectionEvidence, Independence Grouping, and Alignment.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time

# Ensure UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.therapeutic_direction_evidence import (
    TherapeuticAction,
    TherapeuticAlignment,
    EvidenceFamily,
    TherapeuticDirectionEvidence,
)
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.evaluation.benchmark_models import BenchmarkClass, map_alignment_to_class
from backend.reasoning.directional.directional_evidence_builder import DirectionalEvidenceBuilder
from backend.reasoning.directional.therapeutic_alignment import (
    TherapeuticAlignmentEngine,
    normalize_drug_action,
    derive_desired_target_action,
    group_evidence_by_independence,
)
from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver


AUDIT_CASES = [
    ("Testosterone", "Prostate Cancer", BenchmarkClass.NEGATIVE, "BENCH-NEG-03"),
    ("Norepinephrine", "Heart Failure", BenchmarkClass.NEGATIVE, "BENCH-NEG-02"),
    ("Methotrexate", "Rheumatoid Arthritis", BenchmarkClass.UNCERTAIN, "BENCH-UNC-02"),
]


async def run_diagnostic():
    orchestrator = MasterOrchestrator()
    alignment_engine = TherapeuticAlignmentEngine()
    builder = DirectionalEvidenceBuilder()

    print("=" * 90)
    print("CYNTHERA PHASE 4E — DEEP EVIDENCE TRACE AUDIT")
    print("=" * 90)

    audit_results = {}

    for drug_name, disease_name, expected_class, case_id in AUDIT_CASES:
        print(f"\n\n{'#' * 90}")
        print(f"CASE: {drug_name.upper()} -> {disease_name.upper()} ({case_id})")
        print(f"EXPECTED: {expected_class.value}")
        print(f"{'#' * 90}")

        # Run full pipeline with cache to inspect exact package
        t0 = time.time()
        hyp, pkg, res = await orchestrator.evaluate(
            drug_name=drug_name,
            disease_name=disease_name,
            policy=RetrievalPolicy.STANDARD,
            bypass_cache=False,
        )
        elapsed = time.time() - t0

        ta_report = getattr(res.audit_report, "therapeutic_alignment", {}) or {}
        overall_alignment = ta_report.get("overall_alignment", "INSUFFICIENT")
        predicted_class = map_alignment_to_class(overall_alignment)

        print(f"\nExecution Time: {elapsed:.2f}s")
        print(f"Overall Predicted Alignment: {overall_alignment}")
        print(f"Predicted Class: {predicted_class.value} (Expected: {expected_class.value})")
        print(f"Status: {'PASS / CORRECT' if predicted_class == expected_class else 'FAIL / INCORRECT'}")

        # -------------------------------------------------------------
        # 1. RETRIEVAL & CANONICAL TARGETS
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("1. RETRIEVAL & TARGET CANONICALIZATION AUDIT")
        print("=" * 60)
        print(f"Total Targets Retrieved from ChEMBL: {len(pkg.targets)}")
        print(f"Total Proteins in Package: {len(pkg.proteins)}")
        print(f"Total Identifier Mappings: {len(pkg.identifier_mappings)}")

        resolver = BiologicalIdentifierResolver(
            proteins=pkg.proteins,
            genes=pkg.genes,
            mappings=pkg.identifier_mappings,
        )

        for i, t in enumerate(pkg.targets, 1):
            uni = (t.protein_uniprot or "").strip().upper()
            resolved = resolver.resolve(uni, source="ChEMBL")
            canon_sym = resolved.canonical_symbol or resolved.canonical_identifier or uni
            norm_action = normalize_drug_action(t.mechanism)

            # Find matching protein name if available
            pname = "Unknown"
            for p in pkg.proteins:
                if p.uniprot_accession.upper() == uni or (p.gene_symbol and p.gene_symbol.upper() == canon_sym):
                    pname = p.name
                    break

            print(f"  Target #{i}:")
            print(f"    Target Protein:     {pname} ({uni})")
            print(f"    Resolved Canonical: {canon_sym}")
            print(f"    Raw Mechanism:      {t.mechanism}")
            print(f"    Normalized Action:  {norm_action.value}")
            print(f"    Affinity:           {t.affinity_nm} nM ({t.affinity_type})")
            print(f"    Provenance:         {t.provenance.source_name} (Record: {t.provenance.record_id})")

        # -------------------------------------------------------------
        # 2. OPEN TARGETS DoE AUDIT
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("2. OPEN TARGETS DIRECTION-OF-EFFECT (DoE) AUDIT")
        print("=" * 60)
        print(f"Total Open Targets DoE Records Retrieved: {len(pkg.opentargets_doe_evidence)}")
        if not pkg.opentargets_doe_evidence:
            print("  Open Targets DoE Records = NONE")
        else:
            for i, doe in enumerate(pkg.opentargets_doe_evidence, 1):
                tgt_dir = getattr(doe, "direction_on_target", None)
                trait_dir = getattr(doe, "direction_on_trait", None)
                raw_req = derive_desired_target_action(tgt_dir, trait_dir, None)
                print(f"  DoE Record #{i}:")
                print(f"    Target ID (Ensembl/Symbol): {getattr(doe, 'target_id', None)}")
                print(f"    Target Symbol (Raw):        {getattr(doe, 'target_symbol', None)}")
                print(f"    Target UniProt:             {getattr(doe, 'target_uniprot', None)}")
                print(f"    Disease EFO / ID:           {getattr(doe, 'disease_id', None)}")
                print(f"    Target Direction (Raw):     {tgt_dir}")
                print(f"    Trait Direction (Raw):      {trait_dir}")
                print(f"    Derived Required Action:    {raw_req.value}")
                print(f"    Data Source ID:             {getattr(doe, 'datasource_id', None)}")
                print(f"    Score:                      {getattr(doe, 'score', None)}")
                print(f"    Study ID / Literature:      {getattr(doe, 'study_id', None)} / {getattr(doe, 'literature', None)}")

        # -------------------------------------------------------------
        # 3. DATTs AUDIT
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("3. DATTs DIRECTIONAL EVIDENCE AUDIT")
        print("=" * 60)
        print(f"Total DATTs Records Retrieved: {len(pkg.datts_evidence)}")
        if not pkg.datts_evidence:
            print("  DATTs Records = NONE")
        else:
            for i, datts in enumerate(pkg.datts_evidence, 1):
                print(f"  DATTs Record #{i}:")
                print(f"    Gene Symbol:             {datts.gene_symbol}")
                print(f"    UniProt Accession:       {datts.uniprot_id}")
                print(f"    Disease Name:            {datts.disease_name}")
                print(f"    Raw Rel Type:            {datts.rel_type}")
                print(f"    Required Action:         {datts.required_action.value}")
                print(f"    Literature:              {datts.literature}")
                print(f"    Source:                  {datts.source}")
                print(f"    Comment:                 {datts.comment}")

        # -------------------------------------------------------------
        # 4. ChEMBL MECHANISM AUDIT
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("4. ChEMBL MECHANISM & DIRECTIONAL ACTION AUDIT")
        print("=" * 60)
        for t in pkg.targets:
            norm_action = normalize_drug_action(t.mechanism)
            print(f"  UniProt: {t.protein_uniprot}")
            print(f"    Mechanism text:     {t.mechanism}")
            print(f"    Normalized Action:  {norm_action.value}")

        # -------------------------------------------------------------
        # 5. DRUGMECHDB AUDIT
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("5. DRUGMECHDB MECHANISTIC PATH AUDIT")
        print("=" * 60)
        print(f"Total DrugMechDB Records: {len(pkg.drugmechdb_evidence)}")
        if not pkg.drugmechdb_evidence or not any(dm.is_curated_path_available for dm in pkg.drugmechdb_evidence):
            print("  DrugMechDB path = NONE")
        else:
            for dm in pkg.drugmechdb_evidence:
                print(f"  DrugBank ID:             {dm.drugbank_id}")
                print(f"  Curated Path Available:  {dm.is_curated_path_available}")
                print(f"  Target UniProt:          {dm.target_uniprot}")
                print(f"  Path Summary:            {dm.path_summary}")
                print(f"  Intermediate Nodes:      {len(dm.nodes)} nodes, {len(dm.links)} links")
                for node in dm.nodes:
                    print(f"    Node: {node.get('name')} ({node.get('label')})")
                for link in dm.links:
                    print(f"    Link: {link.get('key')} -> {link.get('label')}")

        # -------------------------------------------------------------
        # 6. LITERATURE DIRECTIONAL AUDIT
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("6. LITERATURE DIRECTIONAL CLAIMS AUDIT")
        print("=" * 60)
        lit_records = [r for r in pkg.therapeutic_direction_evidence if r.source == "Literature"]
        print(f"Total Literature Directional Records: {len(lit_records)}")
        if not lit_records:
            print("  Literature evidence = NONE")
        else:
            for i, lr in enumerate(lit_records, 1):
                print(f"  Lit Record #{i}:")
                print(f"    Target Canonical ID:     {lr.target_canonical_id}")
                print(f"    Required Action:         {lr.required_action}")
                print(f"    Causal Grounding:        {lr.causal_grounding}")
                print(f"    Reference / PMID:        {lr.underlying_reference}")
                print(f"    Independence Group:      {lr.independence_group}")

        # -------------------------------------------------------------
        # 7. THERAPEUTIC DIRECTION EVIDENCE (ALL RAW NORMALIZED RECORDS)
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("7. ALL NORMALIZED THERAPEUTIC DIRECTION EVIDENCE RECORDS")
        print("=" * 60)
        print(f"Total TherapeuticDirectionEvidence Records: {len(pkg.therapeutic_direction_evidence)}")
        for i, tde in enumerate(pkg.therapeutic_direction_evidence, 1):
            print(f"  [EVIDENCE #{i}]")
            print(f"    Family:             {tde.evidence_family.value if hasattr(tde.evidence_family, 'value') else tde.evidence_family}")
            print(f"    Subject (Target):   {tde.target_canonical_id}")
            print(f"    Object (Disease):   {tde.disease_canonical_id}")
            print(f"    Target Direction:   {tde.target_direction}")
            print(f"    Trait Direction:    {tde.trait_direction}")
            print(f"    Required Action:    {tde.required_action}")
            print(f"    Causal Grounding:   {tde.causal_grounding.value if hasattr(tde.causal_grounding, 'value') else tde.causal_grounding}")
            print(f"    Source:             {tde.source}")
            print(f"    Confidence:         {tde.confidence}")
            print(f"    Reference:          {tde.underlying_reference}")
            print(f"    Independence Group: {tde.independence_group}")

        # -------------------------------------------------------------
        # 8. INDEPENDENCE GROUPING AUDIT
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("8. INDEPENDENCE GROUPING & DEDUPLICATION AUDIT")
        print("=" * 60)
        # Group by target first
        target_tde_map = {}
        for tde in pkg.therapeutic_direction_evidence:
            tid = tde.target_canonical_id
            target_tde_map.setdefault(tid, []).append(tde)

        for tid, tde_list in target_tde_map.items():
            groups = group_evidence_by_independence(tde_list)
            print(f"\n  Target: {tid}")
            print(f"    Raw Evidence Count:          {len(tde_list)}")
            print(f"    Unique Independence Groups:  {len(groups)}")
            for g in groups:
                print(f"      - Group ID: {g.group_id}")
                print(f"        Desired Action:    {g.desired_action.value}")
                print(f"        Evidence Family:   {g.evidence_family.value if hasattr(g.evidence_family, 'value') else g.evidence_family}")
                print(f"        Causal Grounding:  {g.causal_grounding.value if hasattr(g.causal_grounding, 'value') else g.causal_grounding}")
                print(f"        Member Records:    {g.member_record_count}")
                print(f"        Sources:           {g.sources}")
                print(f"        References:        {g.references}")
                print(f"        Summary:           {g.summary}")

        # -------------------------------------------------------------
        # 9. TARGET-BY-TARGET THERAPEUTIC ALIGNMENT
        # -------------------------------------------------------------
        print("\n" + "=" * 60)
        print("9. TARGET-BY-TARGET THERAPEUTIC ALIGNMENT")
        print("=" * 60)
        for ta in ta_report.get("target_alignments", []):
            print(f"  Target: {ta.get('target_id')} ({ta.get('target_name')})")
            print(f"    Is Primary:           {ta.get('is_primary')}")
            print(f"    Drug Action:          {ta.get('drug_action')}")
            print(f"    Desired Action:       {ta.get('desired_target_action')}")
            print(f"    Alignment Verdict:    {ta.get('alignment')}")
            print(f"    Confidence:           {ta.get('confidence')}")
            print(f"    Supporting Groups:    {ta.get('supporting_groups')}")
            print(f"    Opposing Groups:      {ta.get('opposing_groups')}")
            print(f"    DrugMechDB Validated: {ta.get('drugmechdb_validated')}")
            print(f"    Explanation:          {ta.get('explanation')}")

        audit_results[drug_name] = {
            "pkg": pkg,
            "ta_report": ta_report,
            "predicted_class": predicted_class,
            "expected_class": expected_class,
        }

    return audit_results


if __name__ == "__main__":
    asyncio.run(run_diagnostic())
