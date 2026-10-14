# 05 — Modelagem de Dados

> Versão 0.2.0 · 2026-10-13 · Estado: **aprovado** (2026-10-13) · SGBD: PostgreSQL (versão a confirmar — P-02)

Convenções: chaves primárias `uuid` (gerado na aplicação, UUIDv7 se disponível — DT-011); timestamps `timestamptz` em UTC; nomes em `snake_case`; toda tabela tem `created_at`; exclusões lógicas apenas onde indicado.

## 1. Avaliação das tabelas sugeridas

| Tabela | Decisão | Justificativa |
|--------|---------|---------------|
| users | **Criar** | Identidade e credenciais |
| user_profiles | **Criar** | Separar dados públicos de credenciais (minimiza exposição) |
| user_preferences | **Criar** | RF-007 |
| games | **Criar** (tabela de referência) | Catálogo + flags de habilitação; 3 linhas semeadas por migração |
| matches | **Criar** | Estado oficial |
| match_players | **Criar** | Suporta IA como participante e futuro >2 jogadores |
| match_moves | **Criar** | Histórico, replay, auditoria, idempotência |
| ratings | **Criar** + `rating_history` | Rating atual + trilha auditável |
| sessions | **Criar** | DT-004 (sessão opaca) |
| auth_tokens | **Criar** | Verificação de e-mail e reset de senha (hash) |
| lessons, exercises | **Criar** (fase 3) | Conteúdo da Academy, versionado |
| user_skill_progress | **Criar** (fase 3) | RF-025 |
| exercise_attempts | **Criar** (fase 3) | Evidência para domínio — substitui/generaliza `challenge_attempts` |
| achievements, user_achievements | **Adiar** (fase 6) | RF-026 |
| daily_challenges | **Adiar** (fase 6); tentativas usam `exercise_attempts` | Evita tabela duplicada |
| friendships, invitations | **Adiar** (fase 6) | RF-032; convites de partida usam `matches.invite_code` |
| reports, audit_log | **Criar** (`audit_log` fase 1; `reports` fase 6/7) | RF-031, SEC-11 |
| data_export_requests | **Criar** | RF-029 |

## 2. Entidades (v1)

### users
| Coluna | Tipo | Restrições |
|--------|------|-----------|
| id | uuid | PK |
| email | citext | UNIQUE, NOT NULL |
| password_hash | text | NOT NULL (Argon2id, formato PHC) |
| email_verified_at | timestamptz | NULL |
| role | text | NOT NULL, CHECK in (`user`,`moderator`,`admin`), default `user` |
| status | text | CHECK in (`active`,`suspended`,`pending_deletion`), default `active` |
| deletion_requested_at | timestamptz | NULL |
| age_band | text | NOT NULL, CHECK in (`under_12`,`12_15`,`16_17`,`18_plus`) — DT-015 |
| guardian_user_id | uuid | NULL, FK→users ON DELETE SET NULL (RF-034) |
| terms_version | text | NOT NULL |
| last_login_at | timestamptz | NULL |
| created_at, updated_at | timestamptz | NOT NULL |

Índices: único em `email`; parcial em `status='pending_deletion'`.

### user_profiles
`user_id` PK/FK→users ON DELETE CASCADE; `display_name` citext UNIQUE NOT NULL; `avatar_key` text (lista fechada); `bio` varchar(160); `is_public` bool default true; `display_name_changed_at`.

### user_preferences
`user_id` PK/FK CASCADE; `theme` (`light|dark|system`); `motion` (`full|reduced|none|system`); `sound` bool; `move_confirmation` bool; `piece_styles` jsonb (`{"chess":"classic",…}`, validado por esquema); `locale` default `pt-BR`.

### sessions
`id` uuid PK; `user_id` FK CASCADE; `token_hash` bytea UNIQUE (SHA-256 do token opaco); `created_at`; `last_seen_at`; `expires_at`; `revoked_at`; `user_agent_summary` varchar(80) (ex.: "Firefox / Linux" — sem string completa); **sem IP armazenado em claro** (opcional: prefixo /24 truncado para detecção de abuso — DT-013).

### auth_tokens
`id`; `user_id` FK CASCADE; `purpose` (`verify_email|reset_password`); `token_hash` UNIQUE; `expires_at`; `used_at`. Limpeza diária de expirados.

### games
`id` text PK (`tictactoe`,`checkers`,`chess`); `name`; `enabled` bool; `rules_version` text; `ranked_enabled` bool; `age_rating` text NOT NULL (RF-033).

### matches
| Coluna | Tipo | Notas |
|--------|------|------|
| id | uuid PK | |
| game_id | text FK→games | |
| mode | text | `local`,`ai`,`online_casual`,`online_ranked` |
| status | text | `waiting`,`in_progress`,`finished`,`aborted`,`annulled` |
| invite_code_hash | bytea NULL UNIQUE | só salas por convite |
| invite_expires_at | timestamptz NULL | |
| state | jsonb NOT NULL | estado oficial serializado pelo motor (com `schema_version`) |
| ply | int NOT NULL default 0 | nº de meio-lances aplicados — controle otimista |
| result | text NULL | `p1_win`,`p2_win`,`draw` |
| end_reason | text NULL | `normal`,`resign`,`abandon`,`agreement`,`repetition`,`fifty_move`,`stalemate`,`timeout`,`annulled` |
| rules_version | text NOT NULL | copiada de `games` na criação |
| ai_level | smallint NULL | |
| started_at, finished_at, created_at, updated_at | timestamptz | |

