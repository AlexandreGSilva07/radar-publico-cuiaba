"""Cache empresarial seletivo."""

from pathlib import Path

import duckdb
import httpx
import respx

from radar_publico.enrich import (
    BRASIL_API_CEP,
    BRASIL_API_CNPJ,
    NOMINATIM_SEARCH,
    enrich_companies,
    geocode_company_addresses,
    geocode_company_postal_codes,
)
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
                "cep": 78000001,
                "codigo_municipio_ibge": 5103403,
                "email": "CONTATO@example.com",
                "ddd_telefone_1": "65999999999",
                "ddd_telefone_2": "6533334444",
                "regime_tributario": [
                    {"ano": 2024, "forma_de_tributacao": "LUCRO PRESUMIDO"},
                    {"ano": 2025, "forma_de_tributacao": "LUCRO REAL"},
                ],
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
        "SELECT legal_name, registration_status, primary_cnae, phone_primary, "
        "phone_secondary, email, tax_regime, tax_regime_year, municipality_ibge, postal_code "
        "FROM company_profile"
    ).fetchone() == (
        "Empresa teste",
        "ATIVA",
        "1234",
        "65999999999",
        "6533334444",
        "contato@example.com",
        "LUCRO REAL",
        2025,
        5103403,
        "78000001",
    )
    columns = {
        row[0]
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='company_profile'"
        ).fetchall()
    }
    connection.close()
    assert not {"qsa", "partner", "partner_document"} & columns


@respx.mock
def test_geocodes_cached_company_postal_codes(tmp_path: Path) -> None:
    cache = tmp_path / "enrichment.duckdb"
    connection = duckdb.connect(str(cache))
    connection.execute(
        "CREATE TABLE company_profile(cnpj VARCHAR, postal_code VARCHAR, city VARCHAR)"
    )
    connection.execute(
        "INSERT INTO company_profile VALUES ('00000000000191', '78000001', 'CUIABA')"
    )
    connection.close()
    route = respx.get(f"{BRASIL_API_CEP}/78000001").mock(
        return_value=httpx.Response(
            200,
            json={
                "cep": "78000001",
                "state": "MT",
                "city": "Cuiabá",
                "neighborhood": "Centro",
                "street": "Rua Teste",
                "service": "open-cep",
                "location": {
                    "type": "Point",
                    "coordinates": {"longitude": "-56.0979", "latitude": "-15.6014"},
                },
            },
        )
    )

    with PublicClient(backoff=0) as http:
        report = geocode_company_postal_codes(cache_path=cache, http=http, limit=10, interval=0)

    assert report.geocoded == 1
    assert route.call_count == 1
    connection = duckdb.connect(str(cache), read_only=True)
    assert connection.execute(
        "SELECT postal_code, longitude, latitude, provider FROM company_location"
    ).fetchone() == ("78000001", -56.0979, -15.6014, "open-cep")
    connection.close()


@respx.mock
def test_geocoding_prioritizes_official_agency_postal_codes(tmp_path: Path) -> None:
    cache = tmp_path / "enrichment.duckdb"
    connection = duckdb.connect(str(cache))
    connection.execute(
        "CREATE TABLE company_profile(cnpj VARCHAR, postal_code VARCHAR, city VARCHAR)"
    )
    connection.execute(
        "INSERT INTO company_profile VALUES ('00000000000191', '99999999', 'OUTRA CIDADE')"
    )
    connection.execute(
        "CREATE TABLE agency_directory(source_url VARCHAR PRIMARY KEY, directory_kind VARCHAR, "
        "slug VARCHAR, agency_name VARCHAR, address VARCHAR, postal_code VARCHAR, "
        "phones_json VARCHAR, emails_json VARCHAR, source_hash VARCHAR, fetched_at TIMESTAMP, "
        "address_scope VARCHAR)"
    )
    connection.execute(
        "INSERT INTO agency_directory VALUES ('https://example.test/orgao', 'orgao', 'orgao', "
        "'Órgão', 'Rua Teste', '78000002', '[]', '[]', 'hash', current_timestamp, 'unit')"
    )
    connection.close()
    agency_route = respx.get(f"{BRASIL_API_CEP}/78000002").mock(
        return_value=httpx.Response(
            200,
            json={
                "cep": "78000002",
                "state": "MT",
                "city": "Cuiabá",
                "location": {"coordinates": {"longitude": "-56.09", "latitude": "-15.60"}},
            },
        )
    )

    with PublicClient(backoff=0) as http:
        report = geocode_company_postal_codes(cache_path=cache, http=http, limit=1, interval=0)

    assert report.geocoded == 1
    assert agency_route.call_count == 1


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


