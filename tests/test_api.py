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
          procurement_id, year, search_text, agency, modality, status, published_on, session_on,
          estimated_value, awarded_value, has_document, source_run_id, source_hash
        ) VALUES (
          1, 2026, 'aquisicao cafe', 'Secretaria Teste', 'PREGÃO ELETRÔNICO - 13',
          'EM ANDAMENTO', '2026-01-15', '2026-02-01', 100, 80, true, 'run', 'hash'
        );
        INSERT INTO silver_contracts(
          contract_id, year, search_text, agency, supplier_name, document_type, cnpj, status,
          signed_on, ends_on, category, current_value, has_document, source_run_id, source_hash
        ) VALUES (
          2, 2026, 'aquisicao cafe', 'Secretaria Teste', 'Empresa Ágil', 'cnpj',
          '00000000000191', 'Contrato Vigente', '2026-01-20', '2027-01-20', 'Serviços', 80,
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
          year, creditor_id, creditor_name, search_text, document_type, cpf_masked,
          committed_value, settled_value,
          paid_value, source_run_id, source_hash
        ) VALUES (
          2026, 3, 'Pessoa de Teste', 'pessoa de teste', 'cpf', '***.000.001-**',
          70, 60, 50, 'run', 'hash'
        );
        INSERT INTO data_quality VALUES ('contratos', 2026, 1, 1, 0, 0, 0, 0);
        """
    )
    connection.execute(files("radar_publico").joinpath("migrations/003_gold.sql").read_text())
    connection.close()


def _enrichment(path: Path) -> None:
    connection = duckdb.connect(str(path))
    connection.execute(files("radar_publico").joinpath("migrations/004_enrichment.sql").read_text())
    connection.execute(
        """
        INSERT INTO company_profile(
          cnpj, cnpj_root, legal_name, trade_name, registration_status, company_size,
          legal_nature, share_capital, primary_cnae, primary_cnae_description,
          secondary_cnaes_json, state, city, district, street, street_number, postal_code,
          phone_primary, email, tax_regime, tax_regime_year, municipality_ibge, simples, mei,
          source_url, fetched_at
        ) VALUES (
          '00000000000191', '00000000', 'Empresa Ágil Ltda', 'Ágil', 'ATIVA',
          'MICRO EMPRESA', 'Sociedade Empresária Limitada', 50000, '6201501',
          'Desenvolvimento de programas de computador sob encomenda', '[]', 'MT', 'CUIABA',
          'CENTRO', 'RUA TESTE', '10', '78000001', '65999999999', 'contato@agil.test',
          'LUCRO PRESUMIDO', 2025, 5103403, true, false,
          'https://brasilapi.com.br/api/cnpj/v1/00000000000191', current_timestamp
        );
        INSERT INTO company_location VALUES (
          '78000001', 'MT', 'Cuiabá', 'Centro', 'Rua Teste', 'open-cep',
          -56.0979, -15.6014, 'https://brasilapi.com.br/api/cep/v2/78000001',
          current_timestamp
        );
        """
    )
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
    assert "Mercado público de Cuiabá" in dashboard.text
    assert 'id="procurements-month-chart"' in dashboard.text
    assert 'id="finance-stage-chart"' in dashboard.text
    assert 'id="renewals-chart"' in dashboard.text
    assert 'id="opportunities-agency-chart"' in dashboard.text
    assert 'id="contracts-month-chart"' in dashboard.text
    assert 'id="suppliers-contract-chart"' in dashboard.text
    assert 'id="agencies-value-chart"' in dashboard.text
    assert 'id="expenses-leaders-chart"' in dashboard.text
    assert 'id="view-people"' in dashboard.text
    assert 'id="people-leaders-chart"' in dashboard.text
    assert 'id="people-stages-chart"' in dashboard.text
    assert "CPF mascarado" in dashboard.text
    assert 'id="sidebar-backdrop"' in dashboard.text
    assert 'id="report-button"' in dashboard.text
    assert client.get("/styles.css").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.get("/charts-lib/theme.js").status_code == 200
    assert client.get("/charts-lib/charts.js").status_code == 200
    assert client.get("/cuiaba-boundary.js").status_code == 200


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


def test_person_creditors_are_separate_masked_and_not_enriched(tmp_path: Path) -> None:
    analytics = tmp_path / "analytics.duckdb"
    _analytics(analytics)
    client = TestClient(create_app(analytics, tmp_path / "missing-enrichment.duckdb"))

    response = client.get("/api/person-creditors", params={"q": "000001"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0] == {
        "creditor_id": 3,
        "year": 2026,
        "person_name": "Pessoa de Teste",
        "cpf_masked": "***.000.001-**",
        "committed_value": "70.00",
        "settled_value": "60.00",
        "paid_value": "50.00",
        "payment_rate": 71.4,
    }
    assert "profile" not in payload["items"][0]
    assert "00000000191" not in response.text


def test_market_intelligence_connects_company_metrics_profile_and_location(
    tmp_path: Path,
) -> None:
    analytics = tmp_path / "analytics.duckdb"
    enrichment = tmp_path / "enrichment.duckdb"
    _analytics(analytics)
    _enrichment(enrichment)
    client = TestClient(create_app(analytics, enrichment))

    response = client.get("/api/market-intelligence")
    assert response.status_code == 200
    payload = response.json()
    assert payload["coverage"] == {
        "supplier_count": 2,
        "enriched_count": 1,
        "located_count": 1,
        "phone_count": 1,
    }
    company = payload["items"][0]
    assert company["supplier_name"] == "Empresa Ágil"
    assert company["primary_cnae"] == "6201501"
    assert company["market_sector"] == "Informação e comunicação"
    assert company["phone_primary"] == "65999999999"
    assert company["tax_regime"] == "LUCRO PRESUMIDO"
    assert company["longitude"] == -56.0979
    assert company["latitude"] == -15.6014
    assert "qsa" not in company
    assert payload["sources"][0]["name"] == "Portal da Transparência de Cuiabá"

    export = client.get("/api/export/market-intelligence.csv")
    assert export.status_code == 200
    assert "65999999999" in export.text
    assert "LUCRO PRESUMIDO" in export.text
    assert "-56.0979" in export.text
    assert "qsa" not in export.text


def test_quality_and_pipeline_are_available(tmp_path: Path) -> None:
    analytics = tmp_path / "analytics.duckdb"
    _analytics(analytics)
    client = TestClient(create_app(analytics))

    assert client.get("/api/pipeline").json()[0]["status"] == "EM ANDAMENTO"
    assert client.get("/api/quality").json()[0]["acceptance_rate"] == 100.0


def test_analytics_exposes_chart_ready_aggregates(tmp_path: Path) -> None:
    analytics = tmp_path / "analytics.duckdb"
    _analytics(analytics)
    payload = TestClient(create_app(analytics)).get("/api/analytics")

    assert payload.status_code == 200
    data = payload.json()
    assert data["procurements_by_month"][0] == {
        "month": "2026-01",
        "procurement_count": 1,
        "estimated_value": "100.00",
        "awarded_value": "80.00",
    }
    assert data["procurement_modalities"][0]["modality"] == "Pregão eletrônico"
    assert data["top_agencies"][0]["agency"] == "Secretaria Teste"
    assert data["contract_categories"][0]["category"] == "Serviços"
    assert data["top_person_creditors"][0]["cpf_masked"] == "***.000.001-**"


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

    people = client.get("/api/export/person-creditors.csv")
    assert people.status_code == 200
    assert "Pessoa de Teste" in people.text
    assert "***.000.001-**" in people.text
    assert "Portal da Transparência de Cuiabá" in people.text
    assert "00000000191" not in people.text


def test_csv_escapes_spreadsheet_formulas() -> None:
    response = _csv_response("safe", [{"supplier": "=HYPERLINK('x')", "value": 1}])
    assert "'=HYPERLINK" in response.body.decode("utf-8-sig")
