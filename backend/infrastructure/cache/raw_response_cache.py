"""RawResponseCache — SQLite-backed TTL cache for raw API responses.

Caches only successful HTTP responses (HTTP 200, parsed without exception).
Failures (4xx/5xx, timeouts, parse errors) are NEVER written to cache.
Empty-but-successful responses (e.g. {"mechanisms": []}) ARE cached —
they are valid data, distinct from a failed request.

Cache keys are derived from resolved identifiers and exact API parameters
sent, NOT from raw user input strings, so a pre-fix wrong ID resolution
and a post-fix correct resolution produce different cache entries.

Key format: SHA-256("{source_name}:{resolved_id}:{endpoint}:{params_hash}")
where params_hash = SHA-256(json.dumps(params, sort_keys=True)).

Cache is stored in the existing data/cynthera.db SQLite file (same file as
EvaluationCache and StorageRepository — no new dependencies).

Reference: Implementation plan Part 6 — Cache Layer Design Decision
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DDL_RAW_CACHE = """
CREATE TABLE IF NOT EXISTS raw_response_cache (
    cache_key      TEXT PRIMARY KEY,
    source_name    TEXT NOT NULL,
    resolved_id    TEXT NOT NULL,
    endpoint       TEXT NOT NULL,
    response_json  TEXT NOT NULL,
    created_at     REAL NOT NULL,
    expires_at     REAL NOT NULL,
    hit_count      INTEGER NOT NULL DEFAULT 0
);
"""

_DDL_RAW_CACHE_IDX = """
CREATE INDEX IF NOT EXISTS idx_raw_cache_source
    ON raw_response_cache(source_name, resolved_id);