@respx.mock
def test_refines_company_address_with_cached_nominatim_result(tmp_path: Path) -> None:
    cache = tmp_path / "enrichment.duckdb"
    connection = duckdb.connect(str(cache))
    connection.execute(
        "CREATE TABLE company_profile(cnpj VARCHAR, street VARCHAR, street_number VARCHAR, "
        "city VARCHAR, state VARCHAR, postal_code VARCHAR)"
    )
    connection.execute(
        "INSERT INTO company_profile VALUES "
        "('00000000000191', 'RUA SAO BENEDITO', '645', 'CUIABA', 'MT', '78008405')"
    )
    connection.close()
    route = respx.get(url__startswith=NOMINATIM_SEARCH).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "lat": "-15.5962153",
                    "lon": "-56.0889080",
                    "display_name": "Rua São Benedito, Lixeira, Cuiabá, Brasil",
                    "type": "residential",
                    "addresstype": "road",
                    "address": {"city": "Cuiabá", "country_code": "br"},
                }
            ],
        )
    )

    with PublicClient(backoff=0) as http:
        report = geocode_company_addresses(cache_path=cache, http=http, limit=1, interval=0)
        cached = geocode_company_addresses(cache_path=cache, http=http, limit=1, interval=0)

    assert report.geocoded == 1
    assert cached.attempted == 0
    assert route.call_count == 1
    request = route.calls[0].request
    assert request.url.params["countrycodes"] == "br"
    assert request.url.params["limit"] == "1"
    assert request.url.params["street"] == "645 RUA SAO BENEDITO"
    connection = duckdb.connect(str(cache), read_only=True)
    assert connection.execute(
        "SELECT provider, accuracy, longitude, latitude FROM company_address_location"
    ).fetchone() == ("nominatim-openstreetmap", "street", -56.088908, -15.5962153)
    connection.close()


@respx.mock
def test_address_geocoding_prioritizes_high_value_companies(tmp_path: Path) -> None:
    cache = tmp_path / "enrichment.duckdb"
    connection = duckdb.connect(str(cache))
    connection.execute(
        "CREATE TABLE company_profile(cnpj VARCHAR, street VARCHAR, street_number VARCHAR, "
        "city VARCHAR, state VARCHAR, postal_code VARCHAR)"
    )
    connection.execute(
        "INSERT INTO company_profile VALUES "
        "('00000000000191', 'RUA MENOR', '1', 'CUIABA', 'MT', '78000001'), "
        "('99999999000191', 'RUA PRIORITARIA', '2', 'CUIABA', 'MT', '78000002')"
    )
    connection.close()
    analytics_path = tmp_path / "analytics.duckdb"
    analytics = duckdb.connect(str(analytics_path))
    analytics.execute(
        "CREATE TABLE gold_suppliers(cnpj VARCHAR, paid_value DECIMAL(18,2), "
        "contract_value DECIMAL(18,2))"
    )
    analytics.execute(
        "INSERT INTO gold_suppliers VALUES "
        "('00000000000191', 10, 10), ('99999999000191', 1000, 1000)"
    )
    analytics.close()
    route = respx.get(url__startswith=NOMINATIM_SEARCH).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "lat": "-15.60",
                    "lon": "-56.09",
                    "display_name": "Rua Prioritária, Cuiabá, Brasil",
                    "type": "residential",
                    "addresstype": "road",
                    "address": {"city": "Cuiabá", "country_code": "br"},
                }
            ],
        )
    )

    with PublicClient(backoff=0) as http:
        report = geocode_company_addresses(
            cache_path=cache,
            analytics_path=analytics_path,
            http=http,
            limit=1,
            interval=0,
        )

    assert report.geocoded == 1
    assert route.calls[0].request.url.params["street"] == "2 RUA PRIORITARIA"
