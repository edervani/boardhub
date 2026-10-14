# 06 — API REST e Tempo Real

> Versão 0.2.0 · 2026-10-13 · Estado: **aprovado** (2026-10-13) · Nenhum endpoint implementado.

## 1. Convenções gerais
- Base: `/api/v1`. Versionamento na URL; mudanças incompatíveis ⇒ `/api/v2`, com período de convivência.
- JSON UTF-8; datas ISO 8601 UTC; IDs UUID em texto.
- Autenticação: cookie `bh_session` (HttpOnly, Secure, SameSite=Lax). Requisições que alteram estado exigem cabeçalho `X-CSRF-Token` igual ao cookie `bh_csrf` (double-submit) — SEC-07.
- **Paginação:** por cursor: `?limit=20&cursor=<opaco>`; resposta `{ "items": [...], "next_cursor": "..." | null }`; `limit` máx. 100.
- **Ordenação/filtros:** parâmetros explícitos por endpoint, lista branca (ex.: `sort=-finished_at`).
- **Erros** (RFC 9457 simplificado):
```json
{ "type": "illegal_move", "title": "Jogada ilegal", "status": 422,
  "detail": "A peça em e2 não pode ir para e5.", "request_id": "01J…" }
```
- Nunca expor stack trace, SQL ou detalhes internos.
- Limites de taxa (propostos): anônimo 60 req/min/IP; autenticado 120 req/min/usuário; endpoints de auth com limites próprios (abaixo). Excedido ⇒ 429 com `Retry-After`.

## 2. Endpoints

Legenda auth: **—** pública · **U** usuário autenticado · **V** usuário com e-mail verificado · **M** moderador · **A** admin.

