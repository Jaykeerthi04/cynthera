"""CYNTHERA Analyze API Routes — Researcher-facing stable API per Section 23."""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from backend.api.dtos import (
    AnalysisRequestDTO,
    AnalysisResultDTO,
    ReportModelDTO,
    TherapeuticEvidenceItemDTO,
)
from backend.api.dto_builder import build_analysis_result_dto, build_report_model_dto
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.reporting.pdf_exporter import PDFReporter
from backend.storage.repository import StorageRepository

logger = logging.getLogger(__name__)

analyze_router = APIRouter(prefix="/api", tags=["Analysis"])

_DB_PATH = "data/cynthera.db"
_storage = StorageRepository(db_path=_DB_PATH)


@analyze_router.post("/analyze", response_model=AnalysisResultDTO, status_code=200)
async def analyze_hypothesis(request: AnalysisRequestDTO) -> AnalysisResultDTO:
    """Evaluate a drug-disease hypothesis and return a structured research-grade analysis."""
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
            drug_name=request.drug,
            disease_name=request.disease,
            policy=policy_map.get(request.policy, RetrievalPolicy.STANDARD),
            bypass_cache=request.bypass_cache,
        )
    except Exception as exc:
        logger.error("analyze_endpoint_failed", extra={"error": str(exc)}, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline evaluation error: {exc}")

    return build_analysis_result_dto(hypothesis, package, result)


@analyze_router.get("/analyze/{analysis_id}", response_model=AnalysisResultDTO)
async def get_analysis(analysis_id: str) -> AnalysisResultDTO:
    """Retrieve full analysis result by analysis/hypothesis ID."""
    hypothesis = _storage.get_hypothesis(analysis_id)
    result = _storage.get_reasoning_result(analysis_id)
    if hypothesis is None or result is None:
        raise HTTPException(status_code=404, detail=f"Analysis not found for ID: {analysis_id}")
    package = _storage.get_retrieval_package(analysis_id)
    return build_analysis_result_dto(hypothesis, package, result)


@analyze_router.get("/analyze/{analysis_id}/evidence", response_model=list[TherapeuticEvidenceItemDTO])
async def get_evidence(analysis_id: str) -> list[TherapeuticEvidenceItemDTO]:
    """Retrieve all evidence ledger items with provenance and canonical URLs."""
    analysis = await get_analysis(analysis_id)
    return analysis.therapeutic_evidence


@analyze_router.get("/analyze/{analysis_id}/report", response_model=ReportModelDTO)
async def get_report(analysis_id: str) -> ReportModelDTO:
    """Retrieve full 15-section structured scientific report model."""
    hypothesis = _storage.get_hypothesis(analysis_id)
    result = _storage.get_reasoning_result(analysis_id)
    if hypothesis is None or result is None:
        raise HTTPException(status_code=404, detail=f"Analysis not found for ID: {analysis_id}")
    package = _storage.get_retrieval_package(analysis_id)
    return build_report_model_dto(hypothesis, package, result)


@analyze_router.get("/analyze/{analysis_id}/report/pdf")
async def download_report_pdf(analysis_id: str) -> Response:
    """Download research-grade PDF report."""
    hypothesis = _storage.get_hypothesis(analysis_id)
    result = _storage.get_reasoning_result(analysis_id)
    if hypothesis is None or result is None:
        raise HTTPException(status_code=404, detail=f"Analysis not found for ID: {analysis_id}")

    reporter = PDFReporter(drug_name=hypothesis.drug_name, disease_name=hypothesis.disease_name)
    try:
        pdf_bytes = reporter.generate(result)
    except Exception as exc:
        logger.error("pdf_export_failed", extra={"error": str(exc)}, exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}")

    safe_drug = hypothesis.drug_name.replace(" ", "_")[:25]
    safe_disease = hypothesis.disease_name.replace(" ", "_")[:25]
    filename = f"CYNTHERA_{safe_drug}_{safe_disease}_{analysis_id[:8]}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
