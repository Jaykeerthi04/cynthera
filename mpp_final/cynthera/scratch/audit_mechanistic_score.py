"""Mechanistic Score Root-Cause Diagnostic Audit.

Traces the complete score dataflow across production evaluations to pinpoint
why Mechanistic Score (MS) evaluates to 0 / NONE for test inputs.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.abspath("."))

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner
from backend.reasoning.mechanistic.mechanism_validation import MechanismValidator


AUDIT_PAIRS = [
    ("Furosemide", "Edema"),
    ("Lisinopril", "Hypertension"),
    ("Oseltamivir", "Influenza"),
    ("Dapagliflozin", "Heart Failure"),
    ("Thalidomide", "Multiple Myeloma"),
    ("Aspirin", "Colorectal Cancer"),
    ("Metformin", "Type 2 Diabetes"),
    ("Testosterone", "Prostate Cancer"),
]


async def audit_case(orchestrator: MasterOrchestrator, drug: str, disease: str) -> dict[str, Any]:
    print("=" * 80, flush=True)
    print(f"DIAGNOSTIC AUDIT: {drug.upper()} -> {disease.upper()}", flush=True)
    print("=" * 80, flush=True)

    t0 = time.time()
    hyp, package, rr = await orchestrator.evaluate(drug_name=drug, disease_name=disease, bypass_cache=False)
    elapsed = time.time() - t0
    print(f"  [Evaluated in {elapsed:.2f}s]", flush=True)

    targets = package.targets
    pathways = package.pathways
    reactions = getattr(package, "reactions", []) or []
    disease_genes = package.validated_disease_genes or {}
    evidence_records = package.evidence_records
    
    print("\n--- 1. RETRIEVAL PACKAGE ---", flush=True)
    print(f"  Targets retrieved:        {len(targets)} ({[t.protein_uniprot for t in targets[:5]]})", flush=True)
    print(f"  Pathways retrieved:       {len(pathways)} ({[getattr(p, 'name', getattr(p, 'pathway_name', ''))[:30] for p in pathways[:3]]})", flush=True)
    print(f"  Reactions retrieved:      {len(reactions)}", flush=True)
    print(f"  Validated Disease Genes:  {len(disease_genes)} ({list(disease_genes.keys())[:5]})", flush=True)
    print(f"  Evidence Records:         {len(evidence_records)}", flush=True)
    print(f"  Sources Failed:           {package.sources_failed}", flush=True)

    # 2. Evidence Graph
    print("\n--- 2. EVIDENCE GRAPH ---", flush=True)
    graph_builder = EvidenceGraphBuilder()
    graph, _ = graph_builder.build(package)
    
    node_types = {}
    for node_id, node in graph.nodes.items():
        nt = getattr(node, "type", "UNKNOWN")
        node_types[nt] = node_types.get(nt, 0) + 1
        
    edge_types = {}
    for edge in graph.edges:
        pred = getattr(edge, "predicate", "UNKNOWN")
        edge_types[pred] = edge_types.get(pred, 0) + 1

    print(f"  Total Graph Nodes:        {len(graph.nodes)} -> {node_types}", flush=True)
    print(f"  Total Graph Edges:        {len(graph.edges)} -> {edge_types}", flush=True)
    
    drug_id = f"DRUG:{package.drug.name}"
    disease_id = f"DISEASE:{package.disease.name}"
    print(f"  Drug in graph:            {drug_id in graph.nodes}", flush=True)
    print(f"  Disease in graph:         {disease_id in graph.nodes}", flush=True)

    # 3. Multi-Hop Reasoner (Raw Path Finding)
    print("\n--- 3. MULTI-HOP PATH FINDING ---", flush=True)
    reasoner = MultiHopReasoner()
    paths = reasoner.trace_paths(package)
    print(f"  Traversable Paths Found:  {len(paths)}", flush=True)
    for i, p in enumerate(paths[:3], start=1):
        print(f"    Path {i} [{p.path_type}, conf={p.confidence:.4f}]: {p.description}", flush=True)

    # 4. Candidate Mechanisms (Discovery)
    print("\n--- 4. CANDIDATE MECHANISMS (PRE-VALIDATION) ---", flush=True)
    discovered_candidates = reasoner.discover_candidate_mechanisms(package, paths)
    print(f"  Discovered Candidates:    {len(discovered_candidates)}", flush=True)
    for i, c in enumerate(discovered_candidates[:3], start=1):
        print(f"    Cand {i}: {c.name} | Level={c.support_level} | Conf={c.confidence_score:.4f} | Polarity={c.directional_polarity}", flush=True)

    # 5. Mechanism Validation
    print("\n--- 5. MECHANISM VALIDATION (POST-VALIDATION) ---", flush=True)
    validator = MechanismValidator()
    # Pass claims from rr or empty
    validated_candidates = validator.validate(package, discovered_candidates, getattr(rr, "claims", []) or [])
    print(f"  Validated Candidates:     {len(validated_candidates)}", flush=True)
    for i, c in enumerate(validated_candidates[:3], start=1):
        print(f"    Val Cand {i}: {c.name}", flush=True)
        print(f"      Support Level:        {c.support_level}", flush=True)
        print(f"      Confidence Score:     {c.confidence_score:.4f}", flush=True)
        print(f"      Discovery Status:     {c.discovery_status}", flush=True)
        print(f"      Validation Dims:      {c.validation_dimensions}", flush=True)
        print(f"      Missing Critical:     {c.missing_critical_evidence}", flush=True)

    # 6. Mechanistic Score Derivation
    print("\n--- 6. MECHANISTIC SCORE DERIVATION ---", flush=True)
    raw_ms_from_paths = reasoner.compute_mechanistic_score(paths)
    ms_score, ms_level = reasoner.compute_mechanistic_score_from_candidates(validated_candidates)
    print(f"  Score from paths (raw):       {raw_ms_from_paths:.4f}", flush=True)
    print(f"  Score from candidates:        {ms_score:.4f}", flush=True)
    print(f"  Level from candidates:        {ms_level}", flush=True)

    # 7. End-to-End Orchestrator Reasoning Result
    print("\n--- 7. END-TO-END REASONING RESULT ---", flush=True)
    ms_assessment = rr.mechanistic_assessment
    
    print(f"  ReasoningResult MS Score:     {ms_assessment.score}", flush=True)
    print(f"  ReasoningResult MS Level:     {ms_assessment.level}", flush=True)
    print(f"  Evidence Status:              {ms_assessment.evidence_status}", flush=True)
    print(f"  Rationale:                    {ms_assessment.rationale}", flush=True)
    
    # 8. Directional Alignment
    audit_rep = getattr(rr, "audit_report", None)
    ta_dict = getattr(audit_rep, "therapeutic_alignment", {}) if audit_rep else {}
    da_verdict = ta_dict.get("overall_alignment", "N/A") if isinstance(ta_dict, dict) else "N/A"
    print(f"  Directional Alignment:        {da_verdict}", flush=True)

    # Trace First Zero
    first_zero = None
    cand_conf = round(validated_candidates[0].confidence_score, 4) if validated_candidates else 0.0
    audit_flow = [
        ("Retrieved targets", len(targets)),
        ("Retrieved pathways", len(pathways)),
        ("Retrieved reactions", len(reactions)),
        ("Graph nodes", len(graph.nodes)),
        ("Graph edges", len(graph.edges)),
        ("Complete mechanistic paths", len(paths)),
        ("Candidate mechanisms", len(discovered_candidates)),
        ("Candidate confidence", cand_conf),
        ("Raw MS from paths", raw_ms_from_paths),
        ("Candidate MS score", ms_score),
        ("ReasoningResult MS", ms_assessment.score),
    ]
    for layer, val in audit_flow:
        if (val == 0 or val == 0.0 or val is None) and first_zero is None:
            first_zero = layer

    return {
        "drug": drug,
        "disease": disease,
        "targets": len(targets),
        "pathways": len(pathways),
        "reactions": len(reactions),
        "graph_nodes": len(graph.nodes),
        "graph_edges": len(graph.edges),
        "paths": len(paths),
        "candidates": len(discovered_candidates),
        "cand_conf": cand_conf,
        "cand_level": validated_candidates[0].support_level if validated_candidates else "NONE",
        "raw_ms_paths": raw_ms_from_paths,
        "cand_ms": ms_score,
        "cand_ms_level": ms_level,
        "final_ms": ms_assessment.score,
        "final_level": ms_assessment.level,
        "alignment": da_verdict,
        "first_zero": first_zero or "NONE (Non-zero)",
    }


async def main() -> None:
    print("=" * 80, flush=True)
    print("CYNTHERA MECHANISTIC SCORE ROOT-CAUSE AUDIT")
    print("=" * 80, flush=True)

    orchestrator = MasterOrchestrator()
    summary_rows = []

    for drug, disease in AUDIT_PAIRS:
        try:
            row = await audit_case(orchestrator, drug, disease)
            summary_rows.append(row)
        except Exception as e:
            print(f"ERROR on {drug} -> {disease}: {e}", flush=True)
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 100, flush=True)
    print("FIRST ZERO & SCORE DATAFLOW SUMMARY TABLE", flush=True)
    print("=" * 100, flush=True)
    headers = ["Drug -> Disease", "Targets", "Pathways", "Edges", "Paths", "Cands", "Cand Conf", "Val Level", "Final MS", "Final Level", "Alignment", "First Zero"]
    print(f"{headers[0]:<32} | {headers[1]:<7} | {headers[2]:<8} | {headers[3]:<5} | {headers[4]:<5} | {headers[5]:<5} | {headers[6]:<9} | {headers[7]:<15} | {headers[8]:<8} | {headers[9]:<11} | {headers[10]:<12} | {headers[11]}", flush=True)
    print("-" * 145, flush=True)
    for r in summary_rows:
        pair_str = f"{r['drug']} -> {r['disease']}"
        print(f"{pair_str:<32} | {r['targets']:<7} | {r['pathways']:<8} | {r['graph_edges']:<5} | {r['paths']:<5} | {r['candidates']:<5} | {r['cand_conf']:<9.4f} | {r['cand_level']:<15} | {r['final_ms']:<8.4f} | {r['final_level']:<11} | {r['alignment']:<12} | {r['first_zero']}", flush=True)
    print("=" * 100, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
