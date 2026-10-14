# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões seguem [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Modificado (docs v0.2.0)
- Documentação aprovada pelo responsável pelo produto; ADR-0001 aceito.
- Runtimes definidos: Python 3.13, Node.js 24 LTS, PostgreSQL 17 (DT-014). CI: GitHub Actions.
- Plataforma aberta a todas as idades com classificação indicativa por jogo e conformidade com o ECA Digital (DT-015): novos RF-033 e RF-034, faixa etária no cadastro, endpoints de supervisão parental, risco R-016.
- Hospedagem segue indefinida (P-06), sem bloquear a Fase 1.

### Adicionado
- Fase 0: documentação completa de especificação em `docs/` (00–18 e ADR-0001), todos os itens em estado *proposto*.
- Arquivos raiz: README, AGENTS, CONTRIBUTING, CHANGELOG, `.gitignore`, `.env.example`, `docker-compose.yml` (somente PostgreSQL), `pyproject.toml` e `package.json` mínimos sem dependências fixadas (DT-012).
- `scripts/check_docs.py`: verificação de arquivos obrigatórios, links internos, IDs duplicados, referências e matriz de rastreabilidade.

### Segurança
- Nenhuma aplicação implementada; nenhuma superfície de ataque além do PostgreSQL local publicado apenas em `127.0.0.1`.
