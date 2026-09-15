"""ClaimExtractionAgent — LLM-assisted extraction of structured claims from literature.

Reference: 04_REASONING_SPECIFICATION.md, 05_AGENT_SPECIFICATIONS.md
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any

from backend.core.domain.claim import Claim
from backend.core.domain.evidence import Evidence
from backend.core.enums.predicate_type import PredicateType
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.exceptions import LLMResponseParsingError
from backend.core.utils.api_keys import (
    is_valid_edenai_key,
    is_valid_gemini_key,
    is_valid_groq_key,
    is_valid_openrouter_key,
    sanitize_api_key,
)

from backend.infrastructure.cache.raw_response_cache import RawResponseCache, TTL_LITERATURE

logger = logging.getLogger(__name__)

# Versioned extraction prompt
EXTRACTION_PROMPT_V1 = """You are a biomedical claim extraction system. Extract all biological relationship claims from the following text.

For each claim, extract:
1. subject: The entity performing the action (drug name, gene symbol, protein name)
2. predicate: One of: ACTIVATES, INHIBITS, BINDS, UPREGULATES, DOWNREGULATES, CAUSES, PREVENTS, ASSOCIATED_WITH, NO_EFFECT
3. object: The entity receiving the action (target, pathway, disease)
4. confidence: Float 0.0–1.0 indicating extraction confidence

Return ONLY a valid JSON array of objects with keys: subject, predicate, object, confidence.
Return empty array [] if no clear biological claims are present.

TEXT:
{text}

