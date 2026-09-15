"""CYNTHERA FastAPI Application Factory — Phase 3 Production.

Start the server with:
    python -m uvicorn backend.api.main:app --reload --port 8000

Or from main directory:
    uvicorn backend.api.main:app --reload
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.api.batch_routes import batch_router
from backend.api.report_routes import report_router
from backend.playground.playground_routes import playground_router
from backend.infrastructure.cache.evaluation_cache import EvaluationCache
from backend.infrastructure.knowledge.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Global instances (initialized in lifespan)
# ─────────────────────────────────────────────
_DB_PATH = "data/cynthera.db"
_cache: EvaluationCache | None = None
_knowledge_store: KnowledgeStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager — runs startup/shutdown logic."""
    global _cache, _knowledge_store

    logger.info("CYNTHERA API starting up (Phase 3)...")

    # Warm up the evaluation cache
    _cache = EvaluationCache(db_path=_DB_PATH)
    purged = _cache.purge_expired()
    if purged:
        logger.info(f"Purged {purged} expired cache entries on startup.")

    # Warm up the knowledge store (ensures seed data is loaded)
    _knowledge_store = KnowledgeStore(db_path=_DB_PATH)
    logger.info("KnowledgeStore initialized and seeded.")

    cache_stats = _cache.stats()
    logger.info(
        "startup_complete",
        extra={
            "cache_active_entries": cache_stats["active_entries"],
            "knowledge_store": "ready",
        },
    )

    yield

    logger.info("CYNTHERA API shutting down.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app instance with all Phase 2/3 features.
    """
    app = FastAPI(
        title="CYNTHERA Drug Repurposing API",
        description=(
            "Contradiction-Aware Mechanistic Reasoning for Explainable Drug Repurposing. "
            "Phase 2 & 3 enhanced with: Clinical Safety Agent, Prior Knowledge (vector-DB-style), "
            "Multi-hop Mechanistic Reasoning, Advanced Conflict Resolution, "
            "Batch Evaluation API, Result Caching, PDF Export, and API Key Auth. "
            "API contracts defined in 07_API_CONTRACTS.md."
        ),
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ───────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8501",   # Streamlit default
            "http://localhost:3000",   # React dev
            "http://localhost:8000",   # FastAPI self
            "*",                       # Relaxed for development; tighten in production
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request ID Injection Middleware ─────────────────────────────────
    @app.middleware("http")
    async def add_request_id(request: Request, call_next: Any) -> Response:
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # ── Request Timing Middleware ────────────────────────────────────────
    @app.middleware("http")
    async def add_timing(request: Request, call_next: Any) -> Response:
        start = time.time()
        response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 1)
        response.headers["X-Response-Time-Ms"] = str(duration_ms)
        return response

    # ── Register Routes ─────────────────────────────────────────────────
    app.include_router(router)        # Core evaluation routes
    app.include_router(batch_router)  # Batch evaluation routes
    app.include_router(report_router) # PDF report routes
    app.include_router(playground_router)  # Playground / Evidence Explorer routes

    # ── Cache Stats Endpoint ─────────────────────────────────────────────
    @app.get("/api/v1/cache/stats", tags=["Cache"])
    async def cache_stats() -> dict:
        """Return evaluation cache statistics."""
        global _cache
        if _cache is None:
            _cache = EvaluationCache(db_path=_DB_PATH)
        return _cache.stats()

    @app.get("/api/v1/cache/purge", tags=["Cache"])
    async def purge_cache() -> dict:
        """Purge all expired cache entries."""
        global _cache
        if _cache is None:
            _cache = EvaluationCache(db_path=_DB_PATH)
        removed = _cache.purge_expired()
        return {"purged_entries": removed}

    return app


# Fix the type annotation for middleware (import Any at top-level)
from typing import Any  # noqa: E402

# Application instance — imported by uvicorn
app = create_app()
