---
name: git-workflow
description: Mantém cada unidade do Radar Público Cuiabá validada e recuperável no GitHub.
---

# Fluxo Git

1. Leia `docs/spec_01.md` e o plano vigente.
2. Confira `git status --short` e preserve mudanças fora da tarefa.
3. Não adicione `.env`, tokens, JSON bruto, Parquet, DuckDB, SQLite, logs, downloads ou dados pessoais.
4. Antes do commit execute `git diff --check`, revise o staged e rode testes proporcionais.
5. Use `tipo(escopo): descrição` com `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `build` ou `ci`.
6. Um commit representa uma capacidade pequena e verificável.
7. Após cada commit aprovado, faça push imediatamente. Esta autorização foi registrada pelo usuário em 2026-09-04 para a execução integral do MVP.
8. Nunca faça force push em `main`.
9. Dados operacionais permanecem locais e ignorados; somente código, configuração, migrations, fixtures sintéticas e documentação são publicados.

No fechamento, informe SHA, validações e confirmação do push.
