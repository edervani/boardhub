# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões seguem [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado
- Fase 0: documentação completa de especificação em `docs/` (00–18 e ADR-0001), todos os itens em estado *proposto*.
- Arquivos raiz: README, AGENTS, CONTRIBUTING, CHANGELOG, `.gitignore`, `.env.example`, `docker-compose.yml` (somente PostgreSQL), `pyproject.toml` e `package.json` mínimos sem dependências fixadas (DT-012).
- `scripts/check_docs.py`: verificação de arquivos obrigatórios, links internos, IDs duplicados, referências e matriz de rastreabilidade.

### Segurança
- Nenhuma aplicação implementada; nenhuma superfície de ataque além do PostgreSQL local publicado apenas em `127.0.0.1`.
