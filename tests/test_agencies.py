"""Extração do diretório institucional oficial."""

import re
from pathlib import Path

import duckdb
import httpx
import respx

from radar_publico.agencies import (
    DIRECTORY_ROOT,
    directory_slugs_for,
    enrich_agency_directory,
)
from radar_publico.http import PublicClient


@respx.mock
def test_collects_official_agency_address_and_contacts(tmp_path: Path) -> None:
    secretariats = """
      <li class="secretary-item"><a href="/secretarias/governo">
        <h3 class="secretary-link-title mb-2">Governo</h3>
      </a></li>
      <a class="page-link" href="/secretarias?p=2">2</a>
    """
    secretariats_page_two = """
      <li class="secretary-item"><a href="/secretarias/saude">
        <h3 class="secretary-link-title mb-2">Saúde</h3>
      </a></li>
    """
    agencies = """
      <a href="/orgaos/cuiaba-regula" class="stretched-link">
        <h3 class="secretary-link-title mb-2">Cuiabá Regula</h3>
      </a>
    """
    detail = """
      <a href="tel:6533245903" class="phone">Recepção (65) 3324-5903</a>
      <a href="mailto:governo@cuiaba.mt.gov.br" class="email">E-mail</a>
      <address>Praça Alencastro, 158, Centro, Cuiabá-MT - 78005-360</address>
    """
    respx.get(re.compile(rf"{re.escape(DIRECTORY_ROOT)}/secretarias$")).mock(
        return_value=httpx.Response(200, text=secretariats)
    )
    respx.get(f"{DIRECTORY_ROOT}/orgaos").mock(return_value=httpx.Response(200, text=agencies))
    respx.get(f"{DIRECTORY_ROOT}/secretarias?p=2").mock(
        return_value=httpx.Response(200, text=secretariats_page_two)
    )
    respx.get(f"{DIRECTORY_ROOT}/secretarias/governo").mock(
        return_value=httpx.Response(200, text=detail)
    )
    respx.get(f"{DIRECTORY_ROOT}/orgaos/cuiaba-regula").mock(
        return_value=httpx.Response(200, text=detail)
    )
    respx.get(f"{DIRECTORY_ROOT}/secretarias/saude").mock(
        return_value=httpx.Response(200, text=detail)
    )

    cache = tmp_path / "enrichment.duckdb"
    with PublicClient(backoff=0) as http:
        report = enrich_agency_directory(cache_path=cache, http=http, interval=0)

    assert report.discovered == 3
    assert report.saved == 3
    connection = duckdb.connect(str(cache), read_only=True)
    assert connection.execute(
        "SELECT agency_name, postal_code, phones_json, emails_json, address_scope "
        "FROM agency_directory "
        "WHERE slug='governo'"
    ).fetchone() == (
        "Governo",
        "78005360",
        '["6533245903"]',
        '["governo@cuiaba.mt.gov.br"]',
        "unit",
    )
    connection.close()


def test_agency_matching_uses_only_exact_names_or_versioned_aliases() -> None:
    directory = [
        {"slug": "governo", "agency_name": "Governo"},
        {"slug": "educacao", "agency_name": "Educação"},
        {"slug": "cultura", "agency_name": "Cultura"},
        {"slug": "esportes-e-lazer", "agency_name": "Esportes e Lazer"},
    ]
    assert directory_slugs_for("SECRETARIA MUNICIPAL DE GOVERNO", directory) == ("governo",)
    assert directory_slugs_for(
        "SECRETARIA MUNICIPAL DE EDUCAÇÃO, CULTURA, ESPORTE E LAZER", directory
    ) == ("educacao", "cultura", "esportes-e-lazer")
    assert directory_slugs_for("Secretaria parecida", directory) == ()
