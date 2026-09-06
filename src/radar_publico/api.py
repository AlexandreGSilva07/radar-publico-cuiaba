"""API de consulta somente leitura do Radar Público Cuiabá."""

from __future__ import annotations

import csv
import io
import json
import math
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from radar_publico import __version__
from radar_publico.agencies import directory_slugs_for
from radar_publico.normalize import search_text as normalize_search_text

PORTAL_URL = "https://transparencia.cuiaba.mt.gov.br/portaltransparencia/"


def _market_sector(cnae: object) -> str:
    digits = "".join(character for character in str(cnae or "") if character.isdigit())
    division = int(digits[:2]) if len(digits) >= 2 else -1
    ranges = (
        (1, 3, "Agropecuária"),
        (5, 9, "Indústrias extrativas"),
        (10, 33, "Indústrias de transformação"),
        (35, 35, "Energia"),
        (36, 39, "Água, esgoto e resíduos"),
        (41, 43, "Construção"),
        (45, 47, "Comércio"),
        (49, 53, "Transporte e logística"),
        (55, 56, "Alojamento e alimentação"),
        (58, 63, "Informação e comunicação"),
        (64, 66, "Serviços financeiros"),
        (68, 68, "Atividades imobiliárias"),
        (69, 75, "Serviços profissionais e técnicos"),
        (77, 82, "Serviços administrativos"),
        (84, 84, "Administração pública"),
        (85, 85, "Educação"),
        (86, 88, "Saúde e assistência social"),
        (90, 93, "Artes, cultura e esportes"),
        (94, 96, "Outros serviços"),
        (97, 97, "Serviços domésticos"),
        (99, 99, "Organismos internacionais"),
    )
    return next(
        (label for start, end, label in ranges if start <= division <= end),
        "Não classificado",
    )


def _entity_kind(legal_nature: object, primary_cnae: object) -> str:
    nature = normalize_search_text(str(legal_nature or "")).upper()
    cnae = "".join(character for character in str(primary_cnae or "") if character.isdigit())
    public_markers = (
        "ADMINISTRACAO PUBLICA",
        "AUTARQUIA",
        "FUNDO PUBLICO",
        "EMPRESA PUBLICA",
        "SOCIEDADE DE ECONOMIA MISTA",
        "ORGAO PUBLICO",
        "MUNICIPIO",
    )
    nonprofit_markers = (
        "ASSOCIACAO PRIVADA",
        "FUNDACAO PRIVADA",
        "ORGANIZACAO RELIGIOSA",
        "SINDICATO",
        "SERVICO SOCIAL AUTONOMO",
    )
    if cnae.startswith("84") or any(marker in nature for marker in public_markers):
        return "Setor público"
    if any(marker in nature for marker in nonprofit_markers):
        return "Terceiro setor"
    return "Empresa privada"


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
    "suppliers": (
        "SELECT cnpj, supplier_name, contract_count, contract_value, expense_records, "
        "committed_value, paid_value FROM gold_suppliers "
        "ORDER BY contract_value DESC, paid_value DESC"
    ),
    "expenses": (
        "SELECT cnpj, supplier_name, expense_records, committed_value, paid_value "
        "FROM gold_suppliers WHERE expense_records>0 ORDER BY paid_value DESC"
    ),
    "person-creditors": (
        "SELECT year, creditor_id, person_name, cpf_masked, committed_value, settled_value, "
        "paid_value, payment_rate, 'Portal da Transparência de Cuiabá' AS source, "
        f"'{PORTAL_URL}' AS source_url FROM gold_person_creditors "
        "ORDER BY paid_value DESC, committed_value DESC"
    ),
}

