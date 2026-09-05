"""Contrato do manifesto de fontes."""

import json
from pathlib import Path

import pytest

from radar_publico.sources import ManifestError, load_manifest


def test_manifest_declares_three_verified_resources() -> None:
    manifest = load_manifest()

    assert set(manifest.resources) == {"contratos", "licitacoes", "despesas"}
    assert manifest.url("contratos", "query").endswith("/aapicontrato")
    form = manifest.resources["contratos"].form(year=2026, page=2, page_size=100)
    assert json.loads(form["pagination"])["currentPage"] == 2
    assert json.loads(form["filters"]) == {"ContratoAno": "2026"}


def test_manifest_rejects_missing_resources(tmp_path: Path) -> None:
    path = tmp_path / "bad.yml"
    path.write_text("version: 1\nsource_name: x\nbase_url: https://example.test\nresources: {}\n")

    with pytest.raises(ManifestError, match="recursos obrigatórios"):
        load_manifest(path)


def test_manifest_rejects_unknown_resource() -> None:
    with pytest.raises(ManifestError, match="recurso desconhecido"):
        load_manifest().url("folha", "query")