JSON OUTPUT:"""


class ClaimExtractionAgent:
    """LLM-assisted agent that extracts structured subject-predicate-object claims from text.

    IMPORTANT: This is the ONLY component allowed to call the LLM.
    All other components must be deterministic.

    Attributes:
        _model: LLM model name.
        _api_key: LLM API key from environment.
        _prompt_version: Version string of the extraction prompt used.
        _last_extraction_method: Tracks whether the last call used LLM or rule-based fallback.
            Set per call to 'llm' or 'rule_based_fallback'. Used for audit disclosure.
    """

    PROMPT_VERSION = "v1"

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        api_key: str | None = None,
        db_path: str = "data/cynthera.db",
    ) -> None:
        """Initialize the ClaimExtractionAgent.

        Args:
            model: LLM model identifier.
            api_key: LLM API key (falls back to GROQ_API_KEY / LLM_API_KEY / GEMINI_API_KEY environment variable).
            db_path: Path to SQLite database file for claim caching.
        """
        self._model = model
        resolved = (
            sanitize_api_key(api_key)
            or sanitize_api_key(os.environ.get("GROQ_API_KEY"))
            or sanitize_api_key(os.environ.get("LLM_API_KEY"))
            or sanitize_api_key(os.environ.get("GEMINI_API_KEY"))
        )
        self._api_key = resolved
        self._prompt_version = self.PROMPT_VERSION
        self._last_extraction_method: str = "llm"
        self._has_logged_unconfigured_warning: bool = False
        self._raw_cache = RawResponseCache(db_path=db_path) if db_path else None
        self._sem = asyncio.Semaphore(3)  # Bound concurrent LLM calls to 3 to prevent TPM/RPM bursts

    async def extract_claims(
        self,
        evidence: Evidence,
        drug_name: str,
        disease_name: str,
    ) -> list[Claim]:
        """Extract structured claims from a single Evidence record.

        Args:
            evidence: The Evidence record containing abstract text.
            drug_name: Drug name for context (used in claim matching).
            disease_name: Disease name for context (used in claim matching).

        Returns:
            List of Claim entities extracted from the evidence record.
        """
        if not evidence.abstract:
            logger.info("evidence_abstract_missing", extra={"evidence_id": str(evidence.id)})
            return []

        # Check raw cache for previously extracted claims
        import hashlib
        abstract_hash = hashlib.sha256(evidence.abstract.encode()).hexdigest()[:16]
        cache_key = ""
        if self._raw_cache:
            cache_key = RawResponseCache.make_key(
                "llm_claims",
                evidence.citation_key or abstract_hash,
                "extract_v1",
                {"drug": drug_name.lower().strip(), "disease": disease_name.lower().strip()},
            )
            cached = self._raw_cache.get(cache_key, source_name="llm_claims")
            if cached is not None and isinstance(cached, dict):
                method = cached.get("method", "llm")
                raw_claims = cached.get("claims", [])
                self._last_extraction_method = method
                claims: list[Claim] = []
                for raw in raw_claims:
                    try:
                        claim = self._parse_raw_claim(raw, evidence, extraction_method=method)
                        claims.append(claim)
                    except Exception:
                        continue
                return claims

        raw_claims = await self._call_llm(evidence.abstract, drug_name, disease_name)

        # Store extraction in raw cache for instant 0ms response on future calls
        if self._raw_cache and cache_key and raw_claims:
            self._raw_cache.set(
                cache_key,
                "llm_claims",
                evidence.citation_key or abstract_hash,
                "extract_v1",
                {"claims": raw_claims, "method": self._last_extraction_method},
                TTL_LITERATURE,
            )

        claims: list[Claim] = []
        for raw in raw_claims:
            try:
                claim = self._parse_raw_claim(
                    raw,
                    evidence,
                    extraction_method=self._last_extraction_method,
                )
                claims.append(claim)
            except Exception as exc:
                logger.debug("claim_parse_error", extra={"error": str(exc), "raw": raw})
                continue

        return claims

    async def _call_llm(self, text: str, drug_name: str = "drug", disease_name: str = "disease") -> list[dict[str, Any]]:
        """Call the LLM API and parse the response.

        Provider cascade (in order):
          1. Groq — primary. Tries configured model then free-tier cascade.
          2. OpenRouter — first fallback when Groq is quota-exhausted.
          3. EdenAI — second fallback.
          4. Rule-based keyword matching — last resort, low-quality.

        Args:
            text: Abstract text to extract claims from.
            drug_name: Drug name for context-aware extraction.
            disease_name: Disease name for context-aware extraction.

        Returns:
            List of raw claim dicts.
        """
        async with self._sem:
            groq_key = (
                self._api_key
                if is_valid_groq_key(self._api_key)
                else sanitize_api_key(os.environ.get("GROQ_API_KEY"))
            )
            gemini_key = (
                self._api_key
                if is_valid_gemini_key(self._api_key)
                else sanitize_api_key(os.environ.get("GEMINI_API_KEY"))
                or (
                    sanitize_api_key(os.environ.get("LLM_API_KEY"))
                    if is_valid_gemini_key(os.environ.get("LLM_API_KEY"))
                    else None
                )
            )
            openrouter_key = sanitize_api_key(os.environ.get("OPENROUTER_API_KEY", ""))
            edenai_key = sanitize_api_key(os.environ.get("EDENAI_API_KEY", ""))

            has_valid_groq = is_valid_groq_key(groq_key)
            has_valid_gemini = is_valid_gemini_key(gemini_key)
            has_valid_openrouter = is_valid_openrouter_key(openrouter_key)
            has_valid_edenai = is_valid_edenai_key(edenai_key)

            if has_valid_groq:
                prompt = EXTRACTION_PROMPT_V1.format(text=text[:3000])
                # Honour the configured model; fall through free-tier Groq models on quota errors.
                configured_model = os.environ.get("LLM_MODEL", self._model)
                groq_model_cascade = [
                    configured_model,
                    "qwen/qwen3.8-27b",
                    "groq/compound-mini",
                    "allam-2-7b",
                ]
                seen_m: set[str] = set()
                groq_models_to_try: list[str] = []
                for m in groq_model_cascade:
                    if m and m not in seen_m:
                        seen_m.add(m)
                        groq_models_to_try.append(m)

                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                }
                groq_quota_exhausted = False
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        for model_name in groq_models_to_try:
                            body = {
                                "model": model_name,
                                "messages": [{"role": "user", "content": prompt}],
                                "temperature": 0.0,
                                "max_tokens": 1000,
                            }
                            for attempt in range(3):
                                resp = await client.post(url, headers=headers, json=body)
                                if resp.status_code == 429:
                                    retry_delay = float(resp.headers.get("retry-after", 2.0)) + (attempt * 1.0)
                                    logger.info(
                                        "groq_rate_limit_backoff",
                                        extra={"model": model_name, "attempt": attempt + 1, "retry_delay": retry_delay},
                                    )
                                    await asyncio.sleep(retry_delay)
                                    continue
                                if resp.status_code in (401, 403):
                                    groq_quota_exhausted = True
                                    break
                                resp.raise_for_status()
                                data = resp.json()
                                response_text = data["choices"][0]["message"]["content"]
                                self._last_extraction_method = "llm"
                                return self._parse_llm_response(response_text)
                            else:
                                logger.info("groq_model_quota_exhausted_try_next", extra={"model": model_name})
                                continue
                            break
                        else:
                            groq_quota_exhausted = True
                except Exception as exc:
                    logger.warning(
                        "groq_call_failed",
                        extra={"error": str(exc), "fallback": "openrouter_or_edenai"},
                    )
                    groq_quota_exhausted = True

                if groq_quota_exhausted:
                    if has_valid_gemini:
                        logger.info("groq_exhausted_falling_back_to_gemini")
                        result = await self._call_gemini(gemini_key, text, drug_name, disease_name)
                        if result is not None:
                            return result
                    if has_valid_openrouter:
                        logger.info("groq_exhausted_falling_back_to_openrouter")
                        result = await self._call_openrouter(openrouter_key, text, drug_name, disease_name)
                        if result is not None:
                            return result
                    if has_valid_edenai:
                        logger.info("groq_exhausted_falling_back_to_edenai")
                        result = await self._call_edenai(edenai_key, text, drug_name, disease_name)
                        if result is not None:
                            return result
                    logger.warning("all_llm_providers_exhausted_falling_back_to_rule_based")
                    self._last_extraction_method = "rule_based_fallback"
                    return self._rule_based_fallback(text, drug_name, disease_name)

            elif has_valid_gemini:
                logger.info("groq_key_absent_using_gemini")
                result = await self._call_gemini(gemini_key, text, drug_name, disease_name)
                if result is not None:
                    return result
                if has_valid_openrouter:
                    result = await self._call_openrouter(openrouter_key, text, drug_name, disease_name)
                    if result is not None:
                        return result
                if has_valid_edenai:
                    result = await self._call_edenai(edenai_key, text, drug_name, disease_name)
                    if result is not None:
                        return result
                self._last_extraction_method = "rule_based_fallback"
                return self._rule_based_fallback(text, drug_name, disease_name)

            elif has_valid_openrouter:
                logger.info("groq_key_absent_using_openrouter")
                result = await self._call_openrouter(openrouter_key, text, drug_name, disease_name)
                if result is not None:
                    return result
                if has_valid_edenai:
                    result = await self._call_edenai(edenai_key, text, drug_name, disease_name)
                    if result is not None:
                        return result
                self._last_extraction_method = "rule_based_fallback"
                return self._rule_based_fallback(text, drug_name, disease_name)

            elif has_valid_edenai:
                logger.info("groq_openrouter_absent_using_edenai")
                result = await self._call_edenai(edenai_key, text, drug_name, disease_name)
                if result is not None:
                    return result
                self._last_extraction_method = "rule_based_fallback"
                return self._rule_based_fallback(text, drug_name, disease_name)

            else:
                if not self._has_logged_unconfigured_warning:
                    logger.info(
                        "llm_key_unconfigured_fallback_to_rule_based",
                        extra={"fallback": "rule_based_fallback", "hint": "Set GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY, or EDENAI_API_KEY in .env"},
                    )
                    self._has_logged_unconfigured_warning = True
                self._last_extraction_method = "rule_based_fallback"
                return self._rule_based_fallback(text, drug_name, disease_name)

    async def _call_gemini(
        self,
        api_key: str,
        text: str,
        drug_name: str,
        disease_name: str,
    ) -> list[dict[str, Any]] | None:
        """Call Google Gemini for claim extraction.

        Uses ``google-generativeai`` inside a thread executor. Returns None on failure.
        """
        prompt = EXTRACTION_PROMPT_V1.format(text=text[:3000])
        model_name = os.environ.get("LLM_MODEL", self._model)

        def _generate() -> str:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.0, "max_output_tokens": 1000},
            )
            return response.text or ""

        try:
            response_text = await asyncio.get_event_loop().run_in_executor(None, _generate)
            if response_text.strip():
                self._last_extraction_method = "llm"
                return self._parse_llm_response(response_text)
        except Exception as exc:
            logger.warning("gemini_call_failed", extra={"error": str(exc)})
        return None

    async def _call_openrouter(
        self,
        api_key: str,
        text: str,
        drug_name: str,
        disease_name: str,
    ) -> list[dict[str, Any]] | None:
        """Call OpenRouter for claim extraction (OpenAI-compatible endpoint).

        Uses free or low-cost models available on OpenRouter.
        Returns None on failure so caller can try next provider.
        """
        prompt = EXTRACTION_PROMPT_V1.format(text=text[:3000])
        # Free/cheap models on OpenRouter that support instruction-following well
        models_to_try = [
            os.environ.get("OPENROUTER_MODEL", ""),
            "nvidia/nemotron-3.5-lightning:free",
            "liquid/lfm-2.5-2.6b:free",
        ]
        models_to_try = [m for m in models_to_try if m]  # remove empty

        try:
            import httpx
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://cynthera.ai",
                "X-Title": "Cynthera Drug Repurposing",
            }
            async with httpx.AsyncClient(timeout=25.0) as client:
                for model_name in models_to_try:
                    body = {
                        "model": model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                        "max_tokens": 1000,
                    }
                    try:
                        resp = await client.post(url, headers=headers, json=body)
                        if resp.status_code == 429:
                            await asyncio.sleep(2.0)
                            continue
                        resp.raise_for_status()
                        data = resp.json()
                        response_text = data["choices"][0]["message"]["content"]
                        self._last_extraction_method = "llm"
                        return self._parse_llm_response(response_text)
                    except Exception as model_exc:
                        logger.debug(
                            "openrouter_model_failed",
                            extra={"model": model_name, "error": str(model_exc)},
                        )
                        continue
        except Exception as exc:
            logger.warning("openrouter_call_failed", extra={"error": str(exc)})
        return None

    async def _call_edenai(
        self,
        api_key: str,
        text: str,
        drug_name: str,
        disease_name: str,
    ) -> list[dict[str, Any]] | None:
        """Call EdenAI for claim extraction.

        EdenAI aggregates multiple LLM providers under a single API.
        Returns None on failure so caller can try next provider.
        """
        prompt = EXTRACTION_PROMPT_V1.format(text=text[:3000])
        provider = os.environ.get("EDENAI_PROVIDER", "openai")
        model = os.environ.get("EDENAI_MODEL", "gpt-4o-mini")

        try:
            import httpx
            url = "https://api.edenai.run/v2/text/chat"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "providers": provider,
                "text": prompt,
                "chatbot_global_action": "You are a biomedical claim extraction system. Output only valid JSON.",
                "previous_history": [],
                "temperature": 0.0,
                "max_tokens": 1000,
                "model": model,
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
                # EdenAI response: {provider: {generated_text: "..."}}
                provider_result = data.get(provider, {})
                response_text = provider_result.get("generated_text", "")
                if response_text:
                    self._last_extraction_method = "llm"
                    return self._parse_llm_response(response_text)
        except Exception as exc:
            logger.warning("edenai_call_failed", extra={"error": str(exc)})
        return None

    def _parse_llm_response(self, response_text: str) -> list[dict[str, Any]]:
        """Parse and validate LLM JSON response.

        Args:
            response_text: Raw text response from LLM.

        Returns:
            Validated list of claim dicts.

        Raises:
            LLMResponseParsingError: If JSON is malformed or schema invalid.
        """
        text = response_text.strip()
        # Extract JSON array from response
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        try:
            claims = json.loads(text[start:end])
            if not isinstance(claims, list):
                raise LLMResponseParsingError(
                    message="LLM response is not a JSON array.",
                    context={"response_snippet": text[:200]},
                )
            return claims
        except json.JSONDecodeError as exc:
            raise LLMResponseParsingError(
                message=f"LLM response JSON parse error: {exc}",
                context={"response_snippet": text[:200]},
            ) from exc

    def _rule_based_fallback(self, text: str, drug_name: str = "drug", disease_name: str = "disease") -> list[dict[str, Any]]:
        """Context-aware rule-based fallback when LLM is unavailable.

        Uses drug and disease names from context to produce meaningful claims
        rather than generic placeholders.

        IMPORTANT: Claims produced by this method are low-confidence (0.25) keyword-matched
        guesses, not LLM-verified biological assertions. They must be disclosed as such in
        the audit report. The _last_extraction_method field on the agent is set to
        'rule_based_fallback' before this method is called, enabling upstream disclosure.

        Args:
            text: Abstract text to scan.
            drug_name: Drug name for subject/object labeling.
            disease_name: Disease name for object labeling.

        Returns:
            List of raw claim dicts detected by pattern matching. At most one claim per call.
        """
        claims = []
        text_lower = text.lower()
        drug_lower = drug_name.lower()
        disease_lower = disease_name.lower()

        # Determine the primary object: disease name if mentioned, else generic "target"
        primary_object = disease_name if disease_lower in text_lower else "molecular target"

        patterns = [
            ("inhibit", "INHIBITS"),
            ("activat", "ACTIVATES"),
            ("upregulat", "UPREGULATES"),
            ("downregulat", "DOWNREGULATES"),
            ("prevent", "PREVENTS"),
            ("associat", "ASSOCIATED_WITH"),
            ("bind", "BINDS"),
            ("caus", "CAUSES"),
        ]
        for pattern, predicate in patterns:
            if pattern in text_lower:
                # Use drug name as subject if found in text, else fallback to "compound"
                subject = drug_name if drug_lower in text_lower else "compound"
                claims.append({
                    "subject": subject,
                    "predicate": predicate,
                    "object": primary_object,
                    "confidence": 0.25,  # Low confidence for rule-based extraction
                })
                break
        return claims

    def _parse_raw_claim(
        self,
        raw: dict[str, Any],
        evidence: Evidence,
        extraction_method: str = "llm",
    ) -> Claim:
        """Parse a raw claim dict into a validated Claim entity.

        Args:
            raw: Dict with subject, predicate, object, confidence keys.
            evidence: Parent Evidence record.
            extraction_method: 'llm' or 'rule_based_fallback'. Disclosed in raw_text prefix.

        Returns:
            Validated Claim entity.
        """
        predicate_str = str(raw.get("predicate", "")).upper()
        try:
            predicate = PredicateType(predicate_str)
        except ValueError:
            predicate = PredicateType.ASSOCIATED_WITH

        confidence = float(raw.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        # Disclose extraction method in raw_text so audit reports can surface it.
        # Rule-based claims are prefixed to distinguish them from LLM-verified claims.
        abstract_snippet = evidence.abstract[:500] if evidence.abstract else None
        if extraction_method == "rule_based_fallback" and abstract_snippet:
            raw_text = f"[keyword-extracted — LLM unavailable] {abstract_snippet}"
        else:
            raw_text = abstract_snippet

        erw = evidence.erw
        # Rule-based keyword matching has higher false-positive rates than LLM extraction.
        # Apply a 0.5x weight discount so unverified keyword claims carry less weight
        # and do not over-inflate Support Scores or drive heavy contradiction penalties.
        if extraction_method == "rule_based_fallback":
            erw = ERW.from_base(evidence.erw.base_weight, replication_modifier=0.5)

        return Claim(
            subject=str(raw.get("subject", "unknown"))[:100],
            predicate=predicate,
            object=str(raw.get("object", "unknown"))[:100],
            confidence=confidence,
            erw=erw,
            evidence_ids=[evidence.id],
            provenance=evidence.provenance,
            raw_text=raw_text,
            is_validated=False,
        )
