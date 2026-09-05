"""Semântica das visões executivas Gold."""

from importlib.resources import files

import duckdb


def test_gold_views_expose_business_metrics() -> None:
    connection = duckdb.connect(":memory:")
    connection.execute(files("radar_publico").joinpath("migrations/002_analytics.sql").read_text())
    connection.execute(
        """
        INSERT INTO silver_procurements(
          procurement_id, year, search_text, status, estimated_value, awarded_value,
          has_document, source_run_id, source_hash
        ) VALUES (1, 2026, '', 'EM ANDAMENTO', 100, 80, true, 'run', 'hash');
        INSERT INTO silver_contracts(
          contract_id, year, search_text, document_type, status, current_value,
          has_document, source_run_id, source_hash
        ) VALUES (2, 2026, '', 'missing', 'Contrato Vigente', 80, false, 'run', 'hash');
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

    kpis = connection.execute(
        "SELECT open_procurements, procurement_savings, contract_value, committed_balance, "
        "person_creditor_count, person_paid_value "
        "FROM gold_kpis"
    ).fetchone()
    assert kpis == (1, 20, 80, 20, 1, 50)
    assert connection.execute("SELECT relevance_score FROM gold_opportunities").fetchone()[0] == 115
    assert connection.execute("SELECT acceptance_rate FROM gold_quality").fetchone()[0] == 100
    assert connection.execute(
        "SELECT person_name, cpf_masked, paid_value FROM gold_person_creditors"
    ).fetchone() == ("Pessoa de Teste", "***.000.001-**", 50)
