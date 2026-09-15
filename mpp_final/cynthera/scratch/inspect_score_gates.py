"""Inspect specific cases where paths=0 or graph edges=0."""
from __future__ import annotations

import asyncio
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.abspath("."))

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner


async def inspect_case(drug: str, disease: str) -> None:
    print("=" * 80)
    print(f"INSPECTING GRAPH & PATHS FOR: {drug} -> {disease}")
    print("=" * 80)
    
    orchestrator = MasterOrchestrator()
    hyp, package, rr = await orchestrator.evaluate(drug_name=drug, disease_name=disease, bypass_cache=False)
    
    print(f"Drug: {package.drug.name} (chembl={package.drug.chembl_id})")
    print(f"Disease: {package.disease.name} (mesh={package.disease.mesh_id})")
    print(f"Targets: {[ (t.protein_uniprot, t.mechanism) for t in package.targets ]}")
    print(f"Proteins: {[ (p.uniprot_accession, p.gene_symbol, p.organism) for p in package.proteins ]}")
    print(f"Validated Disease Genes count: {len(package.validated_disease_genes or {})}")
    if package.validated_disease_genes:
        print(f"Sample Disease Genes: {list(package.validated_disease_genes.items())[:10]}")
    
    builder = EvidenceGraphBuilder()
    graph, resolver = builder.build(package)
    
    print(f"\nGraph Nodes ({len(graph.nodes)}):")
    for nid, node in graph.nodes.items():
        print(f"  {nid} (name={getattr(node, 'name', '')})")
        
    print(f"\nGraph Edges ({len(graph.edges)}):")
    for e in graph.edges:
        print(f"  {e.source} --[{e.predicate}]--> {e.target} (strength={e.evidence_strength})")
        
    reasoner = MultiHopReasoner()
    paths = reasoner.trace_paths(package)
    print(f"\nPaths Found: {len(paths)}")
    for p in paths:
        print(f"  Path: {p.description} (conf={p.confidence:.4f})")


async def main() -> None:
    # 1. Inspect Aspirin -> Colorectal Cancer (Paths = 0)
    await inspect_case("Aspirin", "Colorectal Cancer")
    print("\n" * 2)
    # 2. Inspect Oseltamivir -> Influenza (Edges = 0)
    await inspect_case("Oseltamivir", "Influenza")


if __name__ == "__main__":
    asyncio.run(main())