| Método e caminho | Finalidade | Auth | Corpo / parâmetros | Sucesso | Erros | Limite | Persistência / auditoria | RF |
|---|---|---|---|---|---|---|---|---|
| POST /auth/register | Criar conta | — | `email, password, display_name, accept_terms_version` | 201 `{}` | 422, 409 (nome), 429 | 5/h/IP | users, perfil, prefs, token | RF-001 |
| POST /auth/verify-email | Confirmar e-mail | — | `token` | 204 | 400, 429 | 10/h/IP | users.email_verified_at | RF-002 |
| POST /auth/resend-verification | Reenviar | U | — | 204 | 429 | 3/h/usuário | auth_tokens | RF-002 |
| POST /auth/login | Entrar | — | `email, password` | 200 perfil resumido + cookies | 401, 429 | 5/15 min/conta+IP | sessions | RF-003 |
| POST /auth/logout | Sair | U | — | 204 | — | — | sessions.revoked_at | RF-004 |
| GET /auth/sessions | Listar sessões | U | — | 200 lista | — | — | — | RF-004 |
| DELETE /auth/sessions/{id} | Revogar sessão | U (dono) | — | 204 | 404 | — | sessions | RF-004 |
| POST /auth/password/forgot | Pedir reset | — | `email` | 202 sempre | 429 | 3/h/IP e e-mail | auth_tokens | RF-005 |
| POST /auth/password/reset | Redefinir | — | `token, new_password` | 204 | 400, 422 | 10/h/IP | users, sessões revogadas, audit | RF-005 |
| GET /me | Dados da conta | U | — | 200 | — | — | — | RF-006 |
| PATCH /me/profile | Editar perfil | U | `display_name?, bio?, avatar_key?, is_public?, show_in_ranking?` | 200 | 422 (`ranking_requires_public_profile`), 403 (menor: só o responsável), 409, 429 (troca de nome) | — | user_profiles | RF-006 |
| GET /me/preferences · PUT | Preferências | U | objeto completo validado | 200 | 422 | — | user_preferences | RF-007 |
| GET /users/{display_name} | Perfil público | — | — | 200 | 404 (inexistente **ou** privado) | — | — | RF-006 |
| GET /games | Catálogo | — | — | 200 | — | — | — | RF-008 |
| POST /matches | Criar partida (IA, convite, local salva) | U (V se ranqueada) | `game_id, mode, ai_level?, preferred_seat?` (`mode`: `ai`, `local`, `online_casual`, `online_ranked`; DT-019 substitui o campo `ranked?` pelo valor de `mode`) | 201 partida + `invite_code` se convite (mostrado uma vez) | 422 (`ranked_not_available`: jogo sem ranking), 403 (`email_not_verified`), 409 (já tem partida ativa; `repeat_opponent_limit` ao entrar em sala ranqueada) | 20/h | matches, match_players | RF-009–011 |
| POST /matches/join | Entrar por código | U | `invite_code` | 200 partida | 404, 409, 403 | 20/h | match_players, status | RF-011 |
| GET /matches/{id} | Estado e metadados | U participante ou partida pública finalizada | — | 200 | 403/404 | — | — | RF-013/020 |
| GET /matches/{id}/moves | Lances | idem | `?since_ply=` | 200 | 403/404 | — | — | RF-014/020 |
| POST /matches/{id}/moves | Lance (alternativa REST ao WS, para IA/local) | U participante | `expected_ply, move, client_move_id` | 200 estado novo | 409 `stale_state`, 422 `illegal_move`, 403 | 120/min | match_moves, matches | RF-013 |
| POST /engines/{game_id}/apply | Validar lance de partida local de visitante (sem persistência — DT-007) | — | `state, move` (estado validado por desserialização estrita, tamanho ≤ 8 KB) | 200 `{state, outcome, legal}` | 422 | 120/min/IP | Nenhuma | RF-009 |
| POST /matches/{id}/resign | Desistir | U participante | — | 200 | 409 finalizada | — | matches, ratings | RF-015 |
| POST /matches/{id}/draw-offer · /draw-response | Empate | U participante | `accept: bool` | 200 | 409, 429 | — | matches | RF-015 |
| POST /matchmaking/queue · DELETE | Entrar/sair da fila | V | `game_id, ranked?` (padrão `false`) | 202 (`state: queued`, com `ranked` e `rating_window`) / 200 (`matched`) / 204 | 409, 422 (`ranked_not_available`) | 30/h | memória ou fila | RF-012 |
| GET /me/matches | Histórico | U | `game_id, mode, result, cursor, limit` | 200 paginado | 422 | — | — | RF-020 |
| GET /me/stats | Estatísticas | U | `game_id?` | 200 `{games: [{game_id, played, wins, losses, draws, win_rate, by_mode[], streak, rating?}]}` | 404 | — | matches, ratings, rating_history | RF-021 |
| GET /ranking/{game_id} | Ranking público (sem login) | — | `cursor?, limit` (1–100, padrão 20) | 200 `{items: [{rank, display_name, avatar_key, rating, games_played}], next_cursor}` | 404 (jogo sem ranking), 422 (cursor), 429 (120/min por IP) | 120/min/IP | ratings, user_profiles | RF-019 |
| GET /academy/{game_id}/lessons | Lições | U | — | 200 | — | — | — | RF-023 |
| GET /academy/exercises/{id} | Exercício (sem a resposta) | U | — | 200 | 404 | — | — | RF-023 |
| POST /academy/exercises/{id}/attempts | Responder | U | `answer, duration_ms` (as dicas são contadas no servidor) | 200 `{correct, feedback, mastery}` | 422, 429 | 60/min | exercise_attempts, progress | RF-023/025 |
| POST /academy/exercises/{id}/hints | Pedir dica (nível 1–3, registrada no servidor) | U | `level` | 200 `{level, text, hints_used}` | 404, 409, 422 | — | exercise_hints | RF-023 |
| GET /academy/tracks, GET /academy/progress | Trilhas e progresso por conceito | U | — | 200 | — | — | progress | RF-022/025 |
| POST /academy/{game_id}/placement | Avaliação inicial | U | respostas | 200 próximo exercício ou nível estimado (o servidor reexecuta as respostas; sem estado no cliente) | 409 `placement_too_soon`, 422 | 5/dia | progress | RF-022 |
| GET /matches/{id}/analysis | Análise pós-partida | U participante; partida finalizada e **não** em andamento | — | 200 (análise síncrona; 202 não implementado, P-20) | 403, 409 | 10/h | cache de análise | RF-024 |
| POST /me/export | Pedir exportação | U | — | 202 | 429 | 1/24 h | data_export_requests, audit | RF-029 |
| GET /me/export/{id} | Baixar | U dono | — | 200 arquivo | 404, 410 | — | — | RF-029 |
| POST /me/delete | Pedir exclusão | U | `password` | 202 | 401, 429 | 3/dia | users.status, audit | RF-030 |
| POST /me/delete/cancel | Cancelar | U | — | 204 | 409 | — | users.status | RF-030 |
| POST /guardian/links/confirm | Responsável confirma vínculo com menor | U (18+) | `token` | 204 | 400, 422 | 10/h | users.guardian_user_id, audit_log | RF-034 |
| GET /guardian/children · PUT /guardian/children/{id}/settings | Ver e ajustar configurações do menor vinculado | U responsável do menor | `daily_minutes?, allow_open_matchmaking?, profile_public?, show_in_ranking?` | 200 | 403 (não é responsável), 422 | 30/h | user_preferences, audit_log | RF-034 |
| POST /reports | Denunciar | V | `target_type, target_id, reason, note?` | 201 | 422, 429 | 10/dia | reports | RF-031 |
| GET /admin/reports · POST /admin/users/{id}/suspend | Moderação | M/A | — | 200 | 403 | — | **audit_log obrigatório** | RF-031 |
| GET /health/live · /health/ready | Saúde | — (ready só na rede interna) | — | 200/503 | — | — | — | RNF-007 |

