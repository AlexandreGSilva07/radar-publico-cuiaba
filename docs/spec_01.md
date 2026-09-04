# SPEC 01 — MVP de Inteligência de Compras Públicas de Cuiabá

**Status:** proposta inicial  
**Versão:** 0.1  
**Data:** 2026-09-04  
**Produto:** Cuiabá Inteligência Pública  
**Público inicial:** empresas que vendem, ou podem vender, para órgãos públicos em Cuiabá.

## 1. Resumo executivo

Construir um produto de inteligência comercial sobre compras públicas municipais. O MVP deverá coletar dados públicos do Portal da Transparência de Cuiabá, enriquecê-los por CNPJ e apresentar oportunidades, contratos em renovação, histórico de fornecedores e execução financeira em um dashboard consultável.

O produto não será um espelho genérico de transparência. Ele deverá responder perguntas comerciais acionáveis:

- Quais licitações representam oportunidade para o meu segmento?
- Quem já fornece este produto ou serviço à Prefeitura?
- Quais contratos estão perto do vencimento e podem gerar nova contratação?
- Quais órgãos compram mais e com que frequência?
- Um fornecedor atua em quais categorias, órgãos e municípios?

## 2. Objetivo do MVP

Entregar uma base atualizada e auditável de compras públicas de Cuiabá e um dashboard que permita identificar oportunidades e contexto competitivo sem que o usuário tenha de navegar por múltiplos portais públicos.

### 2.1 Resultado mínimo vendável

Para uma categoria e empresa selecionadas, o usuário consegue:

1. ver licitações recentes ou em andamento;
2. identificar contratos ativos e próximos do fim;
3. consultar fornecedores relacionados e seu histórico local;
4. observar gastos por órgão, fornecedor, objeto e período;
5. abrir a fonte pública original de cada registro;
6. saber quando o dado foi coletado e qual a sua cobertura.

## 3. Escopo

### 3.1 Incluído no MVP

| Domínio | Dados principais | Uso no produto |
|---|---|---|
| Licitações | processo, edital, órgão, objeto, modalidade, valor estimado, data e situação | oportunidades e concorrência |
| Contratos | número, órgão, fornecedor, objeto, modalidade, vigência, valores e situação | radar de renovação e incumbente |
| Atas e adesões | identificação, órgão, fornecedor, itens, vigência e situação | compras recorrentes e oportunidades derivadas |
| Execução financeira | credor, empenho, liquidação, pagamento, órgão, descrição, valores e datas | gasto efetivo e histórico comercial |
| Cadastro de fornecedores | CNPJ, nome, CNAE, porte, situação cadastral, endereço, matriz/filial | filtros e perfil de empresa |
| PNCP | contratações e contratos públicos nacionais relacionados a fornecedor/órgão quando disponíveis | perfil competitivo além de Cuiabá |
| Sanções públicas | ocorrência oficial, origem, vigência e data da consulta | alerta contextual, sem juízo editorial |

### 3.2 Explicitamente fora do MVP

- folha de servidores, remunerações, férias, afastamentos e dados funcionais;
- dados de cidadãos, saúde individual, creches, ouvidoria e protocolos;
- OCR e indexação completa de anexos/PDFs;
- scraping de redes sociais, Google Maps, LinkedIn, WhatsApp ou dados de contato não fornecidos por fonte licenciada;
- consulta automatizada a serviços protegidos por CAPTCHA;
- inferência ou exibição de sócios pessoas físicas;
- motor de recomendação por IA generativa;
- cobertura de outros municípios, exceto PNCP como enriquecimento de fornecedor;
- aplicativo móvel nativo, alertas por WhatsApp e integrações de CRM.

## 4. Personas e proposta de valor

### 4.1 Fornecedor de governo

Empresa que já participa ou quer participar de compras públicas. Precisa de oportunidade, histórico de preço e conhecimento dos concorrentes.

### 4.2 Consultoria de licitações

Profissional que monitora diversos segmentos e clientes. Precisa de filtros, exportação e alertas de prazos.

### 4.3 Gestor comercial B2G

Responsável por escolher quais editais e órgãos priorizar. Precisa enxergar recorrência de compras, ticket e renovação de contratos.

## 5. Princípios do produto e dados

