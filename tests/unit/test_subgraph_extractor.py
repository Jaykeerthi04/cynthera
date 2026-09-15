"""Unit tests for Playground Subgraph Extractor."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock
import pytest

from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.reasoning_result import ReasoningResult
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.pathway import Pathway
from backend.core.domain.evidence import Evidence
from backend.core.enums.evidence_type import EvidenceType
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.value_objects.identifier import ResolvedIdentifierSet
from backend.core.enums.recommendation import RecommendationStatus
from backend.playground.subgraph_extractor import extract_relevant_subgraph
from backend.playground.models import PlaygroundGraphData


@pytest.fixture
def mock_evaluation_data():
    """Create a mock RetrievalPackage and ReasoningResult."""
    hyp_id = uuid.uuid4()
    drug_ids = ResolvedIdentifierSet(entity_name="Sildenafil", entity_type="drug")
    disease_ids = ResolvedIdentifierSet(entity_name="Pulmonary Hypertension", entity_type="disease")

    drug = Drug(id=uuid.uuid4(), name="Sildenafil", identifiers=drug_ids, chembl_id="CHEMBL192")
    disease = Disease(id=uuid.uuid4(), name="Pulmonary Hypertension", identifiers=disease_ids, mesh_id="D006976")

    prov = ProvenanceReference(source_name="ChEMBL", source_version="1.0", record_id="CHEMBL192")
    target = Target(
        id=uuid.uuid4(),
        drug_chembl_id="CHEMBL192",
        protein_uniprot="O76074",
        mechanism="INHIBITOR",
        affinity_nm=3.5,
        affinity_type="IC50",
        erw=ERW(value=0.8),
        provenance=prov,
    )
    protein = Protein(
        id=uuid.uuid4(),
        name="PDE5A",
        uniprot_accession="O76074",
        gene_symbol="PDE5A",
        organism="Homo sapiens",
        is_reviewed=True,
    )
    pathway = Pathway(
        id=uuid.uuid4(),
        reactome_id="R-HSA-111634",
        name="cGMP effects",
        participant_uniprot_ids=["O76074"],
    )
    evidence = Evidence(
        id=uuid.uuid4(),
        evidence_type=EvidenceType.IN_VITRO,
        erw=ERW(value=0.6),
        citation_key="PMID:123456",
        title="Inhibition of PDE5A by Sildenafil",
        abstract="Sildenafil inhibits PDE5A...",
        target_uniprot="O76074",
        provenance=prov,
    )

    package = RetrievalPackage(
        id=uuid.uuid4(),
        hypothesis_id=hyp_id,
        drug=drug,
        disease=disease,
        targets=[target],
        proteins=[protein],
        pathways=[pathway],
        evidence_records=[evidence],
        clinical_trials=[],
        validated_disease_genes={"PDE5A": 0.85},
        sources_queried=["chembl", "uniprot", "reactome", "opentargets"],
        sources_failed=[],
        retrieval_confidence="HIGH",
    )

    result = MagicMock()
    result.hypothesis_id = hyp_id
    result.support_assessment.score = 0.75
    result.support_assessment.level = "HIGH"
    result.support_assessment.supporting_claim_ids = ["claim-1"]
    result.mechanistic_assessment.score = 0.65
    result.mechanistic_assessment.level = "HIGH"
    result.mechanistic_assessment.pathway_count = 1
    result.mechanistic_assessment.candidate_mechanisms = [
        {
            "name": "PDE5A inhibition -> cGMP effects",
            "hops": [
                {
                    "from_node": "Drug: Sildenafil",
                    "to_node": "Target: PDE5A",
                    "predicate": "INHIBITOR",
                    "canonical_from_id": "DRUG:Sildenafil",
                    "canonical_to_id": "TARGET:O76074",
                    "supporting_claims": [{"text": "Sildenafil potently inhibits PDE5A", "direction": "supporting"}],
                    "contradicting_claims": [],
                }
            ],
        }
    ]
    result.risk_assessment.score = 0.20
    result.risk_assessment.level = "LOW"
    result.risk_assessment.risk_claim_ids = []
    result.opposition_assessment.score = 0.0
    result.opposition_assessment.level = "NONE"
    result.recommendation_status = RecommendationStatus.PROMISING
    result.recommendation_reasons = ["Strong mechanistic grounding", "High support score"]
    result.contradictions = []
    result.data_source_failures = []
    result.claim_extraction_method = "llm"
    result.claim_citations = {}

    return package, result


def test_extract_relevant_subgraph_deterministic(mock_evaluation_data):
    package, result = mock_evaluation_data
    graph_data_1 = extract_relevant_subgraph(package, result)
    graph_data_2 = extract_relevant_subgraph(package, result)

    assert isinstance(graph_data_1, PlaygroundGraphData)
    assert graph_data_1.drug_name == "Sildenafil"
    assert graph_data_1.disease_name == "Pulmonary Hypertension"
    assert len(graph_data_1.nodes) == len(graph_data_2.nodes)
    assert len(graph_data_1.edges) == len(graph_data_2.edges)


def test_edge_why_is_this_relationship_here_data(mock_evaluation_data):
    package, result = mock_evaluation_data
    graph_data = extract_relevant_subgraph(package, result)

    assert len(graph_data.edges) > 0
    # Check that each edge carries path_count, evidence_count, and hop_claims fields
    for edge in graph_data.edges:
        assert isinstance(edge.path_count, int)
        assert isinstance(edge.evidence_count, int)
        assert isinstance(edge.hop_claims, list)

    # Edge from Sildenafil to PDE5A should have hop claims and evidence
    target_edge = next(
        (e for e in graph_data.edges if "Sildenafil" in e.source_id and "O76074" in e.target_id),
        None,
    )
    assert target_edge is not None
    assert target_edge.evidence_count >= 1
    assert target_edge.path_count >= 1
    assert len(target_edge.hop_claims) >= 1
    assert target_edge.hop_claims[0]["text"] == "Sildenafil potently inhibits PDE5A"


def test_evidence_landscape_and_gaps(mock_evaluation_data):
    package, result = mock_evaluation_data
    graph_data = extract_relevant_subgraph(package, result)

    assert graph_data.landscape.support_score == 0.75
    assert graph_data.landscape.mechanistic_score == 0.65
    assert graph_data.landscape.recommendation_status == "PROMISING"
    assert len(graph_data.evidence_gaps) > 0
