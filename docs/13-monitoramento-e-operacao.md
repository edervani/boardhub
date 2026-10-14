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
Diário: verificar backup; job de limpeza (tokens, sessões, exportações, exclusões de conta). A rotina de privacidade existe como `python -m app.jobs` (dentro do contêiner do backend, ex.: `docker compose exec backend python -m app.jobs`); ela conclui exclusões vencidas (14 dias), apaga exportações expiradas (7 dias) e remove cadastros de menores de 12 anos sem confirmação (7 dias); código de saída diferente de zero indica falha numa exclusão. **Agendamento:** no ambiente `docker compose` (inclusive Windows com Docker Desktop) o serviço `jobs` (mesma imagem do backend, sem portas) executa a rotina ao subir e a cada `JOBS_INTERVAL_SECONDS` (padrão 86400 s = 24 h, configurável no `.env`); se falhar, repete em 5 min; o healthcheck fica saudável só se a última execução bem-sucedida for recente (2 intervalos + 10 min). Ver os registros com `docker compose logs jobs`; execução manual: `docker compose exec backend python -m app.jobs`. Fora do compose, agende o mesmo comando (cron ou Agendador de Tarefas). Semanal: revisar alertas e erros. Mensal: atualizar dependências, revisar acessos. Trimestral: teste de restauração, revisão de capacidade e custos.

## 6. Runbooks
- **RB-01 Banco indisponível:** verificar contêiner/volume → logs do PostgreSQL → espaço em disco → restaurar de backup se corrompido (registrar perda conforme RPO) → comunicar usuários.
- **RB-02 Suspeita de vazamento de credenciais:** revogar todas as sessões (`UPDATE sessions SET revoked_at=now()` via script auditado) → rotacionar segredos → iniciar processo de incidente (doc 09 §5).
- **RB-03 Sobrecarga da IA:** reduzir nível máximo/concorrência por configuração → desabilitar análises temporariamente.
- **RB-04 Segredo encontrado no repositório:** rotacionar imediatamente, depois limpar histórico; a rotação é o que protege.
- **RB-05 Partidas travadas:** listar `in_progress` sem atividade > 24 h → encerrar como `aborted` via script auditado.

## 7. Capacidade e custos
Revisão trimestral: CPU da IA, conexões WS, crescimento de `match_moves`. Orçamento mensal pendente (P-06).

## 8. Modo nativo no Windows (sem Docker) — somente testes (DT-025)

Execução para quem não consegue instalar Docker (ex.: Windows Server 2019 virtualizado). Procedimento completo no [README](../README.md#windows-sem-docker-modo-nativo-só-para-testes).

| Item | Como é no modo nativo |
|------|-----------------------|
| Processos | PostgreSQL 17 portátil (`pg_ctl`, só `127.0.0.1:5433`), backend `uvicorn` (`127.0.0.1:<porta>`, padrão 8080) e, opcionalmente, Mailpit (`127.0.0.1:8025`/`1025`); PIDs em `.native\run`; sem serviço do Windows nem administrador |
| Site | O backend serve `frontend\dist` (`SERVE_FRONTEND_DIR`, fallback de SPA; `/api` nunca cai no fallback); mesma origem de `/api`, sem nginx |
| Cookies/CORS | `COOKIE_SECURE=false` (HTTP em localhost), `SameSite=Lax`, CSRF por cabeçalho inalterado; `FRONTEND_ORIGIN=http://localhost:<porta>` é a única origem aceita por CORS e WebSocket (acessar por `127.0.0.1` ou pelo nome da máquina é recusado) |
| E-mail | `MAIL_BACKEND=file` grava um JSON por linha em `.native\data\emails.jsonl` (inclui links de verificação; só com `APP_ENV` development/test; o log registra apenas que houve gravação) ou SMTP para o Mailpit |
| Segredos | `.native\.env` (permissões restritas ao usuário, ignorado pelo controle de versão) com `SECRET_KEY` e senhas aleatórias; o usuário da aplicação não é superusuário |
| Registros | `.native\logs\backend.log`, `backend.err.log`, `postgres.log`, `jobs.log` |
| Backup | Não há; `pg_dump.exe` fica em `.native\tools\pgsql\bin` se for necessário |
| Limites | Só testes; sem TLS; para se a sessão do Windows terminar; nenhum dado real; não substitui o plano de produção do doc 12 |
