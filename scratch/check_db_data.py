"""Phase 0: Check what evaluations exist in the database for prototyping."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.storage.repository import StorageRepository

repo = StorageRepository(db_path="data/cynthera.db")
evals = repo.list_evaluations(limit=10)

print(f"Found {len(evals)} evaluation(s):\n")
for ev in evals:
    print(f"  ID: {ev['hypothesis_id'][:12]}...")
    print(f"  Drug: {ev['drug_name']}")
    print(f"  Disease: {ev['disease_name']}")
    print(f"  Recommendation: {ev['recommendation']}")
    print(f"  MS: {ev['mechanistic_score']:.3f}, SS: {ev['support_score']:.3f}, RS: {ev['risk_score']:.3f}")
    print(f"  Retrieval: {ev['retrieval_confidence']}")
    print()

if evals:
    # Try loading full package for the first evaluation
    first_id = evals[0]['hypothesis_id']
    print(f"Loading RetrievalPackage for {first_id[:12]}...")
    pkg = repo.get_retrieval_package(first_id)
    if pkg:
        print(f"  Drug: {pkg.drug.name} (ChEMBL: {pkg.drug.chembl_id})")
        print(f"  Disease: {pkg.disease.name} (MeSH: {pkg.disease.mesh_id})")
        print(f"  Targets: {len(pkg.targets)}")
        print(f"  Proteins: {len(pkg.proteins)}")
        print(f"  Pathways: {len(pkg.pathways)}")
        print(f"  Evidence records: {len(pkg.evidence_records)}")
        print(f"  Clinical trials: {len(pkg.clinical_trials)}")
        print(f"  Sources queried: {pkg.sources_queried}")
        print(f"  Sources failed: {pkg.sources_failed}")
    else:
        print("  No RetrievalPackage found!")
    
    print(f"\nLoading ReasoningResult for {first_id[:12]}...")
    result = repo.get_reasoning_result(first_id)
    if result:
        print(f"  Recommendation: {result.recommendation_status.value}")
        print(f"  SS: {result.support_assessment.score:.3f}")
        print(f"  MS: {result.mechanistic_assessment.score:.3f}")
        print(f"  RS: {result.risk_assessment.score:.3f}")
        print(f"  Opposition: {result.opposition_assessment.score:.3f}")
        print(f"  Contradictions: {len(result.contradictions)}")
        print(f"  Candidate mechanisms: {len(result.mechanistic_assessment.candidate_mechanisms)}")
        print(f"  Supporting claims: {len(result.support_assessment.supporting_claim_ids)}")
        print(f"  Risk claims: {len(result.risk_assessment.risk_claim_ids)}")
        print(f"  Claim citations: {len(result.audit_report.claim_citations)}")
    else:
        print("  No ReasoningResult found!")

    # Test EvidenceGraphBuilder
    if pkg:
        print(f"\nRebuilding EvidenceGraph from stored package...")
        from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder
        builder = EvidenceGraphBuilder()
        graph = builder.build(pkg)
        print(f"  Nodes: {len(graph.nodes)}")
        print(f"  Edges: {len(graph.edges)}")
        
        # Show node types
        from collections import Counter
        type_counts = Counter(n.label for n in graph.nodes.values())
        print(f"  Node types: {dict(type_counts)}")
        
        # Show edge predicates
        pred_counts = Counter(e.predicate for e in graph.edges)
        print(f"  Edge predicates: {dict(pred_counts)}")
        
        # Test path finding
        drug_id = f"DRUG:{pkg.drug.name}"
        disease_id = f"DISEASE:{pkg.disease.name}"
        paths = list(graph.find_simple_paths(drug_id, disease_id))
        print(f"  Paths Drug→Disease: {len(paths)}")
        if paths:
            print(f"  Shortest path ({len(paths[0])} hops):")
            for edge in paths[0]:
                print(f"    {edge.source_id} --[{edge.predicate}]--> {edge.target_id} (strength: {edge.evidence_strength:.3f})")
