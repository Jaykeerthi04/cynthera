"""EvidenceGraphBuilder — builds a typed evidence graph from a sealed RetrievalPackage.

This module replaces the old template-enumeration approach in
``multi_hop_reasoner.py`` (fixed DIRECT / 2-HOP / 3-HOP loops over flat lists)
with an actual graph: typed nodes (Drug, Target, Pathway, Gene, Disease) and
typed, evidence-backed edges (predicate, source, evidence_strength, provenance).

Nothing here duplicates ``ClaimGraph`` — that graph is built from LLM-extracted
literature claims (Step 3 of the orchestrator). This graph is built purely from
structured retrieval data (ChEMBL, UniProt, Reactome, Open Targets / DisGeNET)
that is already sitting in the ``RetrievalPackage``.

Design principle: edges are only created when the underlying source data
actually supports them. There is no post-hoc INVALID marking — an edge that
isn't supported by retrieved data is simply never added, so every path the
PathFinder returns is hop-by-hop valid by construction.

Fixes:
  - 1.1  Real graph traversal instead of nested-loop template enumeration.
         The old "3-HOP Effector" template (two arbitrary secondary proteins
         picked because they share pathway membership) is REMOVED.
  - 1.2  Target → mechanism predicate is read from ``target.mechanism``
         (ChEMBL INHIBITOR / AGONIST / ANTAGONIST / ...) instead of a
         hardcoded "modulates" label.
  - 1.3  Gene-disease association is carried through as the real
         ``validated_disease_genes[gene]`` float score, not collapsed to
         binary membership with a flat 0.5 penalty.
  - 1.4  Pathway relevance / membership is computed on gene SYMBOLS on both
         sides. Reactome pathway participants come in as UniProt accessions;
         they are mapped to gene symbols via the retrieved Protein records
         before any overlap is computed.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterator

from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.disease_gene_evidence import DiseaseGeneEvidence, DiseaseGeneScope
from backend.core.value_objects.source_url_builder import EvidenceLink, SourceURLBuilder

# Phase 4B: Directional evidence infrastructure
from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.enums.causal_grounding import CausalGrounding
from backend.reasoning.directional.chembl_polarity import (
    chembl_action_to_polarity,
    chembl_action_to_grounding,
)
from backend.reasoning.directional.reactome_polarity import (
    reactome_role_to_polarity,
    reactome_role_to_grounding,
)
from backend.reasoning.mechanistic.reaction_aggregator import (
    aggregate_reaction_evidence,
    AggregatedReactionEvidence,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Tunable constants (not benchmark-validated yet — see audit §1.7).
# Track in MECHANISTIC_BENCHMARK_RESULTS.md once the benchmark lands.
# ─────────────────────────────────────────────
_HOP_DECAY: float = 0.85               # per-additional-hop length penalty
_MIN_PATH_CONFIDENCE: float = 0.01
_UNREVIEWED_PENALTY: float = 0.3       # TrEMBL (unreviewed) protein multiplier
_UNVALIDATED_GENE_DEFAULT: float = 0.3 # fallback strength when a target's gene
                                        # has no Open Targets/DisGeNET score at all
_MAX_TARGETS: int = 8
_MAX_PATHWAYS_PER_TARGET: int = 6
_MAX_HOPS: int = 5

# Node type constants
_NODE_DRUG = "DRUG"
_NODE_TARGET = "TARGET"
_NODE_REACTION = "REACTION"
_NODE_PATHWAY = "PATHWAY"
_NODE_GENE = "GENE"
_NODE_DISEASE = "DISEASE"

# Target role to edge predicate mapping
_ROLE_TO_PREDICATE: dict[str, str] = {
    "CATALYST": "CATALYZES",
    "INPUT": "INPUT_TO",
    "OUTPUT": "OUTPUT_OF",
    "POSITIVE_REGULATOR": "POSITIVE_REGULATES",
    "NEGATIVE_REGULATOR": "NEGATIVE_REGULATES",
    "REQUIREMENT": "REQUIREMENT_FOR",
    "COMPLEX_COMPONENT": "COMPLEX_COMPONENT_OF",
    "ENTITY_SET_MEMBER": "ENTITY_SET_MEMBER_OF",
    "PARTICIPANT": "PARTICIPATES_IN_REACTION",
}

_NON_HUMAN_KEYWORDS = (
    "bacteria", "bacterial", "virus", "viral", "coli", "yeast",
    "rattus", "mouse", "mus musculus", "bovine", "porcine", "vector",
)


# ─────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────

def clean_uniprot(acc: str | None) -> str:
    """Normalize a UniProt accession by removing isoform suffixes/whitespace."""
    if not acc:
        return ""
    return acc.split("-")[0].strip().upper()


def is_human_protein(protein: Any) -> bool:
    """Return True if organism is human or unstated (unfetched data is not rejected)."""
    if protein is None:
        return True
    organism = getattr(protein, "organism", None)
    if not organism:
        return True
    org_lower = organism.strip().lower()
    if any(k in org_lower for k in _NON_HUMAN_KEYWORDS):
        return False
    return True


def compute_target_confidence(target: Any, evidence_records: list) -> float:
    """Confidence for a target from binding affinity + weighted evidence volume.

    Uses two signals:
    1. Binding affinity strength (nM) mapped via log10 scale.
    2. Volume of evidence records mentioning this target, weighted by ERW.

    Args:
        target: A Target domain model with affinity_nm and protein_uniprot.
        evidence_records: All Evidence records from the RetrievalPackage.

    Returns:
        Confidence in [0.1, 1.0].
    """
    affinity_component = 0.5
    try:
        affinity_nm = target.affinity_nm
        if isinstance(affinity_nm, (int, float)) and affinity_nm > 0:
            affinity_component = max(0.1, min(1.0, 1.0 - (math.log10(affinity_nm) / 5.0)))
    except (TypeError, ValueError):
        pass

    target_uniprot = getattr(target, "protein_uniprot", None)
    if target_uniprot and isinstance(evidence_records, list):
        target_evidence = [
            e for e in evidence_records
            if getattr(e, "target_uniprot", None) == target_uniprot
            and hasattr(e, "erw") and hasattr(e.erw, "value")
        ]
        erw_sum = sum(
            e.erw.value for e in target_evidence
            if isinstance(e.erw.value, (int, float))
        )
        evidence_component = min(1.0, erw_sum / 3.0) if target_evidence else 0.2
    else:
        evidence_component = 0.2

    return round(0.6 * affinity_component + 0.4 * evidence_component, 4)


from backend.reasoning.normalization.biological_identifier_resolver import (
    BiologicalIdentifierResolver,
)


def build_validated_gene_scores(
    package: RetrievalPackage,
    resolver: BiologicalIdentifierResolver | None = None,
) -> dict[str, float]:
    """Return canonical gene symbol → real association score in [0, 1].

    Phase 5.10 Feature:
    Consumes tiered DiseaseGeneEvidence when available, filtering to tiers that are eligible
    to bridge the mechanistic graph (EXACT, EQUIVALENT, CHILD).
    PARENT tier evidence is strictly excluded from forming graph bridge scores.
    """
    if resolver is None:
        resolver = BiologicalIdentifierResolver(
            proteins=package.proteins,
            genes=package.genes,
            mappings=getattr(package, "identifier_mappings", []),
        )

    scores: dict[str, float] = {}

    # 1. Tiered DiseaseGeneEvidence (Phase 5.10 primary)
    d_evs = getattr(package, "disease_gene_evidence", None) or []
    if d_evs:
        for ev in d_evs:
            if not ev.can_bridge_mechanistic_graph():
                # Strictly exclude PARENT tier from graph bridge
                continue
            if ev.evidence_score is not None and ev.evidence_score > 0:
                resolved = resolver.resolve(
                    ev.gene_symbol,
                    source="disease_gene_evidence",
                    confidence=float(ev.evidence_score),
                )
                sym = resolved.canonical_symbol.upper() if resolved.canonical_symbol else ev.gene_symbol.upper()
                score_val = round(min(1.0, max(0.0, float(ev.evidence_score))), 4)
                scores[sym] = max(scores.get(sym, 0.0), score_val)
        if scores:
            return scores

    # 2. Open Targets scores from package.validated_disease_genes (backward compatibility)
    val_genes = getattr(package, "validated_disease_genes", None) or {}
    if val_genes:
        for raw_identifier, score in val_genes.items():
            if not isinstance(score, (int, float)) or score <= 0:
                continue
            resolved = resolver.resolve(
                str(raw_identifier),
                source="validated_disease_genes",
                confidence=float(score),
            )
            if resolved.canonical_symbol:
                sym = resolved.canonical_symbol.upper()
                score_val = round(min(1.0, max(0.0, float(score))), 4)
                scores[sym] = max(scores.get(sym, 0.0), score_val)
            else:
                logger.debug(
                    "biological_identifier_unresolved",
                    extra={
                        "raw_identifier": raw_identifier,
                        "identifier_type": resolved.identifier_type.value,
                        "source": resolved.source,
                    },
                )
        return scores

    # Legacy fallback: DisGeNET evidence records, no real float score available
    disease_mesh = getattr(package.disease, "mesh_id", None)
    if not disease_mesh:
        return scores
    for ev in getattr(package, "evidence_records", []):
        prov = getattr(ev, "provenance", None)
        if prov and getattr(prov, "source_name", "") == "DisGeNET":
            if getattr(ev, "disease_identifier", None) == disease_mesh:
                title = ev.title or ""
                if "DisGeNET association:" in title:
                    parts = title.split(":")
                    if len(parts) > 1:
                        gene = parts[1].split("—")[0].strip()
                        if gene:
                            resolved = resolver.resolve(gene, source="DisGeNET")
                            if resolved.canonical_symbol:
                                scores.setdefault(resolved.canonical_symbol.upper(), _UNVALIDATED_GENE_DEFAULT)
    return scores


def pathway_gene_symbols(
    pathway: Any,
    resolver: BiologicalIdentifierResolver,
) -> set[str]:
    """Return set of canonical gene symbols for pathway participants using the resolver."""
    participant_ids = getattr(pathway, "participant_uniprot_ids", None) or []
    out: set[str] = set()
    for pid in participant_ids:
        resolved = resolver.resolve(pid, source="Reactome")
        if resolved.canonical_symbol:
            out.add(resolved.canonical_symbol.upper())
    return out


def pathway_relevance_score(
    pathway_gene_syms: set[str],
    disease_gene_syms: set[str],
    drug_target_syms: set[str],
) -> float:
    """Gene-symbol-to-gene-symbol overlap score.

    60% weight on disease-gene overlap, 40% on drug-target overlap.
    All sides are in gene-symbol space (fixes audit 1.4 — no accession/symbol mismatch).

    Args:
        pathway_gene_syms: Gene symbols of pathway participants (translated from UniProt).
        disease_gene_syms: Gene symbols with Open Targets/DisGeNET association scores.
        drug_target_syms: Gene symbols of drug targets from ChEMBL/UniProt.

    Returns:
        Relevance score in [0.0, 1.0].
    """
    if not pathway_gene_syms:
        return 0.0
    disease_overlap = (
        len(pathway_gene_syms & disease_gene_syms) / len(pathway_gene_syms)
        if disease_gene_syms else 0.0
    )
    target_overlap = (
        len(pathway_gene_syms & drug_target_syms) / len(pathway_gene_syms)
        if drug_target_syms else 0.0
    )
    return round(0.6 * disease_overlap + 0.4 * target_overlap, 4)


def target_in_pathway(target_uniprot_norm: str, pathway: Any) -> bool:
    """Fail-closed membership check (P8 preserved): unknown membership == non-membership.

    No participant data → reject, never pass unconditionally.
    """
    participant_ids = getattr(pathway, "participant_uniprot_ids", None) or []
    if not participant_ids:
        return False
    clean = {clean_uniprot(pid) for pid in participant_ids if pid}
    return target_uniprot_norm in clean


# ─────────────────────────────────────────────
# Graph model
# ─────────────────────────────────────────────

@dataclass
class GraphNode:
    """A node in the evidence graph."""
    id: str
    label: str          # DRUG | TARGET | PATHWAY | GENE | DISEASE
    name: str
    meta: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """A directed edge in the evidence graph, backed by retrieved source data."""
    source_id: str
    target_id: str
    predicate: str            # e.g. INHIBITOR, AGONIST, PARTICIPATES_IN, ASSOCIATED_WITH
    evidence_strength: float  # [0, 1], grounded in retrieved data
    source: str               # ChEMBL | Reactome | Open Targets | DisGeNET
    provenance: str = ""
    links: list[EvidenceLink] = field(default_factory=list)
    data_quality: str = "EVIDENCE_BACKED"  # "EVIDENCE_BACKED" | "STRUCTURE_ONLY" | "UNVALIDATED"
    direction: str = "UNKNOWN"             # "POSITIVE" | "NEGATIVE" | "UNKNOWN" (legacy string, kept for compat)
    relationship_type: str = ""           # Semantic type e.g. PARTICIPATES_IN, INHIBITS, ASSOCIATED_WITH
    source_id_ref: str = ""               # Database-specific identifier
    evidence_type: str = ""               # IN_VITRO | DATABASE | PATHWAY_MEMBERSHIP | etc.
    context: dict = field(default_factory=dict)
    # Phase 4B: Typed directional fields — separate from legacy string direction
    polarity: MolecularPolarity = field(default=MolecularPolarity.UNKNOWN)
    causal_grounding: CausalGrounding = field(default=CausalGrounding.NONE)


class EvidenceGraph:
    """Directed multigraph over Drug/Target/Pathway/Gene/Disease nodes."""

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self._out: dict[str, list[GraphEdge]] = defaultdict(list)
        self.edges: list[GraphEdge] = []

    def add_node(self, node: GraphNode) -> None:
        """Add node (idempotent — duplicate IDs are silently ignored)."""
        if node.id not in self.nodes:
            self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        """Add edge, deduplicating by (source_id, target_id, predicate)."""
        for existing in self._out[edge.source_id]:
            if (
                existing.target_id == edge.target_id
                and existing.predicate == edge.predicate
            ):
                return
        self._out[edge.source_id].append(edge)
        self.edges.append(edge)

    def out_edges(self, node_id: str) -> list[GraphEdge]:
        return self._out.get(node_id, [])

    def find_simple_paths(
        self, start_id: str, end_id: str, max_hops: int = _MAX_HOPS
    ) -> Iterator[list[GraphEdge]]:
        """DFS over simple paths (no repeated nodes) from start_id to end_id.

        Yields lists of GraphEdge objects representing complete paths.
        """

        def _dfs(node_id: str, visited: set[str], acc: list[GraphEdge]):
            if len(acc) > max_hops:
                return
            if node_id == end_id and acc:
                yield list(acc)
                return
            for e in self._out.get(node_id, []):
                if e.target_id in visited:
                    continue
                visited.add(e.target_id)
                acc.append(e)
                yield from _dfs(e.target_id, visited, acc)
                acc.pop()
                visited.discard(e.target_id)

        yield from _dfs(start_id, {start_id}, [])


# ─────────────────────────────────────────────
# EvidenceGraphBuilder
# ─────────────────────────────────────────────

class EvidenceGraphBuilder:
    """Builds an EvidenceGraph from a sealed RetrievalPackage.

    Every edge is created only when the corresponding source data actually
    supports it — see module docstring. Nothing here queries an LLM.

    Public API:
        builder = EvidenceGraphBuilder()
        graph = builder.build(package)
    """

    def build(self, package: RetrievalPackage) -> tuple[EvidenceGraph, BiologicalIdentifierResolver]:
        """Build and return the EvidenceGraph for the given package.

        Args:
            package: Sealed RetrievalPackage from the retrieval pipeline.

        Returns:
            Tuple of (EvidenceGraph, BiologicalIdentifierResolver).
            The resolver is populated from retrieved proteins/genes/mappings and
            can be passed to AdvancedConflictResolver for canonical entity gating.
        """
        graph = EvidenceGraph()

        drug_id = f"{_NODE_DRUG}:{package.drug.name}"
        disease_id = f"{_NODE_DISEASE}:{package.disease.name}"
        graph.add_node(GraphNode(drug_id, _NODE_DRUG, package.drug.name))
        graph.add_node(GraphNode(disease_id, _NODE_DISEASE, package.disease.name))

        targets = list(package.targets)[:_MAX_TARGETS]
        proteins = list(package.proteins)

        if not targets:
            # No targets → empty graph → PathFinder finds nothing → MS=0 NONE
            # Still return (graph, resolver) tuple for consistent API.
            empty_resolver = BiologicalIdentifierResolver(
                proteins=package.proteins,
                genes=package.genes,
                mappings=getattr(package, "identifier_mappings", []),
            )
            return graph, empty_resolver

        # ── Pre-build lookup tables & resolver ────────────────────────────
        resolver = BiologicalIdentifierResolver(
            proteins=package.proteins,
            genes=package.genes,
            mappings=getattr(package, "identifier_mappings", []),
        )

        # Canonical float scores for disease-associated genes
        gene_scores = build_validated_gene_scores(package, resolver=resolver)

        # Lookup map for DiseaseGeneEvidence provenance
        gene_evidence_map: dict[str, DiseaseGeneEvidence] = {}
        for dev in (getattr(package, "disease_gene_evidence", None) or []):
            if dev.can_bridge_mechanistic_graph() and dev.gene_symbol:
                sym_u = dev.gene_symbol.upper()
                if sym_u not in gene_evidence_map:
                    gene_evidence_map[sym_u] = dev
                elif dev.scope in (DiseaseGeneScope.EXACT, "EXACT"):
                    gene_evidence_map[sym_u] = dev

        protein_by_uniprot: dict[str, Any] = {}
        for p in proteins:
            acc = getattr(p, "uniprot_accession", None)
            if acc:
                protein_by_uniprot[acc] = p
                protein_by_uniprot[clean_uniprot(acc)] = p

        drug_target_syms: set[str] = {
            p.gene_symbol.upper()
            for p in proteins
            if getattr(p, "gene_symbol", None)
        }
        disease_gene_syms: set[str] = set(gene_scores.keys())

        # ── Rank pathways by corrected canonical gene-symbol relevance ───
        ranked_pathways = sorted(
            package.pathways,
            key=lambda pw: pathway_relevance_score(
                pathway_gene_symbols(pw, resolver),
                disease_gene_syms,
                drug_target_syms,
            ),
            reverse=True,
        )

        genes_linked_to_disease: set[str] = set()  # track to avoid duplicate edges

        # Phase 5.4: Pre-aggregate Reactome reaction evidence by canonical biological reaction entity
        raw_rxn_ev = getattr(package, "reactome_reaction_evidence", []) or []
        aggregated_rxn_ev = aggregate_reaction_evidence(raw_rxn_ev)
        rxn_ev_by_target: dict[str, list[AggregatedReactionEvidence]] = defaultdict(list)
        for arev in aggregated_rxn_ev:
            rxn_ev_by_target[arev.target_canonical_id.upper()].append(arev)
            if arev.target_original_id and arev.target_original_id.upper() != arev.target_canonical_id.upper():
                rxn_ev_by_target[arev.target_original_id.upper()].append(arev)
            clean_orig = clean_uniprot(arev.target_original_id)
            if clean_orig and clean_orig.upper() not in (arev.target_canonical_id.upper(), arev.target_original_id.upper()):
                rxn_ev_by_target[clean_orig.upper()].append(arev)

        for target in targets:
            uniprot_id = getattr(target, "protein_uniprot", None)
            norm_uniprot = clean_uniprot(uniprot_id)
            protein = (
                protein_by_uniprot.get(uniprot_id)
                or protein_by_uniprot.get(norm_uniprot)
            )

            # Non-human targets (e.g. viral neuraminidase for Oseltamivir -> Influenza)
            # are valid primary drug targets and must not be dropped from the evidence graph.
            # We record organism in metadata rather than skipping.
            is_human = is_human_protein(protein)


            gene_symbol = getattr(protein, "gene_symbol", None) if protein else None
            target_label = (
                f"{gene_symbol} ({uniprot_id})"
                if gene_symbol
                else (uniprot_id or getattr(target, "name", "unknown"))
            )
            target_id = f"{_NODE_TARGET}:{uniprot_id or getattr(target, 'name', 'unknown')}"

            graph.add_node(GraphNode(
                target_id, _NODE_TARGET, target_label,
                meta={"uniprot": uniprot_id, "gene_symbol": gene_symbol},
            ))

            # ── Drug → Target ─────────────────────────────────────────────
            # Fix 1.2: read target.mechanism instead of hardcoding "modulates"
            target_conf = compute_target_confidence(target, package.evidence_records)
            if protein is not None and not getattr(protein, "is_reviewed", True):
                target_conf = round(target_conf * _UNREVIEWED_PENALTY, 4)

            mechanism = (getattr(target, "mechanism", None) or "").strip().upper()
            predicate = mechanism if mechanism and mechanism not in ("", "UNKNOWN") else "MODULATES"

            dt_links: list[EvidenceLink] = []
            if package.drug.chembl_id:
                u = SourceURLBuilder.chembl_compound_url(package.drug.chembl_id)
                if u:
                    dt_links.append(EvidenceLink("ChEMBL", "Open ChEMBL Compound", u, package.drug.chembl_id, "database"))
            if uniprot_id:
                u = SourceURLBuilder.uniprot_url(uniprot_id)
                if u:
                    dt_links.append(EvidenceLink("UniProt", "Open UniProt", u, uniprot_id, "database"))

            direction = "UNKNOWN"
            pred_u = predicate.upper()
            if pred_u in ("INHIBITOR", "INHIBITS", "ANTAGONIST", "BLOCKER", "NEGATIVE_ALLOSTERIC_MODULATOR"):
                direction = "NEGATIVE"
            elif pred_u in ("ACTIVATOR", "ACTIVATES", "AGONIST", "OPENER", "POSITIVE_ALLOSTERIC_MODULATOR", "PARTIAL_AGONIST"):
                direction = "POSITIVE"

            # Phase 4B: typed polarity and causal grounding derived from ChEMBL action_type
            dt_polarity = chembl_action_to_polarity(mechanism)
            dt_grounding = chembl_action_to_grounding(mechanism)

            graph.add_edge(GraphEdge(
                source_id=drug_id,
                target_id=target_id,
                predicate=predicate,
                evidence_strength=target_conf,
                source="ChEMBL",
                provenance=f"binding affinity + evidence volume for {target_label}",
                links=dt_links,
                data_quality="EVIDENCE_BACKED",
                direction=direction,
                relationship_type=predicate,
                evidence_type="IN_VITRO",
                polarity=dt_polarity,
                causal_grounding=dt_grounding,
            ))

            # ── Target → Gene → Disease ───────────────────────────────────
            # Fix 1.3: use the REAL association-score float magnitude
            gene_sym_u = gene_symbol.upper() if gene_symbol else None
            if gene_sym_u and gene_sym_u in gene_scores:
                gene_score = gene_scores[gene_sym_u]
                gene_id = f"{_NODE_GENE}:{gene_sym_u}"
                graph.add_node(GraphNode(gene_id, _NODE_GENE, gene_sym_u))

                tg_links: list[EvidenceLink] = []
                if uniprot_id:
                    u = SourceURLBuilder.uniprot_url(uniprot_id)
                    if u:
                        tg_links.append(EvidenceLink("UniProt", "Open UniProt", u, uniprot_id, "database"))
                u_ot = SourceURLBuilder.opentargets_target_url(gene_sym_u)
                if u_ot:
                    tg_links.append(EvidenceLink("Open Targets", "Open Targets Target", u_ot, gene_sym_u, "database"))

                graph.add_edge(GraphEdge(
                    source_id=target_id,
                    target_id=gene_id,
                    predicate="ENCODED_BY_DISEASE_ASSOCIATED_GENE",
                    evidence_strength=gene_score,
                    source="Open Targets / DisGeNET",
                    provenance=(
                        f"gene-disease association score {gene_score:.2f} for {gene_sym_u}"
                    ),
                    links=tg_links,
                    data_quality="EVIDENCE_BACKED",
                    direction="UNKNOWN",
                    relationship_type="ENCODED_BY_DISEASE_ASSOCIATED_GENE",
                    evidence_type="DATABASE_ASSOCIATION",
                ))

                if gene_id not in genes_linked_to_disease:
                    gd_links: list[EvidenceLink] = []
                    u_ot_d = SourceURLBuilder.opentargets_disease_url(package.disease.mesh_id or package.disease.name)
                    if u_ot_d:
                        gd_links.append(EvidenceLink("Open Targets", "Open Targets Disease", u_ot_d, package.disease.name, "database"))
                    u_dg = SourceURLBuilder.disgenet_url(gene_sym_u)
                    if u_dg:
                        gd_links.append(EvidenceLink("DisGeNET", "Open DisGeNET", u_dg, gene_sym_u, "database"))

                    d_ev = gene_evidence_map.get(gene_sym_u) if gene_sym_u else None
                    d_scope = d_ev.scope.value if (d_ev and hasattr(d_ev.scope, "value")) else (str(d_ev.scope) if d_ev and d_ev.scope else "EXACT")
                    d_prov = d_ev.provenance if d_ev and d_ev.provenance else f"gene-disease association score {gene_score:.2f}"
                    d_dis_id = d_ev.disease_id if d_ev else (package.disease.mesh_id or package.disease.name)

                    graph.add_edge(GraphEdge(
                        source_id=gene_id,
                        target_id=disease_id,
                        predicate="ASSOCIATED_WITH",
                        evidence_strength=gene_score,
                        source="Open Targets / DisGeNET",
                        provenance=d_prov,
                        links=gd_links,
                        data_quality="EVIDENCE_BACKED",
                        direction="UNKNOWN",
                        relationship_type="ASSOCIATED_WITH",
                        evidence_type="DISEASE_ASSOCIATION",
                        context={
                            "scope": d_scope,
                            "disease_id": d_dis_id,
                        },
                    ))
                    genes_linked_to_disease.add(gene_id)
            else:
                # No disease-gene score for this target's gene.
                # Do NOT create a fallback edge — missing data is not evidence.
                # Paths can only traverse EVIDENCE_BACKED edges.
                logger.debug(
                    "evidence_graph_no_gene_disease_edge",
                    extra={
                        "gene_symbol": gene_sym_u,
                        "reason": "no Open Targets/DisGeNET association score for this gene",
                    },
                )

            # ── Target → Pathway → Disease-associated gene(s) ────────────
            # Filter pathways to those containing this target
            target_pathways = [
                pw for pw in ranked_pathways
                if target_in_pathway(norm_uniprot, pw)
            ]
            # Prioritize pathways with confirmed disease-gene overlap, up to _MAX_PATHWAYS_PER_TARGET
            target_pathways_sorted = sorted(
                target_pathways,
                key=lambda pw: (
                    len(pathway_gene_symbols(pw, resolver) & disease_gene_syms) > 0,
                    pathway_relevance_score(pathway_gene_symbols(pw, resolver), disease_gene_syms, drug_target_syms),
                ),
                reverse=True,
            )

            for pathway in target_pathways_sorted[:_MAX_PATHWAYS_PER_TARGET]:
                pathway_id = f"{_NODE_PATHWAY}:{pathway.reactome_id}"
                graph.add_node(GraphNode(
                    pathway_id,
                    _NODE_PATHWAY,
                    f"{pathway.name} ({pathway.reactome_id})",
                ))

                pw_gene_syms = pathway_gene_symbols(pathway, resolver)
                relevance = pathway_relevance_score(
                    pw_gene_syms, disease_gene_syms, drug_target_syms
                )

                participation_strength = round(0.30 + 0.50 * relevance, 4)


                pw_links: list[EvidenceLink] = []
                u_pw = SourceURLBuilder.reactome_url(pathway.reactome_id)
                if u_pw:
                    pw_links.append(EvidenceLink("Reactome", "Open Reactome Pathway", u_pw, pathway.reactome_id, "database"))

                # ── Reaction-level decomposition (Phase 3) ─────────────────
                # Look up target-specific reactions matching this pathway
                target_evs: list[AggregatedReactionEvidence] = []
                if norm_uniprot in rxn_ev_by_target:
                    target_evs.extend(rxn_ev_by_target[norm_uniprot])
                if gene_sym_u and gene_sym_u in rxn_ev_by_target:
                    for e in rxn_ev_by_target[gene_sym_u]:
                        if e not in target_evs:
                            target_evs.append(e)

                for rev in target_evs:
                    if rev.pathway_id == pathway.reactome_id:
                        rxn_id = f"{_NODE_REACTION}:{rev.reaction_id}"
                        graph.add_node(GraphNode(
                            rxn_id,
                            _NODE_REACTION,
                            f"{rev.reaction_name} ({rev.reaction_id})",
                            meta={
                                "reaction_id": rev.reaction_id,
                                "schema_class": rev.schema_class,
                                "species": rev.species,
                                "compartment": rev.compartment,
                                "disease_context": rev.disease_context,
                                "roles": rev.roles,
                                "evidence_count": rev.evidence_count,
                            },
                        ))

                        rxn_links: list[EvidenceLink] = []
                        u_rxn = SourceURLBuilder.reactome_url(rev.reaction_id)
                        if u_rxn:
                            rxn_links.append(EvidenceLink("Reactome", "Open Reactome Reaction", u_rxn, rev.reaction_id, "database"))

                        # Add a distinct edge for each preserved biological role
                        for role in rev.roles:
                            role_pred = _ROLE_TO_PREDICATE.get(role.upper(), role.upper())
                            rxn_polarity = reactome_role_to_polarity(role)
                            rxn_grounding = reactome_role_to_grounding(role)

                            graph.add_edge(GraphEdge(
                                source_id=target_id,
                                target_id=rxn_id,
                                predicate=role_pred,
                                evidence_strength=participation_strength,
                                source="Reactome",
                                provenance=f"target-specific reaction role: {role} in {rev.reaction_name} (aggregated {rev.evidence_count} record(s))",
                                links=rxn_links,
                                data_quality="EVIDENCE_BACKED",
                                direction="POSITIVE" if rxn_polarity == MolecularPolarity.POSITIVE else ("NEGATIVE" if rxn_polarity == MolecularPolarity.NEGATIVE else "UNKNOWN"),
                                relationship_type=role_pred,
                                source_id_ref=rev.reaction_id,
                                evidence_type="CURATED_REACTION",
                                context={
                                    "target_role": role,
                                    "roles": rev.roles,
                                    "schema_class": rev.schema_class,
                                    "species": rev.species,
                                    "compartment": rev.compartment,
                                    "disease_context": rev.disease_context,
                                    "evidence_count": rev.evidence_count,
                                },
                                polarity=rxn_polarity,
                                causal_grounding=rxn_grounding,
                            ))

                        # Reaction -> Pathway (exactly one edge)
                        graph.add_edge(GraphEdge(
                            source_id=rxn_id,
                            target_id=pathway_id,
                            predicate="PART_OF",
                            evidence_strength=1.0,
                            source="Reactome",
                            provenance=f"reaction {rev.reaction_id} is part of pathway {pathway.name}",
                            links=pw_links,
                            data_quality="EVIDENCE_BACKED",
                            direction="UNKNOWN",
                            relationship_type="PART_OF",
                            source_id_ref=pathway.reactome_id,
                            evidence_type="CURATED_REACTION",
                            context={"evidence_count": rev.evidence_count},
                        ))

                # Retain baseline broad pathway participation edge
                graph.add_edge(GraphEdge(
                    source_id=target_id,
                    target_id=pathway_id,
                    predicate="PARTICIPATES_IN",
                    evidence_strength=participation_strength,
                    source="Reactome",
                    provenance=(
                        f"confirmed pathway participant; "
                        f"disease-gene overlap relevance {relevance:.2f}; "
                        f"participation strength {participation_strength:.2f}"
                    ),
                    links=pw_links,
                    data_quality="EVIDENCE_BACKED",
                    direction="UNKNOWN",
                    relationship_type="PARTICIPATES_IN",
                    evidence_type="PATHWAY_MEMBERSHIP",
                ))

                # Pathway → disease-associated gene(s) that are actually in it
                for sym in pw_gene_syms & disease_gene_syms:
                    gene_id = f"{_NODE_GENE}:{sym}"
                    gene_score = gene_scores[sym]
                    graph.add_node(GraphNode(gene_id, _NODE_GENE, sym))

                    pwg_links: list[EvidenceLink] = []
                    if u_pw:
                        pwg_links.append(EvidenceLink("Reactome", "Open Reactome Pathway", u_pw, pathway.reactome_id, "database"))
                    u_ot_t = SourceURLBuilder.opentargets_target_url(sym)
                    if u_ot_t:
                        pwg_links.append(EvidenceLink("Open Targets", "Open Targets Target", u_ot_t, sym, "database"))

                    graph.add_edge(GraphEdge(
                        source_id=pathway_id,
                        target_id=gene_id,
                        predicate="CONTAINS_ASSOCIATED_GENE",
                        evidence_strength=gene_score,
                        source="Reactome + Open Targets/DisGeNET",
                        provenance=(
                            f"{sym} is both a pathway participant and disease-associated "
                            f"(score {gene_score:.2f})"
                        ),
                        links=pwg_links,
                        data_quality="EVIDENCE_BACKED",
                        direction="UNKNOWN",
                        relationship_type="CONTAINS_ASSOCIATED_GENE",
                        evidence_type="PATHWAY_MEMBERSHIP",
                    ))

                    if gene_id not in genes_linked_to_disease:
                        gd_links2: list[EvidenceLink] = []
                        u_ot_d2 = SourceURLBuilder.opentargets_disease_url(package.disease.mesh_id or package.disease.name)
                        if u_ot_d2:
                            gd_links2.append(EvidenceLink("Open Targets", "Open Targets Disease", u_ot_d2, package.disease.name, "database"))
                        u_dg2 = SourceURLBuilder.disgenet_url(sym)
                        if u_dg2:
                            gd_links2.append(EvidenceLink("DisGeNET", "Open DisGeNET", u_dg2, sym, "database"))

                        d_ev2 = gene_evidence_map.get(sym)
                        d_scope2 = d_ev2.scope.value if (d_ev2 and hasattr(d_ev2.scope, "value")) else (str(d_ev2.scope) if d_ev2 and d_ev2.scope else "EXACT")
                        d_prov2 = d_ev2.provenance if d_ev2 and d_ev2.provenance else f"gene-disease association score {gene_score:.2f}"
                        d_dis_id2 = d_ev2.disease_id if d_ev2 else (package.disease.mesh_id or package.disease.name)

                        graph.add_edge(GraphEdge(
                            source_id=gene_id,
                            target_id=disease_id,
                            predicate="ASSOCIATED_WITH",
                            evidence_strength=gene_score,
                            source="Open Targets / DisGeNET",
                            provenance=d_prov2,
                            links=gd_links2,
                            data_quality="EVIDENCE_BACKED",
                            direction="UNKNOWN",
                            relationship_type="ASSOCIATED_WITH",
                            evidence_type="DISEASE_ASSOCIATION",
                            context={
                                "scope": d_scope2,
                                "disease_id": d_dis_id2,
                            },
                        ))
                        genes_linked_to_disease.add(gene_id)

        logger.info(
            "evidence_graph_built",
            extra={
                "hypothesis_id": str(package.hypothesis_id),
                "nodes": len(graph.nodes),
                "edges": len(graph.edges),
            },
        )
        # Phase 4B: return (graph, resolver) so callers can pass resolver to
        # AdvancedConflictResolver for canonical entity gating.
        return graph, resolver
