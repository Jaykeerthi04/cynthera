"""GraphIntegrityAudit — Generic diagnostic audit for EvidenceGraph structural integrity.

Provides comprehensive observability into biological entity ingestion, identifier canonicalization,
actual graph node/edge creation, evidence coverage, hop connectivity, partial path depth,
isolated node detection, and empirical root-cause localization without modifying production reasoning.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.value_objects.biological_identifier import (
    BiologicalDirection,
    BiologicalIdentifierType,
)
from backend.reasoning.mechanistic.evidence_graph import (
    EvidenceGraph,
    EvidenceGraphBuilder,
    GraphEdge,
    GraphNode,
    build_validated_gene_scores,
    pathway_gene_symbols,
    pathway_relevance_score,
    target_in_pathway,
    clean_uniprot,
    _MAX_TARGETS,
    _MAX_PATHWAYS_PER_TARGET,
    _NODE_DRUG,
    _NODE_TARGET,
    _NODE_PATHWAY,
    _NODE_GENE,
    _NODE_DISEASE,
)
from backend.reasoning.mechanistic.multi_hop_reasoner import PathFinder, MechanisticPath
from backend.reasoning.normalization.biological_identifier_resolver import (
    BiologicalIdentifierResolver,
)
from backend.reasoning.normalization.normalization_audit import (
    NormalizationAudit,
    build_package_normalization_audit,
    calculate_matching_audit,
)


class GraphGapDiagnosis(str, Enum):
    """Empirical root-cause localization based on observed graph state."""
    RETRIEVAL_GAP = "RETRIEVAL_GAP"
    IDENTIFIER_NORMALIZATION_GAP = "IDENTIFIER_NORMALIZATION_GAP"
    GRAPH_NODE_CONSTRUCTION_GAP = "GRAPH_NODE_CONSTRUCTION_GAP"
    GRAPH_EDGE_CONSTRUCTION_GAP = "GRAPH_EDGE_CONSTRUCTION_GAP"
    EVIDENCE_ATTACHMENT_GAP = "EVIDENCE_ATTACHMENT_GAP"
    PATH_TRAVERSAL_GAP = "PATH_TRAVERSAL_GAP"
    NO_GRAPH_GAP_DETECTED = "NO_GRAPH_GAP_DETECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class EdgeGroupSummary:
    source_type: str
    relationship_type: str
    direction: str
    target_type: str
    count: int


@dataclass
class GraphIntegrityReport:
    drug_name: str
    disease_name: str

    # Level 1: Retrieval Inventory
    retrieval_targets: int
    retrieval_proteins: int
    retrieval_pathways: int
    retrieval_disease_genes: int
    retrieval_evidence_records: int
    retrieval_mappings: int

    # Level 2: Canonicalization
    identifiers_audited: int
    resolved: int
    unresolved: int
    resolution_rate: float
    canonical_entities: int
    duplicate_raw_ids: int
    raw_matching: int
    canonical_matching: int
    new_matches_revealed: int

    # Level 3: Actual Graph Nodes
    graph_nodes_by_type: dict[str, int]
    total_graph_nodes: int

    # Level 4: Edge Inventory
    edge_groups: list[EdgeGroupSummary]
    total_graph_edges: int

    # Level 5: Edge Evidence Coverage
    edges_with_source: int
    edges_with_source_id: int
    edges_with_evidence_type: int
    edges_with_context: int
    evidence_coverage_pct: float

    # Level 6: Connectivity by Hop
    hop_connectivity: dict[str, dict[str, int]]

    # Level 7: Path Traversal & Depths
    depth_1_paths: int
    depth_2_paths: int
    depth_3_paths: int
    depth_4_paths: int
    complete_paths: int
    shortest_path_len: int
    longest_path_len: int

    # Level 8: Isolated Node Analysis
    isolated_nodes: dict[str, list[str]]

    # Level 9: Root-Cause Diagnosis
    diagnosis: GraphGapDiagnosis
    diagnosis_evidence: str
    affected_layer: str
    recommended_next_step: str


class GraphIntegrityAuditor:
    """Read-only diagnostic auditor for biological EvidenceGraph integrity."""

    def audit(
        self,
        package: RetrievalPackage,
        graph: EvidenceGraph | None = None,
    ) -> GraphIntegrityReport:
        """Run full integrity audit on a RetrievalPackage and its built EvidenceGraph."""
        # 1. Normalization & Resolver
        resolver = BiologicalIdentifierResolver(
            proteins=package.proteins,
            genes=package.genes,
            mappings=getattr(package, "identifier_mappings", []),
        )
        norm_audit = build_package_normalization_audit(package)
        match_audit = calculate_matching_audit(package, resolver)

        # 2. Build graph if not supplied (read-only)
        if graph is None:
            builder = EvidenceGraphBuilder()
            graph, _ = builder.build(package)

        # 3. Node Inventory
        nodes_by_type: dict[str, int] = defaultdict(int)
        for node in graph.nodes.values():
            nodes_by_type[node.label] += 1

        # 4. Edge Inventory
        edge_group_counts: dict[tuple[str, str, str, str], int] = defaultdict(int)
        edges_with_source = 0
        edges_with_source_id = 0
        edges_with_evidence_type = 0
        edges_with_context = 0

        for edge in graph.edges:
            src_node = graph.nodes.get(edge.source_id)
            tgt_node = graph.nodes.get(edge.target_id)
            src_type = src_node.label if src_node else "UNKNOWN"
            tgt_type = tgt_node.label if tgt_node else "UNKNOWN"
            rel_type = edge.relationship_type or edge.predicate
            direction = edge.direction or "UNKNOWN"

            edge_group_counts[(src_type, rel_type, direction, tgt_type)] += 1

            if edge.source:
                edges_with_source += 1
            if getattr(edge, "source_id_ref", "") or getattr(edge, "provenance", ""):
                edges_with_source_id += 1
            if getattr(edge, "evidence_type", "") or getattr(edge, "data_quality", ""):
                edges_with_evidence_type += 1
            if getattr(edge, "context", None) or getattr(edge, "links", None):
                edges_with_context += 1

        total_edges = len(graph.edges)
        evidence_pct = (edges_with_source / total_edges * 100.0) if total_edges > 0 else 0.0

        edge_groups = [
            EdgeGroupSummary(
                source_type=k[0],
                relationship_type=k[1],
                direction=k[2],
                target_type=k[3],
                count=v,
            )
            for k, v in sorted(edge_group_counts.items(), key=lambda x: (x[0][0], x[0][3], x[0][1]))
        ]

        # 5. Incremental Hop Connectivity
        gene_scores = build_validated_gene_scores(package, resolver=resolver)
        disease_gene_syms = set(gene_scores.keys())

        # Drug -> Target
        dt_edges = [e for e in graph.edges if e.source_id.startswith(f"{_NODE_DRUG}:") and e.target_id.startswith(f"{_NODE_TARGET}:")]
        # Target -> Pathway
        tp_edges = [e for e in graph.edges if e.source_id.startswith(f"{_NODE_TARGET}:") and e.target_id.startswith(f"{_NODE_PATHWAY}:")]
        # Pathway -> Gene
        pg_edges = [e for e in graph.edges if e.source_id.startswith(f"{_NODE_PATHWAY}:") and e.target_id.startswith(f"{_NODE_GENE}:")]
        # Gene -> Disease
        gd_edges = [e for e in graph.edges if e.source_id.startswith(f"{_NODE_GENE}:") and e.target_id.startswith(f"{_NODE_DISEASE}:")]

        hop_connectivity = {
            "Drug -> Target": {
                "candidate": len(package.targets),
                "graph_edges": len(dt_edges),
                "connected_targets": len({e.target_id for e in dt_edges}),
            },
            "Target -> Pathway": {
                "candidate": len(package.targets) * min(len(package.pathways), _MAX_PATHWAYS_PER_TARGET),
                "graph_edges": len(tp_edges),
                "connected_pathways": len({e.target_id for e in tp_edges}),
            },
            "Pathway -> Gene": {
                "candidate": sum(len(getattr(pw, "participant_uniprot_ids", []) or []) for pw in package.pathways),
                "graph_edges": len(pg_edges),
                "connected_genes": len({e.target_id for e in pg_edges}),
            },
            "Gene -> Disease": {
                "candidate": len(disease_gene_syms),
                "graph_edges": len(gd_edges),
                "connected_genes": len({e.source_id for e in gd_edges}),
            },
        }

        # 6. Path Traversal & Depth Distribution
        drug_node_id = f"{_NODE_DRUG}:{package.drug.name}"
        disease_node_id = f"{_NODE_DISEASE}:{package.disease.name}"

        # Count partial paths by depth (1-hop, 2-hop, 3-hop, 4-hop from Drug)
        depth_1_count = len(graph.out_edges(drug_node_id))
        depth_2_nodes = {e.target_id for e in graph.out_edges(drug_node_id)}
        depth_2_count = sum(len(graph.out_edges(nid)) for nid in depth_2_nodes)

        depth_3_nodes = set()
        for nid in depth_2_nodes:
            depth_3_nodes.update(e.target_id for e in graph.out_edges(nid))
        depth_3_count = sum(len(graph.out_edges(nid)) for nid in depth_3_nodes)

        depth_4_nodes = set()
        for nid in depth_3_nodes:
            depth_4_nodes.update(e.target_id for e in graph.out_edges(nid))
        depth_4_count = sum(len(graph.out_edges(nid)) for nid in depth_4_nodes)

        finder = PathFinder()
        complete_paths = finder.find(graph, drug_node_id, disease_node_id)
        path_lengths = [len(p.hops) for p in complete_paths]
        min_len = min(path_lengths) if path_lengths else 0
        max_len = max(path_lengths) if path_lengths else 0

        # 7. Isolated Node Analysis
        in_degree: dict[str, int] = defaultdict(int)
        out_degree: dict[str, int] = defaultdict(int)
        for e in graph.edges:
            out_degree[e.source_id] += 1
            in_degree[e.target_id] += 1

        isolated_targets = []
        for nid, node in graph.nodes.items():
            if node.label == _NODE_TARGET:
                # Target is isolated if it has no incoming Drug edge or no outgoing Pathway/Gene edge
                if in_degree[nid] == 0 or out_degree[nid] == 0:
                    isolated_targets.append(node.name)

        isolated_pathways = []
        for nid, node in graph.nodes.items():
            if node.label == _NODE_PATHWAY:
                # Pathway is isolated if it has no incoming Target edge or no outgoing Gene edge
                if in_degree[nid] == 0 or out_degree[nid] == 0:
                    isolated_pathways.append(node.name)

        isolated_genes = []
        for nid, node in graph.nodes.items():
            if node.label == _NODE_GENE:
                # Gene is isolated if it has no incoming edge or no outgoing edge to Disease
                if in_degree[nid] == 0 or out_degree[nid] == 0:
                    isolated_genes.append(node.name)

        isolated_nodes = {
            "Targets": isolated_targets,
            "Pathways": isolated_pathways,
            "Genes": isolated_genes,
        }

        # 8. Empirical Root-Cause Diagnosis
        diagnosis = GraphGapDiagnosis.NO_GRAPH_GAP_DETECTED
        evidence = "Complete hop-by-hop paths successfully traced from Drug to Disease."
        affected_layer = "NONE"
        next_step = "Proceed to direction-of-effect and mechanistic scoring validation."

        if len(package.targets) == 0:
            diagnosis = GraphGapDiagnosis.RETRIEVAL_GAP
            evidence = "RetrievalPackage contains 0 targets from ChEMBL."
            affected_layer = "Retrieval (ChEMBL)"
            next_step = "Inspect drug identity resolution and ChEMBL target query."
        elif len(disease_gene_syms) == 0:
            diagnosis = GraphGapDiagnosis.RETRIEVAL_GAP
            evidence = "RetrievalPackage contains 0 validated disease genes from Open Targets / DisGeNET."
            affected_layer = "Retrieval (Open Targets / DisGeNET)"
            next_step = "Inspect disease ontology grounding (MONDO / MeSH) and association query."
        elif norm_audit.unresolved > 0 and (norm_audit.unresolved / max(1, norm_audit.total_identifiers)) > 0.30:
            diagnosis = GraphGapDiagnosis.IDENTIFIER_NORMALIZATION_GAP
            evidence = f"High unresolved identifier rate ({norm_audit.unresolved}/{norm_audit.total_identifiers})."
            affected_layer = "Identifier Normalization"
            next_step = "Inspect connector mapping extraction for unresolved entities."
        elif len(graph.nodes) <= 2:
            diagnosis = GraphGapDiagnosis.GRAPH_NODE_CONSTRUCTION_GAP
            evidence = f"Only {len(graph.nodes)} nodes created in EvidenceGraph despite retrieved entities."
            affected_layer = "EvidenceGraphBuilder Node Construction"
            next_step = "Inspect target filtering (human organism check) and node creation loops."
        elif len(complete_paths) == 0:
            if len(tp_edges) == 0 and len(dt_edges) > 0:
                diagnosis = GraphGapDiagnosis.GRAPH_EDGE_CONSTRUCTION_GAP
                evidence = "Target -> Pathway edge creation failed: targets do not match Reactome participants."
                affected_layer = "Target -> Pathway edge construction"
                next_step = "Audit Reactome participant IDs vs target UniProt accessions."
            elif len(pg_edges) == 0 and len(tp_edges) > 0:
                diagnosis = GraphGapDiagnosis.GRAPH_EDGE_CONSTRUCTION_GAP
                evidence = "Pathway -> Gene edge creation failed: pathway participants do not overlap with disease genes."
                affected_layer = "Pathway -> Gene edge construction (zero disease-gene overlap)"
                next_step = "Inspect disease-gene candidate ranking and pathway participant coverage."
            else:
                diagnosis = GraphGapDiagnosis.GRAPH_EDGE_CONSTRUCTION_GAP
                evidence = "No complete path formed between active target mechanisms and disease genes."
                affected_layer = "Graph Edge Connectivity"
                next_step = "Inspect intermediate gene and pathway bridges."
        elif total_edges > 0 and evidence_pct < 80.0:
            diagnosis = GraphGapDiagnosis.EVIDENCE_ATTACHMENT_GAP
            evidence = f"Only {evidence_pct:.1f}% of edges have explicit evidence sources."
            affected_layer = "Edge Evidence Attachment"
            next_step = "Ensure all GraphEdge instantiations attach Source and Provenance."

        return GraphIntegrityReport(
            drug_name=package.drug.name,
            disease_name=package.disease.name,
            retrieval_targets=len(package.targets),
            retrieval_proteins=len(package.proteins),
            retrieval_pathways=len(package.pathways),
            retrieval_disease_genes=len(package.validated_disease_genes),
            retrieval_evidence_records=len(package.evidence_records),
            retrieval_mappings=len(package.identifier_mappings),
            identifiers_audited=norm_audit.total_identifiers,
            resolved=norm_audit.resolved,
            unresolved=norm_audit.unresolved,
            resolution_rate=norm_audit.resolution_rate,
            canonical_entities=norm_audit.canonical_entities,
            duplicate_raw_ids=norm_audit.duplicate_raw_identifiers,
            raw_matching=match_audit.get("raw_matches", 0),
            canonical_matching=match_audit.get("canonical_matches", 0),
            new_matches_revealed=match_audit.get("new_matches_revealed", 0),
            graph_nodes_by_type=dict(nodes_by_type),
            total_graph_nodes=len(graph.nodes),
            edge_groups=edge_groups,
            total_graph_edges=total_edges,
            edges_with_source=edges_with_source,
            edges_with_source_id=edges_with_source_id,
            edges_with_evidence_type=edges_with_evidence_type,
            edges_with_context=edges_with_context,
            evidence_coverage_pct=evidence_pct,
            hop_connectivity=hop_connectivity,
            depth_1_paths=depth_1_count,
            depth_2_paths=depth_2_count,
            depth_3_paths=depth_3_count,
            depth_4_paths=depth_4_count,
            complete_paths=len(complete_paths),
            shortest_path_len=min_len,
            longest_path_len=max_len,
            isolated_nodes=isolated_nodes,
            diagnosis=diagnosis,
            diagnosis_evidence=evidence,
            affected_layer=affected_layer,
            recommended_next_step=next_step,
        )

    def format_markdown(self, report: GraphIntegrityReport) -> str:
        """Format report exactly according to the required specification."""
        lines = [
            "============================================================",
            "CYNTHERA GRAPH INTEGRITY AUDIT",
            "============================================================",
            "",
            f"PACKAGE",
            f"    Drug: {report.drug_name}",
            f"    Disease: {report.disease_name}",
            "",
            "------------------------------------------------------------",
            "1. RETRIEVAL INVENTORY",
            "------------------------------------------------------------",
            f"Targets: {report.retrieval_targets}",
            f"Proteins: {report.retrieval_proteins}",
            f"Pathways: {report.retrieval_pathways}",
            f"Disease genes: {report.retrieval_disease_genes}",
            f"Evidence: {report.retrieval_evidence_records}",
            "",
            "------------------------------------------------------------",
            "2. CANONICALIZATION",
            "------------------------------------------------------------",
            f"Identifiers audited: {report.identifiers_audited}",
            f"Resolved: {report.resolved} ({report.resolution_rate * 100:.1f}%)",
            f"Unresolved: {report.unresolved}",
            f"Duplicate raw IDs: {report.duplicate_raw_ids}",
            f"Canonical entities: {report.canonical_entities}",
            "",
            f"Raw matching: {report.raw_matching}",
            f"Canonical matching: {report.canonical_matching}",
            f"New matches: {report.new_matches_revealed}",
            "",
            "------------------------------------------------------------",
            "3. ACTUAL GRAPH",
            "------------------------------------------------------------",
            "Nodes:",
            f"    Drug: {report.graph_nodes_by_type.get(_NODE_DRUG, 0)}",
            f"    Target: {report.graph_nodes_by_type.get(_NODE_TARGET, 0)}",
            f"    Protein: {report.graph_nodes_by_type.get('PROTEIN', 0)}",
            f"    Pathway: {report.graph_nodes_by_type.get(_NODE_PATHWAY, 0)}",
            f"    Gene: {report.graph_nodes_by_type.get(_NODE_GENE, 0)}",
            f"    Disease: {report.graph_nodes_by_type.get(_NODE_DISEASE, 0)}",
            "",
            "Edges:",
            "    SOURCE        RELATIONSHIP                        DIRECTION    TARGET       COUNT",
            "    " + "-" * 75,
        ]

        if not report.edge_groups:
            lines.append("    [NO EDGES IN GRAPH]")
        else:
            for eg in report.edge_groups:
                lines.append(
                    f"    {eg.source_type:<12}  {eg.relationship_type:<34}  {eg.direction:<11}  {eg.target_type:<11}  {eg.count:>4}"
                )

        lines.extend([
            "",
            "------------------------------------------------------------",
            "4. EDGE EVIDENCE COVERAGE",
            "------------------------------------------------------------",
            f"Total edges: {report.total_graph_edges}",
            f"With source: {report.edges_with_source} ({report.evidence_coverage_pct:.1f}%)",
            f"With source ID: {report.edges_with_source_id}",
            f"With evidence type: {report.edges_with_evidence_type}",
            f"With context: {report.edges_with_context}",
            "",
            "------------------------------------------------------------",
            "5. CONNECTIVITY",
            "------------------------------------------------------------",
        ])

        for hop_name, stats in report.hop_connectivity.items():
            lines.append(f"{hop_name}: {stats['graph_edges']} edges (candidates: {stats['candidate']})")

        lines.extend([
            "",
            "------------------------------------------------------------",
            "6. PATH TRAVERSAL",
            "------------------------------------------------------------",
            f"Depth 1: {report.depth_1_paths}",
            f"Depth 2: {report.depth_2_paths}",
            f"Depth 3: {report.depth_3_paths}",
            f"Depth 4: {report.depth_4_paths}",
            f"Complete Drug -> Disease paths: {report.complete_paths}",
            f"Shortest path length: {report.shortest_path_len}",
            f"Longest path length: {report.longest_path_len}",
            "",
            "------------------------------------------------------------",
            "7. ISOLATED NODES",
            "------------------------------------------------------------",
            f"Targets: {len(report.isolated_nodes['Targets'])} ({', '.join(report.isolated_nodes['Targets'][:3]) if report.isolated_nodes['Targets'] else 'None'})",
            f"Pathways: {len(report.isolated_nodes['Pathways'])} ({', '.join(report.isolated_nodes['Pathways'][:3]) if report.isolated_nodes['Pathways'] else 'None'})",
            f"Genes: {len(report.isolated_nodes['Genes'])} ({', '.join(report.isolated_nodes['Genes'][:3]) if report.isolated_nodes['Genes'] else 'None'})",
            f"Other: 0",
            "",
            "------------------------------------------------------------",
            "8. ROOT-CAUSE DIAGNOSIS",
            "------------------------------------------------------------",
            f"Classification: {report.diagnosis.value}",
            "",
            f"Evidence: {report.diagnosis_evidence}",
            "",
            f"Affected layer: {report.affected_layer}",
            "",
            f"Recommended NEXT INVESTIGATION: {report.recommended_next_step}",
            "",
            "============================================================",
        ])

        return "\n".join(lines)
