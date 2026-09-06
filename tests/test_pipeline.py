"""Atualização completa e transacional no nível do produto."""

from pathlib import Path

import httpx
import respx

from radar_publico.http import PublicClient
from radar_publico.pipeline import refresh
from radar_publico.sources import load_manifest


def _page(record: dict[str, object]) -> list[dict[str, object]]:
    return [{"totalRecords": 1, "registers": [record]}]


@respx.mock
def test_refresh_collects_all_sources_before_transforming(tmp_path: Path) -> None:
    manifest = load_manifest()
    respx.post(manifest.url("contratos", "query")).mock(
        return_value=httpx.Response(
            200,
            json=_page(
                {
                    "ContratoId": 1,
                    "ContratoAno": 2026,
                    "ContratoDsc": "Teste",
                    "ContratoLicitacaoId": 0,
                    "ContratoLicitacaoAno": 0,
                    "ContratoValor": "10.00",
                    "ContratoValorAtual": "10.00",
                }
            ),
        )
    )
    respx.post(manifest.url("licitacoes", "query")).mock(
        return_value=httpx.Response(
            200,
            json=_page(
                {
                    "LicitacaoId": 2,
                    "LicitacaoAno": 2026,
                    "LicitacaoObjeto": "Teste",
                    "LicitacaoValorEstimado": "20,00",
                }
            ),
        )
    )
    respx.post(manifest.url("despesas", "query")).mock(
        return_value=httpx.Response(
            200,
            json=_page(
                {
                    "DespesaCredorId": 3,
                    "DespesaCredorNome": "Teste",
                    "DespesaEmpenho": "30.00",
                    "DespesaLiquidacao": "20.00",
                    "DespesaPagamento": "10.00",
                }
            ),
        )
    )

    with PublicClient(backoff=0) as http:
        report = refresh(
            year=2026,
            ops_path=tmp_path / "ops.duckdb",
            bronze_root=tmp_path / "bronze",
            analytics_path=tmp_path / "analytics.duckdb",
            enrichment_path=tmp_path / "enrichment.duckdb",
            enrichment_limit=0,
            agency_directory_limit=0,
            geocoding_limit=0,
            cycle_id="integration-test",
            http=http,
        )

    assert [item.status for item in report.collections] == ["complete", "complete", "complete"]
    assert report.analytics.counts == {"contratos": 1, "licitacoes": 1, "despesas": 1}
    assert report.analytics.output_path.exists()
    assert report.agency_directory is None
