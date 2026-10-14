# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões seguem [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado (testes ponta a ponta e axe, RNF-014/015/016)
- Pacote `e2e/` (Playwright + `@axe-core/playwright`) e job `e2e` no CI: sobe o `docker compose`, cria uma conta sintética verificada pelo Mailpit e audita com axe as telas principais (cadastro/login, jogos, partidas, histórico/revisão, lobby, ranking, perfil, privacidade, Academy, tema escuro); serious/critical reprovam. Jogo da velha completo contra a IA e um lance de damas e xadrez só pelo teclado. Relatório e traces como artefato em falha. O push em `test/**` passa a disparar o CI e o job `lockfiles` cobre `e2e/package-lock.json`.
- CA-006 (bio com `<script>` permanece texto na tela do próprio perfil) e CA-033 (selos de classificação em texto na lista de jogos) verificados em E2E; demais lacunas de P-15 seguem abertas.
- **Limites:** só Chromium roda no CI (Firefox/WebKit declarados, não executados); checklist manual WCAG, 320 px, zoom e reduced-motion pendentes.

### Corrigido
- Lobby: resposta atrasada da consulta periódica da fila podia recolocar o usuário na fila logo após "Sair da fila" (causa do teste instável "sair da fila volta ao seletor"); teste de regressão adicionado.
- Damas: removida a `opacity` das casas vazias não jogáveis, que reduzia o contraste do número da casa (correção preventiva, calculada à mão; o axe não chegou a reprovar a versão anterior porque a suíte já nasceu com a correção).
- E2E: lockfile `e2e/package-lock.json` gerado pelo job `lockfiles` e versionado.

### Adicionado (Fase 5 — ranking Elo e estatísticas, RF-019, RF-021)
- Elo puro (`game_engines/elo.py`): rating inicial 1200, K = 40 nas primeiras 30 partidas ranqueadas e 20 depois (por jogador), arredondamento meio afastando de zero, piso de 100; valores conferidos à mão em teste (DT-019).
- Modo `online_ranked`: convite (`POST /matches` com `mode: online_ranked`) e fila ranqueada (`ranked: true`), só com contas verificadas e jogos com `ranked_enabled` (por ora só o xadrez; damas aguardam P-16/P-07 — **P-21**). O servidor liquida o rating na mesma transação que encerra a partida (lance final, desistência, abandono ou acordo de empate), de forma idempotente e com as linhas de `ratings` bloqueadas em ordem; contra a IA, local, casual e partidas anuladas nada muda. Desistência/abandono antes do 2º lance de cada lado anula a partida ranqueada. `rating_changes` vai em `MatchOut` e no evento `match_ended`.
- Fila ranqueada separada da casual: janela de rating ±100, +50 a cada 10 s até ±400, candidato mais próximo, reavaliada a cada consulta da fila; no máximo 3 partidas ranqueadas por hora contra o mesmo oponente (fila e convite).
- `GET /ranking/{game_id}` (público, paginado, 120/min por IP): só apelido, avatar, posição, rating e partidas de perfis públicos e ativos que escolheram aparecer, com ≥ 10 partidas; `PATCH /me/profile` aceita `show_in_ranking` (menores só pelo responsável). `GET /me/stats`: vitórias/derrotas/empates por jogo e por modo, sequência atual, rating e histórico de variações.
- Migração 0007 (`ratings`, `rating_history`, `match_players.rating_before/after`, `matchmaking_queue.ranked`; xadrez com ranking).
- Frontend: aba Ranking (tabela acessível paginada), estatísticas e rating no perfil, opções ranqueadas no lobby (convite e fila), variação de rating ao fim da partida.
- Testes: Elo (29 casos), liquidação/idempotência/concorrência/atomicidade, fila e antiabuso, ranking (privacidade, paginação, ECA), estatísticas (500 partidas sintéticas, IDOR) e Vitest.
- **Pendência P-21:** conflito entre RF-019 (Elo para damas) e doc 14/P-16 (regras de damas não conferidas); damas ficam fora do ranking até decisão humana.

