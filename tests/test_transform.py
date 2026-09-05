"""Materialização Bronze -> Silver."""

import json
from pathlib import Path

import duckdb

from radar_publico.bronze import BronzeStore
from radar_publico.state import State
from radar_publico.transform import build_analytics


def _snapshot(
    state: State,
    store: BronzeStore,
    resource: str,
    year: int,
    records: list[dict[str, object]],
) -> None:
    run = state.start_run(resource, year, "test-cycle")
    content = json.dumps([{"totalRecords": len(records), "registers": records}]).encode()
    bronze = store.write(resource, year, 0, content)
    request = state.start_request(run.run_id, 0)
    object_id = state.record_object(bronze.content_hash, bronze.relative_path)
    state.complete_page(
        request, object_id=object_id, record_count=len(records), total_records=len(records)
    )
    state.set_coverage(
        run.run_id,
        expected_pages=1,
        collected_pages=1,
        expected_records=len(records),
        collected_records=len(records),
        status="complete",
    )
    state.finish_run(run.run_id, "succeeded")


def test_builds_atomic_silver_and_suppresses_cpf(tmp_path: Path) -> None:
    bronze_root = tmp_path / "bronze"
    store = BronzeStore(bronze_root)
    with State(tmp_path / "ops.duckdb") as state:
        _snapshot(
            state,
            store,
            "contratos",
            2026,
            [
                {
                    "ContratoId": 1,
                    "ContratoAno": 2026,
                    "ContratoDsc": "Aquisição de café",
                    "ContratoFornecedorDoc": "00.000.000/0001-91",
                    "ContratoLicitacaoId": 0,
                    "ContratoLicitacaoAno": 0,
                    "ContratoValor": "1.234,50",
                    "ContratoValorAtual": "1234.50",
                },
                {
                    "ContratoId": 1,
                    "ContratoAno": 2026,
                    "ContratoDsc": "Duplicata de paginação",
                    "ContratoFornecedorDoc": "00.000.000/0001-91",
                    "ContratoLicitacaoId": 0,
                    "ContratoLicitacaoAno": 0,
                    "ContratoValor": "1.234,50",
                    "ContratoValorAtual": "1234.50",
                },
            ],
        )
        _snapshot(
            state,
            store,
            "licitacoes",
            2026,
            [
                {
                    "LicitacaoId": 2,
                    "LicitacaoAno": 2026,
                    "LicitacaoObjeto": "Compra de café",
                    "LicitacaoData": "2026-01-01",
                    "LicitacaoDataSessao": "0000-00-00",
                    "LicitacaoValorEstimado": "2.000,00",
                }
            ],
        )
        _snapshot(
            state,
            store,
            "despesas",
            2026,
            [
                {
                    "DespesaCredorId": 3,
                    "DespesaCredorDoc": "000.000.001-91",
                    "DespesaCredorNome": "Pessoa protegida",
                    "DespesaEmpenho": "10.00",
                    "DespesaLiquidacao": "8.00",
                    "DespesaPagamento": "7.00",
                }
            ],
        )

    output = tmp_path / "analytics.duckdb"
    report = build_analytics(
        ops_path=tmp_path / "ops.duckdb",
        bronze_root=bronze_root,
        output_path=output,
        year=2026,
    )

    assert report.counts == {"contratos": 1, "licitacoes": 1, "despesas": 1}
    assert report.rejected["contratos"] == 1
    connection = duckdb.connect(str(output), read_only=True)
    assert connection.execute("SELECT cnpj FROM silver_contracts").fetchone()[0] == "00000000000191"
    assert connection.execute(
        "SELECT document_type, cnpj FROM silver_expenses"
    ).fetchone() == ("cpf", None)
    assert connection.execute(
        "SELECT cpf_suppressed_records FROM data_quality WHERE resource='despesas'"
    ).fetchone()[0] == 1
    connection.close()
