from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.app.models import SavedIdea, ScenarioValuation, Thesis


class ResearchRepository:
    """Small SQLite persistence layer for local user-authored research."""

    def __init__(self, sqlite_path: Path):
        self.sqlite_path = sqlite_path
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS theses (
                    ticker TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS valuations (
                    ticker TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_ideas (
                    ticker TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def get_thesis(self, ticker: str) -> Thesis | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM theses WHERE ticker = ?", (ticker.upper(),)).fetchone()
        if row is None:
            return None
        return Thesis.model_validate_json(row["payload"])

    def save_thesis(self, thesis: Thesis) -> Thesis:
        payload = thesis.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO theses (ticker, payload, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(ticker) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (thesis.ticker.upper(), payload),
            )
        return thesis

    def get_valuation(self, ticker: str) -> ScenarioValuation | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM valuations WHERE ticker = ?", (ticker.upper(),)).fetchone()
        if row is None:
            return None
        return ScenarioValuation.model_validate_json(row["payload"])

    def save_valuation(self, valuation: ScenarioValuation) -> ScenarioValuation:
        payload = valuation.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO valuations (ticker, payload, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(ticker) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (valuation.ticker.upper(), payload),
            )
        return valuation

    def list_saved_ideas(self) -> list[SavedIdea]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM saved_ideas ORDER BY updated_at DESC, ticker ASC").fetchall()
        return [SavedIdea.model_validate_json(row["payload"]) for row in rows]

    def get_saved_idea(self, ticker: str) -> SavedIdea | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM saved_ideas WHERE ticker = ?", (ticker.upper(),)).fetchone()
        if row is None:
            return None
        return SavedIdea.model_validate_json(row["payload"])

    def save_saved_idea(self, idea: SavedIdea) -> SavedIdea:
        existing = self.get_saved_idea(idea.ticker)
        normalized = idea.model_copy(
            update={
                "ticker": idea.ticker.upper(),
                "created_at": existing.created_at if existing else idea.created_at,
            }
        )
        payload = normalized.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO saved_ideas (ticker, payload, created_at, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(ticker) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (normalized.ticker, payload),
            )
        return normalized

    def delete_saved_idea(self, ticker: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM saved_ideas WHERE ticker = ?", (ticker.upper(),))

    def export_payload(self) -> dict[str, object]:
        with self._connect() as conn:
            theses = conn.execute("SELECT ticker, payload FROM theses ORDER BY ticker").fetchall()
            valuations = conn.execute("SELECT ticker, payload FROM valuations ORDER BY ticker").fetchall()
            saved_ideas = conn.execute("SELECT ticker, payload FROM saved_ideas ORDER BY ticker").fetchall()
        return {
            "theses": {row["ticker"]: json.loads(row["payload"]) for row in theses},
            "valuations": {row["ticker"]: json.loads(row["payload"]) for row in valuations},
            "saved_ideas": {row["ticker"]: json.loads(row["payload"]) for row in saved_ideas},
        }
