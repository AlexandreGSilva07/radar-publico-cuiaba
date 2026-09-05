"""Contrato HTTP do produto."""

from importlib.resources import files
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from radar_publico.api import create_app


def _analytics(path: Path) -> None:
    connection = duckdb.connect(str(path))
    connection.execute(files("radar_publico").joinpath("migrations/002_analytics.sql").read_text())
    connection.execute(
        """
        INSERT INTO analytics_metadata VALUES ('built_at', '2026-09-04T12:00:00Z');
        INSERT INTO silver_procurements(
          procurement_id, year, search_text, status, estimated_value, awarded_value,
          has_document, source_run_id, source_hash
        ) VALUES (1, 2026, '', 'EM ANDAMENTO', 100, 80, true, 'run', 'hash');
        INSERT INTO silver_contracts(
          contract_id, year, search_text, document_type, status, current_value,
          has_document, source_run_id, source_hash
        ) VALUES (2, 2026, '', 'missing', 'Contrato Vigente', 80, false, 'run', 'hash');
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


def test_health_reports_missing_database(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "missing.duckdb"))
    assert client.get("/api/health").status_code == 503
