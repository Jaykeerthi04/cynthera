"""Subgraph extractor — builds the Playground graph view from existing CYNTHERA data.

This is a VIEW ADAPTER, not a new graph system. It:
1. Calls EvidenceGraphBuilder().build(package) to reconstruct the evidence graph
2. Extracts claims and contradictions from the ReasoningResult
3. Assembles PlaygroundGraphData for the frontend

Zero network calls. Purely deterministic.

Reference: implementation_plan.md — Phase 2
"""
from __future__ import annotations

import logging
from typing import Any

from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.reasoning_result import ReasoningResult
from backend.core.value_objects.source_url_builder import SourceURLBuilder
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder, EvidenceGraph
from backend.playground.models import (
    PlaygroundGraphData,
    PlaygroundNode,
    PlaygroundEdge,
    PlaygroundClaim,
    PlaygroundEvidence,
    PlaygroundClinicalTrial,
    PlaygroundContradiction,
    EvidenceLandscape,
    EvidenceGap,
)

logger = logging.getLogger(__name__)


def _classify_evidence_direction(claim_predicate: str) -> str:
    """Map a predicate to supporting/opposing/neutral direction."""
    _SUPPORTING = {
        "ACTIVATES", "UPREGULATES", "CAUSES", "BINDS",
        "ASSOCIATED_WITH", "PREVENTS",
    }
    _OPPOSING = {
        "INHIBITS", "DOWNREGULATES", "NO_EFFECT",
    }
    pred_upper = claim_predicate.upper()
    if pred_upper in _SUPPORTING:
        return "supporting"
    elif pred_upper in _OPPOSING:
        return "opposing"
    return "neutral"


def _classify_edge_direction(predicate: str) -> str:
    """Classify an evidence graph edge predicate as a direction type."""
    pred_upper = predicate.upper()
    # Structural/mechanistic predicates
    if pred_upper in (
        "PARTICIPATES_IN", "ENCODED_BY_DISEASE_ASSOCIATED_GENE",
        "CONTAINS_ASSOCIATED_GENE",
    ):
        return "structural"
    # Target interaction predicates
    if pred_upper in ("INHIBITOR", "AGONIST", "ANTAGONIST", "MODULATOR", "MODULATES"):
        return "supporting"
    if pred_upper == "ASSOCIATED_WITH":
        return "supporting"
    return "structural"


def _build_evidence_links(evidence: Any) -> list[dict[str, str]]:
    """Build clickable links for an evidence record."""
    links = []
    citation_key = getattr(evidence, "citation_key", "") or ""
    title = getattr(evidence, "title", None)
    for link in SourceURLBuilder.build_links_for_citation_key(citation_key, title):
        links.append(link.to_dict())
    return links


def _count_evidence_for_target(package: RetrievalPackage, target_uniprot: str | None) -> int:
    """Count evidence records mentioning a specific target."""
    if not target_uniprot:
        return 0
    return sum(
        1 for e in package.evidence_records
        if getattr(e, "target_uniprot", None) == target_uniprot
    )


