# Radar Público Cuiabá

Dashboard e pipeline auditável de compras públicas municipais.

## Desenvolvimento

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run radar-cuiaba --help
```

Dados operacionais são gravados em `data/` e nunca entram no Git.

Consulte [a especificação](docs/spec_01.md) e [o plano](docs/plan_01.md).
