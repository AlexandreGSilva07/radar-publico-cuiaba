"""API de consulta somente leitura do Radar Público Cuiabá."""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from radar_publico import __version__

PORTAL_URL = "https://transparencia.cuiaba.mt.gov.br/portaltransparencia/"

EXPORTS = {
    "opportunities": (
        "SELECT procurement_id, number, year, object_text, agency, modality, status, "
        "published_on, session_on, estimated_value, relevance_score "
        "FROM gold_opportunities ORDER BY relevance_score DESC, procurement_id DESC"
    ),
    "contracts": (
        "SELECT contract_id, number, year, object_text, agency, supplier_name, cnpj, status, "
        "signed_on, starts_on, ends_on, contract_type, category, original_value, current_value, "
        "procurement_id, procurement_status FROM gold_contract_links "
        "ORDER BY current_value DESC NULLS LAST"
    ),
    "agencies": "SELECT * FROM gold_agencies ORDER BY contract_value DESC",
    "suppliers": "SELECT * FROM gold_suppliers ORDER BY contract_value DESC, paid_value DESC",
    "expenses": (
        "SELECT cnpj, supplier_name, expense_records, committed_value, paid_value "
        "FROM gold_suppliers WHERE expense_records>0 ORDER BY paid_value DESC"
    ),
}


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

    def profiles(self, cnpjs: list[str]) -> dict[str, dict[str, Any]]:
        path = self.enrichment_path
        if path is None or not path.exists() or not cnpjs:
            return {}
        connection = duckdb.connect(str(path), read_only=True)
        try:
            placeholders = ",".join("?" for _ in cnpjs)
            result = connection.execute(
                "SELECT cnpj, legal_name, trade_name, registration_status, company_size, "
                "primary_cnae, primary_cnae_description, city, state "
                f"FROM company_profile WHERE cnpj IN ({placeholders})",
                cnpjs,
            )
            columns = [item[0] for item in result.description]
            return {str(row[0]): dict(zip(columns, row, strict=True)) for row in result.fetchall()}
        finally:
            connection.close()


def _paged(
    database: AnalyticsDatabase,
    *,
    select_sql: str,
    count_sql: str,
    parameters: list[object],
    page: int,
    page_size: int,
) -> dict[str, Any]:
    total = int(database.row(count_sql, parameters)["total"])
    items = database.rows(
        f"{select_sql} LIMIT ? OFFSET ?", [*parameters, page_size, (page - 1) * page_size]
    )
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size),
    }


