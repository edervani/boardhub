# 11 — Testes e Qualidade

> Versão 0.2.0 · 2026-10-13 · Estado: **aprovado** (2026-10-13) · **Nenhum teste de aplicação existe ainda** (não há código). Os únicos testes executáveis hoje são as verificações de documentação (`scripts/check_docs.py`).

## 1. Pirâmide e ferramentas

| Nível | Ferramenta proposta | Escopo |
|-------|--------------------|--------|
| Unitário backend | pytest (+ hypothesis para propriedades) | motores, serviços com repositórios falsos, segurança |
| Unitário frontend | Vitest + Testing Library | componentes, hooks, cliente WS |
| Integração/API | pytest + httpx (ASGI) + PostgreSQL real em contêiner | rotas, transações, migrações |
| WebSocket | pytest com cliente WS de teste | protocolo, reconexão, concorrência |
| E2E | Playwright (Chromium, Firefox, WebKit) | jornadas completas, axe-core |
| Carga | ferramenta a escolher (ex.: k6 ou Locust — P-12) | RNF-001–006 |
| Segurança | pip-audit, npm audit, gitleaks, ZAP baseline | RNF-011/012 |

Versões não fixadas (DT-012).

## 2. Princípios
- Cobertura é indicador, não prova (RNF-020/021). Prioridade: **invariantes de negócio, casos-limite e cenários de abuso**.
- Dados sintéticos: e-mails `@example.test`, nomes como `jogador_teste_01`. **Proibido dado pessoal real.**
- Testes determinísticos: sementes fixas, relógio injetável, sem dependência de rede externa.
- Mocks só em testes; nunca em código de produção.
- Falha de teste nunca é silenciada (`skip`/`xfail` exigem issue vinculada).

## 3. Testes de regras dos jogos
- Tabelas de posições por regra (doc 07), incluindo regras raras (en passant, promoção a cavalo, lei da maioria, não-promoção durante captura).
- **Propriedades (hypothesis):** para qualquer sequência de lances legais aleatórios: `apply` nunca gera estado inválido; `serialize∘deserialize = id`; replay de `match_moves` reproduz o estado; jogo sempre termina dentro do limite teórico.
- perft para xadrez (valores públicos conhecidos) e damas (valores a obter — P-07).

## 4. Testes de IA
Tempo máximo por nível (RNF-002); nunca retorna lance ilegal (10.000 posições aleatórias); nível maior vence nível menor em ≥ 60% de 200 partidas (calibração, não bloqueante); velha nível 5 nunca perde; Mentor: explicações contêm apenas lances verificados; filtro de saída do LLM rejeita lance inventado e HTML.

## 5. Concorrência
Dois `submit_move` simultâneos com mesmo `expected_ply` ⇒ exatamente um aplicado; mesmo `client_move_id` 10× em paralelo ⇒ 1 registro; fim de partida simultâneo com desistência ⇒ um único resultado e um único ajuste de rating; dois pareamentos simultâneos do mesmo usuário ⇒ 1 partida.

## 6. Segurança, privacidade e logs
IDOR em todo endpoint com `{id}`; CSRF (requisição sem token ⇒ 403); WS com origem inválida ⇒ fechado; sessão revogada ⇒ WS fechado; rate limit; enumeração (respostas idênticas, tempo semelhante); varredura de logs dos testes E2E por padrões de senha de teste, tokens e e-mails completos (RNF-013); exportação não contém hash de senha; exclusão pseudonimiza partidas.

## 7. Recuperação, migração e desempenho
Reinício do backend durante partidas (RNF-009); restauração de backup em banco limpo (RNF-008); `alembic upgrade head` → `downgrade base` → `upgrade head` em CI (RNF-028); carga conforme RNF-001–006.

## 8. Matriz de rastreabilidade

