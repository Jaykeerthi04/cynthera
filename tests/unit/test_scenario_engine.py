"""Unit tests for Playground Scenario Engine."""
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
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.value_objects.identifier import ResolvedIdentifierSet
from backend.core.enums.recommendation import RecommendationStatus
from backend.playground.scenario_engine import ScenarioEngine
from backend.playground.models import ScenarioModifications, ScenarioModification


@pytest.fixture
def mock_scenario_data():
    """Create a mock RetrievalPackage and ReasoningResult with a traceable path."""
    hyp_id = uuid.uuid4()
    drug_ids = ResolvedIdentifierSet(entity_name="DrugX", entity_type="drug")
    disease_ids = ResolvedIdentifierSet(entity_name="DiseaseY", entity_type="disease")

    drug = Drug(id=uuid.uuid4(), name="DrugX", identifiers=drug_ids, chembl_id="CHEMBL1")
    disease = Disease(id=uuid.uuid4(), name="DiseaseY", identifiers=disease_ids, mesh_id="D001")

    prov = ProvenanceReference(source_name="ChEMBL", source_version="1.0", record_id="CHEMBL1")
    target = Target(
        id=uuid.uuid4(),
        drug_chembl_id="CHEMBL1",
        protein_uniprot="P99999",
        mechanism="INHIBITOR",
        affinity_nm=10.0,
        affinity_type="IC50",
        erw=ERW(value=0.8),
        provenance=prov,
    )
    protein = Protein(
        id=uuid.uuid4(),
        name="Protein A",
        uniprot_accession="P99999",
        gene_symbol="GENEA",
        organism="Homo sapiens",
        is_reviewed=True,
    )
    pathway = Pathway(
        id=uuid.uuid4(),
        reactome_id="R-HSA-999999",
        name="Pathway 1",
        participant_uniprot_ids=["P99999"],
    )

    package = RetrievalPackage(
        id=uuid.uuid4(),
        hypothesis_id=hyp_id,
        drug=drug,
        disease=disease,
        targets=[target],
        proteins=[protein],
        pathways=[pathway],
        evidence_records=[],
        clinical_trials=[],
        validated_disease_genes={"GENEA": 0.8},
        sources_queried=["chembl", "uniprot", "reactome", "opentargets"],
        sources_failed=[],
        retrieval_confidence="HIGH",
    )

    result = MagicMock()
    result.hypothesis_id = hyp_id
    result.support_assessment.score = 0.82
    result.support_assessment.level = "HIGH"
    result.support_assessment.supporting_claim_ids = ["c1"]
    result.mechanistic_assessment.score = 0.70
    result.mechanistic_assessment.level = "HIGH"
    result.mechanistic_assessment.pathway_count = 1
    result.mechanistic_assessment.candidate_mechanisms = []
    result.risk_assessment.score = 0.15
    result.risk_assessment.level = "LOW"
    result.risk_assessment.risk_claim_ids = []
    result.opposition_assessment.score = 0.0
    result.opposition_assessment.level = "NONE"
    result.recommendation_status = RecommendationStatus.PROMISING
    result.recommendation_reasons = ["Valid mechanism"]
    result.contradictions = []

    return package, result


def test_scenario_ms_only_recomputation(mock_scenario_data):
    package, result = mock_scenario_data
    engine = ScenarioEngine()

    # Disable the DrugX -> TargetA edge
    mods = ScenarioModifications(
        modifications=[
            ScenarioModification(
                action="disable_edge",
                edge_id="DRUG:DrugX->TARGET:P99999",
            )
        ]
    )
    res = engine.compute_scenario(package, result, mods)

    # 1. Mechanistic score should drop to 0 because the sole path is severed
    assert res.scenario_mechanistic_score < res.original_mechanistic_score
    assert res.scenario_mechanistic_score == 0.0
    assert res.affected_paths > 0

    # 2. Honest labeling: SS, RS, Opposition kept from original
    assert res.original_support_score == 0.82
    assert res.original_risk_score == 0.15
    assert res.original_opposition_score == 0.0
    assert res.scores_recomputed == ["mechanistic_score"]
    assert "support_score" in res.scores_kept_original
    assert "risk_score" in res.scores_kept_original
    assert "opposition_score" in res.scores_kept_original

    # 3. Disclaimer present
    assert "Only Mechanistic Score was recomputed" in res.disclaimer


def test_scenario_no_modifications(mock_scenario_data):
    package, result = mock_scenario_data
    engine = ScenarioEngine()

    mods = ScenarioModifications(modifications=[])
    res = engine.compute_scenario(package, result, mods)

    assert res.scenario_mechanistic_score == res.original_mechanistic_score
    assert res.affected_paths == 0
    assert res.disabled_edge_count == 0
