"""Testes sentinela do pacote."""

from typer.testing import CliRunner

from radar_publico import __version__
from radar_publico.cli import app


def test_package_version_is_exposed_by_cli() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