def _search_pattern(query: str) -> str:
    escaped = query.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _safe_csv_cell(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _csv_response(dataset: str, rows: list[dict[str, Any]]) -> Response:
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows({key: _safe_csv_cell(value) for key, value in row.items()} for row in rows)
    content = "\ufeff" + output.getvalue()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="radar-cuiaba-{dataset}.csv"'},
    )


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

    @application.get("/api/opportunities")
    def opportunities(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        q: str | None = Query(None, max_length=100),
        agency: str | None = Query(None, max_length=200),
        status: str | None = Query(None, max_length=40),
        min_value: float | None = Query(None, ge=0),
    ) -> dict[str, Any]:
        conditions = ["1=1"]
        parameters: list[object] = []
        if q:
            conditions.append("lower(coalesce(object_text,'')) LIKE ? ESCAPE '\\\\'")
            parameters.append(_search_pattern(q))
        if agency:
            conditions.append("agency=?")
            parameters.append(agency)
        if status:
            conditions.append("status=?")
            parameters.append(status)
        if min_value is not None:
            conditions.append("coalesce(estimated_value,0)>=?")
            parameters.append(min_value)
        where = " AND ".join(conditions)
        try:
            return _paged(
                database,
                select_sql=f"SELECT * FROM gold_opportunities WHERE {where} "
                "ORDER BY relevance_score DESC, session_on DESC NULLS LAST, procurement_id DESC",
                count_sql=f"SELECT count(*) AS total FROM gold_opportunities WHERE {where}",
                parameters=parameters,
                page=page,
                page_size=page_size,
            )
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc

    @application.get("/api/contracts")
    def contracts(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        q: str | None = Query(None, max_length=100),
        agency: str | None = Query(None, max_length=200),
        status: str | None = Query(None, max_length=80),
    ) -> dict[str, Any]:
        conditions = ["1=1"]
        parameters: list[object] = []
        if q:
            conditions.append(
                "(lower(coalesce(object_text,'')) LIKE ? ESCAPE '\\\\' OR "
                "lower(coalesce(supplier_name,'')) LIKE ? ESCAPE '\\\\')"
            )
            pattern = _search_pattern(q)
            parameters.extend([pattern, pattern])
        if agency:
            conditions.append("agency=?")
            parameters.append(agency)
        if status:
            conditions.append("status=?")
            parameters.append(status)
        where = " AND ".join(conditions)
        columns = (
            "contract_id, number, year, object_text, agency, supplier_name, cnpj, status, "
            "signed_on, starts_on, ends_on, contract_type, category, original_value, "
            "current_value, has_document, procurement_id, procurement_status, procurement_linked"
        )
        try:
            return _paged(
                database,
                select_sql=f"SELECT {columns} FROM gold_contract_links WHERE {where} "
                "ORDER BY current_value DESC NULLS LAST, contract_id DESC",
                count_sql=f"SELECT count(*) AS total FROM gold_contract_links WHERE {where}",
                parameters=parameters,
                page=page,
                page_size=page_size,
            )
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc

    @application.get("/api/renewals")
    def renewals(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        within_days: int = Query(180, ge=1, le=1825),
    ) -> dict[str, Any]:
        parameters: list[object] = [within_days]
        where = "days_to_end BETWEEN 0 AND ?"
        try:
            return _paged(
                database,
                select_sql=f"SELECT * FROM gold_contract_renewals WHERE {where} "
                "ORDER BY days_to_end, current_value DESC NULLS LAST",
                count_sql=f"SELECT count(*) AS total FROM gold_contract_renewals WHERE {where}",
                parameters=parameters,
                page=page,
                page_size=page_size,
            )
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc

    @application.get("/api/agencies")
    def agencies(
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=100),
        q: str | None = Query(None, max_length=100),
    ) -> dict[str, Any]:
        parameters: list[object] = []
        where = "1=1"
        if q:
            where = "lower(agency) LIKE ? ESCAPE '\\\\'"
            parameters.append(_search_pattern(q))
        try:
            return _paged(
                database,
                select_sql=f"SELECT * FROM gold_agencies WHERE {where} "
                "ORDER BY contract_value DESC, estimated_value DESC",
                count_sql=f"SELECT count(*) AS total FROM gold_agencies WHERE {where}",
                parameters=parameters,
                page=page,
                page_size=page_size,
            )
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc

    @application.get("/api/suppliers")
    def suppliers(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        q: str | None = Query(None, max_length=100),
        contracted_only: bool = Query(False),
    ) -> dict[str, Any]:
        conditions = ["1=1"]
        parameters: list[object] = []
        if q:
            conditions.append(
                "(lower(coalesce(supplier_name,'')) LIKE ? ESCAPE '\\\\' OR cnpj LIKE ?)"
            )
            pattern = _search_pattern(q)
            parameters.extend([pattern, f"%{''.join(filter(str.isdigit, q))}%"])
        if contracted_only:
            conditions.append("contract_count>0")
        where = " AND ".join(conditions)
        try:
            result = _paged(
                database,
                select_sql=f"SELECT * FROM gold_suppliers WHERE {where} "
                "ORDER BY contract_value DESC, paid_value DESC",
                count_sql=f"SELECT count(*) AS total FROM gold_suppliers WHERE {where}",
                parameters=parameters,
                page=page,
                page_size=page_size,
            )
            items = result["items"]
            profiles = database.profiles([str(item["cnpj"]) for item in items])
            for item in items:
                item["profile"] = profiles.get(str(item["cnpj"]))
            return result
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc

    @application.get("/api/expenses")
    def expenses(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        q: str | None = Query(None, max_length=100),
    ) -> dict[str, Any]:
        parameters: list[object] = []
        where = "expense_records>0"
        if q:
            where += " AND lower(coalesce(supplier_name,'')) LIKE ? ESCAPE '\\\\'"
            parameters.append(_search_pattern(q))
        columns = "cnpj, supplier_name, expense_records, committed_value, paid_value"
        try:
            return _paged(
                database,
                select_sql=f"SELECT {columns} FROM gold_suppliers WHERE {where} "
                "ORDER BY paid_value DESC",
                count_sql=f"SELECT count(*) AS total FROM gold_suppliers WHERE {where}",
                parameters=parameters,
                page=page,
                page_size=page_size,
            )
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc

    @application.get("/api/pipeline")
    def pipeline() -> list[dict[str, Any]]:
        try:
            return database.rows(
                "SELECT * FROM gold_procurement_pipeline ORDER BY procurement_count DESC"
            )
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc

    @application.get("/api/quality")
    def quality() -> list[dict[str, Any]]:
        try:
            return database.rows("SELECT * FROM gold_quality ORDER BY resource")
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc

    @application.get("/api/export/{dataset}.csv", response_class=Response)
    def export_csv(dataset: str) -> Response:
        query = EXPORTS.get(dataset)
        if query is None:
            raise HTTPException(status_code=404, detail="dataset de exportação inexistente")
        try:
            return _csv_response(dataset, database.rows(query))
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc

    @application.get("/")
    def root() -> dict[str, str]:
        return {"product": "Radar Público Cuiabá", "api_docs": "/api/docs"}

    return application


app = create_app()


def run(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    uvicorn.run("radar_publico.api:app", host=host, port=port, reload=reload)
