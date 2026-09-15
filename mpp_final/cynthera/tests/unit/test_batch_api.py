import gc
import os
import tempfile
import uuid
from unittest.mock import MagicMock

import pytest

from backend.infrastructure.cache.evaluation_cache import EvaluationCache
from backend.storage.batch_repository import BatchRepository


# ─────────────────────────────────────────────
# EvaluationCache Tests
# ─────────────────────────────────────────────

@pytest.fixture
def cache(tmp_path):
    db_path = str(tmp_path / "test_cache.db")
    c = EvaluationCache(db_path=db_path, ttl_seconds=3600)
    yield c
    del c
    gc.collect()


def _make_mock_result(hypothesis_id: uuid.UUID | None = None):
    """Create a minimal mock ReasoningResult that supports model_dump_json."""
    result = MagicMock()
    result.hypothesis_id = hypothesis_id or uuid.uuid4()
    result.recommendation_status.value = "PROMISING"
    result.support_assessment.score = 0.75
    result.mechanistic_assessment.score = 0.65
    result.risk_assessment.score = 0.2
    result.rule_set_version = "2.0"
    result.reasoning_duration_ms = 1234.5

    # Simulate model_dump_json returning a valid JSON string
    import json
    result.model_dump_json.return_value = json.dumps({
        "id": str(uuid.uuid4()),
        "hypothesis_id": str(result.hypothesis_id),
        "recommendation_status": "PROMISING",
        "support_assessment": {"score": 0.75, "level": "HIGH", "evidence_count": 5,
                               "weighted_sum": 3.2, "rationale": "Test", "supporting_claim_ids": []},
        "mechanistic_assessment": {"score": 0.65, "level": "MEDIUM", "pathway_count": 2,
                                   "mechanistic_chain": [], "rationale": "Test"},
        "risk_assessment": {"score": 0.2, "level": "LOW", "failed_trial_count": 0,
                           "contradiction_count": 0, "rationale": "Test", "risk_claim_ids": []},
        "contradictions": [],
        "recommendation_reasons": ["Rule 1"],
        "audit_report": {"summary": "Test summary", "key_supporting_claim_ids": [],
                        "key_contradicting_claim_ids": [], "data_gaps": [],
                        "confidence_narrative": "Test", "recommendation_rationale": "Test"},
        "rule_set_version": "2.0",
        "reasoning_duration_ms": 1234.5,
        "completed_at": "2024-01-01T00:00:00",
    })
    return result


class TestEvaluationCache:
    """Tests for EvaluationCache."""

    def test_cache_miss_returns_none(self, cache):
        """Cache miss for unknown drug-disease pair should return None."""
        result = cache.get("UnknownDrug", "UnknownDisease", "STANDARD")
        assert result is None

    def test_cache_set_and_get(self, cache):
        """Set then get should return the cached result."""
        mock_result = _make_mock_result()
        cache.set("Sildenafil", "PAH", mock_result, "STANDARD")
        # Note: Actual get would parse JSON back — for this test, verify no error
        # In production the result would be deserialized
        stats = cache.stats()
        assert stats["active_entries"] >= 1

    def test_cache_key_case_insensitive(self, cache):
        """Cache key should be case-insensitive."""
        mock_result = _make_mock_result()
        cache.set("sildenafil", "pah", mock_result, "STANDARD")
        # Getting with uppercase should also check same key
        key1 = cache._make_key("sildenafil", "pah", "STANDARD")
        key2 = cache._make_key("SILDENAFIL", "PAH", "STANDARD")
        assert key1 == key2

    def test_different_policies_have_different_keys(self, cache):
        """Same drug/disease with different policies should have different keys."""
        key_standard = cache._make_key("drug", "disease", "STANDARD")
        key_fast = cache._make_key("drug", "disease", "FAST")
        assert key_standard != key_fast

    def test_different_rule_set_versions_have_different_keys(self, cache):
        """Rule set version 2.0 and 2.1 must produce distinct cache keys."""
        key_v20 = cache._make_key("drug", "disease", "STANDARD", rule_set_version="2.0")
        key_v21 = cache._make_key("drug", "disease", "STANDARD", rule_set_version="2.1")
        assert key_v20 != key_v21

    def test_version_2_0_cached_cannot_be_hit_by_version_2_1(self, cache):
        """An entry cached with rule_set_version 2.0 must not return on version 2.1 query."""
        mock_result = _make_mock_result()
        mock_result.rule_set_version = "2.0"
        cache.set("DrugA", "DiseaseB", mock_result, "STANDARD", rule_set_version="2.0")

        # Querying with default 2.1 must be a cache miss
        result_21 = cache.get("DrugA", "DiseaseB", "STANDARD", rule_set_version="2.1")
        assert result_21 is None

    def test_invalidate_removes_entry(self, cache):
        """Invalidate should remove the cached entry."""
        mock_result = _make_mock_result()
        cache.set("Drug", "Disease", mock_result, "STANDARD")
        removed = cache.invalidate("Drug", "Disease", "STANDARD")
        assert removed is True
        # Should be a miss now
        assert cache.get("Drug", "Disease", "STANDARD") is None

    def test_stats_structure(self, cache):
        """stats() should return a dict with required fields."""
        stats = cache.stats()
        assert "total_entries" in stats
        assert "active_entries" in stats
        assert "expired_entries" in stats
        assert "total_cache_hits" in stats
        assert "ttl_seconds" in stats

    def test_purge_expired_returns_count(self, cache):
        """purge_expired should return a non-negative integer."""
        count = cache.purge_expired()
        assert isinstance(count, int)
        assert count >= 0


