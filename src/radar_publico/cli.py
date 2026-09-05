"""Linha de comando do Radar Público Cuiabá."""

from pathlib import Path

import typer

from radar_publico import __version__
from radar_publico.sources import ManifestError, load_manifest
from radar_publico.state import State

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


if __name__ == "__main__":
    app()