1. **Fonte antes de conclusão:** todo indicador deve permitir abrir o registro público de origem.
2. **Dados brutos imutáveis:** resposta original, horário da coleta, endpoint, parâmetros e hash são preservados.
3. **Atualização incremental:** não baixar todo o histórico a cada execução.
4. **CNPJ como chave de empresa:** normalizar CNPJ, mas preservar o documento de origem quando houver CPF ou documento inválido.
5. **Sem atribuição especulativa:** relação entre empresas só pode ser afirmada pela mesma raiz CNPJ ou fonte oficial explícita.
6. **Privacidade por padrão:** não exibir CPF, nome de sócio, telefone ou e-mail de pessoa física.
7. **Risco com contexto:** sanção é exibida com fonte, período e situação; nunca como rótulo absoluto da empresa.

## 6. Fontes de dados

### 6.1 Fonte primária: Portal da Transparência de Cuiabá

O portal é uma aplicação Angular. A extração deve consumir os endpoints públicos que alimentam a interface, em vez de raspar o HTML renderizado.

Padrão identificado:

```text
POST /portaltransparencia/servlet/aapi<recurso>
GET  /portaltransparencia/servlet/aapifilter<recurso>
```

Os endpoints de consulta recebem `multipart/form-data` com:

```json
{
  "pagination": {
    "currentPage": 0,
    "recordsPerPage": 100,
    "totalRecords": 0,
    "columnOrder": ""
  },
  "filters": {}
}
```

Recursos prioritários esperados:

```text
aapilicitacao                aapifilterlicitacao
aapicontrato                 aapifiltercontrato
aapiata                      aapifilterata
aapiadesaoata                aapifilteradesaoata
aapidespesacredor            aapifilterdespesacredor
aapiempenho                  aapifilterempenho
aapiliquidacao               aapifilterliquidacao
aapipagamento                aapifilterpagamento
```

Detalhes e anexos serão inventariados, porém a coleta de anexos só será ativada em fase posterior do MVP.

### 6.2 Enriquecimento CNPJ

| Fonte | Papel | Estratégia |
|---|---|---|
| BrasilAPI | enriquecimento rápido por CNPJ durante desenvolvimento e para misses | cache local e fila com limite de requisições |
| Dados abertos da Receita Federal | fonte de produção em lote para empresa, estabelecimento, CNAE e situação | importar recorte dos CNPJs relevantes; não baixar/servir contatos pessoais |
| ViaCEP/geocodificação opcional | padronização de endereço e mapa | somente após a base CNPJ estar normalizada |

Campos desejados para `empresa` e `estabelecimento`:

- CNPJ de 14 dígitos e CNPJ raiz de 8 dígitos;
- razão social e nome fantasia;
- situação cadastral e data de situação;
- matriz ou filial;
- CNAE principal e secundários;
- porte, natureza jurídica, capital social quando disponível;
- CEP, município, UF, bairro e endereço normalizado;
- data de abertura;
- fonte e data de atualização.

### 6.3 PNCP

Usar como enriquecimento nacional de compras públicas, inicialmente apenas para CNPJs já identificados como fornecedores ou para CNPJs de órgãos compradores relevantes. Não deve bloquear a entrega do MVP local.

### 6.4 Sanções da CGU

Consultar ou importar os conjuntos públicos CEIS/CNEP/CEPIM compatíveis com uso público. O dashboard apresentará somente dados oficiais vigentes ou históricos com período claramente exibido.

### 6.5 IBGE

Usar dados municipais agregados para contexto territorial posterior: município, população, PIB e atividade econômica. Não é fonte de oportunidade individual e não deve atrasar o núcleo do MVP.

## 7. Arquitetura de dados

### 7.1 Camadas

```text
Fontes públicas
      ↓
ingestão (HTTP + paginação + retentativa)
      ↓
bronze: JSON bruto, metadados e hash
      ↓
silver: tabelas normalizadas, tipadas e deduplicadas
      ↓
gold: métricas, alertas, busca e views para o dashboard
      ↓
API/dashboard
```

### 7.2 Armazenamento inicial

