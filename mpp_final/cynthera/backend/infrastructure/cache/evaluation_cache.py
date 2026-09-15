"""EvaluationCache — SQLite-backed TTL cache for ReasoningResult.

Phase 3 Production Feature: avoids re-running identical evaluations by
caching results keyed on (drug_name, disease_name, retrieval_policy) with
a configurable TTL (default 24 hours).

Reference: Phase 3 — Result caching
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from backend.core.domain.reasoning_result import ReasoningResult

logger = logging.getLogger(__name__)

# Default TTL: 24 hours in seconds
_DEFAULT_TTL_SECONDS: int = 86400

_DDL_CACHE = """
CREATE TABLE IF NOT EXISTS evaluation_cache (
    cache_key TEXT PRIMARY KEY,
    drug_name TEXT NOT NULL,
    disease_name TEXT NOT NULL,
    retrieval_policy TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0
);
"""

_DDL_CACHE_IDX = """
CREATE INDEX IF NOT EXISTS idx_cache_drug_disease
    ON evaluation_cache(drug_name, disease_name);
"""


class EvaluationCache:
    """SQLite-backed TTL cache for ReasoningResult objects.

    Cache key is computed as SHA-256(drug_name:disease_name:policy).
    Expired entries are lazily removed on each get() call.

    Args:
        db_path: Path to the SQLite database (shared with StorageRepository).
        ttl_seconds: Time-to-live in seconds (default 86400 = 24 hours).
    """

    def __init__(
        self,
        db_path: str = "data/cynthera.db",
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self._db_path = db_path
        self._ttl = ttl_seconds
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(_DDL_CACHE)
            try:
                conn.execute(_DDL_CACHE_IDX)
            except sqlite3.OperationalError:
                pass
            conn.commit()

    # ClinicalTrials.gov Safe Fix: disease relation, placebo matching, background subtraction, whyStopped negation
    _CACHE_VERSION: str = "v7.9_clinicaltrials_safe_fix"
    _DEFAULT_RULE_SET_VERSION: str = "3.2"

    @classmethod
    def _make_key(
        cls,
        drug_name: str,
        disease_name: str,
        policy: str = "STANDARD",
        rule_set_version: str = "3.2",
    ) -> str:
        """Compute deterministic structured cache key including version namespace and rule_set_version."""
        identity = {
            "version_namespace": cls._CACHE_VERSION,
            "drug": drug_name.lower().strip(),
            "disease": disease_name.lower().strip(),
            "policy": policy.upper().strip(),
            "rule_set_version": str(rule_set_version).strip(),
        }
        encoded = json.dumps(identity, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def get(
        self,
        drug_name: str,
        disease_name: str,
        policy: str = "STANDARD",
        rule_set_version: str = "3.2",
    ) -> ReasoningResult | None:
        """Retrieve a cached ReasoningResult.

        Args:
            drug_name: Drug name used in the original evaluation.
            disease_name: Disease name used in the original evaluation.
            policy: Retrieval policy string.
            rule_set_version: Rule engine version (must match cached result).

        Returns:
            ReasoningResult if cached and not expired, else None.
        """
        key = self._make_key(drug_name, disease_name, policy, rule_set_version)
        now = time.time()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT result_json, expires_at, hit_count FROM evaluation_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()

        if row is None:
            logger.debug(
                "cache_miss",
                extra={
                    "drug": drug_name,
                    "disease": disease_name,
                    "rule_set_version": rule_set_version,
                },
            )
            return None

        if row["expires_at"] < now:
            self._delete(key)
            logger.info("cache_expired", extra={"drug": drug_name, "disease": disease_name})
            return None

        try:
            result = ReasoningResult.model_validate_json(row["result_json"])
            if result.rule_set_version != rule_set_version:
                logger.info(
                    "cache_rule_set_version_mismatch",
                    extra={
                        "cached_version": result.rule_set_version,
                        "expected_version": rule_set_version,
                    },
                )
                self._delete(key)
                return None
        except Exception as exc:
            logger.warning("cache_parse_error", extra={"error": str(exc)})
            self._delete(key)
            return None

        # Update hit count
        with self._connect() as conn:
            conn.execute(
                "UPDATE evaluation_cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
                (key,),
            )
            conn.commit()

        logger.info(
            "cache_hit",
            extra={
                "drug": drug_name,
                "disease": disease_name,
                "hit_count": row["hit_count"] + 1,
                "rule_set_version": rule_set_version,
            },
        )
        return result

    def set(
        self,
        drug_name: str,
        disease_name: str,
        result: ReasoningResult,
        policy: str = "STANDARD",
        rule_set_version: str | None = None,
    ) -> None:
        """Store a ReasoningResult in the cache.

        Args:
            drug_name: Drug name.
            disease_name: Disease name.
            result: The ReasoningResult to cache.
            policy: Retrieval policy string.
            rule_set_version: Rule engine version string (defaults to result.rule_set_version).
        """
        r_ver = rule_set_version or getattr(result, "rule_set_version", self._DEFAULT_RULE_SET_VERSION)
        key = self._make_key(drug_name, disease_name, policy, r_ver)
        now = time.time()
        expires_at = now + self._ttl
        result_json = result.model_dump_json()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO evaluation_cache
                    (cache_key, drug_name, disease_name, retrieval_policy,
                     result_json, created_at, expires_at, hit_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(cache_key) DO UPDATE SET
                    result_json  = excluded.result_json,
                    created_at   = excluded.created_at,
                    expires_at   = excluded.expires_at,
                    hit_count    = 0
                """,
                (
                    key,
                    drug_name.lower().strip(),
                    disease_name.lower().strip(),
                    policy.upper(),
                    result_json,
                    now,
                    expires_at,
                ),
            )
            conn.commit()

        logger.info(
            "cache_set",
            extra={
                "drug": drug_name,
                "disease": disease_name,
                "rule_set_version": r_ver,
                "ttl_seconds": self._ttl,
            },
        )

    def invalidate(
        self,
        drug_name: str,
        disease_name: str,
        policy: str = "STANDARD",
        rule_set_version: str | None = None,
    ) -> bool:
        """Invalidate a specific cache entry (or all versions for this drug/disease/policy).

        Returns:
            True if an entry was removed.
        """
        if rule_set_version is not None:
            key = self._make_key(drug_name, disease_name, policy, rule_set_version)
            return self._delete(key)

        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM evaluation_cache WHERE drug_name = ? AND disease_name = ? AND retrieval_policy = ?",
                (drug_name.lower().strip(), disease_name.lower().strip(), policy.upper().strip()),
            )
            conn.commit()
        return result.rowcount > 0

    def _delete(self, key: str) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM evaluation_cache WHERE cache_key = ?", (key,)
            )
            conn.commit()
        return result.rowcount > 0

    def purge_expired(self) -> int:
        """Remove all expired cache entries.

        Returns:
            Number of entries removed.
        """
        now = time.time()
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM evaluation_cache WHERE expires_at < ?", (now,)
            )
            conn.commit()
        removed = result.rowcount
        if removed > 0:
            logger.info("cache_purge", extra={"removed": removed})
        return removed

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        now = time.time()
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM evaluation_cache"
            ).fetchone()["cnt"]
            active = conn.execute(
                "SELECT COUNT(*) as cnt FROM evaluation_cache WHERE expires_at >= ?",
                (now,),
            ).fetchone()["cnt"]
            hits = conn.execute(
                "SELECT SUM(hit_count) as total_hits FROM evaluation_cache"
            ).fetchone()["total_hits"] or 0

        return {
            "total_entries": total,
            "active_entries": active,
            "expired_entries": total - active,
            "total_cache_hits": hits,
            "ttl_seconds": self._ttl,
        }
