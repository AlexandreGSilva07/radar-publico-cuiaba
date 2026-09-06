# Manual operacional

## 1. Objetivo

Este documento cobre atualização, validação, recuperação e publicação local do Radar Público Cuiabá. Os comandos devem ser executados na raiz do repositório.

## 2. Primeira execução

```bash
uv sync --locked --all-groups
uv run radar-cuiaba validate-config
uv run radar-cuiaba refresh --year 2026 --live --enrichment-limit 20 --geocoding-limit 50
uv run radar-cuiaba serve
```

O `refresh` usa o mesmo `cycle_id` para contratos, licitações e despesas. Ele só transforma depois que os três runs forem classificados como `complete` ou `empty` e tiverem páginas e contagens reconciliadas. Depois publica Silver/Gold, atualiza perfis CNPJ, coleta o diretório oficial de órgãos e resolve por CEP apenas os registros ausentes ou vencidos no cache.

## 3. Rotina recomendada

Para o piloto, executar diariamente:

```bash
uv run radar-cuiaba refresh --year 2026 --live --enrichment-limit 0 --geocoding-limit 50
```

Uma vez por semana, habilitar novos perfis empresariais:

```bash
uv run radar-cuiaba enrich --live --limit 50
uv run radar-cuiaba enrich-agencies --live --limit 50
uv run radar-cuiaba geocode --live --limit 100
```

O cache considera o perfil atual por 30 dias. A BrasilAPI é uma fonte auxiliar: indisponibilidade externa é registrada por CNPJ e não remove nem invalida os dados municipais.

Para refinar coordenadas de endereço em lote pequeno, execute separadamente:

```bash
uv run radar-cuiaba geocode-addresses --live --limit 25
```

Esse comando usa o Nominatim público em uma única thread, aguarda mais de um segundo entre chamadas, identifica o repositório e guarda cada resultado por 365 dias. Não o agende como rotina de carga massiva. Para operação comercial recorrente, configure uma instância própria ou outro provedor compatível e mantenha atribuição ao OpenStreetMap.

## 4. Retomada de coleta

Se uma execução cair, reutilize o `cycle_id` exibido no terminal:

```bash
uv run radar-cuiaba collect \
  --resource despesas \
  --year 2026 \
  --cycle-id refresh-2026-ID-EXISTENTE \
  --live
```

O coletor começa na primeira página ainda não concluída. Não apague Bronze nem `ops.duckdb`: eles são o mecanismo de retomada e auditoria.

Depois valide o run informado na saída:

```bash
uv run radar-cuiaba coverage --run-id UUID --validate
```

Quando todos os domínios estiverem completos:

```bash
uv run radar-cuiaba transform --year 2026
```

## 5. Verificações após atualização

```bash
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:8000/api/meta
curl --fail http://127.0.0.1:8000/api/summary
curl --fail http://127.0.0.1:8000/api/analytics
curl --fail http://127.0.0.1:8000/api/market-intelligence
curl --fail http://127.0.0.1:8000/api/agency-intelligence
curl --fail --output /tmp/radar-contracts.csv \
  http://127.0.0.1:8000/api/export/contracts.csv
curl --fail --output /tmp/radar-market.csv \
  http://127.0.0.1:8000/api/export/market-intelligence.csv
curl --fail --output /tmp/radar-agencies.csv \
  http://127.0.0.1:8000/api/export/agency-intelligence.csv
```

No dashboard, conferir:

1. ano e horário de atualização;
2. KPIs e gráficos sem valores vazios inesperados;
3. evolução mensal, rankings e composição coerentes com o mesmo recorte anual;
4. oportunidades e contratos com paginação;
5. cross-filter por nicho, tipo, cidade, bairro, porte, situação, mapa e busca formatada por CNPJ/telefone;
6. contatos empresariais e institucionais, precisão geográfica e atribuição das fontes;
7. credores PF separados, com nome publicado e CPF somente mascarado;
8. exportação CSV e botão `Relatório PDF` preparando todas as páginas;
9. tela de qualidade, cobertura e link para a fonte oficial.

## 6. Recuperação

| Sintoma | Diagnóstico | Ação segura |
|---|---|---|
| `snapshot completo ausente` | um dos três runs está parcial/falho | retomar com o mesmo ciclo e validar cobertura |
| `hash Bronze divergente` | arquivo local corrompido | preservar evidência, iniciar novo ciclo e recolher a página |
| API retorna 503 | `analytics.duckdb` ausente/ilegível | executar `transform`; não criar banco vazio manualmente |
| BrasilAPI falha | limite ou indisponibilidade externa | manter dashboard municipal; repetir enriquecimento depois |
| CEP falha | CEP inexistente ou falha transitória | consultar `geocoding_attempt`; repetir somente as ausências após estabilização da fonte |
| Nominatim não encontra endereço | cadastro incompleto ou cobertura OSM | manter fallback por CEP; não promover centroide a endereço exato |
| filtro sem resultados | busca literal não encontrou correspondência | limpar filtro; não criar correspondência aproximada automática |

`analytics.duckdb` é reconstruído em arquivo temporário e trocado atomicamente. Se a transformação falhar, a versão anterior permanece intacta.

## 7. Backup

Os commits protegem código e documentação, mas não os dados ignorados pelo Git. Para uma operação com clientes, copiar regularmente todo o diretório `data/` para armazenamento versionado e criptografado. O conjunto mínimo de recuperação é:

- `ops.duckdb`;
- diretório `bronze/` completo;
- `enrichment.duckdb`.

`analytics.duckdb` pode ser regenerado a partir deles.

## 8. Política de dados

O Bronze contém a resposta pública original e deve permanecer restrito ao operador. Apenas Silver/Gold alimentam o produto. CPF integral nunca é copiado para o analítico: a visão de controle social conserva apenas máscara irreversível, nome publicado e valores. O cache empresarial usa uma lista permitida de campos e nunca persiste o corpo completo retornado pela [BrasilAPI](https://github.com/BrasilAPI/BrasilAPI/blob/main/pages/docs/doc/cnpj.json). QSA e contatos de pessoas físicas não são coletados. O diretório institucional preserva apenas contato da unidade; telefones do rodapé geral são isolados pelo parser.

Antes de abrir acesso a clientes externos, adicionar autenticação, HTTPS, termos de uso, monitoramento, backup testado e controle de acesso ao diretório de dados.
