"""Cache empresarial seletivo."""

from pathlib import Path

import duckdb
import httpx
import respx

from radar_publico.enrich import BRASIL_API_CNPJ, enrich_companies
from radar_publico.http import PublicClient


@respx.mock
def test_enriches_only_whitelisted_company_fields(tmp_path: Path) -> None:
    analytics = tmp_path / "analytics.duckdb"
    connection = duckdb.connect(str(analytics))
    connection.execute(
        "CREATE TABLE gold_suppliers(cnpj VARCHAR, contract_count INTEGER, "
        "contract_value DECIMAL(18,2), paid_value DECIMAL(18,2))"
    )
    connection.execute("INSERT INTO gold_suppliers VALUES ('00000000000191', 1, 100, 50)")
    connection.close()
    route = respx.get(f"{BRASIL_API_CNPJ}/00000000000191").mock(
        return_value=httpx.Response(
            200,
            json={
                "cnpj": "00000000000191",
                "razao_social": "Empresa teste",
                "descricao_situacao_cadastral": "ATIVA",
                "cnae_fiscal": 1234,
                "cnae_fiscal_descricao": "Serviços",
                "email": "nao.persistir@example.com",
                "ddd_telefone_1": "65999999999",
                "qsa": [{"nome_socio": "Não Persistir"}],
            },
        )
    )

    cache = tmp_path / "enrichment.duckdb"
    with PublicClient(backoff=0) as http:
        report = enrich_companies(
            analytics_path=analytics,
            cache_path=cache,
            http=http,
            limit=10,
            interval=0,
        )
    assert report.enriched == 1
    assert route.call_count == 1

    connection = duckdb.connect(str(cache), read_only=True)
    assert connection.execute(
        "SELECT legal_name, registration_status, primary_cnae FROM company_profile"
    ).fetchone() == ("Empresa teste", "ATIVA", "1234")
    columns = {
        row[0]
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='company_profile'"
        ).fetchall()
    }
    connection.close()
    assert not {"email", "phone", "qsa", "partner"} & columns


def test_cli_or_function_cache_avoids_second_request(tmp_path: Path) -> None:
    analytics = tmp_path / "analytics.duckdb"
    connection = duckdb.connect(str(analytics))
    connection.execute(
        "CREATE TABLE gold_suppliers(cnpj VARCHAR, contract_count INTEGER, "
        "contract_value DECIMAL(18,2), paid_value DECIMAL(18,2))"
    )
    connection.execute("INSERT INTO gold_suppliers VALUES ('00000000000191', 1, 1, 1)")
    connection.close()
    cache = tmp_path / "enrichment.duckdb"

    with respx.mock:
        route = respx.get(f"{BRASIL_API_CNPJ}/00000000000191").mock(
            return_value=httpx.Response(200, json={"cnpj": "00000000000191"})
        )
        with PublicClient(backoff=0) as http:
            enrich_companies(
                analytics_path=analytics, cache_path=cache, http=http, limit=1, interval=0
            )
            second = enrich_companies(
                analytics_path=analytics, cache_path=cache, http=http, limit=1, interval=0
            )
        assert route.call_count == 1
        assert second.attempted == 0
