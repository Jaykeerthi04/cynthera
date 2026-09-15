"""CYNTHERA Playground API routes — endpoints for interactive hypothesis exploration.

Endpoints:
    GET  /api/v1/playground/{hypothesis_id}            — Full PlaygroundGraphData
    GET  /api/v1/playground/{hypothesis_id}/evidence/{evidence_id} — Evidence detail
    POST /api/v1/playground/{hypothesis_id}/scenario    — Compute scenario result
    POST /api/v1/playground/{hypothesis_id}/notes       — Save researcher note
    GET  /api/v1/playground/{hypothesis_id}/notes       — Get all notes
    GET  /api/v1/playground/{hypothesis_id}/investigation — Load saved investigation
    POST /api/v1/playground/{hypothesis_id}/investigation — Save investigation

All endpoints return structured JSON. No markdown parsing on the frontend.

Reference: implementation_plan.md — Phase 1
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.storage.repository import StorageRepository
from backend.playground.subgraph_extractor import extract_relevant_subgraph
from backend.playground.scenario_engine import ScenarioEngine
from backend.playground.investigation_store import InvestigationStore
from backend.playground.models import (
    PlaygroundGraphData,
    ScenarioModifications,
    ScenarioResult,
    ResearcherNote,
)

logger = logging.getLogger(__name__)

playground_router = APIRouter(prefix="/api/v1/playground", tags=["Playground"])

# Shared instances
_DB_PATH = "data/cynthera.db"
_storage = StorageRepository(db_path=_DB_PATH)
_investigation_store = InvestigationStore(db_path=_DB_PATH)
_scenario_engine = ScenarioEngine()


# ─────────────────────────────────────────────
# Request Models
# ─────────────────────────────────────────────

class NoteRequest(BaseModel):
    """Request body for POST /notes."""
    target_type: str = Field(..., description="hypothesis | node | edge | evidence")
    target_id: str | None = Field(None)
    text: str = Field(..., min_length=1)


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@playground_router.get("/{hypothesis_id}", response_model=PlaygroundGraphData)
async def get_playground(hypothesis_id: str) -> PlaygroundGraphData:
    """Load the full Playground data for a completed hypothesis.

    Reconstructs the evidence graph from the stored RetrievalPackage,
    combines with the stored ReasoningResult, and returns structured
    graph data for the frontend.

    No network calls. Fully deterministic.

    Args:
        hypothesis_id: UUID string of the hypothesis.

    Returns:
        PlaygroundGraphData with nodes, edges, evidence, claims, etc.

    Raises:
        404: If no data found for the given hypothesis.
    """
    package = _storage.get_retrieval_package(hypothesis_id)
    result = _storage.get_reasoning_result(hypothesis_id)

    if package is None or result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No completed evaluation found for hypothesis '{hypothesis_id}'. "
                "Run an evaluation first, then open the Playground."
            ),
        )

    try:
        graph_data = extract_relevant_subgraph(package, result)
        return graph_data
    except Exception as exc:
        logger.error("playground_extraction_failed", extra={"error": str(exc)}, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to extract Playground data: {str(exc)}",
        )


@playground_router.get("/{hypothesis_id}/evidence/{evidence_id}")
async def get_evidence_detail(hypothesis_id: str, evidence_id: str) -> dict[str, Any]:
    """Get detailed information for a specific evidence record.

    Args:
        hypothesis_id: UUID of the hypothesis.
        evidence_id: UUID of the evidence record.

    Returns:
        Evidence detail as JSON dict.

    Raises:
        404: If evidence not found.
    """
    package = _storage.get_retrieval_package(hypothesis_id)
    if package is None:
        raise HTTPException(status_code=404, detail="Hypothesis data not found.")

    for ev in package.evidence_records:
        if str(ev.id) == evidence_id:
            prov = getattr(ev, "provenance", None)
            from backend.core.value_objects.source_url_builder import SourceURLBuilder
            links = SourceURLBuilder.build_links_for_citation_key(
                ev.citation_key, ev.title
            )
            return {
                "id": str(ev.id),
                "evidence_type": ev.evidence_type.value,
                "erw": ev.erw.value,
                "citation_key": ev.citation_key,
                "title": ev.title,
                "abstract": ev.abstract,
                "source_name": prov.source_name if prov else "",
                "source_version": prov.source_version if prov else "",
                "source_url": prov.url if prov else None,
                "record_id": prov.record_id if prov else "",
                "retrieved_at": prov.retrieved_at.isoformat() if prov else None,
                "drug_chembl_id": ev.drug_chembl_id,
                "disease_identifier": ev.disease_identifier,
                "target_uniprot": ev.target_uniprot,
                "links": [link.to_dict() for link in links],
            }

    raise HTTPException(status_code=404, detail=f"Evidence '{evidence_id}' not found.")


@playground_router.post("/{hypothesis_id}/scenario", response_model=ScenarioResult)
async def compute_scenario(
    hypothesis_id: str,
    modifications: ScenarioModifications,
) -> ScenarioResult:
    """Compute a local scenario result from modified evidence graph.

    No network calls. No LLM calls. The original assessment is never mutated.
    The scenario operates on a copy of the evidence graph.

    Target latency: < 1 second.

    Args:
        hypothesis_id: UUID of the hypothesis.
        modifications: Edge modifications to apply.

    Returns:
        ScenarioResult with original vs modified comparison.

    Raises:
        404: If hypothesis data not found.
    """
    package = _storage.get_retrieval_package(hypothesis_id)
    result = _storage.get_reasoning_result(hypothesis_id)

    if package is None or result is None:
        raise HTTPException(status_code=404, detail="Hypothesis data not found.")

    try:
        scenario = _scenario_engine.compute_scenario(package, result, modifications)
        return scenario
    except Exception as exc:
        logger.error("scenario_computation_failed", extra={"error": str(exc)}, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Scenario computation failed: {str(exc)}",
        )


@playground_router.post("/{hypothesis_id}/notes")
async def save_note(hypothesis_id: str, request: NoteRequest) -> dict[str, str]:
    """Save a researcher note.

    Notes are researcher annotations. They are NOT machine-generated evidence.
    They do not affect official scores.

    Args:
        hypothesis_id: UUID of the hypothesis.
        request: Note content and target.

    Returns:
        Dict with the note ID.
    """
    note = ResearcherNote(
        hypothesis_id=hypothesis_id,
        target_type=request.target_type,
        target_id=request.target_id,
        text=request.text,
    )
    note_id = _investigation_store.save_note(note)
    return {"note_id": note_id, "status": "saved"}


@playground_router.get("/{hypothesis_id}/notes")
async def get_notes(hypothesis_id: str) -> list[dict[str, Any]]:
    """Retrieve all researcher notes for a hypothesis.

    Args:
        hypothesis_id: UUID of the hypothesis.

    Returns:
        List of notes as JSON dicts.
    """
    notes = _investigation_store.get_notes(hypothesis_id)
    return [
        {
            "id": n.id,
            "target_type": n.target_type,
            "target_id": n.target_id,
            "text": n.text,
            "created_at": n.created_at.isoformat() if hasattr(n.created_at, "isoformat") else str(n.created_at),
        }
        for n in notes
    ]
