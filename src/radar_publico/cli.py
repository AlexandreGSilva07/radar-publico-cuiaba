"""Linha de comando do Radar Público Cuiabá."""

import json
from pathlib import Path
from uuid import uuid4

import typer

from radar_publico import __version__
from radar_publico.api import run as run_api
from radar_publico.collect import CollectionError, collect
from radar_publico.coverage import reports, require_valid
from radar_publico.enrich import (
    EnrichmentError,
    enrich_companies,
    geocode_company_postal_codes,
)
from radar_publico.http import HttpError, PublicClient
from radar_publico.pipeline import refresh
from radar_publico.sources import ManifestError, load_manifest
from radar_publico.state import State, StateError
from radar_publico.transform import TransformError, build_analytics

app = typer.Typer(add_completion=False, invoke_without_command=True, no_args_is_help=True)


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", help="Exibe a versão instalada."),
) -> None:
    """Coleta, transforma e publica dados do Radar Público Cuiabá."""
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command("validate-config")
def validate_config(
    path: Path = typer.Option(Path("config/sources/cuiaba.yml"), exists=True, dir_okay=False),
) -> None:
    """Valida o manifesto sem acessar a rede."""
    try:
        manifest = load_manifest(path)
    except ManifestError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Manifesto válido: {', '.join(manifest.resources)}")


@app.command("init-state")
def init_state(path: Path = typer.Option(Path("data/ops.duckdb"))) -> None:
    """Inicializa o banco operacional local."""
    with State(path):
        pass
    typer.echo(f"Estado pronto: {path}")


@app.command("smoke")
def smoke(
    resource: str = typer.Option(...),
    live: bool = typer.Option(False, help="Autoriza uma consulta externa."),
) -> None:
    """Consulta somente o catálogo de filtros."""
    if not live:
        typer.echo("Rede bloqueada; use --live.")
        return
    manifest = load_manifest()
    with PublicClient() as http:
        response = http.get(manifest.url(resource, "filter"))
    typer.echo(f"Smoke OK: resource={resource} fields={len(response.payload)}")


@app.command("collect")
def collect_command(
    resource: str = typer.Option(...),
    year: int = typer.Option(...),
    live: bool = typer.Option(False, help="Autoriza rede e Bronze local."),
    max_pages: int | None = typer.Option(None, min=1),
    cycle_id: str | None = typer.Option(None),
    state_path: Path = typer.Option(Path("data/ops.duckdb")),
    bronze_path: Path = typer.Option(Path("data/bronze")),
) -> None:
    """Coleta um recurso/ano explicitamente autorizado."""
    if not live:
        typer.echo("Coleta bloqueada; use --live.", err=True)
        raise typer.Exit(2)
    try:
        manifest = load_manifest()
        with State(state_path) as state, PublicClient() as http:
            report = collect(
                manifest=manifest,
                resource_name=resource,
                year=year,
                state=state,
                http=http,
                bronze_root=bronze_path,
                cycle_id=cycle_id or str(uuid4()),
                max_pages=max_pages,
            )
    except (CollectionError, HttpError, ManifestError) as exc:
        typer.echo(f"Coleta falhou: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"run={report.run_id} cycle={report.cycle_id} status={report.status} "
        f"pages={report.collected_pages}/{report.expected_pages} "
        f"records={report.collected_records}/{report.expected_records}"
    )


@app.command("coverage")
def coverage_command(
    state_path: Path = typer.Option(Path("data/ops.duckdb")),
    run_id: str | None = typer.Option(None),
    validate: bool = typer.Option(False, help="Falha se o run não estiver completo."),
) -> None:
    """Exibe cobertura local em JSON."""
    try:
        with State(state_path) as state:
            if validate:
                if run_id is None:
                    raise typer.BadParameter("--run-id é obrigatório com --validate")
                require_valid(state, run_id)
            payload = [item.dict() for item in reports(state, run_id)]
    except StateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command("transform")
def transform_command(
    year: int = typer.Option(...),
    ops_path: Path = typer.Option(Path("data/ops.duckdb")),
    bronze_path: Path = typer.Option(Path("data/bronze")),
    output_path: Path = typer.Option(Path("data/analytics.duckdb")),
) -> None:
    """Reconstrói a camada Silver a partir de snapshots completos."""
    try:
        report = build_analytics(
            ops_path=ops_path,
            bronze_root=bronze_path,
            output_path=output_path,
            year=year,
        )
    except TransformError as exc:
        typer.echo(f"Transformação falhou: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"Silver pronta: year={report.year} counts={report.counts} "
        f"rejected={report.rejected} path={report.output_path}"
    )