| Camada | Tecnologia inicial | Motivo |
|---|---|---|
| Bronze | arquivos JSON comprimidos | reprocessamento e auditoria simples |
| Silver/Gold analítico | Parquet + DuckDB | baixo custo, consultas rápidas e portabilidade |
| Metadados operacionais | DuckDB ou SQLite | checkpoints, execuções e erros |
| Aplicação futura | PostgreSQL quando houver múltiplos usuários | concorrência e API de produção |

O MVP deve poder rodar localmente sem depender de infraestrutura em nuvem.

## 8. Modelo de dados lógico

### 8.1 Entidades centrais

```text
orgao
  1 ── N licitacao
  1 ── N contrato
  1 ── N despesa/empenho/pagamento

empresa (CNPJ raiz)
  1 ── N estabelecimento (CNPJ 14)
  1 ── N fornecedor_publico

fornecedor_publico
  N ── N licitacao          via licitacao_fornecedor
  1 ── N contrato
  1 ── N despesa_credor

licitacao
  1 ── N item_licitacao
  1 ── N licitacao_fornecedor
  0 ── N contrato

contrato
  1 ── N contrato_item
  1 ── N contrato_alteracao
  0 ── N empenho

empenho
  1 ── N liquidacao
  1 ── N pagamento
```

### 8.2 Tabelas Silver mínimas

| Tabela | Chave natural inicial | Conteúdo |
|---|---|---|
| `stg_source_run` | `run_id` | fonte, endpoint, parâmetros, horário, status e hash |
| `stg_raw_object` | `raw_id` | local do JSON bruto e referência à execução |
| `dim_orgao` | `source_orgao_id` | órgão, nome e vigência observada |
| `dim_empresa` | `cnpj_raiz` | atributos da pessoa jurídica sem dados pessoais |
| `dim_estabelecimento` | `cnpj` | estabelecimento, CNAEs e endereço |
| `dim_fornecedor` | `source_fornecedor_id` | credor/fornecedor como aparece no portal e vínculo CNPJ quando confiável |
| `fct_licitacao` | `source_licitacao_id` | cabeçalho da licitação |
| `fct_licitacao_fornecedor` | licitação + fornecedor | vencedor, participante e papel quando disponível |
| `fct_contrato` | `source_contrato_id` | contrato e vigência |
| `fct_ata` | `source_ata_id` | atas e status |
| `fct_adesao_ata` | `source_adesao_id` | adesões a atas |
| `fct_empenho` | `source_empenho_id` | valor empenhado e vínculo disponível |
| `fct_liquidacao` | `source_liquidacao_id` | valor liquidado |
| `fct_pagamento` | `source_pagamento_id` | valor pago |
| `fct_sancao` | fonte + identificador | sanção, período, situação e origem |

### 8.3 Regras de identidade e relacionamento

1. CNPJ deve ter somente dígitos e passar por validação de dígito verificador antes de enriquecer.
2. Documento de CPF, máscara incompleta ou CNPJ inválido permanece como `documento_origem` e não entra em `dim_empresa`.
3. `cnpj_raiz` é derivado dos oito primeiros dígitos de um CNPJ válido; não substitui o CNPJ do estabelecimento.
4. Vínculo entre fornecedor do portal e CNPJ recebe `confidence`: `exact`, `normalized_name`, `manual_review` ou `unmatched`.
5. Dashboard padrão usa somente `exact`; os demais vínculos são revisáveis e não alimentam ranking automaticamente.
6. Valores monetários devem usar decimal, nunca `float`.
7. Datas devem ser preservadas na forma original e normalizadas para ISO 8601.

## 9. Pipeline ETL

### 9.1 Fase A — inventário e manifesto de endpoints

Criar um manifesto declarativo, versionado, por exemplo `config/sources/cuiaba.yml`.

Cada recurso deve declarar:

- nome lógico e endpoint;
- endpoint de filtros;
- método HTTP e formato do corpo;
- paginação e tamanho máximo seguro;
- chave natural esperada;
- filtros por período disponíveis;
- endpoint de detalhe, se houver;
- campos de CNPJ/documento;
- dependências e prioridade;
- política de atualização;
- status de cobertura.

**Saída:** inventário de fontes e um comando que consiga validar todos os endpoints sem baixar o histórico completo.

### 9.2 Fase B — coletor genérico

