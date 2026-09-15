"""Semantic Scholar Connector — queries the Semantic Scholar Graph API.

Semantic Scholar provides AI-curated research context, citation velocity,
and influential citation detection. Free API with no key required.

API: https://api.semanticscholar.org/graph/v1
Reference: 03_RETRIEVAL_SPECIFICATION.md, Phase 2 literature scan expansion
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any

import httpx

from backend.core.domain.evidence import Evidence
from backend.core.enums.evidence_type import EvidenceType, ERW_BASE_WEIGHTS
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

_S2_BASE = "https://api.semanticscholar.org/graph/v1"
_DEFAULT_TIMEOUT = 20.0
_MAX_RESULTS = 12


class SemanticScholarConnector(BaseConnector):
    """Connector for the Semantic Scholar Graph API.

    Fetches literature evidence enriched with:
    - Influential citation count (highly cited, high-quality papers)
    - Fields of study (to validate relevance)
    - Open access PDF availability

    Authenticated using x-api-key header.
    Rate-limited to strictly below 1 req/sec to avoid API rejection.
    """

    source_name = "semantic_scholar"
    base_url = _S2_BASE
    timeout_seconds = _DEFAULT_TIMEOUT

    # Class-level rate limiter lock and timestamp to enforce <= 1 req/s threshold globally
    _rate_limit_lock = asyncio.Lock()
    _last_request_time: float = 0.0
    _min_request_interval: float = 1.05  # 1.05s interval stays safely under 1 req/s limit

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the Semantic Scholar connector.

        Args:
            api_key: Optional Semantic Scholar API key for higher rate limits.
        """
        import os
        from backend.core.utils.api_keys import sanitize_api_key
        key = sanitize_api_key(api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY"))
        super().__init__(api_key=key)

    def _build_headers(self) -> dict[str, str]:
        """Build default request headers override to set x-api-key if valid key is provided."""
        headers = {"Accept": "application/json", "User-Agent": "CYNTHERA/1.0"}
        if self._api_key and not self._api_key.startswith("your-") and self._api_key.strip() != "":
            headers["x-api-key"] = self._api_key
        return headers

    async def _rate_limit(self) -> None:
        """Enforce strict rate limit (< 1 req/sec) to avoid overloading S2 API."""
        import asyncio
        import time
        async with SemanticScholarConnector._rate_limit_lock:
            now = time.monotonic()
            elapsed = now - SemanticScholarConnector._last_request_time
            if elapsed < SemanticScholarConnector._min_request_interval:
                wait_time = SemanticScholarConnector._min_request_interval - elapsed
                logger.debug(
                    "semantic_scholar_rate_limiting",
                    extra={"wait_seconds": round(wait_time, 3)},
                )
                await asyncio.sleep(wait_time)
            SemanticScholarConnector._last_request_time = time.monotonic()

    _circuit_open_until: float = 0.0

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GET request with rate-limiting delay and circuit breaker."""
        import time
        from backend.core.exceptions import SourceUnavailableError
        now = time.monotonic()
        if now < SemanticScholarConnector._circuit_open_until:
            raise SourceUnavailableError("semantic_scholar rate-limited (circuit breaker open)")
        await self._rate_limit()
        try:
            return await super()._get(url, params=params)
        except Exception as exc:
            if "429" in str(exc):
                SemanticScholarConnector._circuit_open_until = time.monotonic() + 300.0
            raise

    async def fetch(self, **kwargs: Any) -> dict[str, Any]:
        """Fetch raw data from the Semantic Scholar API.

        Satisfies the ``BaseConnector`` abstract contract. Delegates to the
        ``/paper/search`` endpoint using ``query`` and optional ``limit``
        kwargs.

        Args:
            **kwargs: Accepts ``query`` (str) and ``limit`` (int).

        Returns:
            Raw JSON payload as returned by the Semantic Scholar API.
        """
        params: dict[str, Any] = {
            "query": kwargs.get("query", ""),
            "fields": (
                "paperId,title,abstract,year,citationCount,"
                "influentialCitationCount,fieldsOfStudy,isOpenAccess,externalIds"
            ),
            "limit": min(int(kwargs.get("limit", _MAX_RESULTS)), 20),
        }
        url = f"{self.base_url}/paper/search"
        return await self._get(url, params=params)

    async def fetch_literature(
        self,
        drug_name: str,
        disease_name: str,
        hypothesis_id: uuid.UUID,
        max_results: int = _MAX_RESULTS,
    ) -> list[Evidence]:
        """Fetch literature evidence from Semantic Scholar.

        Args:
            drug_name: Drug name to search.
            disease_name: Disease name to search.
            hypothesis_id: UUID of the owning hypothesis.
            max_results: Maximum number of results.

        Returns:
            List of Evidence records.
        """
        from backend.core.exceptions import SourceUnavailableError

        query = f"{drug_name} {disease_name}"
        params: dict[str, Any] = {
            "query": query,
            "fields": (
                "paperId,title,abstract,year,citationCount,"
                "influentialCitationCount,fieldsOfStudy,isOpenAccess,externalIds"
            ),
            "limit": min(max_results, 20),
        }
        url = f"{self.base_url}/paper/search"

        try:
            data = await self._get(url, params=params)
        except SourceUnavailableError:
            logger.warning(
                "semantic_scholar_unavailable",
                extra={"drug": drug_name, "disease": disease_name},
            )
            raise
        except Exception as exc:
            logger.warning(
                "semantic_scholar_fetch_error",
                extra={"drug": drug_name, "disease": disease_name, "error": str(exc)},
            )
            raise SourceUnavailableError(
                source_name=self.source_name,
                retry_count=3,
            ) from exc

        papers = data.get("data") or []
        evidence_records: list[Evidence] = []

        for paper in papers[:max_results]:
            ev = self._parse_paper(paper, drug_name, disease_name, hypothesis_id)
            if ev is not None:
                evidence_records.append(ev)

        logger.info(
            "semantic_scholar_fetch_complete",
            extra={
                "drug": drug_name,
                "disease": disease_name,
                "records_returned": len(evidence_records),
            },
        )
        return evidence_records

    def _parse_paper(
        self,
        paper: dict[str, Any],
        drug_name: str,
        disease_name: str,
        hypothesis_id: uuid.UUID,
    ) -> Evidence | None:
        """Parse a Semantic Scholar paper into an Evidence object."""
        try:
            title = paper.get("title") or "Untitled"
            abstract = paper.get("abstract") or ""
            pub_year = paper.get("year") or 2000
            citation_count = paper.get("citationCount") or 0
            influential_count = paper.get("influentialCitationCount") or 0
            paper_id = paper.get("paperId") or ""

            # Extract DOI if available
            external_ids = paper.get("externalIds") or {}
            doi = external_ids.get("DOI") or external_ids.get("doi") or ""

            # citation_key is required (min_length=1) — prefer DOI, fall back to S2 paperId
            if doi:
                citation_key = f"doi:{doi}"
            elif paper_id:
                citation_key = f"s2:{paper_id}"
            else:
                return None  # no usable identifier at all — drop the record

            provenance = ProvenanceReference(
                source_name="semantic_scholar",
                source_version="graph/v1",
                record_id=paper_id or citation_key,
                url=f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else None,
                retrieved_at=datetime.utcnow(),
            )

            erw = ERW.from_base(base_weight=ERW_BASE_WEIGHTS["LITERATURE"])

            return Evidence(
                evidence_type=EvidenceType.LITERATURE,
                erw=erw,
                citation_key=citation_key,
                title=title[:500],
                abstract=abstract[:2000] if abstract else None,
                provenance=provenance,
            )

        except Exception as exc:
            logger.debug("semantic_scholar_parse_error", extra={"error": str(exc)})
            return None

    def _compute_erw(
        self,
        citation_count: int,
        influential_count: int,
        pub_year: int,
    ) -> float:
        """Compute ERW with influential citation boost.

        Influential citations (papers that heavily cited this work) signal
        high scientific impact and receive an additional boost.
        """
        import math

        citation_score = 1.0 - math.exp(-0.008 * citation_count)
        influential_boost = min(0.2, influential_count * 0.02)
        age = max(0, datetime.utcnow().year - pub_year)
        recency_score = math.exp(-0.04 * age)

        erw = 0.5 * citation_score + influential_boost + 0.3 * recency_score
        return round(min(1.0, max(0.05, erw)), 4)
