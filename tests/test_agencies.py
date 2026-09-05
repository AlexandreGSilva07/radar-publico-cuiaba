"""Extração do diretório institucional oficial."""

from pathlib import Path

import duckdb
import httpx
import respx

from radar_publico.agencies import DIRECTORY_ROOT, enrich_agency_directory
from radar_publico.http import PublicClient


@respx.mock
def test_collects_official_agency_address_and_contacts(tmp_path: Path) -> None:
    secretariats = """
      <li class="secretary-item"><a href="/secretarias/governo">
        <h3 class="secretary-link-title mb-2">Governo</h3>
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
    respx.get(f"{DIRECTORY_ROOT}/secretarias").mock(
        return_value=httpx.Response(200, text=secretariats)
    )
    respx.get(f"{DIRECTORY_ROOT}/orgaos").mock(return_value=httpx.Response(200, text=agencies))
    respx.get(f"{DIRECTORY_ROOT}/secretarias/governo").mock(
        return_value=httpx.Response(200, text=detail)
    )
    respx.get(f"{DIRECTORY_ROOT}/orgaos/cuiaba-regula").mock(
        return_value=httpx.Response(200, text=detail)
    )

    cache = tmp_path / "enrichment.duckdb"
    with PublicClient(backoff=0) as http:
        report = enrich_agency_directory(cache_path=cache, http=http, interval=0)

    assert report.discovered == 2
    assert report.saved == 2
    connection = duckdb.connect(str(cache), read_only=True)
    assert connection.execute(
        "SELECT agency_name, postal_code, phones_json, emails_json FROM agency_directory "
        "WHERE slug='governo'"
    ).fetchone() == (
        "Governo",
        "78005360",
        '["6533245903"]',
        '["governo@cuiaba.mt.gov.br"]',
    )
    connection.close()
