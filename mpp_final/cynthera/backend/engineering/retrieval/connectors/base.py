"""BaseConnector — abstract base class for all source connectors.

Reference: 08_IMPLEMENTATION_GUIDE.md §5.5, 03_RETRIEVAL_SPECIFICATION.md
"""
from __future__ import annotations

import abc
import asyncio
import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from backend.core.utils.api_keys import sanitize_api_key

logger = logging.getLogger(__name__)

_MAX_429_RETRIES = 4


class BaseConnector(abc.ABC):
    """Abstract base class that all Source connectors must extend.

    Enforces:
    - Async HTTP calls via httpx
    - Retry logic via tenacity (configured in subclass)
    - Structured error handling: httpx errors re-raised as domain exceptions
    - No normalization or reasoning in this layer

    Subclasses must implement:
        - source_name (class attribute)
        - base_url (class attribute)
        - fetch() method
    """

    source_name: str = "base"
    base_url: str = ""
    timeout_seconds: float = 30.0

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the connector with an optional API key.

        Args:
            api_key: Optional API key for authenticated endpoints.
        """
        self._api_key = sanitize_api_key(api_key)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BaseConnector":
        """Open the async HTTP client context."""
        self._client = httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers=self._build_headers(),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Close the async HTTP client context."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _build_headers(self) -> dict[str, str]:
        """Build default request headers. Override in subclass for auth headers."""
        headers = {"Accept": "application/json", "User-Agent": "CYNTHERA/1.0"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    @abc.abstractmethod
    async def fetch(self, **kwargs: Any) -> dict[str, Any]:
        """Fetch raw data from the source API.

        Args:
            **kwargs: Source-specific query parameters.

        Returns:
            Raw JSON payload as a Python dict.

        Raises:
            SourceUnavailableError: If all retries are exhausted.
        """
        raise NotImplementedError

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def _get_with_retry(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GET request with tenacity retry logic.

        Retries up to 3 times with exponential backoff (1s, 2s, 4s)
        for RequestError and HTTPStatusError.

        Args:
            url: Full URL to request.
            params: Optional query parameters.

        Returns:
            Parsed JSON response as dict.
        """
        last_response: httpx.Response | None = None
        for attempt in range(_MAX_429_RETRIES):
            response = await self._client.get(url, params=params)
            if response.status_code == 429:
                if self.source_name == "semantic_scholar":
                    response.raise_for_status()
                delay = float(response.headers.get("retry-after", 2.0 + attempt * 2))
                logger.info(
                    "rate_limited_backoff",
                    extra={
                        "source": self.source_name,
                        "attempt": attempt + 1,
                        "delay_seconds": delay,
                    },
                )
                await asyncio.sleep(delay)
                last_response = response
                continue
            response.raise_for_status()
            return response.json()
        if last_response is not None:
            last_response.raise_for_status()
        response.raise_for_status()
        return response.json()

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GET request with retry and return parsed JSON.

        Args:
            url: Full URL to request.
            params: Optional query parameters.

        Returns:
            Parsed JSON response as dict.

        Raises:
            SourceUnavailableError: If the request fails after retries.
        """
        from backend.core.exceptions import SourceUnavailableError

        if not self._client:
            raise RuntimeError(
                f"{self.__class__.__name__} must be used as an async context manager."
            )
        try:
            return await self._get_with_retry(url, params)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                f"http_error: source={self.source_name} url={url} status={exc.response.status_code}",
                extra={
                    "source": self.source_name,
                    "url": url,
                    "status_code": exc.response.status_code,
                },
            )
            raise SourceUnavailableError(
                source_name=self.source_name,
                retry_count=3,
            ) from exc
        except httpx.RequestError as exc:
            logger.error(
                f"request_error: source={self.source_name} url={url} error={exc}",
                extra={"source": self.source_name, "url": url, "error": str(exc)},
            )
            raise SourceUnavailableError(
                source_name=self.source_name,
                retry_count=3,
            ) from exc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def _post_with_retry(
        self, url: str, json_body: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a POST request with JSON body and tenacity retry logic.

        Identical retry configuration to _get_with_retry (3 attempts,
        exponential backoff 1s→2s→4s).

        Args:
            url: Full URL to POST to.
            json_body: JSON-serialisable request body dict.

        Returns:
            Parsed JSON response as dict.
        """
        response = await self._client.post(url, json=json_body)
        response.raise_for_status()
        return response.json()

    async def _post(
        self, url: str, json_body: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a POST request with retry and return parsed JSON.

        Used by connectors that require POST (e.g. GraphQL endpoints).
        Follows the identical error-handling pattern as _get().

        Args:
            url: Full URL to POST to.
            json_body: JSON-serialisable request body dict.

        Returns:
            Parsed JSON response as dict.

        Raises:
            SourceUnavailableError: If the request fails after retries.
        """
        from backend.core.exceptions import SourceUnavailableError

        if not self._client:
            raise RuntimeError(
                f"{self.__class__.__name__} must be used as an async context manager."
            )
        try:
            return await self._post_with_retry(url, json_body)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                f"http_error: source={self.source_name} url={url} status={exc.response.status_code}",
                extra={
                    "source": self.source_name,
                    "url": url,
                    "status_code": exc.response.status_code,
                },
            )
            raise SourceUnavailableError(
                source_name=self.source_name,
                retry_count=3,
            ) from exc
        except httpx.RequestError as exc:
            logger.error(
                f"request_error: source={self.source_name} url={url} error={exc}",
                extra={"source": self.source_name, "url": url, "error": str(exc)},
            )
            raise SourceUnavailableError(
                source_name=self.source_name,
                retry_count=3,
            ) from exc