"""

# TTL constants (seconds) — per data category
TTL_STRUCTURAL = 30 * 86400       # 30 days: ChEMBL, UniProt, Reactome
TTL_ASSOCIATIONS = 14 * 86400     # 14 days: Open Targets, DisGeNET
TTL_LITERATURE = 7 * 86400        # 7 days: PubMed, OpenAlex, S2, Europe PMC
TTL_CLINICAL_TRIALS = 1 * 86400   # 1 day: ClinicalTrials.gov


class RawResponseCache:
    """SQLite-backed TTL cache for raw API response payloads.

    Stores raw JSON-serialisable data returned by external API connectors.
    Only successful responses are stored — see module docstring for the
    success/failure distinction contract.

    Cache observability: hits and misses are logged at INFO level (not DEBUG)
    so they are visible in terminal output during active debugging without
    requiring a log-level change.

    Args:
        db_path: Path to the SQLite database (shared with EvaluationCache
                 and StorageRepository).
    """

    def __init__(self, db_path: str = "data/cynthera.db") -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(_DDL_RAW_CACHE)
            try:
                conn.execute(_DDL_RAW_CACHE_IDX)
            except sqlite3.OperationalError:
                pass
            conn.commit()

    @staticmethod
    def make_key(
        source_name: str,
        resolved_id: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Compute a deterministic cache key.

        Args:
            source_name: Connector name (e.g. "chembl_activity").
            resolved_id: The resolved API identifier used in the request
                         (e.g. "CHEMBL468", not the raw user string "Thalidomide").
            endpoint: API endpoint suffix (e.g. "activity.json", "allForms").
            params: Query parameters actually sent (for variable-param endpoints).

        Returns:
            SHA-256 hex digest string.
        """
        params_hash = ""
        if params:
            params_hash = ":" + hashlib.sha256(
                json.dumps(params, sort_keys=True).encode()
            ).hexdigest()[:16]
        raw = f"{source_name}:{resolved_id}:{endpoint}{params_hash}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, cache_key: str, source_name: str = "") -> Any | None:
        """Retrieve a cached response payload.

        Args:
            cache_key: Key produced by make_key().
            source_name: Used for log messages only.

        Returns:
            Deserialized JSON payload, or None on cache miss / expiry.
        """
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT response_json, expires_at FROM raw_response_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()

        if row is None:
            logger.info(
                "%s_cache_miss",
                source_name or "raw",
                extra={"cache_key": cache_key[:16]},
            )
            return None

        if row["expires_at"] < now:
            self._delete(cache_key)
            logger.info(
                "%s_cache_expired",
                source_name or "raw",
                extra={"cache_key": cache_key[:16]},
            )
            return None

        # Increment hit count
        with self._connect() as conn:
            conn.execute(
                "UPDATE raw_response_cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
                (cache_key,),
            )
            conn.commit()

        logger.info(
            "%s_cache_hit",
            source_name or "raw",
            extra={"cache_key": cache_key[:16]},
        )

        try:
            return json.loads(row["response_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "raw_cache_parse_error",
                extra={"cache_key": cache_key[:16], "error": str(exc)},
            )
            self._delete(cache_key)
            return None

    def set(
        self,
        cache_key: str,
        source_name: str,
        resolved_id: str,
        endpoint: str,
        value: Any,
        ttl_seconds: int = TTL_STRUCTURAL,
    ) -> None:
        """Store a successful API response in cache.

        ONLY call this after a confirmed successful HTTP 200 response that
        parsed without exception. Do NOT call after 4xx/5xx, timeout, or
        parse failure.

        Args:
            cache_key: Key from make_key().
            source_name: Connector name for index/logging.
            resolved_id: Resolved API identifier (for the index column).
            endpoint: API endpoint suffix (for the index column).
            value: JSON-serialisable response payload to cache.
            ttl_seconds: Time-to-live in seconds.
        """
        now = time.time()
        expires_at = now + ttl_seconds
        try:
            response_json = json.dumps(value, default=str)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "raw_cache_serialize_error",
                extra={"source": source_name, "error": str(exc)},
            )
            return

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO raw_response_cache
                    (cache_key, source_name, resolved_id, endpoint,
                     response_json, created_at, expires_at, hit_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(cache_key) DO UPDATE SET
                    response_json = excluded.response_json,
                    created_at    = excluded.created_at,
                    expires_at    = excluded.expires_at,
                    hit_count     = 0
                """,
                (cache_key, source_name, resolved_id, endpoint,
                 response_json, now, expires_at),
            )
            conn.commit()

        logger.debug(
            "raw_cache_set",
            extra={"source": source_name, "resolved_id": resolved_id, "ttl": ttl_seconds},
        )

    def _delete(self, cache_key: str) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM raw_response_cache WHERE cache_key = ?", (cache_key,)
            )
            conn.commit()
        return result.rowcount > 0

    def purge_expired(self) -> int:
        """Remove all expired cache entries. Returns count removed."""
        now = time.time()
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM raw_response_cache WHERE expires_at < ?", (now,)
            )
            conn.commit()
        removed = result.rowcount
        if removed > 0:
            logger.info("raw_cache_purge", extra={"removed": removed})
        return removed

    def stats(self) -> dict[str, Any]:
        """Return cache statistics for the pipeline summary log line."""
        now = time.time()
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS cnt FROM raw_response_cache"
            ).fetchone()["cnt"]
            active = conn.execute(
                "SELECT COUNT(*) AS cnt FROM raw_response_cache WHERE expires_at >= ?",
                (now,),
            ).fetchone()["cnt"]
            hits = conn.execute(
                "SELECT SUM(hit_count) AS h FROM raw_response_cache"
            ).fetchone()["h"] or 0
            by_source = conn.execute(
                """
                SELECT source_name,
                       COUNT(*) AS entries,
                       SUM(hit_count) AS total_hits
                FROM raw_response_cache
                GROUP BY source_name
                ORDER BY total_hits DESC
                """
            ).fetchall()

        return {
            "total_entries": total,
            "active_entries": active,
            "expired_entries": total - active,
            "total_cache_hits": hits,
            "by_source": [
                {"source": r["source_name"], "entries": r["entries"], "hits": r["total_hits"]}
                for r in by_source
            ],
        }