def _build_evidence_landscape(
    package: RetrievalPackage,
    result: ReasoningResult,
) -> EvidenceLandscape:
    """Build the evidence landscape summary from existing scores and evidence."""
    from backend.core.enums.evidence_type import EvidenceType

    supporting_ids = set(result.support_assessment.supporting_claim_ids)
    opposing_ids = set(result.risk_assessment.risk_claim_ids)

    # Count evidence by type
    mechanistic_count = 0
    literature_count = 0
    clinical_count = 0

    for ev in package.evidence_records:
        et = getattr(ev, "evidence_type", None)
        if et in (EvidenceType.IN_VITRO, EvidenceType.IN_VIVO, EvidenceType.COMPUTATIONAL):
            mechanistic_count += 1
        elif et in (EvidenceType.LITERATURE, EvidenceType.OBSERVATIONAL):
            literature_count += 1
        elif et in (EvidenceType.RCT, EvidenceType.META_ANALYSIS):
            clinical_count += 1

    supporting_count = len(supporting_ids)
    opposing_count = len(opposing_ids)
    uncertain_count = max(0, len(package.evidence_records) - supporting_count - opposing_count)

    return EvidenceLandscape(
        supporting_count=supporting_count,
        opposing_count=opposing_count,
        uncertain_count=uncertain_count,
        mechanistic_count=mechanistic_count,
        literature_count=literature_count,
        clinical_count=clinical_count + len(package.clinical_trials),
        safety_count=0,  # Safety signals come from the audit report
        support_score=result.support_assessment.score,
        mechanistic_score=result.mechanistic_assessment.score,
        risk_score=result.risk_assessment.score,
        opposition_score=result.opposition_assessment.score,
        support_level=result.support_assessment.level,
        mechanistic_level=result.mechanistic_assessment.level,
        risk_level=result.risk_assessment.level,
        opposition_level=result.opposition_assessment.level,
        recommendation_status=result.recommendation_status.value,
        recommendation_reasons=list(result.recommendation_reasons),
    )


def _build_evidence_gaps(
    package: RetrievalPackage,
    result: ReasoningResult,
) -> list[EvidenceGap]:
    """Build evidence gap indicators from existing data.

    These are explicitly labeled as UI heuristics, not scientific conclusions.
    """
    gaps: list[EvidenceGap] = []

    # Drug-target evidence
    if package.targets:
        gaps.append(EvidenceGap(
            category="drug_target",
            status="FOUND",
            label="Drug-target interaction evidence",
        ))
    else:
        gaps.append(EvidenceGap(
            category="drug_target",
            status="MISSING",
            label="No drug-target interactions retrieved",
        ))

    # Mechanistic pathway evidence
    if result.mechanistic_assessment.pathway_count > 0:
        gaps.append(EvidenceGap(
            category="mechanistic",
            status="FOUND",
            label=f"Mechanistic pathway evidence ({result.mechanistic_assessment.pathway_count} pathways)",
        ))
    else:
        gaps.append(EvidenceGap(
            category="mechanistic",
            status="MISSING",
            label="No mechanistic pathway connections found",
        ))

    # Literature evidence
    lit_count = len(package.literature_evidence)
    if lit_count >= 5:
        gaps.append(EvidenceGap(
            category="literature",
            status="FOUND",
            label=f"Literature evidence ({lit_count} records)",
        ))
    elif lit_count > 0:
        gaps.append(EvidenceGap(
            category="literature",
            status="LIMITED",
            label=f"Limited literature evidence ({lit_count} records)",
        ))
    else:
        gaps.append(EvidenceGap(
            category="literature",
            status="MISSING",
            label="No literature evidence retrieved",
        ))

    # Clinical trial evidence
    if package.clinical_trials:
        gaps.append(EvidenceGap(
            category="clinical",
            status="FOUND",
            label=f"Clinical trial data ({len(package.clinical_trials)} trials)",
        ))
    elif package.clinical_trial_retrieval_status == "NOT_FOUND":
        gaps.append(EvidenceGap(
            category="clinical",
            status="MISSING",
            label="No clinical trials found for this drug-disease pair",
        ))
    elif package.clinical_trial_retrieval_status == "API_FAILURE":
        gaps.append(EvidenceGap(
            category="clinical",
            status="MISSING",
            label="Clinical trial data unavailable (API failure)",
        ))
    else:
        gaps.append(EvidenceGap(
            category="clinical",
            status="MISSING",
            label="No clinical trial data",
        ))

    # Contradiction status
    if result.contradictions:
        gaps.append(EvidenceGap(
            category="safety",
            status="CONFLICTED",
            label=f"Conflicting findings detected ({len(result.contradictions)} contradictions)",
        ))

    # Opposition evidence
    if result.opposition_assessment.score > 0:
        gaps.append(EvidenceGap(
            category="safety",
            status="CONFLICTED",
            label=f"Therapeutic opposition evidence detected (score: {result.opposition_assessment.score:.2f})",
        ))

    return gaps