@app.command("enrich")
def enrich_command(
    live: bool = typer.Option(False, help="Autoriza consultas à BrasilAPI."),
    limit: int = typer.Option(20, min=1, help="Máximo de CNPJs consultados nesta execução."),
    max_age_days: int = typer.Option(30, min=0, help="Validade do perfil em cache."),
    analytics_path: Path = typer.Option(Path("data/analytics.duckdb")),
    cache_path: Path = typer.Option(Path("data/enrichment.duckdb")),
) -> None:
    """Enriquece CNPJs prioritários usando cache local."""
    if not live:
        typer.echo("Enriquecimento bloqueado; use --live.", err=True)
        raise typer.Exit(2)
    try:
        with PublicClient() as http:
            report = enrich_companies(
                analytics_path=analytics_path,
                cache_path=cache_path,
                http=http,
                limit=limit,
                max_age_days=max_age_days,
            )
    except EnrichmentError as exc:
        typer.echo(f"Enriquecimento falhou: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"Enriquecimento concluído: candidates={report.candidates} "
        f"attempted={report.attempted} enriched={report.enriched} "
        f"failed={report.failed} cached={report.cached}"
    )


@app.command("geocode")
def geocode_command(
    live: bool = typer.Option(False, help="Autoriza consultas de CEP à BrasilAPI."),
    limit: int = typer.Option(50, min=1, help="Máximo de CEPs consultados nesta execução."),
    max_age_days: int = typer.Option(180, min=0, help="Validade da coordenada em cache."),
    cache_path: Path = typer.Option(Path("data/enrichment.duckdb")),
) -> None:
    """Geocodifica CEPs empresariais cacheados para visualização em mapa."""
    if not live:
        typer.echo("Geocodificação bloqueada; use --live.", err=True)
        raise typer.Exit(2)
    try:
        with PublicClient() as http:
            report = geocode_company_postal_codes(
                cache_path=cache_path,
                http=http,
                limit=limit,
                max_age_days=max_age_days,
            )
    except EnrichmentError as exc:
        typer.echo(f"Geocodificação falhou: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"Geocodificação concluída: candidates={report.candidates} "
        f"attempted={report.attempted} geocoded={report.geocoded} "
        f"missing_coordinates={report.missing_coordinates} failed={report.failed} "
        f"cached={report.cached}"
    )


@app.command("serve")
def serve_command(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000, min=1, max=65535),
    reload: bool = typer.Option(False),
) -> None:
    """Inicia a API e o dashboard local."""
    run_api(host=host, port=port, reload=reload)


@app.command("refresh")
def refresh_command(
    year: int = typer.Option(...),
    live: bool = typer.Option(False, help="Autoriza coleta e enriquecimento externos."),
    enrichment_limit: int = typer.Option(20, min=0),
    cycle_id: str | None = typer.Option(None),
    ops_path: Path = typer.Option(Path("data/ops.duckdb")),
    bronze_path: Path = typer.Option(Path("data/bronze")),
    analytics_path: Path = typer.Option(Path("data/analytics.duckdb")),
    enrichment_path: Path = typer.Option(Path("data/enrichment.duckdb")),
) -> None:
    """Coleta, valida, transforma e enriquece em uma única execução."""
    if not live:
        typer.echo("Atualização bloqueada; use --live.", err=True)
        raise typer.Exit(2)
    try:
        report = refresh(
            year=year,
            ops_path=ops_path,
            bronze_root=bronze_path,
            analytics_path=analytics_path,
            enrichment_path=enrichment_path,
            enrichment_limit=enrichment_limit,
            cycle_id=cycle_id,
        )
    except (
        CollectionError,
        EnrichmentError,
        HttpError,
        ManifestError,
        StateError,
        TransformError,
    ) as exc:
        typer.echo(f"Atualização falhou: {exc}", err=True)
        raise typer.Exit(1) from exc
    collection_counts = ", ".join(
        f"{item.resource}: {item.collected_records}" for item in report.collections
    )
    typer.echo(
        f"Atualização concluída: cycle={report.cycle_id} year={year} "
        f"collections={{{collection_counts}}} "
        f"silver={report.analytics.counts}"
    )


if __name__ == "__main__":
    app()
