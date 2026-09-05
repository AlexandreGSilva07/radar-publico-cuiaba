"""API de consulta somente leitura do Radar Público Cuiabá."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb
import uvicorn
from fastapi import FastAPI, HTTPException

from radar_publico import __version__

PORTAL_URL = "https://transparencia.cuiaba.mt.gov.br/portaltransparencia/"


class AnalyticsDatabase:
    def __init__(self, path: Path, enrichment_path: Path | None = None) -> None:
        self.path = path
        self.enrichment_path = enrichment_path

    @contextmanager
    def connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        connection = duckdb.connect(str(self.path), read_only=True)
        try:
            yield connection
        finally:
            connection.close()

    def rows(self, sql: str, parameters: list[object] | None = None) -> list[dict[str, Any]]:
        with self.connect() as connection:
            result = connection.execute(sql, parameters or [])
            columns = [item[0] for item in result.description]
            return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]

    def row(self, sql: str, parameters: list[object] | None = None) -> dict[str, Any]:
        rows = self.rows(sql, parameters)
        if not rows:
            raise LookupError("consulta sem resultado")
        return rows[0]

    def enrichment_count(self) -> int:
        path = self.enrichment_path
        if path is None or not path.exists():
            return 0
        connection = duckdb.connect(str(path), read_only=True)
        try:
            row = connection.execute("SELECT count(*) FROM company_profile").fetchone()
            return int(row[0]) if row else 0
        finally:
            connection.close()


def create_app(
    analytics_path: Path = Path("data/analytics.duckdb"),
    enrichment_path: Path = Path("data/enrichment.duckdb"),
) -> FastAPI:
    application = FastAPI(
        title="Radar Público Cuiabá API",
        description="Inteligência comercial derivada de dados públicos municipais.",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
    )
    database = AnalyticsDatabase(analytics_path, enrichment_path)
    application.state.database = database

    @application.get("/api/health")
    def health() -> dict[str, object]:
        try:
            database.row("SELECT 1 AS healthy")
        except (duckdb.Error, FileNotFoundError, LookupError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc
        return {"status": "ok", "version": __version__}

    @application.get("/api/meta")
    def metadata() -> dict[str, object]:
        try:
            items = database.rows("SELECT key, value FROM analytics_metadata ORDER BY key")
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc
        return {
            "dataset": {str(item["key"]): item["value"] for item in items},
            "enriched_companies": database.enrichment_count(),
            "source": "Portal da Transparência de Cuiabá",
            "source_url": PORTAL_URL,
        }

    @application.get("/api/summary")
    def summary() -> dict[str, Any]:
        try:
            return database.row("SELECT * FROM gold_kpis")
        except (duckdb.Error, FileNotFoundError, LookupError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc

    @application.get("/")
    def root() -> dict[str, str]:
        return {"product": "Radar Público Cuiabá", "api_docs": "/api/docs"}

    return application


app = create_app()


def run(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    uvicorn.run("radar_publico.api:app", host=host, port=port, reload=reload)