Colunas: requisito · documento de origem · módulo responsável · endpoint/componente · caso de teste · critério de aceite · estado · evidência. RF-001 a RF-005 estão **implementado** (PR #1 mesclado); RF-006, RF-007, RF-033 e RF-034 seguem **aprovado** com código mesclado e aceite parcial (P-15). Evidência da Fase 1 na branch `feat/fase-1-base`: CI verde (backend 76 testes pytest, frontend 6 testes Vitest); nenhum requisito é marcado `implementado` antes do merge. Gerada e verificada por `scripts/check_docs.py`.

<!-- MATRIZ:INICIO -->
| Requisito | Origem | Módulo | Endpoint/componente | Teste | Critério | Estado | Evidência |
|---|---|---|---|---|---|---|---|
| RF-001 | doc 02 | services/auth_service | POST /auth/register | T-001 | CA-001 | implementado | [PR #1](https://github.com/edervani/boardhub/pull/1); CI verde |
| RF-002 | doc 02 | services/auth_service | POST /auth/verify-email | T-002 | CA-002 | implementado | [PR #1](https://github.com/edervani/boardhub/pull/1); CI verde |
| RF-003 | doc 02 | services/auth_service | POST /auth/login | T-003 | CA-003 | implementado | [PR #1](https://github.com/edervani/boardhub/pull/1); CI verde |
| RF-004 | doc 02 | services/auth_service | /auth/logout, /auth/sessions | T-004 | CA-004 | implementado | [PR #1](https://github.com/edervani/boardhub/pull/1); CI verde |
| RF-005 | doc 02 | services/auth_service | /auth/password/* | T-005 | CA-005 | implementado | [PR #1](https://github.com/edervani/boardhub/pull/1); CI verde |
| RF-006 | doc 02 | services/user_service | PATCH /me/profile; features/profile | T-006 | CA-006 | aprovado | parcial em [PR #1](https://github.com/edervani/boardhub/pull/1); lacunas em P-15 |
| RF-007 | doc 02 | services/user_service | /me/preferences; features/profile | T-007 | CA-007 | aprovado | parcial em [PR #1](https://github.com/edervani/boardhub/pull/1); lacunas em P-15 |
| RF-008 | doc 02 | frontend features/lobby | GET /games; features/lobby | T-008 | CA-008 | aprovado | — |
| RF-009 | doc 02 | services/match_service | POST /engines/{game}/apply; POST /matches | T-009 | CA-009 | aprovado | parcial em [PR #1](https://github.com/edervani/boardhub/pull/1); lacunas em P-15 |
| RF-010 | doc 02 | services/match_service + ai/opponents | POST /matches; WS submit_move | T-010 | CA-010 | aprovado | parcial em [PR #1](https://github.com/edervani/boardhub/pull/1); lacunas em P-15 |
| RF-011 | doc 02 | services/match_service | POST /matches, /matches/join | T-011 | CA-011 | aprovado | — |
| RF-012 | doc 02 | services/matchmaking_service | /matchmaking/queue | T-012 | CA-012 | aprovado | — |
| RF-013 | doc 02 | services/match_service + realtime | WS submit_move | T-013 | CA-013 | aprovado | parcial em [PR #1](https://github.com/edervani/boardhub/pull/1); lacunas em P-15 |
| RF-014 | doc 02 | realtime | WS join_match | T-014 | CA-014 | aprovado | — |
| RF-015 | doc 02 | services/match_service | /matches/{id}/resign, draw-* | T-015 | CA-015 | aprovado | parcial em [PR #1](https://github.com/edervani/boardhub/pull/1); lacunas em P-15 |
| RF-016 | doc 02 | game_engines/tictactoe | features/tictactoe | T-016 | CA-016 | aprovado | parcial em [PR #1](https://github.com/edervani/boardhub/pull/1); lacunas em P-15 |
| RF-017 | doc 02 | game_engines/checkers | features/checkers | T-017 | CA-017 | aprovado | parcial em [PR #1](https://github.com/edervani/boardhub/pull/1); lacunas em P-15 |
| RF-018 | doc 02 | game_engines/chess | features/chess | T-018 | CA-018 | aprovado | parcial em [PR #1](https://github.com/edervani/boardhub/pull/1); lacunas em P-15 |
| RF-019 | doc 02 | services/rating_service | GET /ranking/{game_id} | T-019 | CA-019 | aprovado | — |
| RF-020 | doc 02 | services/match_service | GET /me/matches; /matches/{id}/moves | T-020 | CA-020 | aprovado | parcial em [PR #1](https://github.com/edervani/boardhub/pull/1); lacunas em P-15 |
| RF-021 | doc 02 | services/stats_service | GET /me/stats | T-021 | CA-021 | aprovado | — |
| RF-022 | doc 02 | services/academy_service | POST /academy/{game}/placement | T-022 | CA-022 | aprovado | código na branch `feat/fase-6-academy` (PR aberto; `implementado` só após merge) |
| RF-023 | doc 02 | services/academy_service | /academy/exercises/* | T-023 | CA-023 | aprovado | código na branch `feat/fase-6-academy` (PR aberto; `implementado` só após merge) |
| RF-024 | doc 02 | ai/mentor + ai/llm | GET /matches/{id}/analysis | T-024 | CA-024 | aprovado | código na branch `feat/fase-6-academy` (PR aberto; `implementado` só após merge) |
| RF-025 | doc 02 | services/academy_service | features/academy | T-025 | CA-025 | aprovado | código na branch `feat/fase-6-academy` (PR aberto; `implementado` só após merge) |
| RF-026 | doc 02 | services/achievement_service | (fase 6) | T-026 | CA-026 | aprovado | — |
| RF-027 | doc 02 | services/academy_service | (fase 6) | T-027 | CA-027 | aprovado | — |
| RF-028 | doc 02 | services/notification_service | WS eventos | T-028 | CA-028 | aprovado | — |
| RF-029 | doc 02 | services/privacy_service | /me/export | T-029 | CA-029 | aprovado | — |
| RF-030 | doc 02 | services/privacy_service | /me/delete | T-030 | CA-030 | aprovado | — |
| RF-031 | doc 02 | services/moderation_service | /reports, /admin/* | T-031 | CA-031 | aprovado | — |
| RF-032 | doc 02 | services/social_service | (fase 6) | T-032 | CA-032 | aprovado | — |
| RF-033 | doc 02 | services/catalog_service | GET /games; features/lobby | T-033 | CA-033 | aprovado | parcial em [PR #1](https://github.com/edervani/boardhub/pull/1); lacunas em P-15 |
| RF-034 | doc 02 | services/guardian_service | /guardian/*; features/guardian | T-034 | CA-034 | aprovado | parcial em [PR #1](https://github.com/edervani/boardhub/pull/1); lacunas em P-15 |
| RNF-001 | doc 03 | transversal | — | T-101 | CA-101 | aprovado | — |
| RNF-002 | doc 03 | transversal | — | T-102 | CA-102 | aprovado | — |
| RNF-003 | doc 03 | transversal | — | T-103 | CA-103 | aprovado | — |
| RNF-004 | doc 03 | transversal | — | T-104 | CA-104 | aprovado | — |
| RNF-005 | doc 03 | transversal | — | T-105 | CA-105 | aprovado | — |
| RNF-006 | doc 03 | transversal | — | T-106 | CA-106 | aprovado | — |
| RNF-007 | doc 03 | transversal | — | T-107 | CA-107 | aprovado | — |
| RNF-008 | doc 03 | transversal | — | T-108 | CA-108 | aprovado | — |
| RNF-009 | doc 03 | transversal | — | T-109 | CA-109 | aprovado | — |
| RNF-010 | doc 03 | transversal | — | T-110 | CA-110 | aprovado | — |
| RNF-011 | doc 03 | transversal | — | T-111 | CA-111 | aprovado | — |
| RNF-012 | doc 03 | transversal | — | T-112 | CA-112 | aprovado | — |
| RNF-013 | doc 03 | transversal | — | T-113 | CA-113 | aprovado | — |
| RNF-014 | doc 03 | transversal | — | T-114 | CA-114 | aprovado | — |
| RNF-015 | doc 03 | transversal | — | T-115 | CA-115 | aprovado | — |
| RNF-016 | doc 03 | transversal | — | T-116 | CA-116 | aprovado | — |
| RNF-017 | doc 03 | transversal | — | T-117 | CA-117 | aprovado | — |
| RNF-018 | doc 03 | transversal | — | T-118 | CA-118 | aprovado | — |
| RNF-019 | doc 03 | transversal | — | T-119 | CA-119 | aprovado | — |
| RNF-020 | doc 03 | transversal | — | T-120 | CA-120 | aprovado | — |
| RNF-021 | doc 03 | transversal | — | T-121 | CA-121 | aprovado | — |
| RNF-022 | doc 03 | transversal | — | T-122 | CA-122 | aprovado | — |
| RNF-023 | doc 03 | transversal | — | T-123 | CA-123 | aprovado | — |
| RNF-024 | doc 03 | transversal | — | T-124 | CA-124 | aprovado | — |
| RNF-025 | doc 03 | transversal | — | T-125 | CA-125 | aprovado | — |
| RNF-026 | doc 03 | transversal | — | — | CA-126 | aprovado | — |
| RNF-027 | doc 03 | transversal | — | T-127 | CA-127 | aprovado | — |
| RNF-028 | doc 03 | transversal | — | T-128 | CA-128 | aprovado | — |
<!-- MATRIZ:FIM -->