Implementar um cliente HTTP reutilizável que:

1. consulta filtros e salva seu snapshot;
2. percorre páginas até `totalRecords` ou condição de término verificável;
3. aplica espera, retentativa exponencial e timeout;
4. grava cada resposta em Bronze antes de qualquer transformação;
5. registra erro, duração, status HTTP e contagens;
6. evita requisições duplicadas por chave de execução;
7. suporta execução por endpoint, período, órgão e página;
8. nunca tenta contornar CAPTCHA, autenticação ou bloqueio.

**Saída:** `collect` capaz de reexecutar de forma idempotente.

### 9.3 Fase C — extração histórica e incremental

Ordem inicial de extração:

1. órgãos e catálogos de filtros;
2. licitações;
3. contratos;
4. fornecedores/credores;
5. empenhos;
6. liquidações e pagamentos;
7. atas e adesões.

Estratégia:

- primeira carga: percorrer períodos disponíveis, começando por 24 meses e ampliando conforme volume;
- atualização diária: licitações e contratos recentes;
- atualização semanal: execução financeira recente e cadastros;
- reconciliação mensal: reconsultar janela móvel de 90 dias para mudanças retroativas;
- não declarar histórico completo enquanto qualquer ano, página ou filtro necessário estiver pendente.

**Saída:** JSONs brutos e relatório de cobertura por recurso/período.

### 9.4 Fase D — tratamento Silver

Transformações obrigatórias:

- achatamento de respostas aninhadas;
- padronização de nomes de colunas em `snake_case`;
- conversão de valores, datas, documentos e códigos;
- deduplicação por chave natural + hash de conteúdo;
- manutenção de `observed_at`, `source_url`, `source_endpoint` e `raw_id`;
- separação de cabeçalho e itens/detalhes;
- mapeamento dos órgãos e fornecedores entre domínios;
- geração de tabelas Parquet particionadas por domínio e competência/ano quando aplicável.

**Saída:** tabelas Silver consultáveis no DuckDB e teste de qualidade por tabela.

### 9.5 Fase E — enriquecimento de empresas

Ordem de resolução:

1. CNPJ já presente no registro de origem;
2. consulta cache de `dim_estabelecimento`;
3. consulta BrasilAPI apenas em CNPJ novo e válido;
4. importação/atualização de recorte Receita Federal quando necessário;
5. vínculo por nome normalizado somente como sugestão, nunca como dado definitivo.

Gerar um perfil consolidado:

- histórico de contratos e pagamentos em Cuiabá;
- CNAEs e localização;
- grupo de matriz/filial por CNPJ raiz;
- cobertura PNCP, se habilitada;
- status cadastral e alertas de sanção quando houver correspondência exata.

### 9.6 Fase F — Gold e métricas

Criar views/materializações para:

- oportunidades por situação, período, modalidade, órgão e palavras-chave;
- contratos vencendo em 30, 60, 90, 120 e 180 dias;
- ranking de gasto por órgão, fornecedor e categoria de objeto;
- perfil de fornecedor: número de contratos, valor contratado, empenhado, liquidado e pago;
- recorrência de objeto/categoria por órgão;
- discrepâncias entre valor contratado e execução financeira quando os vínculos forem confiáveis;
- qualidade e cobertura: última coleta, registros, erros e períodos cobertos.

## 10. Classificação de objeto e segmento

Como o objeto de licitação é texto livre, o MVP terá uma taxonomia manual versionada por regras de palavras-chave e expressões.

Categorias iniciais sugeridas:

- construção e engenharia;
- limpeza, resíduos e conservação;
- alimentação e eventos;
- tecnologia, telecom e software;
- saúde e medicamentos;
- educação e material didático;
- transporte, frota e combustíveis;
- segurança e vigilância;
- serviços profissionais e consultoria;
- materiais e suprimentos gerais.

Regras devem produzir `segmento`, `confidence` e `rule_version`. Registros sem classificação permanecem em `não_classificado`; não forçar classificação por IA no MVP.

## 11. Dashboard MVP

### 11.1 Páginas

