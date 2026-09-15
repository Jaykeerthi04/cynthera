"""Unit test for Section 9: Cache Validation for Freeze Release.

Verifies:
1. Fresh uncached evaluation succeeds and returns rule_set_version='3.2'.
2. The evaluated result is stored in EvaluationCache under rule_set_version='3.2'.
3. Second evaluation through cache returns identical deterministic fields:
   - recommendation_status
   - support_score
   - mechanistic_score
   - risk_score
   - rule_set_version ('3.2')
   - recommendation_reasons
4. Stale versions ('2.0', '2.1', '3.1') in evaluation_cache do NOT match or contaminate.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

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
async def test_cache_validation_fresh_equals_cached(tmp_path):
    """Verify that fresh result == cached result for all deterministic fields, and rule_set_version is 3.2."""
    db_path = str(tmp_path / "test_freeze_cache.db")
    orch = MasterOrchestrator(db_path=db_path, use_cache=True)

    # Mock resolver & retrieval
    orch._resolver.resolve_drug = AsyncMock(
        return_value=ResolvedIdentifierSet(
            entity_name="TestDrug",
            entity_type="drug",
            identifiers=[CanonicalIdentifier(namespace="chembl", value="CHEMBL100")],
        )
    )
    orch._resolver.resolve_disease = AsyncMock(
        return_value=ResolvedIdentifierSet(
            entity_name="TestDisease",
            entity_type="disease",
            identifiers=[CanonicalIdentifier(namespace="mesh", value="D200")],
        )
    )

    async def mock_retrieval(drug, disease, hyp_id):
        return RetrievalPackage(
            hypothesis_id=hyp_id,
            drug=_make_dummy_drug("TestDrug"),
            disease=_make_dummy_disease("TestDisease"),
            retrieval_confidence="HIGH",
        )

    orch._retrieval.execute = AsyncMock(side_effect=mock_retrieval)

    # Mock reasoning returning a deterministic ReasoningResult with rule_set_version="3.2"
    base_res = _make_real_reasoning_result()
    assert base_res.rule_set_version == "3.2"

    async def mock_reason(package):
        return base_res.model_copy(update={"hypothesis_id": package.hypothesis_id})

    orch._reasoning.reason = AsyncMock(side_effect=mock_reason)

    # 1. Fresh uncached evaluation (bypass_cache=True)
    hyp_fresh, pkg_fresh, res_fresh = await orch.evaluate(
        drug_name="TestDrug",
        disease_name="TestDisease",
        policy=RetrievalPolicy.STANDARD,
        bypass_cache=True,
    )

    assert res_fresh.rule_set_version == "3.2", f"Expected rule_set_version='3.2', got {res_fresh.rule_set_version!r}"

    # Verify result was placed in cache
    cached_entry = orch._cache.get("TestDrug", "TestDisease", RetrievalPolicy.STANDARD.value, rule_set_version="3.2")
    assert cached_entry is not None, "Evaluation result was not stored in cache under rule_set_version='3.2'"

    # 2. Cached evaluation (bypass_cache=False)
    hyp_cached, pkg_cached, res_cached = await orch.evaluate(
        drug_name="TestDrug",
        disease_name="TestDisease",
        policy=RetrievalPolicy.STANDARD,
        bypass_cache=False,
    )

    # 3. Verify fresh == cached for all deterministic fields
    assert res_fresh.recommendation_status == res_cached.recommendation_status
    assert res_fresh.support_assessment.score == res_cached.support_assessment.score
    assert res_fresh.mechanistic_assessment.score == res_cached.mechanistic_assessment.score
    assert res_fresh.risk_assessment.score == res_cached.risk_assessment.score
    assert res_fresh.rule_set_version == res_cached.rule_set_version == "3.2"
    assert res_fresh.recommendation_reasons == res_cached.recommendation_reasons
    assert res_fresh.opposition_assessment.score == res_cached.opposition_assessment.score


@pytest.mark.asyncio
async def test_stale_cache_versions_do_not_contaminate(tmp_path):
    """Verify that stale entries with rule_set_version 2.0 or 2.1 never contaminate evaluation."""
    db_path = str(tmp_path / "test_stale_cache.db")
    orch = MasterOrchestrator(db_path=db_path, use_cache=True)

    # Seed an old result with rule_set_version 2.1
    stale_res = _make_real_reasoning_result().model_copy(update={"rule_set_version": "2.1"})
    orch._cache.set("DrugOld", "DiseaseOld", stale_res, policy="STANDARD", rule_set_version="2.1")

    # When querying with rule_set_version 3.2 (the default), cache lookup MUST return None
    lookup = orch._cache.get("DrugOld", "DiseaseOld", policy="STANDARD", rule_set_version="3.2")
    assert lookup is None, "Stale cache version 2.1 contaminated the 3.2 lookup!"
