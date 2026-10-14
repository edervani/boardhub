# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões seguem [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Modificado
- RF-001 a RF-005 passam a `implementado` (PR #1); matriz de rastreabilidade com evidência.

### Adicionado (Fase 2a — motor do jogo da velha)
- `game_engines`: contrato comum (`IllegalMove`, `InvalidState`, `Outcome`, hash canônico do estado) e motor do jogo da velha com serialização validada (RF-016).
- `ai/opponents`: IA do jogo da velha em 5 níveis com semente injetada (doc 07 §2).
- Testes: as 5.478 posições alcançáveis, invariantes, 8 linhas, estados inconsistentes, nível 5 sem derrotas em 1.000 partidas e tempo de resposta (CA-016, RNF-002).
- Sem partidas persistidas, endpoints ou frontend de jogo ainda (Fases 2b a 2d).

### Adicionado (Fase 1 — base técnica)
- Backend FastAPI (monólito modular): configuração, logs sanitizados, erros RFC 9457, limitador de taxa, cabeçalhos de segurança, CSRF por duplo envio, migração Alembic 0001 (identidade, catálogo, auditoria).
- Autenticação (RF-001 a RF-005): cadastro com Argon2id, verificação de e-mail, login com cookies `HttpOnly`/`Secure`, sessões revogáveis, redefinição de senha, antienumeração.
- Perfil e preferências (RF-006, RF-007), perfil público sem e-mail, limite de troca de nome a cada 30 dias.
- Classificação indicativa (RF-033): `GET /games` filtra pela faixa etária do usuário; visitante vê somente jogos Livres.
- Supervisão parental (RF-034): vínculo por convite de uso único restrito ao e-mail convidado, painel do responsável, auditoria, remoção de cadastros de menores de 12 anos sem confirmação em 7 dias.
- Frontend React 19 + Vite: cadastro, login, perfil, preferências e lista de jogos com selo etário em texto; tokens de tema claro/escuro.
- CI (GitHub Actions): docs, backend (ruff, mypy estrito, pytest com PostgreSQL 17, pip-audit), frontend (tsc, vitest, build, npm audit), geração de lockfiles.

### Pendente nesta fase (ver docs/16 §Pendências, P-15)
- Bloqueio de nova partida ao atingir o limite diário (CA-034) e histórico visível ao responsável dependem das partidas (Fase 2+).
- Notação de lances exibida (RF-007) e verificações E2E/Playwright de CA-006/CA-033 ainda não implementadas.
- Painel do responsável e selo antes da partida no frontend ainda não implementados.

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
