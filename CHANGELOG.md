# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões seguem [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado (Fase 4 — xadrez, backend)
- Motor `chess` (`chess-fide-1`) sobre python-chess (nova dependência `chess>=1.11`, GPL-3.0 — DT-005): estado = lances UCI desde a posição inicial, validado ao carregar (lances reexecutados e FEN conferido); fim por xeque-mate, afogamento, material insuficiente, quíntupla repetição e 75 lances; limite de 600 meios-lances.
- IA em 5 níveis: 1 aleatório com preferência por capturas; 2–5 negamax com poda alfa-beta, aprofundamento iterativo com limite de tempo (0,3/1/2/3 s), tabelas de casas, ordenação MVV-LVA e quiescência de capturas. Stockfish/UCI fica para a Fase 5.
- Migração 0004 (xadrez habilitado); `stalemate` e `fifty_move` passam a ser gravados como motivo de fim.
- Testes: perft 20/400/8902 e Kiwipete 48/2039, mate do pastor, afogamento, roque, en passant, promoção, material insuficiente, estados adulterados, IA×IA curta e partidas pela API com replay e hashes.
- **Pendência P-17:** sem reivindicação de empate (3x/50 lances) nem acordo nesta fase. Frontend do xadrez não incluído.
### Adicionado (Fase 4 — interface do xadrez)
- Frontend: opção "Xadrez" no seletor, `ChessBoard` acessível (casas rotuladas como "e4: peão branco, jogável", lance por dois cliques sobre os lances UCI legais, seletor de promoção, setas do teclado, tabuleiro invertido para as pretas, glifos Unicode sem depender de cor), `fenToSquares` pura e textos de status (xeque-mate, afogamento, repetição quíntupla, 75 lances, desistência).
- `MatchState.to_move` passa a opcional; `fen` e `moves` adicionados.
- Testes Vitest em `frontend/tests/Chess.test.tsx`.

### Adicionado (Fase 3 — damas brasileiras)
- Motor `checkers` (regras brasileiras: captura obrigatória e pela maioria, dama voadora, promoção só ao terminar na última fileira, peças capturadas como obstáculo até o fim do lance), IA em 5 níveis (negamax com poda alfa-beta e profundidade iterativa; sem tabela de transposição) e migração 0003 (damas habilitadas, `kings_only`, lance até 64 caracteres).
- Frontend: seleção do jogo, tabuleiro de damas acessível (casas numeradas, lance por clique em cada casa do caminho, tabuleiro invertido para as pretas).
- Testes: invariantes do motor, perft 7/49/302/1469, partida local aleatória com replay e hashes.
- **Não confirmado em fonte oficial** (P-16): vitória por bloqueio, empate por tripla repetição, contagem de 40 lances só com damas e empates de finais de 5 lances (não implementados).

### Adicionado (execução local no Windows — DT-016)
- Dockerfiles do backend e do site (nginx com proxy `/api`), `docker-compose.yml` completo com Mailpit e scripts `scripts/windows/iniciar.ps1` e `parar.ps1`.
- Teste de fumaça ponta a ponta (`scripts/smoke_compose.py`) e job `compose` no CI.
- P-06 (hospedagem) e P-04 (revisão jurídica) marcadas como resolvidas por declaração do responsável.

### Adicionado (Fase 2d — tabuleiro jogável)
- Frontend: tabuleiro do jogo da velha acessível (rótulos por casa, setas do teclado, estado em texto com `aria-live`), partida contra a IA (níveis 1–5, escolha de assento), partida local de visitante validada pelo servidor, desistência e histórico paginado.
- Lógica fora dos componentes visuais (`useGame.ts`, `status.ts`); ressincronização automática em `stale_state`.
- Ainda ausentes: E2E Playwright e auditoria axe (RNF-014/015/016), lobby completo (RF-008), partidas online.

### Adicionado (Fase 2b — partidas contra a IA e locais)
- Migração 0002: `matches`, `match_players`, `match_moves`; jogo da velha habilitado (classificação "Livre" a validar — P-04).
- `POST /matches` (modos `ai` e `local`), `GET /matches/{id}`, `GET /matches/{id}/moves`, `POST /matches/{id}/moves` (idempotente por `client_move_id`, controle otimista por `expected_ply`, bloqueio de linha), `POST /matches/{id}/resign`, `GET /me/matches` (cursor) e `POST /engines/{game_id}/apply` (visitante, sem persistência, limite 8 KB).
- Estado inválido aborta a partida com registro em auditoria; não participantes recebem 404 (IDOR); replay dos lances reproduz estado e hashes (T-122).
- Ainda ausentes: partidas online (convite, fila, WebSocket, reconexão), ranking, empate por acordo e interface do tabuleiro.

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
