# 13 — Monitoramento e Operação

> Versão 0.2.0 · 2026-10-13 · Estado: **aprovado** (2026-10-13)

## 1. Logs
- JSON estruturado em stdout: `timestamp`, `level`, `logger`, `request_id`, `event`, `user_ref` (hash truncado do ID, não e-mail), `match_id` quando relevante, `duration_ms`, `status`.
- Sanitização central (SEC-12): lista negra de chaves (`password`, `token`, `cookie`, `authorization`, `secret`, `email`) mascaradas antes da serialização; teste automatizado (RNF-013).
- Não registrar conteúdo de partidas além de IDs e contagens; não registrar textos enviados ao Ollama.
- Retenção 30 dias; acesso restrito.

## 2. Métricas (formato Prometheus proposto, endpoint interno)
- Aplicação: requisições por rota/status, latência p50/p95/p99, erros 5xx, 429 por rota.
- Jogo: `ws_connections_active`, `ws_messages_total{type}`, `move_validation_seconds{game}`, `ai_move_seconds{game,level}`, `matches_active{game,mode}`, `reconnects_total`, `abandon_claims_total`, `stale_state_total`.
- Banco: conexões em uso do pool, tempo de consulta, bloqueios aguardando, tamanho, idade do último backup bem-sucedido.
- IA: `llm_requests_total{outcome=ok|timeout|rejected}`.
Ferramenta (Prometheus + Grafana auto-hospedados) é proposta; nenhuma ferramenta externa de terceiros sem análise de privacidade.

## 3. Saúde
`/health/live` (processo responde) e `/health/ready` (banco acessível, migrações em dia; Ollama **não** entra no readiness por ser opcional).

## 4. Alertas (limiares propostos)
| Alerta | Condição | Severidade |
|--------|----------|-----------|
| API indisponível | readiness falha 2 min | Crítica |
| Erros 5xx | > 2% por 5 min | Alta |
| Latência de lance | p95 > 2× meta RNF-001 por 10 min | Média |
| Backup | último sucesso > 26 h | Alta |
| Disco do banco | > 80% | Média |
| Picos de 429/login falho | > 10× linha de base | Média (possível ataque) |

## 5. Rotinas operacionais
Diário: verificar backup; job de limpeza (tokens, sessões, exportações, exclusões de conta). Semanal: revisar alertas e erros. Mensal: atualizar dependências, revisar acessos. Trimestral: teste de restauração, revisão de capacidade e custos.

## 6. Runbooks
- **RB-01 Banco indisponível:** verificar contêiner/volume → logs do PostgreSQL → espaço em disco → restaurar de backup se corrompido (registrar perda conforme RPO) → comunicar usuários.
- **RB-02 Suspeita de vazamento de credenciais:** revogar todas as sessões (`UPDATE sessions SET revoked_at=now()` via script auditado) → rotacionar segredos → iniciar processo de incidente (doc 09 §5).
- **RB-03 Sobrecarga da IA:** reduzir nível máximo/concorrência por configuração → desabilitar análises temporariamente.
- **RB-04 Segredo encontrado no repositório:** rotacionar imediatamente, depois limpar histórico; a rotação é o que protege.
- **RB-05 Partidas travadas:** listar `in_progress` sem atividade > 24 h → encerrar como `aborted` via script auditado.

## 7. Capacidade e custos
Revisão trimestral: CPU da IA, conexões WS, crescimento de `match_moves`. Orçamento mensal pendente (P-06).