def extract_relevant_subgraph(
    package: RetrievalPackage,
    result: ReasoningResult,
) -> PlaygroundGraphData:
    """Extract the relevant subgraph for the Playground from existing CYNTHERA data.

    This is NOT a new graph. It is a presentation view over:
    - EvidenceGraph (from EvidenceGraphBuilder)
    - ReasoningResult (scores, claims, contradictions, candidate mechanisms)
    - RetrievalPackage (evidence records, clinical trials, provenance)

    Args:
        package: Sealed RetrievalPackage from the completed evaluation.
        result: ReasoningResult from the completed evaluation.

    Returns:
        PlaygroundGraphData ready for JSON serialization to the frontend.
    """
    # ── Step 1: Rebuild evidence graph from stored package ──────────────
    builder = EvidenceGraphBuilder()
    evidence_graph = builder.build(package)

    # ── Step 2: Convert graph nodes ────────────────────────────────────
    nodes: list[PlaygroundNode] = []
    for gn in evidence_graph.nodes.values():
        node_links: list[dict[str, str]] = []
        meta = dict(gn.meta)

        # Add source URLs based on node type
        if gn.label == "TARGET":
            uniprot = meta.get("uniprot")
            if uniprot:
                url = SourceURLBuilder.uniprot_url(uniprot)
                if url:
                    node_links.append({"source_name": "UniProt", "display_label": "Open UniProt", "url": url})
            gene = meta.get("gene_symbol")
            if gene:
                url = SourceURLBuilder.opentargets_target_url(gene)
                if url:
                    node_links.append({"source_name": "Open Targets", "display_label": "Open Targets Target", "url": url})
            ev_count = _count_evidence_for_target(package, meta.get("uniprot"))
        elif gn.label == "DRUG":
            if package.drug.chembl_id:
                url = SourceURLBuilder.chembl_compound_url(package.drug.chembl_id)
                if url:
                    node_links.append({"source_name": "ChEMBL", "display_label": "Open ChEMBL", "url": url})
            ev_count = 0
        elif gn.label == "DISEASE":
            mesh_id = getattr(package.disease, "mesh_id", None)
            if mesh_id:
                url = SourceURLBuilder.opentargets_disease_url(mesh_id)
                if url:
                    node_links.append({"source_name": "Open Targets", "display_label": "Open Targets Disease", "url": url})
            ev_count = 0
        elif gn.label == "PATHWAY":
            # Extract Reactome ID from node ID
            reactome_id = gn.id.replace("PATHWAY:", "")
            url = SourceURLBuilder.reactome_url(reactome_id)
            if url:
                node_links.append({"source_name": "Reactome", "display_label": "Open Reactome", "url": url})
            ev_count = 0
        elif gn.label == "GENE":
            gene_sym = gn.name
            url = SourceURLBuilder.opentargets_target_url(gene_sym)
            if url:
                node_links.append({"source_name": "Open Targets", "display_label": "Open Targets", "url": url})
            url2 = SourceURLBuilder.disgenet_url(gene_sym)
            if url2:
                node_links.append({"source_name": "DisGeNET", "display_label": "Open DisGeNET", "url": url2})
            ev_count = 0
        else:
            ev_count = 0

        nodes.append(PlaygroundNode(
            id=gn.id,
            label=gn.label,
            name=gn.name,
            meta=meta,
            evidence_count=ev_count,
            links=node_links,
        ))

    # ── Step 3: Convert graph edges ────────────────────────────────────
    edges: list[PlaygroundEdge] = []
    for ge in evidence_graph.edges:
        edge_links = [link.to_dict() for link in ge.links]
        edges.append(PlaygroundEdge(
            source_id=ge.source_id,
            target_id=ge.target_id,
            predicate=ge.predicate,
            direction=_classify_edge_direction(ge.predicate),
            evidence_strength=ge.evidence_strength,
            source_database=ge.source,
            provenance=ge.provenance,
            data_quality=ge.data_quality,
            links=edge_links,
        ))

    # ── Step 4: Extract evidence records ───────────────────────────────
    evidence_list: list[PlaygroundEvidence] = []
    for ev in package.evidence_records:
        prov = getattr(ev, "provenance", None)
        evidence_list.append(PlaygroundEvidence(
            id=str(ev.id),
            evidence_type=ev.evidence_type.value if hasattr(ev.evidence_type, "value") else str(ev.evidence_type),
            erw=ev.erw.value if hasattr(ev.erw, "value") else float(ev.erw),
            citation_key=ev.citation_key,
            title=ev.title,
            abstract=ev.abstract,
            source_name=prov.source_name if prov else "",
            source_url=prov.url if prov else None,
            retrieved_at=prov.retrieved_at.isoformat() if prov and hasattr(prov.retrieved_at, "isoformat") else None,
            links=_build_evidence_links(ev),
        ))

    # ── Step 5: Extract clinical trials ────────────────────────────────
    trials: list[PlaygroundClinicalTrial] = []
    for ct in package.clinical_trials:
        ct_url = SourceURLBuilder.clinicaltrials_url(ct.nct_id)
        trials.append(PlaygroundClinicalTrial(
            id=str(ct.id),
            nct_id=ct.nct_id,
            title=ct.title,
            phase=ct.phase,
            status=ct.status.value if hasattr(ct.status, "value") else str(ct.status),
            primary_outcome=ct.primary_outcome,
            enrollment=ct.enrollment,
            url=ct_url,
        ))

    # ── Step 6: Extract contradictions ─────────────────────────────────
    contradictions: list[PlaygroundContradiction] = []
    for c in result.contradictions:
        contradictions.append(PlaygroundContradiction(
            id=str(c.id),
            conflict_type=c.conflict_type,
            contradiction_score=c.contradiction_score,
            shared_subject=c.shared_subject,
            explanation=c.explanation,
            claim_a_summary=f"Claim {str(c.claim_id_a)[:8]}",
            claim_b_summary=f"Claim {str(c.claim_id_b)[:8]}",
            claim_a_evidence_ids=[str(c.claim_id_a)],
            claim_b_evidence_ids=[str(c.claim_id_b)],
        ))

    # ── Step 7: Extract claims from audit report ───────────────────────
    claims: list[PlaygroundClaim] = []
    # Supporting claims from support assessment
    for claim_id in result.support_assessment.supporting_claim_ids:
        claims.append(PlaygroundClaim(
            id=claim_id,
            subject="",
            predicate="SUPPORTS",
            object="",
            direction="supporting",
            provenance_source="support_assessment",
        ))
    # Risk claims
    for claim_id in result.risk_assessment.risk_claim_ids:
        claims.append(PlaygroundClaim(
            id=claim_id,
            subject="",
            predicate="OPPOSES",
            object="",
            direction="opposing",
            provenance_source="risk_assessment",
        ))

    # ── Step 8: Build landscape and gaps ───────────────────────────────
    landscape = _build_evidence_landscape(package, result)
    evidence_gaps = _build_evidence_gaps(package, result)

    # ── Step 9: Assemble ───────────────────────────────────────────────
    return PlaygroundGraphData(
        hypothesis_id=str(result.hypothesis_id),
        drug_name=package.drug.name,
        disease_name=package.disease.name,
        nodes=nodes,
        edges=edges,
        claims=claims,
        evidence=evidence_list,
        clinical_trials=trials,
        contradictions=contradictions,
        landscape=landscape,
        evidence_gaps=evidence_gaps,
        candidate_mechanisms=list(result.mechanistic_assessment.candidate_mechanisms),
        retrieval_confidence=package.retrieval_confidence,
        sources_queried=list(package.sources_queried),
        sources_failed=list(package.sources_failed),
        sealed_at=package.sealed_at.isoformat() if hasattr(package.sealed_at, "isoformat") else None,
        data_source_failures=list(result.data_source_failures),
        claim_extraction_method=result.claim_extraction_method,
    )