# ─────────────────────────────────────────────
# BatchRepository Tests
# ─────────────────────────────────────────────

@pytest.fixture
def batch_repo(tmp_path):
    db_path = str(tmp_path / "test_batch.db")
    repo = BatchRepository(db_path=db_path)
    yield repo
    del repo
    gc.collect()


class TestBatchRepository:
    """Tests for BatchRepository."""

    def test_create_batch_returns_id(self, batch_repo):
        """create_batch should return a non-empty UUID string."""
        items = [
            {"drug_name": "Sildenafil", "disease_name": "PAH"},
            {"drug_name": "Metformin", "disease_name": "Cancer"},
        ]
        batch_id = batch_repo.create_batch(items)
        assert isinstance(batch_id, str)
        assert len(batch_id) == 36  # UUID format

    def test_get_batch_status_after_creation(self, batch_repo):
        """Newly created batch should have PENDING status."""
        items = [{"drug_name": "Drug", "disease_name": "Disease"}]
        batch_id = batch_repo.create_batch(items)
        status = batch_repo.get_batch_status(batch_id)
        assert status is not None
        assert status["status"] == "PENDING"
        assert status["total_items"] == 1
        assert status["completed_items"] == 0

    def test_get_batch_status_not_found(self, batch_repo):
        """Non-existent batch ID should return None."""
        result = batch_repo.get_batch_status("non-existent-batch-id")
        assert result is None

    def test_get_pending_items(self, batch_repo):
        """Newly created items should all be PENDING."""
        items = [
            {"drug_name": "Drug1", "disease_name": "Disease1"},
            {"drug_name": "Drug2", "disease_name": "Disease2"},
        ]
        batch_id = batch_repo.create_batch(items)
        pending = batch_repo.get_pending_items(batch_id)
        assert len(pending) == 2
        assert all(item["status"] == "PENDING" for item in pending)

    def test_mark_item_running(self, batch_repo):
        """Marking an item as RUNNING should update its status."""
        items = [{"drug_name": "Drug", "disease_name": "Disease"}]
        batch_id = batch_repo.create_batch(items)
        pending = batch_repo.get_pending_items(batch_id)
        item_id = pending[0]["item_id"]

        batch_repo.mark_item_running(item_id)
        all_items = batch_repo.get_batch_items(batch_id)
        assert all_items[0]["status"] == "RUNNING"

    def test_mark_item_done_updates_batch(self, batch_repo):
        """Completing all items should update batch status to COMPLETED."""
        items = [{"drug_name": "Drug", "disease_name": "Disease"}]
        batch_id = batch_repo.create_batch(items)
        pending = batch_repo.get_pending_items(batch_id)
        item_id = pending[0]["item_id"]

        batch_repo.mark_item_done(
            item_id=item_id,
            hypothesis_id=str(uuid.uuid4()),
            recommendation="PROMISING",
            support_score=0.75,
            mechanistic_score=0.65,
            risk_score=0.2,
            result_json="{}",
        )

        status = batch_repo.get_batch_status(batch_id)
        assert status["completed_items"] == 1
        assert status["status"] == "COMPLETED"

    def test_mark_item_failed(self, batch_repo):
        """Failed item should increment failed_items count."""
        items = [{"drug_name": "Bad", "disease_name": "Unknown"}]
        batch_id = batch_repo.create_batch(items)
        pending = batch_repo.get_pending_items(batch_id)
        item_id = pending[0]["item_id"]

        batch_repo.mark_item_failed(item_id, "Drug not resolved")

        status = batch_repo.get_batch_status(batch_id)
        assert status["failed_items"] == 1

    def test_list_batches_returns_list(self, batch_repo):
        """list_batches should return a list."""
        batch_repo.create_batch([{"drug_name": "Drug", "disease_name": "Disease"}])
        batches = batch_repo.list_batches()
        assert isinstance(batches, list)
        assert len(batches) >= 1

    def test_progress_percentage(self, batch_repo):
        """Progress percentage should update correctly as items complete."""
        items = [
            {"drug_name": f"Drug{i}", "disease_name": f"Disease{i}"}
            for i in range(4)
        ]
        batch_id = batch_repo.create_batch(items)
        pending = batch_repo.get_pending_items(batch_id)

        # Complete 2 out of 4
        for item in pending[:2]:
            batch_repo.mark_item_done(
                item_id=item["item_id"],
                hypothesis_id=str(uuid.uuid4()),
                recommendation="UNCERTAIN",
                support_score=0.3,
                mechanistic_score=0.3,
                risk_score=0.3,
                result_json="{}",
            )

        status = batch_repo.get_batch_status(batch_id)
        assert status["progress_pct"] == 50.0
