# PLAN 01 — Execução integral do MVP

**Derivado de:** `spec_01.md` e `data_check_01.md`
**Regra:** cada item termina em validação, commit e push antes do seguinte.

## 1. Ingestão

### I1 — Bootstrap

Python 3.12, `uv`, CLI, pytest, Ruff e mypy. Aceite: instalação limpa e suite local sem rede.

### I2 — Manifesto

Declarar contratos, licitações e despesas por credor: endpoints, métodos, campos de ano, chave natural, paginação e política de atualização. Aceite: configuração inválida falha antes da rede.

### I3 — Estado operacional

DuckDB local com runs, requests, objetos Bronze, tentativas e cobertura. Aceite: mesmo ciclo retoma; ciclo novo cria execução nova; migrations são idempotentes.

### I4 — HTTP e Bronze

Timeout, retry limitado, erro sanitizado, JSON gzip escrito por temporário + `os.replace`, SHA-256 e proveniência. Aceite: drift ainda é preservado; corpo/CPF nunca aparece em log.

### I5 — Coleta paginada

Motor único por manifesto, `--live`, ano explícito, `--max-pages` e `cycle-id`. Aceite: contratos/licitações/despesas reconciliam páginas e `totalRecords`; parcial nunca vira completo.

### I6 — Cobertura

Relatório texto/JSON e validador com código não zero. Aceite: completo, parcial, vazio, falho e não verificado são distintos.

## 2. ETL

### E1 — Normalizadores

Funções puras para dinheiro, data, texto e documento. Testar sentinelas, valores brasileiros, CNPJ DV e CPF descartado.

### E2 — Silver

DuckDB independente com `dim_orgao`, `dim_fornecedor`, `fct_contrato`, `fct_licitacao`, `bridge_licitacao_fornecedor`, `fct_despesa_credor` e rejeições. Toda linha tem proveniência.

### E3 — Enriquecimento

Cache BrasilAPI somente por CNPJ válido, sem QSA/telefone/e-mail. Falha externa não bloqueia transformação municipal.

### E4 — Gold

Views de oportunidades, renovação, órgãos, fornecedores, despesas PJ e qualidade. Somente relações `exact` entram nos totais empresariais.

## 3. Produto

### P1 — API

FastAPI com health, resumo, oportunidades, contratos, órgãos, fornecedores, despesas, qualidade e CSV. Filtros e paginação obrigatórios nas listas.

### P2 — Dashboard

Frontend estático responsivo servido pelo FastAPI, com navegação lateral, cards, gráficos, tabelas, filtros globais, estados de carregamento/erro/vazio e links de origem.

### P3 — Operação

Comando único para coletar/transformar, README, `.env.example`, Docker e CI. Aceite: novo clone executa testes e sobe o dashboard documentadamente.

## 4. Gates finais

- G1: smoke dos filtros e uma página por recurso.
- G2: carga real reconciliada do ano corrente.
- G3: Silver sem CPF, sem `float`, com rejeições rastreáveis.
- G4: totais Gold reproduzíveis por SQL/testes.
- G5: dashboard abre no navegador, API saudável e CSV válido.

Dados reais, bancos, Bronze, Parquet e caches ficam em `data/`, ignorados pelo Git.
