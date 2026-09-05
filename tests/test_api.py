"""Contrato HTTP do produto."""

from importlib.resources import files
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from radar_publico.api import _csv_response, create_app


def _analytics(path: Path) -> None:
    connection = duckdb.connect(str(path))
    connection.execute(files("radar_publico").joinpath("migrations/002_analytics.sql").read_text())
    connection.execute(
        """
        INSERT INTO analytics_metadata VALUES ('built_at', '2026-09-04T12:00:00Z');
        INSERT INTO silver_procurements(
          procurement_id, year, search_text, status, estimated_value, awarded_value,
          has_document, source_run_id, source_hash
        ) VALUES (1, 2026, 'aquisicao cafe', 'EM ANDAMENTO', 100, 80, true, 'run', 'hash');
        INSERT INTO silver_contracts(
          contract_id, year, search_text, supplier_name, document_type, cnpj, status, current_value,
          has_document, source_run_id, source_hash
        ) VALUES (
          2, 2026, 'aquisicao cafe', 'Empresa Ágil', 'cnpj', '00000000000191',
          'Contrato Vigente', 80,
          false, 'run', 'hash'
        );
        INSERT INTO silver_contracts(
          contract_id, year, search_text, supplier_name, document_type, cnpj, status, current_value,
          has_document, source_run_id, source_hash
        ) VALUES (
          4, 2026, '', 'Outra Companhia', 'cnpj', '19131243000197', 'Contrato Vigente', 40,
          false, 'run', 'hash'
        );
        INSERT INTO silver_expenses(
          year, creditor_id, search_text, document_type, committed_value, settled_value,
          paid_value, source_run_id, source_hash
        ) VALUES (2026, 3, '', 'cpf', 70, 60, 50, 'run', 'hash');
        INSERT INTO data_quality VALUES ('contratos', 2026, 1, 1, 0, 0, 0, 0);
        """
    )
    connection.execute(files("radar_publico").joinpath("migrations/003_gold.sql").read_text())
    connection.close()


def test_health_metadata_and_summary(tmp_path: Path) -> None:
    analytics = tmp_path / "analytics.duckdb"
    _analytics(analytics)
    client = TestClient(create_app(analytics, tmp_path / "missing-enrichment.duckdb"))

    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/meta").json()["enriched_companies"] == 0
    summary = client.get("/api/summary")
    assert summary.status_code == 200
    assert summary.json()["open_procurements"] == 1
    assert summary.json()["committed_balance"] == "20.00"

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Radar Público Cuiabá" in dashboard.text
    assert client.get("/styles.css").status_code == 200


def test_health_reports_missing_database(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "missing.duckdb"))
    assert client.get("/api/health").status_code == 503


def test_lists_are_paginated_and_filters_are_validated(tmp_path: Path) -> None:
    analytics = tmp_path / "analytics.duckdb"
    _analytics(analytics)
    client = TestClient(create_app(analytics, tmp_path / "missing-enrichment.duckdb"))

    opportunities = client.get("/api/opportunities", params={"page_size": 1}).json()
    assert opportunities["total"] == 1
    assert opportunities["items"][0]["status"] == "EM ANDAMENTO"
    contracts = client.get("/api/contracts").json()
    assert contracts["total"] == 2
    assert "source_hash" not in contracts["items"][0]
    suppliers = client.get(
        "/api/suppliers", params={"contracted_only": True, "q": "Empresa Agil"}
    ).json()
    assert suppliers["total"] == 1
    assert suppliers["items"][0]["profile"] is None
    assert client.get("/api/opportunities", params={"q": "aquisicao"}).json()["total"] == 1
    assert client.get("/api/contracts", params={"q": "agil"}).json()["total"] == 1
    assert client.get("/api/contracts", params={"page_size": 101}).status_code == 422


def test_quality_and_pipeline_are_available(tmp_path: Path) -> None:
    analytics = tmp_path / "analytics.duckdb"
    _analytics(analytics)
    client = TestClient(create_app(analytics))

    assert client.get("/api/pipeline").json()[0]["status"] == "EM ANDAMENTO"
    assert client.get("/api/quality").json()[0]["acceptance_rate"] == 100.0


def test_csv_export_is_allowlisted_and_downloadable(tmp_path: Path) -> None:
    analytics = tmp_path / "analytics.duckdb"
    _analytics(analytics)
    client = TestClient(create_app(analytics))

    response = client.get("/api/export/contracts.csv")
    assert response.status_code == 200
    assert response.content.startswith("contract_id".encode("utf-8-sig"))
    assert "attachment" in response.headers["content-disposition"]
    assert "source_hash" not in response.text
    assert client.get("/api/export/bronze.csv").status_code == 404


def test_csv_escapes_spreadsheet_formulas() -> None:
    response = _csv_response("safe", [{"supplier": "=HYPERLINK('x')", "value": 1}])
    assert "'=HYPERLINK" in response.body.decode("utf-8-sig")