### Adicionado (Fase 7 — direitos do titular, RF-029 e RF-030)
- Exportação dos dados (`POST /me/export`, `GET /me/export`, `GET /me/export/{id}`): JSON com conta, perfil, preferências, sessões (sem hashes), partidas e lances, progresso da Academy e eventos de auditoria da própria conta; sem hash de senha, tokens nem nome, e-mail ou id de outras pessoas (o oponente aparece só como tipo). Um pedido por 24 h por titular (429 com `Retry-After`), link válido por 7 dias (410 depois), 404 para quem não pediu (IDOR).
- Exclusão de conta (`POST /me/delete` com senha, `POST /me/delete/cancel`): carência de 14 dias; o pedido revoga todas as sessões, tira da fila, encerra por desistência as partidas online abertas e esconde o apelido do oponente. Em carência o login é restrito (só `/me`, exportação, cancelamento e logout). Limite de 3 pedidos por dia.
- Rotina diária `python -m app.jobs`: conclui exclusões vencidas (cascata; partidas com outro humano ficam com o jogador "Conta removida"; partidas só da conta são apagadas; `audit_log` `account_deleted` sem autor nem dados pessoais), apaga exportações expiradas e cadastros de menores de 12 anos sem confirmação.
- Responsável legal: `POST /guardian/children/{id}/export`, `…/delete` (com a senha do responsável) e `…/delete/cancel`; cada pedido só é cancelado por quem o fez; ao excluir o responsável, o menor volta ao padrão protetivo.
- Migração 0008 (`data_export_requests`, `users.deletion_by_guardian`). Frontend: página Privacidade (pedir e baixar exportação, excluir com senha e confirmação, cancelar).
- Testes: pytest (`test_privacidade.py`) e Vitest (`Privacy.test.tsx`).
- **Pendência P-22:** conciliação entre "sessões revogadas" e cancelamento, fluxo do responsável sem tela, ranking a incluir ao mesclar a Fase 5, cadeia da migração e agendamento da rotina. Decisão DT-020 (proposta).

### Adicionado (Fase 6 — Academy e Mentor, RF-022 a RF-025)
- Conteúdo original em pt-BR como dados versionados (`backend/app/academy/content/*.json`, DT-018): trilhas de jogo da velha, damas brasileiras e xadrez, com lições, conceitos e exercícios; cada solução é conferida pelo motor em teste.
- Backend: trilhas, lições, exercício sem solução, dicas contadas no servidor, resposta validada pelos motores, domínio por conceito com revisão espaçada (3/7/21/60 dias), nivelamento adaptativo sem estado no cliente e progresso. Migração 0006.
- Mentor pós-partida determinístico (sem Stockfish): `GET /matches/{id}/analysis` reexecuta os lances do usuário, classifica pelos limiares do doc 08, cacheia e limita a 10/h; não participante recebe 404.
- IA generativa só atrás de `LLMProvider` (padrão `NullProvider`, sem chamada externa); a reformulação é descartada se acrescentar lance ou casa.
- Frontend: página Academy (trilhas, lição, exercício com os tabuleiros existentes, dicas, nivelamento) e revisão da partida a partir do histórico.
- **Pendências:** P-19 (α provisório 0,30 por conflito com CA-025) e P-20 (revisão do conteúdo, sem provedor local, sem 202).
### Adicionado (Fase 2c — partidas online entre humanos)
- Backend: modo `online_casual` (não ranqueado), convite por código (HMAC, validade de 15 min, uso único), fila de pareamento por jogo (trava consultiva no PostgreSQL, sem rating), desistência, oferta/aceite/recusa de empate por acordo (`agreement`) e abandono por inatividade ou desconexão (`abandon`), com `GET /me/active-matches`.
- WebSocket `/api/v1/ws` (cookie de sessão + verificação de Origin, mensagens Pydantic estritas, fan-out em memória por processo, ping/pong, limites de tamanho e taxa, retomada com `last_known_ply`).
- Migração 0005 (colunas de convite em `matches`, `match_players.disconnected_at`, `draw_offers`, `matchmaking_queue`).
- Frontend: lobby acessível (criar convite, entrar por código, fila, partidas em andamento), `useWebSocket` com reconexão exponencial, avisos `aria-live` de empate/desistência, reuso do tabuleiro; nginx e Vite com proxy de WebSocket.
- Testes: pytest (REST e `websocket_connect`, concorrência, reconexão, IDOR, rate limit, ECA) e Vitest.
- Fora desta entrega: ranking, limite de revanche, limite diário de minutos, chat, testes Playwright/axe.

### Adicionado (Fase 4 — xadrez, backend)
- Motor `chess` (`chess-fide-1`) sobre python-chess (nova dependência `chess>=1.11`, GPL-3.0 — DT-005): estado = lances UCI desde a posição inicial, validado ao carregar (lances reexecutados e FEN conferido); fim por xeque-mate, afogamento, material insuficiente, quíntupla repetição e 75 lances; limite de 600 meios-lances.
- IA em 5 níveis: 1 aleatório com preferência por capturas; 2–5 negamax com poda alfa-beta, aprofundamento iterativo com limite de tempo (0,3/1/2/3 s), tabelas de casas, ordenação MVV-LVA e quiescência de capturas. Stockfish/UCI fica para a Fase 5.
- Migração 0004 (xadrez habilitado); `stalemate` e `fifty_move` passam a ser gravados como motivo de fim.
- Testes: perft 20/400/8902 e Kiwipete 48/2039, mate do pastor, afogamento, roque, en passant, promoção, material insuficiente, estados adulterados, IA×IA curta e partidas pela API com replay e hashes.
- CI: o job `lockfiles` passou a sempre atualizar `backend/uv.lock` (versões já fixadas são preservadas).
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