Índices: (`status`, `game_id`); (`updated_at`) para limpeza de abandonos.

### match_players
PK (`match_id`,`seat`); `seat` smallint (1/2); `user_id` uuid NULL FK→users **ON DELETE SET NULL** (pseudonimização em RF-030); `is_ai` bool; `rating_before`, `rating_after` int NULL; `connected` bool; `disconnected_at`. CHECK: `is_ai` XOR `user_id` não nulo (exceto após exclusão — flag `removed_account`). Índice (`user_id`, `match_id`). Restrição parcial: um usuário em no máx. 1 partida `in_progress` online por jogo — garantida por serviço + índice único parcial em tabela auxiliar `active_online_matches(user_id, game_id)`.

### match_moves
PK (`match_id`,`ply`); `seat`; `move` text (notação do jogo: índice 0–8, PDN, UCI); `client_move_id` uuid; `state_after_hash` bytea (integridade); `created_at`. UNIQUE (`match_id`,`client_move_id`) → idempotência.

### ratings / rating_history
`ratings`: PK (`user_id`,`game_id`); `rating` int default 1200; `games_played` int; `updated_at`.
`rating_history`: `id`; `user_id`; `game_id`; `match_id` UNIQUE com `user_id`; `before`; `after`; `created_at`.

### Academy (fase 3)
> **DT-018:** `lessons` e `exercises` não são tabelas; o conteúdo vive em `backend/app/academy/content/*.json`. Tabelas criadas na migração 0006: `exercise_attempts`, `user_skill_progress`, `exercise_hints`, `academy_placements`, `match_analyses`.

- `lessons`: `id`, `game_id`, `concept_key`, `title`, `content` jsonb, `version`, `order_index`, `published`.
- `exercises`: `id`, `lesson_id`, `concept_key`, `difficulty` (1–5), `initial_state` jsonb, `objective` jsonb (ex.: `{"type":"best_move","accept":["e2e4"]}` ou `{"type":"mate_in","n":1}`), `hints` jsonb, `version`.
- `exercise_attempts`: `id`, `user_id` CASCADE, `exercise_id`, `correct` bool, `hints_used`, `duration_ms`, `created_at`.
- `user_skill_progress`: PK (`user_id`,`game_id`,`concept_key`); `mastery` real 0–1; `status`; `next_review_at`; `updated_at`.

### audit_log
`id`; `actor_user_id` NULL; `action`; `target_type`; `target_id`; `details` jsonb (sem dados pessoais desnecessários); `created_at`. Somente inserção (permissão de UPDATE/DELETE revogada para o usuário da aplicação).

### data_export_requests
`id`; `user_id` CASCADE; `status`; `file_key`; `expires_at`; `created_at`.

## 3. Estado oficial da partida
- Fonte da verdade: `matches.state` + `matches.ply`; `match_moves` permite reconstrução (replay de todos os lances a partir do estado inicial deve produzir o mesmo `state` — invariante testada T-122).
- O cliente **nunca** envia estado; só lances.
- `state` inclui `schema_version`; mudança de formato exige migração de dados ou leitor retrocompatível.

## 4. Transações e concorrência
- `submit_move`: `BEGIN; SELECT … FROM matches WHERE id=$1 FOR UPDATE;` verifica `ply == expected_ply`, aplica, grava, `COMMIT`. Nível READ COMMITTED basta graças ao bloqueio de linha.
- Fim de partida + rating: mesma transação; bloquear as linhas de `ratings` dos dois jogadores em ordem determinística (menor `user_id` primeiro) para evitar deadlock.
- Pareamento: `SELECT … FOR UPDATE SKIP LOCKED` na fila (ou estrutura em memória na v1 com uma instância — DT-009).

## 5. Proteção contra duplicidade
UNIQUE em e-mail, nome de exibição, (`match_id`,`ply`), (`match_id`,`client_move_id`), (`user_id`,`match_id`) em `rating_history`, `user_achievements(user_id, achievement_id)`.

## 6. Retenção (propostas — validar com jurídico, P-04)

| Dado | Retenção |
|------|----------|
| Conta e perfil | Enquanto ativa; apagados 14 dias após pedido de exclusão |
| Sessões | 90 dias após expiração/revogação, depois apagadas |
| auth_tokens | 7 dias após expirar |
| Partidas e lances | Indefinido, pseudonimizados após exclusão de conta |
| exercise_attempts | 24 meses, depois agregados anonimizados |
| audit_log | 2 anos |
| Exportações | Arquivo apagado em 7 dias |
| Logs de aplicação | 30 dias (doc 13) |

## 7. Exclusão e exportação
- Exclusão (RF-030): job diário processa `pending_deletion` vencidos: apaga `users` (CASCADE em perfil, preferências, sessões, tokens, progresso, tentativas), `match_players.user_id` vira NULL com `removed_account=true`, ratings apagados, `audit_log` mantém o `actor_user_id` substituído por NULL.
- Exportação (RF-029): JSON gerado a partir das tabelas acima, sem hashes de senha nem tokens.

## 8. Migrações
Alembic; uma migração por mudança lógica; revisão obrigatória; `downgrade` implementado ou justificativa escrita (RNF-028); migrações de dados separadas das de esquema; nunca editar migração já aplicada em homologação/produção.

## 9. Dados analíticos
Nenhuma tabela analítica com dados pessoais na v1. Métricas de produto são agregadas (contagens por dia) sem identificador de usuário.
