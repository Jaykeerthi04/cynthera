"""Unit tests verifying bypass_cache semantics and EvaluationCache versioning in MasterOrchestrator."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.domain.disease import Disease
from backend.core.domain.drug import Drug
from backend.core.domain.hypothesis import Hypothesis
from backend.core.domain.reasoning_result import ReasoningResult
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.core.value_objects.identifier import CanonicalIdentifier, ResolvedIdentifierSet
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from tests.unit.test_opposition_reasoning_result_integration import _make_real_reasoning_result


def _make_dummy_drug(name: str) -> Drug:
    return Drug(
        name=name,
        identifiers=ResolvedIdentifierSet(
            entity_name=name,
            entity_type="drug",
            identifiers=[CanonicalIdentifier(namespace="chembl", value="CHEMBL123")],
        ),
    )


def _make_dummy_disease(name: str) -> Disease:
    return Disease(
        name=name,
        identifiers=ResolvedIdentifierSet(
            entity_name=name,
            entity_type="disease",
            identifiers=[CanonicalIdentifier(namespace="mesh", value="D123")],
        ),
    )


@pytest.mark.asyncio
async def test_evaluate_cache_hit_when_bypass_cache_is_false(tmp_path):
    """When bypass_cache=False and a valid cached result exists, MasterOrchestrator returns it."""
    db_path = str(tmp_path / "test_eval_cache.db")
    orch = MasterOrchestrator(db_path=db_path, use_cache=True)

    # Seed cache with a real ReasoningResult (already rule_set_version='2.1')
    cached_rr = _make_real_reasoning_result()
    orch._cache.set("DrugX", "DiseaseY", cached_rr, policy="STANDARD")

    # Seed storage with matching hypothesis and package
    hyp = Hypothesis(
        id=cached_rr.hypothesis_id,
        drug_name="DrugX",
        disease_name="DiseaseY",
        retrieval_policy=RetrievalPolicy.STANDARD,
    )
    orch._storage.save_hypothesis(hyp)

    pkg = RetrievalPackage(
        hypothesis_id=cached_rr.hypothesis_id,
        drug=_make_dummy_drug("DrugX"),
        disease=_make_dummy_disease("DiseaseY"),
        retrieval_confidence="HIGH",
    )
    orch._storage.save_retrieval_package(pkg)

    # Evaluate with bypass_cache=False
    eval_hyp, ret_pkg, res = await orch.evaluate(
        drug_name="DrugX",
        disease_name="DiseaseY",
        policy=RetrievalPolicy.STANDARD,
        bypass_cache=False,
    )

    assert res.hypothesis_id == cached_rr.hypothesis_id
    assert res.rule_set_version == "3.2"


@pytest.mark.asyncio
async def test_evaluate_bypasses_cache_when_bypass_cache_is_true(tmp_path):
    """When bypass_cache=True, MasterOrchestrator ignores cached result and re-executes pipeline."""
    db_path = str(tmp_path / "test_eval_cache_bypass.db")
    orch = MasterOrchestrator(db_path=db_path, use_cache=True)

    # Seed cache with an old result
    old_cached_rr = _make_real_reasoning_result()
    orch._cache.set("DrugX", "DiseaseY", old_cached_rr, policy="STANDARD")

    # Mock resolver, retrieval, reasoning
    fresh_rr = _make_real_reasoning_result()
    assert fresh_rr.hypothesis_id != old_cached_rr.hypothesis_id

    orch._resolver.resolve_drug = AsyncMock(
        return_value=ResolvedIdentifierSet(
            entity_name="DrugX",
            entity_type="drug",
            identifiers=[CanonicalIdentifier(namespace="chembl", value="CHEMBL123")],
        )
    )
    orch._resolver.resolve_disease = AsyncMock(
        return_value=ResolvedIdentifierSet(
            entity_name="DiseaseY",
            entity_type="disease",
            identifiers=[CanonicalIdentifier(namespace="mesh", value="D123")],
        )
    )

    async def mock_retrieval_execute(drug, disease, hyp_id):
        return RetrievalPackage(
            hypothesis_id=hyp_id,
            drug=_make_dummy_drug("DrugX"),
            disease=_make_dummy_disease("DiseaseY"),
            retrieval_confidence="HIGH",
        )

    async def mock_reason(package):
        res = _make_real_reasoning_result()
        return res.model_copy(update={"hypothesis_id": package.hypothesis_id})

    orch._retrieval.execute = AsyncMock(side_effect=mock_retrieval_execute)
    orch._reasoning.reason = AsyncMock(side_effect=mock_reason)

    # Evaluate with bypass_cache=True
    hyp, ret_pkg, res = await orch.evaluate(
        drug_name="DrugX",
        disease_name="DiseaseY",
        policy=RetrievalPolicy.STANDARD,
        bypass_cache=True,
    )

    # Must return fresh result, NOT the cached one
    assert res.hypothesis_id == hyp.id
    assert res.hypothesis_id != old_cached_rr.hypothesis_id

    # Must set _bypass_raw_cache=True on retrieval pipeline
    assert orch._retrieval._bypass_raw_cache is True
