# DATA CHECK 01 — Fontes públicas confirmadas

**Observação inicial:** 2026-09-04, America/Cuiaba
**Modo:** leitura pública mínima, sem autenticação

## Conclusão

O portal usa endpoints JSON públicos; não é necessário raspar o HTML Angular. Consultas paginadas usam `POST multipart/form-data`, com os campos JSON `pagination` e `filters`.

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

A BrasilAPI fornece situação cadastral, CNAE, município, porte, natureza jurídica e capital para CNPJ. Telefone, e-mail e QSA não serão persistidos ou exibidos. O enriquecimento é cache opcional e não bloqueia a fonte municipal.

## Regras derivadas

1. Datas vazias e `0000-00-00` viram `NULL`.
2. Valores brasileiros são convertidos com `Decimal`.
3. Documento é classificado como `cnpj`, `cpf`, `missing` ou `invalid`.
4. Somente CNPJ validado alimenta empresa e ranking.
5. Cobertura é reconciliada com `totalRecords` por recurso/ano.
6. Resposta bruta fica em Bronze; nenhum JSON operacional entra no Git.
