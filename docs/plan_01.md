# PLAN 01 — Execução integral do MVP

**Derivado de:** `spec_01.md` e `data_check_01.md`
**Regra:** cada item termina em validação, commit e push antes do seguinte.

## 1. Ingestão

### I1 — Bootstrap ✅

Python 3.12, `uv`, CLI, pytest, Ruff e mypy. Aceite: instalação limpa e suite local sem rede.

### I2 — Manifesto ✅

Declarar contratos, licitações e despesas por credor: endpoints, métodos, campos de ano, chave natural, paginação e política de atualização. Aceite: configuração inválida falha antes da rede.

### I3 — Estado operacional ✅

DuckDB local com runs, requests, objetos Bronze, tentativas e cobertura. Aceite: mesmo ciclo retoma; ciclo novo cria execução nova; migrations são idempotentes.

### I4 — HTTP e Bronze ✅

Timeout, retry limitado, erro sanitizado, JSON gzip escrito por temporário + `os.replace`, SHA-256 e proveniência. Aceite: drift ainda é preservado; corpo/CPF nunca aparece em log.

### I5 — Coleta paginada ✅

Motor único por manifesto, `--live`, ano explícito, `--max-pages` e `cycle-id`. Aceite: contratos/licitações/despesas reconciliam páginas e `totalRecords`; parcial nunca vira completo.

### I6 — Cobertura ✅

Relatório texto/JSON e validador com código não zero. Aceite: completo, parcial, vazio, falho e não verificado são distintos.

## 2. ETL

### E1 — Normalizadores e proteção de documento ✅

Funções puras para dinheiro, data, texto e documento. Testar sentinelas, valores brasileiros, CNPJ DV e máscara irreversível de CPF. CPF integral permanece apenas no Bronze restrito.

### E2 — Silver ✅

DuckDB independente com tabelas Silver tipadas de contrato, licitação e despesa por credor, além de qualidade e rejeições. A forma plana reduz joins prematuros no MVP; as views Gold apresentam as relações necessárias. Toda linha tem proveniência por run e hash.

### E3 — Enriquecimento empresarial e geográfico ✅

Cache BrasilAPI somente por CNPJ válido, sem QSA: razão/nome, CNAE, porte, natureza, situação, endereço, contato empresarial e regime. BrasilAPI CEP v2 fornece fallback geográfico; Nominatim refina endereço em comando explícito, serial e cacheado. O diretório oficial fornece endereço, telefone e e-mail das unidades compradoras. Falha externa não bloqueia transformação municipal.

### E4 — Gold ✅

Views de oportunidades, renovação, órgãos, fornecedores, despesas PJ, credores PF mascarados e qualidade. Somente relações `exact` entram nos totais empresariais; PF nunca entra em enriquecimento ou ranking PJ.

## 3. Produto

### P1 — API ✅

FastAPI com health, resumo, oportunidades, contratos, órgãos, fornecedores, despesas, credores PF, qualidade, inteligência empresarial e institucional conectadas e CSV. Filtros e paginação obrigatórios nas listas.

### P2 — Dashboard ✅

Frontend estático responsivo servido pelo FastAPI, com navegação lateral, KPIs, gráficos SVG, tabelas secundárias, estados completos e fonte persistente. O workspace empresarial cruza em tempo real tipo institucional, nicho CNAE, cidade, bairro, porte, situação, busca, mapa, KPIs e tabela. Inclui CSV enriquecido e preparação de todas as páginas para impressão em PDF.

### P3 — Operação ✅

Comando único para coletar/transformar/enriquecer empresas e diretório oficial/geocodificar CEP, comando separado para endereço conforme política OSM, README, `.env.example`, Docker e CI. Aceite: novo clone executa testes e sobe o dashboard documentadamente.

## 4. Gates finais

- G1: smoke dos filtros e uma página por recurso.
- G2: carga real reconciliada do ano corrente.
- G3: Silver sem CPF integral, sem `float`, com máscara irreversível em PF e rejeições rastreáveis.
- G4: totais Gold reproduzíveis por SQL/testes.
- G5: dashboard abre no navegador, API saudável, cross-filter/mapa sem erro, CSV válido e relatório imprimível.

## 5. Evidência da execução inicial

- 46 testes automatizados aprovados, Ruff e mypy sem erros;
- pacote wheel construído com migrations e assets web;
- coleta 2026 reconciliada: 170 contratos, 174 licitações e 2.150 despesas por credor;
- Silver: 156 contratos únicos, 174 licitações e 2.150 despesas;
- 14 duplicatas de contrato isoladas; 1.204 credores PF preservados em visão separada com CPF irreversivelmente mascarado;
- 951 CNPJs válidos enriquecidos, cobrindo toda a base empresarial do snapshot;
- 31 unidades do diretório oficial coletadas, 27 com telefone e 16 com ponto oficial; 23 dos 24 compradores ligados por regra exata ou alias versionado;
- 772 dos 778 CEPs únicos geolocalizados: 945 das 951 empresas com coordenada e 34 refinadas por endereço/rua, priorizadas por valor econômico;
- dashboard de BI validado em Chromium a 1440×1000 e 390×844, com cross-filter, mapa agrupado, relatório PDF, URLs diretas, redimensionamento, menu por teclado e sem erro de console ou overflow;
- filtro por fornecedor, paginação, API e CSV testados sobre o banco real;
- cada unidade foi commitada e enviada ao remoto antes da seguinte.

O primeiro snapshot de produto permanece no ano corrente para que todos os cards representem um período inequívoco. Backfill de 2024–2025 passa a ser a primeira extensão após validação com usuários piloto, acompanhado de filtro global de período.

Dados reais, bancos, Bronze, Parquet e caches ficam em `data/`, ignorados pelo Git.
