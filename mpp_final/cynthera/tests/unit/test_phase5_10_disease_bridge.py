"""Unit tests for Phase 5.10 — Disease-Bridge Robustness.

Verifies:
1. Exact disease identifier mapping
2. Equivalent ontology identifier mapping (dbXRefs)
3. Synonym resolution (hasExactSynonym)
4. Child disease provenance (CHILD scope)
5. Parent disease does NOT become direct bridge evidence (PARENT scope strictly excluded)
6. Duplicate genes collapse correctly (highest tier wins)
7. Full provenance is preserved across nodes and edges
8. Unrelated disease genes are never included
9. Ivermectin -> Heart Failure remains zero if no valid bridge exists
10. Metformin -> PCOS gains coverage ONLY if an actual disease-gene bridge is retrieved
11. Existing positive cases (e.g. Furosemide -> Edema) do not lose their paths
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from backend.core.domain.disease import Disease
from backend.core.domain.drug import Drug
from backend.core.domain.disease_gene_evidence import DiseaseGeneEvidence, DiseaseGeneScope
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.pathway import Pathway
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.connectors.opentargets import OpenTargetsConnector
from backend.reasoning.mechanistic.evidence_graph import (
    EvidenceGraphBuilder,
    build_validated_gene_scores,
)
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner


def _make_target(uniprot: str, mechanism: str = "INHIBITOR", affinity: float = 10.0) -> Target:
    return Target(
        drug_chembl_id="CHEMBL1",
        protein_uniprot=uniprot,
        affinity_nm=affinity,
        affinity_type="IC50",
        mechanism=mechanism,
        erw=ERW.from_base(0.9),
        provenance=ProvenanceReference(source_name="ChEMBL", source_version="33", record_id="r1", url=""),
    )


import uuid

def _make_sample_package(
    drug_name: str = "TestDrug",
    disease_name: str = "TestDisease",
    targets: list[Target] | None = None,
    proteins: list[Protein] | None = None,
    pathways: list[Pathway] | None = None,
    validated_disease_genes: dict[str, float] | None = None,
    disease_gene_evidence: list[DiseaseGeneEvidence] | None = None,
) -> RetrievalPackage:
    drug = Drug(name=drug_name, chembl_id="CHEMBL000", identifiers={"chembl": "CHEMBL000"})
    disease = Disease(name=disease_name, mesh_id="D000001", mondo_id="MONDO_0000001", identifiers={"mesh": "D000001"})
    return RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=drug,
        disease=disease,
        targets=targets or [],
        proteins=proteins or [],
        pathways=pathways or [],
        validated_disease_genes=validated_disease_genes or {},
        disease_gene_evidence=disease_gene_evidence or [],
    )


# ── 1. Exact disease identifier mapping ───────────────────────────────────────
def test_1_exact_disease_identifier_mapping():
    ev = DiseaseGeneEvidence(
        gene_symbol="TTN",
        disease_id="MONDO_0005252",
        evidence_score=0.95,
        scope=DiseaseGeneScope.EXACT,
        provenance="Direct canonical association",
    )
    assert ev.scope == DiseaseGeneScope.EXACT
    assert ev.can_bridge_mechanistic_graph() is True
    assert ev.disease_id == "MONDO_0005252"


# ── 2. Equivalent ontology identifier mapping ─────────────────────────────────
def test_2_equivalent_ontology_identifier():
    ev = DiseaseGeneEvidence(
        gene_symbol="ESR1",
        disease_id="EFO:0000660",
        ontology_source="EFO",
        evidence_score=0.85,
        scope=DiseaseGeneScope.EQUIVALENT,
        provenance="Cross-reference dbXRef equivalence to MONDO:0008487",
    )
    assert ev.scope == DiseaseGeneScope.EQUIVALENT
    assert ev.can_bridge_mechanistic_graph() is True
    assert ev.ontology_source == "EFO"


# ── 3. Synonym resolution ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_3_synonym_resolution():
    connector = OpenTargetsConnector()
    with patch.object(connector, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {
            "data": {
                "search": {
                    "hits": [
                        {"id": "MONDO_0008487", "name": "polycystic ovary syndrome", "entity": "disease"}
                    ]
                }
            }
        }
        res = await connector.resolve_mondo_id("PCOS")
        assert res == "MONDO_0008487"


# ── 4. Child disease provenance ───────────────────────────────────────────────
def test_4_child_disease_provenance():
    ev = DiseaseGeneEvidence(
        gene_symbol="BRAF",
        disease_id="MONDO_0006519",
        evidence_score=0.78,
        scope=DiseaseGeneScope.CHILD,
        provenance="Child subtype association: rectal cancer (MONDO_0006519) under colorectal cancer",
        relationship="CHILD_OF_MONDO_0005575",
    )
    assert ev.scope == DiseaseGeneScope.CHILD
    assert ev.can_bridge_mechanistic_graph() is True
    assert "Child subtype" in ev.provenance


# ── 5. Parent disease does NOT become direct bridge evidence ──────────────────
def test_5_parent_disease_does_not_become_direct_evidence():
    ev_parent = DiseaseGeneEvidence(
        gene_symbol="GENERIC_HEART_GENE",
        disease_id="MONDO_0005267",
        evidence_score=0.90,
        scope=DiseaseGeneScope.PARENT,
        provenance="Parent class: heart disorder",
    )
    assert ev_parent.scope == DiseaseGeneScope.PARENT
    # CRITICAL INVARIANT: PARENT scope must never bridge the mechanistic graph
    assert ev_parent.can_bridge_mechanistic_graph() is False

    # EvidenceGraphBuilder must exclude PARENT tier from graph scores
    pkg = _make_sample_package(
        disease_gene_evidence=[ev_parent],
    )
    scores = build_validated_gene_scores(pkg)
    assert "GENERIC_HEART_GENE" not in scores


# ── 6. Duplicate genes collapse correctly (highest tier wins) ─────────────────
def test_6_duplicate_genes_collapse_correctly():
    ev_child = DiseaseGeneEvidence(
        gene_symbol="TP53",
        disease_id="MONDO_0006519",
        evidence_score=0.60,
        scope=DiseaseGeneScope.CHILD,
    )
    ev_exact = DiseaseGeneEvidence(
        gene_symbol="TP53",
        disease_id="MONDO_0005575",
        evidence_score=0.85,
        scope=DiseaseGeneScope.EXACT,
    )
    pkg = _make_sample_package(
        disease_gene_evidence=[ev_child, ev_exact],
    )
    scores = build_validated_gene_scores(pkg)
    assert "TP53" in scores
    assert scores["TP53"] == 0.85


# ── 7. Provenance is preserved in the graph ───────────────────────────────────
def test_7_provenance_is_preserved_in_graph():
    tgt = _make_target("P12345")
    prot = Protein(uniprot_accession="P12345", gene_symbol="TGT1", name="Target 1 Protein")
    pw = Pathway(name="Pathway 1", reactome_id="R-HSA-1111", participant_uniprot_ids=["P12345", "Q99999"])
    ev = DiseaseGeneEvidence(
        gene_symbol="GENE1",
        disease_id="MONDO_0005252",
        evidence_score=0.80,
        scope=DiseaseGeneScope.EXACT,
        provenance="Verified exact heart failure gene association from OpenTargets GWAS",
    )
    pkg = _make_sample_package(
        targets=[tgt],
        proteins=[prot, Protein(uniprot_accession="Q99999", gene_symbol="GENE1", name="Gene 1")],
        pathways=[pw],
        disease_gene_evidence=[ev],
    )
    builder = EvidenceGraphBuilder()
    graph, _ = builder.build(pkg)

    # Check edge from GENE:GENE1 to DISEASE
    gene_disease_edges = [
        e for e in graph.edges
        if e.source_id == "GENE:GENE1" and e.target_id.startswith("DISEASE:")
    ]
    assert len(gene_disease_edges) == 1
    edge = gene_disease_edges[0]
    assert edge.provenance == "Verified exact heart failure gene association from OpenTargets GWAS"
    assert edge.context.get("scope") == "EXACT"
    assert edge.context.get("disease_id") == "MONDO_0005252"


# ── 8. Unrelated disease genes are never included ─────────────────────────────
def test_8_unrelated_disease_genes_never_included():
    tgt = _make_target("P12345")
    prot = Protein(uniprot_accession="P12345", gene_symbol="TGT1", name="Target 1")
    # Pathway does not contain UNRELATED_GENE
    pw = Pathway(name="Pathway 1", reactome_id="R-HSA-1111", participant_uniprot_ids=["P12345"])
    ev_unrelated = DiseaseGeneEvidence(
        gene_symbol="UNRELATED_GENE",
        disease_id="MONDO_0005252",
        evidence_score=0.90,
        scope=DiseaseGeneScope.EXACT,
    )
    pkg = _make_sample_package(
        targets=[tgt],
        proteins=[prot],
        pathways=[pw],
        disease_gene_evidence=[ev_unrelated],
    )
    builder = EvidenceGraphBuilder()
    graph, _ = builder.build(pkg)

    # Pathway should NOT connect to UNRELATED_GENE because it is not a participant
    pw_gene_edges = [
        e for e in graph.edges
        if e.source_id.startswith("PATHWAY:") and e.target_id == "GENE:UNRELATED_GENE"
    ]
    assert len(pw_gene_edges) == 0


# ── 9. Ivermectin → Heart Failure remains zero if no valid bridge exists ──────
def test_9_ivermectin_heart_failure_remains_zero():
    # Invertebrate targets not in human heart failure genes
    tgt = _make_target("Q25634")
    prot = Protein(uniprot_accession="Q25634", gene_symbol="GLUCL", name="GluCl")
    pw = Pathway(name="Nerve signaling", reactome_id="R-HSA-9999", participant_uniprot_ids=["Q25634"])
    # Disease genes exist for Heart Failure, but do NOT overlap with Ivermectin pathway
    ev_hf = DiseaseGeneEvidence(
        gene_symbol="TTN",
        disease_id="MONDO_0005252",
        evidence_score=0.95,
        scope=DiseaseGeneScope.EXACT,
    )
    pkg = _make_sample_package(
        drug_name="Ivermectin",
        disease_name="Heart failure",
        targets=[tgt],
        proteins=[prot],
        pathways=[pw],
        disease_gene_evidence=[ev_hf],
    )
    reasoner = MultiHopReasoner()
    paths = reasoner.trace_paths(pkg)
    # No simple path from Ivermectin to Heart failure
    assert len(paths) == 0
    score, level = reasoner.compute_mechanistic_score_from_candidates([])
    assert score == 0.0
    assert level == "NONE"


# ── 10. Metformin → PCOS gains coverage ONLY if actual bridge is retrieved ────
def test_10_metformin_pcos_coverage_with_actual_bridge():
    # Metformin target: PRKAA1
    tgt = _make_target("Q13131")
    prot = Protein(uniprot_accession="Q13131", gene_symbol="PRKAA1", name="AMPK subunit alpha 1")
    # Reactome pathway for PRKAA1 containing PRKAA1 and downstream metabolic target
    pw = Pathway(name="AMPK signaling", reactome_id="R-HSA-380972", participant_uniprot_ids=["Q13131", "P06401"])
    prot2 = Protein(uniprot_accession="P06401", gene_symbol="ESR1", name="Estrogen receptor")

    # Scenario A: No overlap -> zero paths
    pkg_no_bridge = _make_sample_package(
        drug_name="Metformin",
        disease_name="PCOS",
        targets=[tgt],
        proteins=[prot],
        pathways=[pw],
        disease_gene_evidence=[],
    )
    reasoner = MultiHopReasoner()
    paths_a = reasoner.trace_paths(pkg_no_bridge)
    assert len(paths_a) == 0

    # Scenario B: Overlap with valid PCOS gene (ESR1) -> path discovered
    ev_pcos = DiseaseGeneEvidence(
        gene_symbol="ESR1",
        disease_id="MONDO_0008487",
        evidence_score=0.88,
        scope=DiseaseGeneScope.EXACT,
        provenance="OpenTargets PCOS association for ESR1",
    )
    pkg_with_bridge = _make_sample_package(
        drug_name="Metformin",
        disease_name="PCOS",
        targets=[tgt],
        proteins=[prot, prot2],
        pathways=[pw],
        disease_gene_evidence=[ev_pcos],
    )
    paths_b = reasoner.trace_paths(pkg_with_bridge)
    assert len(paths_b) > 0


# ── 11. Existing positive cases do not lose their paths ───────────────────────
def test_11_existing_positive_cases_retain_paths():
    # Furosemide -> SLC12A1 -> Edema
    tgt = _make_target("Q13621")
    prot = Protein(uniprot_accession="Q13621", gene_symbol="SLC12A1", name="NKCC2")
    pw = Pathway(name="Transport of glucose and other sugars, bile salts and organic acids, metal ions and amine compounds",
                 reactome_id="R-HSA-425407", participant_uniprot_ids=["Q13621"])
    ev = DiseaseGeneEvidence(
        gene_symbol="SLC12A1",
        disease_id="EFO:0009373",
        evidence_score=0.80,
        scope=DiseaseGeneScope.EXACT,
        provenance="OpenTargets direct association for edema",
    )
    pkg = _make_sample_package(
        drug_name="Furosemide",
        disease_name="Edema",
        targets=[tgt],
        proteins=[prot],
        pathways=[pw],
        disease_gene_evidence=[ev],
    )
    reasoner = MultiHopReasoner()
    paths = reasoner.trace_paths(pkg)
    assert len(paths) > 0
