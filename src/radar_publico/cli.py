"""Linha de comando do Radar Público Cuiabá."""

import typer

from radar_publico import __version__

app = typer.Typer(add_completion=False, invoke_without_command=True, no_args_is_help=True)


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", help="Exibe a versão instalada."),
) -> None:
    """Coleta, transforma e publica dados do Radar Público Cuiabá."""
    if version:
        typer.echo(__version__)
        raise typer.Exit()


if __name__ == "__main__":
    app()
