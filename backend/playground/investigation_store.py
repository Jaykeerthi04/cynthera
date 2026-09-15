"""Investigation store — SQLite persistence for Playground researcher notes.

Extends the existing cynthera.db with a table for:
- playground_notes (researcher annotations)

Reference: implementation_plan.md (v2) — MVP Notes Persistence
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.playground.models import ResearcherNote

logger = logging.getLogger(__name__)

_DDL_NOTES = """
CREATE TABLE IF NOT EXISTS playground_notes (
    id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    note_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_DDL_IDX_NOTES = """
CREATE INDEX IF NOT EXISTS idx_notes_hypothesis
    ON playground_notes(hypothesis_id);
"""


class InvestigationStore:
    """SQLite-backed store for Playground researcher notes.

    Uses the same database file as the main CYNTHERA storage.

    Args:
        db_path: Path to the SQLite database file.
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
            conn.execute(_DDL_NOTES)
            try:
                conn.execute(_DDL_IDX_NOTES)
            except sqlite3.OperationalError:
                pass
            conn.commit()

    # ─────────────────────────────────────────────
    # Notes
    # ─────────────────────────────────────────────

    def save_note(self, note: ResearcherNote) -> str:
        """Persist a researcher note.

        Args:
            note: The ResearcherNote to persist.

        Returns:
            The note ID.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO playground_notes
                    (id, hypothesis_id, target_type, target_id, note_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    note_text = excluded.note_text
                """,
                (
                    note.id,
                    note.hypothesis_id,
                    note.target_type,
                    note.target_id,
                    note.text,
                    note.created_at.isoformat() if hasattr(note.created_at, "isoformat") else datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
        return note.id

    def get_notes(self, hypothesis_id: str) -> list[ResearcherNote]:
        """Retrieve all notes for a hypothesis.

        Args:
            hypothesis_id: UUID string of the hypothesis.

        Returns:
            List of ResearcherNote objects, ordered by creation time.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, hypothesis_id, target_type, target_id, note_text, created_at
                FROM playground_notes
                WHERE hypothesis_id = ?
                ORDER BY created_at ASC
                """,
                (hypothesis_id,),
            ).fetchall()

        notes: list[ResearcherNote] = []
        for row in rows:
            try:
                notes.append(ResearcherNote(
                    id=row["id"],
                    hypothesis_id=row["hypothesis_id"],
                    target_type=row["target_type"],
                    target_id=row["target_id"],
                    text=row["note_text"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                ))
            except Exception:
                continue
        return notes

    def delete_note(self, note_id: str) -> bool:
        """Delete a researcher note by ID."""
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM playground_notes WHERE id = ?", (note_id,)
            )
            conn.commit()
        return result.rowcount > 0