Validação: Pydantic com `extra="forbid"`, tamanhos máximos em todas as strings, enums fechados. IDs de usuário **nunca** vêm do corpo; usa-se o da sessão.

## 3. WebSocket

### 3.1 Conexão
- URL: `wss://<host>/api/v1/ws` (DT-017; códigos de fechamento 4401, 4403, 4408, 4429, 1009, 1013; retomada com `last_known_ply`; endpoints REST extras: `/matches/{id}/cancel`, `/claim-abandon`, `GET /matchmaking/queue`, `/me/active-matches`). Uma conexão por aba; multiplexa partidas.
- Handshake: valida cookie de sessão e cabeçalho `Origin` contra lista branca; falha ⇒ fecha com código 4401 (não autenticado) ou 4403 (origem).
- Heartbeat: servidor envia `ping` a cada 20 s; sem `pong` em 40 s ⇒ conexão considerada perdida.
- Tamanho máximo de mensagem 4 KB; limite 20 mensagens/s por conexão (excedido ⇒ fecha 4429).

### 3.2 Envelope
```json
{ "type": "submit_move", "id": "<uuid da mensagem>", "payload": { ... } }
```
Respostas a comandos ecoam `reply_to: <id>`. Eventos difundidos têm `seq` monotônico por partida (= `ply` quando ligado a lance).

### 3.3 Mensagens cliente → servidor
| type | payload | Autorização | Resposta |
|------|---------|------------|----------|
| `join_match` | `match_id, last_known_ply` | participante (ou espectador futuro) | `match_snapshot` ou `moves_since` |
| `leave_match` | `match_id` | — | `ack` |
| `submit_move` | `match_id, expected_ply, move, client_move_id` | participante, sua vez | `move_applied` (difundido) ou `error` |
| `resign` | `match_id` | participante | `match_ended` |
| `offer_draw` / `respond_draw` | `match_id`, `accept` | participante | `draw_offered` / `match_ended` / `draw_declined` |
| `claim_abandon` | `match_id` | oponente após tolerância | `match_ended` ou `error: too_early` |
| `pong` | — | — | — |

### 3.4 Eventos servidor → cliente
`match_snapshot {state, ply, players, status, your_seat}` · `move_applied {ply, seat, move, state, next_seat}` · `match_ended {result, end_reason, rating_changes?}` (`rating_changes`: `[{seat, before, after}]`, só em partida ranqueada liquidada; `end_reason: annulled` com `result: null` na partida anulada) · `player_connection {seat, connected, grace_deadline}` · `draw_offered {by_seat}` · `match_started` · `error {code, message, reply_to, current_ply?}`.

### 3.5 Turnos, idempotência e sincronização
- Turno e legalidade verificados no servidor sob bloqueio (doc 05 §4).
- `client_move_id` repetido ⇒ servidor retorna o mesmo `move_applied` sem reaplicar.
- `expected_ply` diferente ⇒ `error: stale_state` com `current_ply`; cliente envia `join_match` para ressincronizar.
- Cliente pode exibir lance otimista, mas **desfaz** se receber `error`.

### 3.6 Desconexão e reconexão
1. Conexão cai ⇒ servidor marca `connected=false`, define `grace_deadline` (60 s) e difunde `player_connection`.
2. Reconexão com backoff exponencial (1, 2, 4, 8 s, máx. 30 s, com jitter).
3. `join_match` com `last_known_ply` ⇒ servidor envia lances faltantes (ou snapshot se > 20).
4. Após o prazo, o oponente pode `claim_abandon`.
5. Reinício do servidor: estado está no banco; clientes reconectam e recebem snapshot (RNF-009).

### 3.7 Segurança específica
Nenhuma mensagem aceita `user_id`, `seat`, `result` ou `state` do cliente. Toda mensagem revalida participação (a sessão pode ter sido revogada: conexões de sessões revogadas são fechadas em até 60 s).