| Página | Conteúdo | Ação principal |
|---|---|---|
| Visão geral | KPIs, oportunidades novas, contratos próximos do vencimento, cobertura | entrar no recorte de interesse |
| Oportunidades | licitações filtráveis | salvar/exportar lista e abrir fonte |
| Radar de renovação | contratos por janela de vencimento | investigar incumbente e órgão |
| Órgãos compradores | gasto, volume, categorias e tendência | priorizar conta pública |
| Fornecedores | ranking e perfil por CNPJ | analisar concorrente/parceiro |
| Detalhe de oportunidade | licitação/contrato, itens, fornecedor, execução, fonte | tomar decisão comercial |
| Qualidade dos dados | data de atualização, cobertura, falhas e ressalvas | confiar corretamente no painel |

### 11.2 Filtros globais

- período;
- órgão;
- segmento/categoria;
- modalidade;
- situação;
- faixa de valor;
- município/UF do fornecedor;
- porte empresarial quando disponível;
- fornecedor/CNPJ;
- termo no objeto.

### 11.3 Indicadores prioritários

- licitações abertas/em andamento no período;
- valor estimado das oportunidades;
- contratos a vencer por janela;
- órgãos com maior gasto e variação;
- fornecedores com maior valor contratado/pago;
- valor pago por categoria;
- percentual de registros enriquecidos com CNPJ válido;
- data/hora e cobertura da última coleta.

## 12. API e aplicação

### 12.1 Backend inicial

- API REST ou camada de consulta tipada sobre DuckDB;
- endpoints paginados e filtráveis para dashboard;
- endpoint de detalhe com links de origem;
- endpoint de status/cobertura;
- sem autenticação no protótipo local; autenticação é requisito antes de venda externa.

### 12.2 Frontend inicial

- dashboard web responsivo;
- tabelas com ordenação, filtros e paginação;
- gráficos simples; nenhum gráfico sem tabela ou fonte correspondente;
- URLs compartilháveis com filtros;
- estado vazio e ressalvas de cobertura claros.

## 13. Fases de entrega

### Fase 0 — fundação e decisão técnica

**Objetivo:** preparar repositório, convenções, manifesto inicial e ambiente reproduzível.

**Entregáveis:**

- estrutura de projeto;
- configuração e variáveis de ambiente sem segredos;
- manifesto de fontes;
- esquema DuckDB inicial;
- comandos `collect`, `transform`, `enrich`, `serve` e `validate` documentados.

**Aceite:** qualquer pessoa consegue instalar, executar validação de fonte e consultar banco vazio de forma documentada.

### Fase 1 — parser e ingestão Bronze

**Objetivo:** obter dados públicos de licitações e contratos de forma confiável.

**Entregáveis:**

- coletor HTTP genérico;
- paginação e retentativas;
- snapshots de filtros;
- Bronze para licitação e contrato;
- relatório de execução e cobertura.

**Aceite:** coletar uma janela definida de tempo duas vezes sem duplicar objetos Bronze e registrar contagens verificáveis.

### Fase 2 — Silver e relações principais

**Objetivo:** disponibilizar dados normalizados para análise.

**Entregáveis:**

- `dim_orgao`, `dim_fornecedor`, `fct_licitacao`, `fct_contrato`;
- detalhes/itens quando acessíveis;
- chaves naturais, documentos normalizados e rastreabilidade;
- testes de unicidade, campos obrigatórios e valores monetários.

**Aceite:** é possível relacionar contrato, órgão e fornecedor e retornar o JSON original que originou cada linha.

### Fase 3 — execução financeira e enriquecimento CNPJ

**Objetivo:** calcular histórico de mercado e perfil de fornecedor.

**Entregáveis:**

- credores, empenhos, liquidações e pagamentos;
- cache CNPJ e perfis de empresa/estabelecimento;
- classificação inicial de objetos;
- vínculo de fornecedor com CNPJ por confiança.

**Aceite:** dashboard/consulta mostra valores por órgão, fornecedor e segmento; vínculos não exatos não contaminam indicadores padrão.

### Fase 4 — Gold e dashboard funcional

**Objetivo:** transformar dados em decisão comercial.

**Entregáveis:**

- páginas Oportunidades, Renovação, Órgãos e Fornecedores;
- filtros globais;
- links de origem;
- paginação e exportação de recorte;
- tela de qualidade/cobertura.

