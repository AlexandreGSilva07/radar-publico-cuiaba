# Radar Público Cuiabá

Inteligência comercial sobre compras públicas municipais, construída a partir de dados oficiais do Portal da Transparência de Cuiabá.

O MVP entrega um pipeline auditável e um dashboard executivo local com oportunidades, contratos, fornecedores PJ, órgãos compradores, execução financeira, qualidade dos dados e exportação CSV.

## Resultado atual

Snapshot operacional de 2026 validado em 4 de setembro de 2026:

| Domínio | Origem | Silver | Observação |
|---|---:|---:|---|
| Contratos | 170 | 156 | 14 duplicatas de paginação isoladas |
| Licitações | 174 | 174 | 12 em andamento |
| Despesas por credor | 2.150 | 2.150 | 1.204 CPFs suprimidos antes da Silver |

Indicadores atuais: R$ 100,5 milhões em contratos, R$ 1,35 bilhão pagos e 951 fornecedores/credores com CNPJ válido. Quarenta perfis prioritários já foram enriquecidos pela BrasilAPI no cache local.

## Início rápido

Requisitos: Python 3.12 e [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/AlexandreGSilva07/radar-publico-cuiaba.git
cd radar-publico-cuiaba
uv sync --locked --all-groups
```

Em um clone novo, gere os dados do ano desejado. `--live` é obrigatório para evitar acesso externo acidental:

```bash
uv run radar-cuiaba refresh --year 2026 --live --enrichment-limit 20
```

Depois, inicie o produto:

```bash
uv run radar-cuiaba serve
```

Acesse [http://127.0.0.1:8000](http://127.0.0.1:8000). A documentação interativa da API fica em `/api/docs`.

## Fluxo dos dados

```text
Portal de Cuiabá
      │ coleta paginada + cobertura
      ▼
Bronze JSON.gz imutável ── SHA-256 / runs / checkpoints
      │ normalização e proteção de CPF
      ▼
Silver DuckDB ── contratos / licitações / despesas / rejeições
      │ relações exatas e agregações reproduzíveis
      ▼
Gold DuckDB ── KPIs / oportunidades / renovações / rankings
      │                         │
      │                         └── BrasilAPI → cache CNPJ permitido
      ▼
FastAPI → dashboard responsivo + JSON + CSV
```

Uma coleta parcial nunca substitui o banco analítico. A transformação lê somente runs com páginas e registros integralmente reconciliados e publica o novo DuckDB por troca atômica.

## Comandos

```bash
# validar configuração sem rede
uv run radar-cuiaba validate-config

# verificar o contrato público de uma fonte
uv run radar-cuiaba smoke --resource contratos --live

# coletar ou retomar um recurso específico
uv run radar-cuiaba collect --resource contratos --year 2026 --cycle-id manual-2026 --live

# verificar cobertura de um run
uv run radar-cuiaba coverage --run-id UUID --validate

# reconstruir Silver e Gold sem rede
uv run radar-cuiaba transform --year 2026

# enriquecer apenas novos CNPJs válidos
uv run radar-cuiaba enrich --limit 20 --live

# cadeia completa
uv run radar-cuiaba refresh --year 2026 --live
```

Todos os artefatos operacionais ficam em `data/`, fora do Git:

- `data/ops.duckdb`: runs, requests, hashes e cobertura;
- `data/bronze/`: respostas originais comprimidas e imutáveis;
- `data/analytics.duckdb`: Silver e Gold publicadas;
- `data/enrichment.duckdb`: cache seletivo da BrasilAPI.

## API

| Rota | Uso |
|---|---|
| `GET /api/health` | saúde do banco analítico |
| `GET /api/meta` | ano, atualização, fonte e cobertura de enriquecimento |
| `GET /api/summary` | KPIs executivos |
| `GET /api/opportunities` | oportunidades filtráveis e paginadas |
| `GET /api/contracts` | contratos filtráveis e paginados |
| `GET /api/renewals` | vencimentos por horizonte em dias |
| `GET /api/agencies` | órgãos compradores |
| `GET /api/suppliers` | fornecedores PJ e perfil cadastral disponível |
| `GET /api/expenses` | execução agregada apenas para CNPJ válido |
| `GET /api/quality` | aceitação, rejeições e CPFs protegidos |
| `GET /api/export/{dataset}.csv` | exportação permitida e protegida contra fórmulas |

Listas aceitam `page` e `page_size`; filtros específicos aparecem no OpenAPI em `/api/docs`.

## Desenvolvimento

```bash
uv run ruff check src tests
uv run ruff format --check src tests
node --check src/radar_publico/web/app.js
uv run mypy src
uv run pytest
uv build
```

Os testes não acessam a rede. Chamadas HTTP são simuladas; validações ao vivo exigem `--live`.

## Docker

Gere `data/analytics.duckdb` no host antes de iniciar o container. O volume é montado como somente leitura:

```bash
cp .env.example .env
docker compose up --build
```

O dashboard ficará em `http://127.0.0.1:8000` ou na porta definida em `RADAR_PORT`.

## Privacidade e limites

- CPF não é gravado em Silver, Gold, cache CNPJ, API, tela, CSV ou logs.
- O enriquecimento persiste cadastro empresarial, CNAE e localização; QSA, telefone e e-mail são descartados.
- Vínculos empresariais entram nos indicadores somente por CNPJ válido e exato.
- A licitação não fornece CNPJ do vencedor no cabeçalho; nome semelhante não é tratado como identidade.
- Valores refletem a publicação da fonte e não constituem recomendação comercial ou garantia de contratação.

Leia a [especificação do MVP](docs/spec_01.md), o [plano executável](docs/plan_01.md), a [checagem da fonte](docs/data_check_01.md) e o [manual operacional](docs/operations.md).