ANALYTICS_QUERIES = {
    "procurements_by_month": (
        "SELECT strftime(published_on, '%Y-%m') AS \"month\", count(*) AS procurement_count, "
        "coalesce(sum(estimated_value), 0) AS estimated_value, "
        "coalesce(sum(awarded_value), 0) AS awarded_value "
        "FROM silver_procurements WHERE published_on IS NOT NULL "
        "GROUP BY 1 ORDER BY 1"
    ),
    "contracts_by_month": (
        "SELECT strftime(signed_on, '%Y-%m') AS \"month\", count(*) AS contract_count, "
        "coalesce(sum(current_value), 0) AS contract_value "
        "FROM silver_contracts WHERE signed_on IS NOT NULL GROUP BY 1 ORDER BY 1"
    ),
    "procurement_statuses": (
        "SELECT status, count(*) AS procurement_count, "
        "coalesce(sum(estimated_value), 0) AS estimated_value, "
        "coalesce(sum(awarded_value), 0) AS awarded_value "
        "FROM silver_procurements GROUP BY status ORDER BY procurement_count DESC"
    ),
    "procurement_modalities": (
        "SELECT CASE "
        "WHEN upper(modality) LIKE '%PREGÃO ELETRÔNICO%' THEN 'Pregão eletrônico' "
        "WHEN upper(modality) LIKE '%INEXIGIBILIDADE%' THEN 'Inexigibilidade' "
        "WHEN upper(modality) LIKE '%CONCORRÊNCIA%' THEN 'Concorrência eletrônica' "
        "WHEN upper(modality) LIKE '%DISPENSA%' THEN 'Dispensa de licitação' "
        "WHEN upper(modality) LIKE '%COMPRA DIRETA%' THEN 'Compra direta' "
        "ELSE coalesce(modality, 'Não informado') END AS modality, "
        "count(*) AS procurement_count, coalesce(sum(estimated_value), 0) AS estimated_value "
        "FROM silver_procurements GROUP BY 1 ORDER BY procurement_count DESC"
    ),
    "top_agencies": (
        "SELECT agency, procurement_count, open_procurements, contract_count, contract_value, "
        "estimated_value, awarded_value FROM gold_agencies "
        "ORDER BY contract_value DESC, estimated_value DESC LIMIT 10"
    ),
    "top_suppliers": (
        "SELECT cnpj, supplier_name, contract_count, contract_value, paid_value "
        "FROM gold_suppliers WHERE contract_count > 0 "
        "ORDER BY contract_value DESC, paid_value DESC LIMIT 10"
    ),
    "renewals_by_month": (
        "SELECT strftime(ends_on, '%Y-%m') AS \"month\", count(*) AS contract_count, "
        "coalesce(sum(current_value), 0) AS contract_value FROM silver_contracts "
        "WHERE ends_on BETWEEN current_date AND current_date + INTERVAL 365 DAY "
        "GROUP BY 1 ORDER BY 1"
    ),
    "contract_categories": (
        "SELECT coalesce(category, 'Não informado') AS category, count(*) AS contract_count, "
        "coalesce(sum(current_value), 0) AS contract_value FROM silver_contracts "
        "GROUP BY 1 ORDER BY contract_value DESC LIMIT 10"
    ),
    "expense_leaders": (
        "SELECT cnpj, supplier_name, expense_records, committed_value, paid_value, "
        "round(100 * paid_value / nullif(committed_value, 0), 1) AS payment_rate "
        "FROM gold_suppliers WHERE committed_value > 0 "
        "ORDER BY paid_value DESC LIMIT 10"
    ),
    "top_person_creditors": (
        "SELECT creditor_id, year, person_name, cpf_masked, committed_value, settled_value, "
        "paid_value, payment_rate FROM gold_person_creditors "
        "ORDER BY paid_value DESC, committed_value DESC LIMIT 10"
    ),
    "open_opportunities_by_agency": (
        "SELECT agency, count(*) AS opportunity_count, "
        "coalesce(sum(estimated_value), 0) AS estimated_value "
        "FROM gold_opportunities GROUP BY agency "
        "ORDER BY opportunity_count DESC, estimated_value DESC LIMIT 10"
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
                "SELECT p.cnpj, p.legal_name, p.trade_name, p.registration_status, "
                "p.status_on, p.opened_on, p.headquarters_type, p.company_size, "
                "p.legal_nature, p.share_capital, p.primary_cnae, "
                "p.primary_cnae_description, p.secondary_cnaes_json, p.state, p.city, "
                "p.district, p.street, p.street_number, p.address_extra, p.postal_code, "
                "p.phone_primary, p.phone_secondary, p.email, p.tax_regime, "
                "p.tax_regime_year, p.municipality_ibge, p.simples, p.mei, "
                "p.source_url AS profile_source_url, p.fetched_at AS profile_fetched_at, "
                "coalesce(a.longitude, l.longitude) AS longitude, "
                "coalesce(a.latitude, l.latitude) AS latitude, "
                "CASE WHEN a.longitude IS NOT NULL THEN a.provider ELSE l.provider END "
                "AS geocode_provider, "
                "CASE WHEN a.longitude IS NOT NULL THEN a.accuracy "
                "WHEN l.longitude IS NOT NULL THEN 'postal_code' END AS geocode_accuracy, "
                "CASE WHEN a.longitude IS NOT NULL THEN a.source_url ELSE l.source_url END "
                "AS geocode_source_url, a.display_name AS geocode_display_name "
                "FROM company_profile p LEFT JOIN company_location l USING (postal_code) "
                "LEFT JOIN company_address_location a USING (cnpj) "
                f"WHERE p.cnpj IN ({placeholders})",
                cnpjs,
            )
            columns = [item[0] for item in result.description]
            return {str(row[0]): dict(zip(columns, row, strict=True)) for row in result.fetchall()}
        finally:
            connection.close()

    def market_companies(self) -> tuple[int, list[dict[str, Any]]]:
        metrics = self.rows(
            "SELECT cnpj, supplier_name, contract_count, contract_value, expense_records, "
            "committed_value, paid_value FROM gold_suppliers "
            "ORDER BY paid_value DESC, contract_value DESC"
        )
        profiles = self.profiles([str(item["cnpj"]) for item in metrics])
        items = [
            {
                **item,
                **profiles[str(item["cnpj"])],
                "market_sector": _market_sector(profiles[str(item["cnpj"])]["primary_cnae"]),
                "entity_kind": _entity_kind(
                    profiles[str(item["cnpj"])]["legal_nature"],
                    profiles[str(item["cnpj"])]["primary_cnae"],
                ),
            }
            for item in metrics
            if str(item["cnpj"]) in profiles
        ]
        return len(metrics), items

    def agency_directory(self) -> list[dict[str, Any]]:
        path = self.enrichment_path
        if path is None or not path.exists():
            return []
        connection = duckdb.connect(str(path), read_only=True)
        try:
            exists = connection.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name='agency_directory'"
            ).fetchone()
            if not exists or not exists[0]:
                return []
            result = connection.execute(
                "SELECT d.source_url, d.directory_kind, d.slug, d.agency_name, d.address, "
                "d.address_scope, d.postal_code, d.phones_json, d.emails_json, d.fetched_at, "
                "l.longitude, l.latitude, l.provider AS geocode_provider, "
                "l.source_url AS geocode_source_url FROM agency_directory d "
                "LEFT JOIN company_location l USING (postal_code) ORDER BY d.agency_name"
            )
            columns = [item[0] for item in result.description]
            rows = [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
            for row in rows:
                row["phones"] = json.loads(row.pop("phones_json"))
                row["emails"] = json.loads(row.pop("emails_json"))
            return rows
        finally:
            connection.close()

    def agency_intelligence(self) -> dict[str, Any]:
        agencies = self.rows(
            "SELECT agency, procurement_count, open_procurements, contract_count, "
            "contract_value, estimated_value, awarded_value FROM gold_agencies "
            "ORDER BY contract_value DESC, estimated_value DESC"
        )
        directory = self.agency_directory()
        by_slug = {str(item["slug"]): item for item in directory}
        matched = 0
        items = []
        for agency in agencies:
            locations = [
                by_slug[slug]
                for slug in directory_slugs_for(agency["agency"], directory)
                if slug in by_slug
            ]
            if locations:
                matched += 1
            items.append({**agency, "locations": locations})
        return {
            "coverage": {
                "agency_count": len(agencies),
                "matched_agency_count": matched,
                "directory_count": len(directory),
                "located_unit_count": sum(
                    item["longitude"] is not None and item["latitude"] is not None
                    for item in directory
                ),
            },
            "items": items,
        }


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
    normalized = normalize_search_text(query)
    escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
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
        description=(
            "Inteligência comercial e controle social derivados de dados públicos municipais."
        ),
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
            conditions.append("search_text LIKE ? ESCAPE '\\'")
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
            columns = (
                "procurement_id, number, year, object_text, agency, modality, status, "
                "published_on, session_on, estimated_value, has_document, relevance_score"
            )
            return _paged(
                database,
                select_sql=f"SELECT {columns} FROM gold_opportunities WHERE {where} "
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
                "(search_text LIKE ? ESCAPE '\\' OR "
                "strip_accents(lower(coalesce(supplier_name,''))) LIKE ? ESCAPE '\\')"
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
            where = "strip_accents(lower(agency)) LIKE ? ESCAPE '\\'"
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
            pattern = _search_pattern(q)
            digits = "".join(filter(str.isdigit, q))
            if digits:
                conditions.append("(supplier_search LIKE ? ESCAPE '\\' OR cnpj LIKE ?)")
                parameters.extend([pattern, f"%{digits}%"])
            else:
                conditions.append("supplier_search LIKE ? ESCAPE '\\'")
                parameters.append(pattern)
        if contracted_only:
            conditions.append("contract_count>0")
        where = " AND ".join(conditions)
        try:
            result = _paged(
                database,
                select_sql=(
                    "SELECT cnpj, supplier_name, contract_count, contract_value, "
                    "expense_records, committed_value, paid_value "
                    f"FROM gold_suppliers WHERE {where} "
                    "ORDER BY contract_value DESC, paid_value DESC"
                ),
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
            where += " AND supplier_search LIKE ? ESCAPE '\\'"
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

    @application.get("/api/person-creditors")
    def person_creditors(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        q: str | None = Query(None, max_length=100),
    ) -> dict[str, Any]:
        conditions = ["1=1"]
        parameters: list[object] = []
        if q:
            pattern = _search_pattern(q)
            digits = "".join(filter(str.isdigit, q))
            if digits:
                conditions.append(
                    "(person_search LIKE ? ESCAPE '\\' OR "
                    "regexp_replace(cpf_masked, '[^0-9]', '', 'g') LIKE ?)"
                )
                parameters.extend([pattern, f"%{digits}%"])
            else:
                conditions.append("person_search LIKE ? ESCAPE '\\'")
                parameters.append(pattern)
        where = " AND ".join(conditions)
        columns = (
            "creditor_id, year, person_name, cpf_masked, committed_value, settled_value, "
            "paid_value, payment_rate"
        )
        try:
            return _paged(
                database,
                select_sql=f"SELECT {columns} FROM gold_person_creditors WHERE {where} "
                "ORDER BY paid_value DESC, committed_value DESC, creditor_id",
                count_sql=f"SELECT count(*) AS total FROM gold_person_creditors WHERE {where}",
                parameters=parameters,
                page=page,
                page_size=page_size,
            )
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc

    @application.get("/api/market-intelligence")
    def market_intelligence() -> dict[str, Any]:
        try:
            supplier_count, items = database.market_companies()
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="enrichment database unavailable") from exc
        return {
            "coverage": {
                "supplier_count": supplier_count,
                "enriched_count": len(items),
                "located_count": sum(
                    item["longitude"] is not None and item["latitude"] is not None for item in items
                ),
                "phone_count": sum(bool(item["phone_primary"]) for item in items),
                "precise_location_count": sum(
                    item["geocode_accuracy"] in {"address", "street"} for item in items
                ),
            },
            "items": items,
            "sources": [
                {"name": "Portal da Transparência de Cuiabá", "url": PORTAL_URL},
                {"name": "BrasilAPI — CNPJ e CEP v2", "url": "https://brasilapi.com.br/docs"},
                {
                    "name": "OpenStreetMap — Nominatim",
                    "url": "https://www.openstreetmap.org/copyright",
                },
            ],
        }

    @application.get("/api/agency-intelligence")
    def agency_intelligence() -> dict[str, Any]:
        try:
            payload = database.agency_intelligence()
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="agency intelligence unavailable") from exc
        payload["sources"] = [
            {"name": "Portal da Transparência de Cuiabá", "url": PORTAL_URL},
            {
                "name": "Diretório oficial da Prefeitura",
                "url": "https://www.cuiaba.mt.gov.br/secretarias",
            },
        ]
        return payload

    @application.get("/api/pipeline")
    def pipeline() -> list[dict[str, Any]]:
        try:
            return database.rows(
                "SELECT * FROM gold_procurement_pipeline ORDER BY procurement_count DESC"
            )
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc

    @application.get("/api/analytics")
    def analytics() -> dict[str, list[dict[str, Any]]]:
        try:
            return {name: database.rows(query) for name, query in ANALYTICS_QUERIES.items()}
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
        if dataset == "agency-intelligence":
            try:
                payload = database.agency_intelligence()
            except (duckdb.Error, FileNotFoundError) as exc:
                raise HTTPException(
                    status_code=503, detail="agency intelligence unavailable"
                ) from exc
            fields = (
                "agency",
                "procurement_count",
                "open_procurements",
                "contract_count",
                "contract_value",
                "estimated_value",
                "awarded_value",
                "official_unit",
                "directory_kind",
                "address",
                "address_scope",
                "postal_code",
                "phones",
                "emails",
                "longitude",
                "latitude",
                "source_url",
                "geocode_source_url",
            )
            rows = []
            for agency in payload["items"]:
                locations = agency["locations"] or [{}]
                for location in locations:
                    row = {
                        **agency,
                        "official_unit": location.get("agency_name"),
                        **location,
                        "phones": " | ".join(location.get("phones", [])),
                        "emails": " | ".join(location.get("emails", [])),
                    }
                    rows.append({field: row.get(field) for field in fields})
            return _csv_response(dataset, rows)
        if dataset == "market-intelligence":
            try:
                _, companies = database.market_companies()
            except (duckdb.Error, FileNotFoundError) as exc:
                raise HTTPException(
                    status_code=503, detail="enrichment database unavailable"
                ) from exc
            fields = (
                "cnpj",
                "supplier_name",
                "legal_name",
                "trade_name",
                "registration_status",
                "company_size",
                "entity_kind",
                "legal_nature",
                "market_sector",
                "primary_cnae",
                "primary_cnae_description",
                "tax_regime",
                "tax_regime_year",
                "simples",
                "mei",
                "phone_primary",
                "phone_secondary",
                "email",
                "street",
                "street_number",
                "district",
                "postal_code",
                "city",
                "state",
                "longitude",
                "latitude",
                "contract_count",
                "contract_value",
                "expense_records",
                "committed_value",
                "paid_value",
                "geocode_provider",
                "geocode_accuracy",
                "geocode_display_name",
                "profile_source_url",
                "geocode_source_url",
            )
            rows = [{field: company.get(field) for field in fields} for company in companies]
            return _csv_response(dataset, rows)
        query = EXPORTS.get(dataset)
        if query is None:
            raise HTTPException(status_code=404, detail="dataset de exportação inexistente")
        try:
            return _csv_response(dataset, database.rows(query))
        except (duckdb.Error, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="analytics database unavailable") from exc

    web_root = Path(__file__).parent / "web"
    application.mount("/", StaticFiles(directory=web_root, html=True), name="dashboard")

    return application


app = create_app()


def run(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    uvicorn.run("radar_publico.api:app", host=host, port=port, reload=reload)
