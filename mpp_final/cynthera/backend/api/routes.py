"""CYNTHERA FastAPI Routes — implements all public API endpoints per 07_API_CONTRACTS.md.

Endpoints:
    POST /api/v1/evaluate         — Run a new drug-disease evaluation
    GET  /api/v1/results/{id}     — Retrieve a ReasoningResult by hypothesis ID
    GET  /api/v1/audit/{id}       — Retrieve the ScientificAuditReport by hypothesis ID
    GET  /api/v1/history          — List all past evaluations
    GET  /api/v1/health           — Health check
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.storage.repository import StorageRepository

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["CYNTHERA"])

# Singleton storage instance (shared with orchestrator via same db_path)
_DB_PATH = "data/cynthera.db"
_storage = StorageRepository(db_path=_DB_PATH)


# ─────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────

class EvaluationRequest(BaseModel):
    """Request body for POST /api/v1/evaluate."""
    drug_name: str = Field(..., min_length=1, max_length=200, description="Common name of the drug.")
    disease_name: str = Field(..., min_length=1, max_length=200, description="Disease name to evaluate.")
    retrieval_policy: str = Field(
        default="STANDARD",
        pattern="^(STANDARD|FAST|COMPREHENSIVE)$",
        description="Retrieval depth: STANDARD, FAST, or COMPREHENSIVE.",
    )
    bypass_cache: bool = Field(
        default=False,
        description="If true, skip cache lookup and force a fresh evaluation.",
    )


class EvaluationSummaryResponse(BaseModel):
    """Lightweight response returned after submitting an evaluation."""
    hypothesis_id: str
    drug_name: str
    disease_name: str
    recommendation: str
    support_score: float
    mechanistic_score: float
    risk_score: float
    retrieval_confidence: str
    sources_queried: list[str]
    sources_failed: list[str]
    summary: str
    duration_ms: float
    from_cache: bool = False
    rule_set_version: str = "3.2"


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    db_path: str
    phase: str = "Phase 2 & 3"
    features: list[str] = []


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.post("/evaluate", response_model=EvaluationSummaryResponse, status_code=201)
async def evaluate(request: EvaluationRequest) -> EvaluationSummaryResponse:
    """Run a full drug-disease repurposing evaluation.

    This is a synchronous endpoint that runs the complete 10-step pipeline
    and returns the final result. Results are automatically persisted to the
    SQLite database for later retrieval.

    Returns:
        EvaluationSummaryResponse with scores, recommendation, and summary.

    Raises:
        422: If input validation fails.
        500: If pipeline execution fails.
    """
    policy_map = {
        "STANDARD": RetrievalPolicy.STANDARD,
        "FAST": RetrievalPolicy.FAST,
        "COMPREHENSIVE": RetrievalPolicy.COMPREHENSIVE,
    }

    orchestrator = MasterOrchestrator(
        llm_api_key=os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY"),
        ncbi_api_key=os.environ.get("NCBI_API_KEY"),
        disgenet_api_key=os.environ.get("DISGENET_API_KEY"),
        db_path=_DB_PATH,
    )

    try:
        hypothesis, package, result = await orchestrator.evaluate(
            drug_name=request.drug_name,
            disease_name=request.disease_name,
            policy=policy_map.get(request.retrieval_policy, RetrievalPolicy.STANDARD),
            bypass_cache=request.bypass_cache,
        )
    except Exception as exc:
        logger.error("evaluate_endpoint_failed", extra={"error": str(exc)}, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return EvaluationSummaryResponse(
        hypothesis_id=str(hypothesis.id),
        drug_name=request.drug_name,
        disease_name=request.disease_name,
        recommendation=result.recommendation_status.value,
        support_score=result.support_assessment.score,
        mechanistic_score=result.mechanistic_assessment.score,
        risk_score=result.risk_assessment.score,
        retrieval_confidence=package.retrieval_confidence if package else "CACHED",
        sources_queried=package.sources_queried if package else [],
        sources_failed=package.sources_failed if package else [],
        summary=result.audit_report.summary,
        duration_ms=result.reasoning_duration_ms,
        rule_set_version=result.rule_set_version,
    )


@router.get("/results/{hypothesis_id}")
async def get_results(hypothesis_id: str) -> dict[str, Any]:
    """Retrieve the full ReasoningResult for a hypothesis.

    Args:
        hypothesis_id: UUID string of the hypothesis.

    Returns:
        Full ReasoningResult as JSON.

    Raises:
        404: If no result is found for the given ID.
    """
    result = _storage.get_reasoning_result(hypothesis_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No result found for hypothesis ID '{hypothesis_id}'.",
        )
    return result.model_dump()


@router.get("/audit/{hypothesis_id}")
async def get_audit(hypothesis_id: str) -> dict[str, Any]:
    """Retrieve the ScientificAuditReport for a hypothesis.

    Args:
        hypothesis_id: UUID string of the hypothesis.

    Returns:
        ScientificAuditReport as JSON.

    Raises:
        404: If no result is found for the given ID.
    """
    result = _storage.get_reasoning_result(hypothesis_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No result found for hypothesis ID '{hypothesis_id}'.",
        )
    return result.audit_report.model_dump()


@router.get("/history")
async def get_history(limit: int = 50) -> list[dict[str, Any]]:
    """Return a list of all past evaluations.

    Args:
        limit: Maximum number of records to return (default 50).

    Returns:
        List of evaluation summary dicts ordered by most recent first.
    """
    return _storage.list_evaluations(limit=min(limit, 200))


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint.

    Returns:
        System status and version information.
    """
    return HealthResponse(
        status="ok",
        version="1.0.0",
        db_path=_DB_PATH,
    )
