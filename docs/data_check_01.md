# DATA CHECK 01 — Fontes públicas confirmadas

**Observação inicial:** 2026-09-04; enriquecimento validado em 2026-09-05, America/Cuiaba
**Modo:** leitura pública mínima, sem autenticação

## Conclusão

O Portal da Transparência usa endpoints JSON públicos; não é necessário raspar o HTML Angular. Consultas paginadas usam `POST multipart/form-data`, com os campos JSON `pagination` e `filters`. O diretório institucional fica em outro site oficial e exige parser HTML pequeno e isolado.

Base confirmada:

```text
https://transparencia.cuiaba.mt.gov.br/portaltransparencia/servlet/
```

## Contratos

- filtros: `GET aapifiltercontrato`;
- dados: `POST aapicontrato`;
- recorte 2026: 170 registros;
- documento presente: 170; CNPJ com 14 dígitos: 169;
- `ContratoLicitacaoId` presente: 107;
- documento/anexo indicado: 164.

Campos centrais: `ContratoId`, número/ano, objeto, datas, situação, valor original/atual, órgão, fornecedor, documento e identificador de licitação.

## Licitações

- filtros: `GET aapifilterlicitacao`;
- dados: `POST aapilicitacao`;
- recorte 2026: 174 registros;
- vencedor por nome preenchido: 146;
- valores estimado/homologado preenchidos: 150;
- data de sessão ausente ou `0000-00-00`: 87.

O cabeçalho não fornece CNPJ do vencedor. Nome não pode criar vínculo empresarial exato.

## Despesas por credor

- filtros: `GET aapifilterdespesacredor`;
- dados: `POST aapidespesacredor`;
- recorte 2026: 2.150 registros;
- documento presente: 2.148;
- CNPJ de 14 dígitos: 944;
- documento de 11 dígitos: 1.204;
- pagamento positivo: 1.873.

O endpoint é agregado por credor. O dashboard comercial usa somente credores com CNPJ válido. Não há chave comprovada de despesa para contrato.

## Enriquecimento

A BrasilAPI forneceu perfil para os 951 CNPJs válidos: 948 cadastros ativos, 871 com telefone, 591 com regime tributário e 581 sediados em Cuiabá. Nenhum e-mail empresarial veio preenchido neste snapshot. Razão/nome, CNAE, município, porte, natureza, capital, endereço, regime e contato cadastral da pessoa jurídica entram na allowlist; QSA é descartado.

Dos 778 CEPs únicos, 772 retornaram coordenadas, cobrindo 945 das 951 organizações. Um primeiro lote Nominatim, limitado e serial, produziu 34 pontos por endereço/rua, dois por localidade e 15 resultados não encontrados; o restante conserva o centroide de CEP com precisão declarada.

## Diretório institucional

- índices oficiais: `https://www.cuiaba.mt.gov.br/secretarias` e `/orgaos`;
- 31 unidades coletadas após seguir a paginação;
- 30 com CEP, 27 com telefone institucional e 22 com e-mail;
- 16 com latitude/longitude publicadas no próprio link de mapa da unidade;
- 23 dos 24 compradores analíticos ligados por igualdade canônica ou alias manual versionado.

O parser limita contatos ao bloco da unidade. Telefones e endereço do rodapé geral não são promovidos a contato próprio; quando o único endereço disponível é o geral, ele recebe `municipal_headquarters`.

## Regras derivadas

1. Datas vazias e `0000-00-00` viram `NULL`.
2. Valores brasileiros são convertidos com `Decimal`.
3. Documento é classificado como `cnpj`, `cpf`, `missing` ou `invalid`.
4. Somente CNPJ validado alimenta empresa e ranking.
5. Cobertura é reconciliada com `totalRecords` por recurso/ano.
6. Resposta bruta fica em Bronze; nenhum JSON operacional entra no Git.
7. Contato empresarial/institucional pode ser exibido com fonte; QSA e contatos pessoais não são coletados.
8. Coordenada oficial prevalece sobre endereço refinado, que prevalece sobre CEP.
