"""Paginação genérica e cobertura."""

from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from radar_publico.cli import app
from radar_publico.collect import collect
from radar_publico.http import PublicClient
from radar_publico.sources import load_manifest
from radar_publico.state import State


def page(total: int, start: int, count: int) -> list[dict[str, object]]:
    return [
        {
            "registers": [{"ContratoId": i} for i in range(start, start + count)],
            "totalRecords": total,
        }
    ]


@respx.mock
def test_collects_pages_and_preserves_bronze(tmp_path: Path) -> None:
    manifest = load_manifest()
    url = manifest.url("contratos", "query")
    route = respx.post(url).mock(
        side_effect=[
            httpx.Response(200, json=page(101, 0, 100)),
            httpx.Response(200, json=page(101, 100, 1)),
        ]
    )
    with State(tmp_path / "ops.duckdb") as state, PublicClient(backoff=0) as http:
        report = collect(
            manifest=manifest,
            resource_name="contratos",
            year=2026,
            state=state,
            http=http,
            bronze_root=tmp_path / "bronze",
            cycle_id="cycle",
        )
    assert report.status == "complete"
    assert report.collected_records == 101
    assert route.call_count == 2
    assert len(list((tmp_path / "bronze").rglob("*.json.gz"))) == 2


@respx.mock
def test_limit_is_partial_and_same_cycle_resumes(tmp_path: Path) -> None:
    manifest = load_manifest()
    route = respx.post(manifest.url("licitacoes", "query")).mock(
        side_effect=[
            httpx.Response(200, json=page(101, 0, 100)),
            httpx.Response(200, json=page(101, 100, 1)),
        ]
    )
    with State(tmp_path / "ops.duckdb") as state, PublicClient(backoff=0) as http:
        first = collect(
            manifest=manifest,
            resource_name="licitacoes",
            year=2026,
            state=state,
            http=http,
            bronze_root=tmp_path / "bronze",
            cycle_id="cycle",
            max_pages=1,
        )
        second = collect(
            manifest=manifest,
            resource_name="licitacoes",
            year=2026,
            state=state,
            http=http,
            bronze_root=tmp_path / "bronze",
            cycle_id="cycle",
        )
    assert first.status == "partial"
    assert second.status == "complete"
    assert route.call_count == 2


def test_cli_blocks_network_by_default(monkeypatch: object) -> None:
    result = CliRunner().invoke(app, ["collect", "--resource", "contratos", "--year", "2026"])
    assert result.exit_code == 2
    assert "bloqueada" in result.output
