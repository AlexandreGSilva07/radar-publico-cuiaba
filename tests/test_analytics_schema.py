"""Contrato físico da camada analítica."""

from importlib.resources import files

import duckdb


def test_analytics_schema_has_expected_tables_and_no_raw_document() -> None:
    connection = duckdb.connect(":memory:")
    sql = files("radar_publico").joinpath("migrations/002_analytics.sql").read_text()
    connection.execute(sql)

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
    }
    assert {
        "silver_contracts",
        "silver_procurements",
        "silver_expenses",
        "data_quality",
        "transform_rejections",
    } <= tables

    for table in ("silver_contracts", "silver_expenses"):
        columns = {
            row[0]
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=?", [table]
            ).fetchall()
        }
        assert "cnpj" in columns
        assert "document" not in columns
        assert "cpf" not in columns

    expense_columns = {
        row[0]
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='silver_expenses'"
        ).fetchall()
    }
    assert "cpf_masked" in expense_columns