**Aceite:** uma empresa do segmento escolhido consegue responder às cinco perguntas da seção 1 em menos de cinco minutos.

### Fase 5 — enriquecimento seletivo e refinamento

**Objetivo:** elevar confiança e diferencial sem aumentar complexidade prematuramente.

**Entregáveis:**

- PNCP para fornecedores com CNPJ confirmado;
- sanções oficiais com contexto;
- dados IBGE agregados;
- alertas de renovação e novas oportunidades;
- revisão de performance, segurança e UX.

**Aceite:** enriquecimento é opcional, rastreável e falhas externas não interrompem a coleta municipal nem o dashboard.

## 14. Qualidade, observabilidade e segurança

### 14.1 Controles de qualidade

- reconciliar `totalRecords` do portal com registros extraídos;
- registrar páginas ausentes e reprocessar falhas;
- validar CNPJ e preservar documento original;
- sinalizar valores negativos ou datas incoerentes, sem descartá-los silenciosamente;
- versionar transformações e taxonomia;
- comparar contagem e hash entre execuções;
- criar amostra de validação manual contra o portal em cada execução relevante.

### 14.2 Observabilidade

Cada execução deve registrar:

- fonte, recurso, filtros e período;
- início, fim, duração e status;
- páginas esperadas/coletadas;
- registros recebidos, inseridos, atualizados e rejeitados;
- erros e tentativa de recuperação;
- versão do código, manifesto e esquema.

### 14.3 Segurança e uso responsável

- credenciais não entram no repositório;
- somente fontes públicas e acessos permitidos;
- respeitar limitação, termos e disponibilidade de cada fonte;
- não expor documentos pessoais em exportações;
- registrar data de consulta em sanções e dados cadastrais;
- implementar autenticação, autorização e auditoria antes de acesso por clientes externos.

## 15. Riscos e respostas

| Risco | Impacto | Mitigação |
|---|---|---|
| endpoint muda ou fica indisponível | coleta interrompida | manifesto, testes de saúde, Bronze e aviso de desatualização |
| dados históricos incompletos | indicador enganoso | cobertura explícita por período e domínio |
| CNPJ ausente/inválido | enriquecimento parcial | `unmatched`, cache e revisão; não usar aproximação como fato |
| documentos excessivos | custo/tempo alto | anexos fora do MVP e coleta sob demanda |
| objetos livres difíceis de classificar | filtros ruins | taxonomia simples, regras versionadas e fila de revisão |
| fonte externa tem limite | lentidão | cache, fila, batch e enriquecimento não bloqueante |
| interpretação indevida de sanções | risco reputacional | origem, vigência, aviso e sem score opinativo |

## 16. Métricas de sucesso do MVP

### Produto

- ao menos 90% das licitações e contratos da janela coberta aparecem no painel, com contagem reconciliada;
- ao menos 80% do valor associado a fornecedores PJ possui CNPJ válido ou está marcado como não resolvido;
- contratos próximos do vencimento podem ser filtrados por órgão e categoria;
- cada card/tabela principal aponta para fonte e data de coleta;
- resposta de consulta comum em menos de 3 segundos no recorte local.

### Negócio

- três a cinco usuários piloto conseguem identificar oportunidades relevantes;
- pelo menos um usuário declara que deixaria de acompanhar manualmente o portal para usar o painel;
- registrar quais filtros, categorias e alertas são mais usados antes de ampliar fontes.

## 17. Decisões pendentes

1. Janela histórica inicial: 24 meses, 36 meses ou histórico completo?
2. Segmento de lançamento: amplo ou um vertical prioritário?
3. Forma de venda: assinatura por empresa, consultoria ou white label?
4. Frequência de atualização percebida pelo cliente: diária ou semanal?
5. Acesso de clientes: dashboard fechado, relatórios exportáveis ou ambos?
6. Fonte de produção CNPJ: somente cache BrasilAPI inicialmente ou importação do recorte Receita desde a primeira versão?
7. Licença, termos e política de uso dos dados na oferta comercial.

## 18. Próximo artefato

Após aprovação desta spec, criar `docs/plan_01.md` com tarefas executáveis em ordem, dependências, critérios de pronto e comandos de validação para as Fases 0 e 1.
