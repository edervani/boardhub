# 15 — Critérios de Aceite

> Versão 0.2.0 · 2026-10-13 · Estado: **aprovado** (2026-10-13)

Regra geral: uma funcionalidade **não** é aceita porque a tela existe ou o código compila. Aceite exige: testes automatizados indicados passando no CI, verificação descrita executada e evidência anexada ao PR (log do CI, captura, relatório). Formato: **Dado / Quando / Então**.

## 1. Critérios por requisito funcional

| ID | Requisito | Critérios (todos obrigatórios) | Verificação | Evidência |
|----|-----------|-------------------------------|-------------|-----------|
| CA-001 | RF-001 | (a) Dado e-mail novo e senha válida, quando cadastra, então 201 e linhas em users/perfil/prefs com hash Argon2id. (b) E-mail já existente ⇒ resposta HTTP e corpo idênticos a (a). (c) Senha de 11 caracteres ⇒ 422. (d) 6º cadastro/h do mesmo IP ⇒ 429. (e) Logs da requisição não contêm a senha. | T-001 (integração) | Relatório pytest |
| CA-002 | RF-002 | Token válido verifica; reutilização ⇒ 400; expirado (relógio +25 h) ⇒ 400; token não aparece em claro no banco; conta não verificada recebe 403 ao criar partida ranqueada. | T-002 | pytest |
| CA-003 | RF-003 | Credenciais corretas ⇒ cookie com HttpOnly, Secure, SameSite=Lax; erradas ⇒ 401 com mesma mensagem para e-mail inexistente; 6ª falha em 15 min ⇒ 429. | T-003 | pytest + inspeção de cabeçalhos |
| CA-004 | RF-004 | Logout invalida cookie no servidor (reuso ⇒ 401); revogar outra sessão funciona; troca de senha revoga demais sessões; sessão expirada ⇒ 401. | T-004 | pytest |
| CA-005 | RF-005 | Pedido para e-mail inexistente ⇒ 202 idêntico; token usado duas vezes ⇒ segunda 400; após reset, sessões antigas ⇒ 401. | T-005 | pytest |
| CA-006 | RF-006 | Editar perfil próprio ⇒ 200; não há endpoint que edite perfil alheio; bio com `<script>` é exibida como texto (E2E); perfil privado ⇒ 404 igual a inexistente; e-mail ausente da resposta pública. | T-006 | pytest + Playwright |
| CA-007 | RF-007 | Preferências persistem entre sessões; `prefers-reduced-motion` define padrão; alterar estilo de peças não altera nível da IA nem `ai_level` (teste de inspeção de dependências); a notação escolhida (`move_notation`) muda só a exibição: o servidor segue em UCI e entrega `san_moves`. | T-007 | Vitest + pytest |
| CA-008 | RF-008 | Lobby lista 3 jogos e partidas ativas do usuário; aviso de conta não verificada visível; navegável por teclado. | T-008 | Playwright + axe |
| CA-009 | RF-009 | Partida local completa nos 3 jogos sem conta; lance ilegal rejeitado com mensagem; resultado não altera rating. | T-009 | Playwright |
| CA-010 | RF-010 | Partida contra IA em cada nível termina sem lance ilegal; resposta da IA dentro do RNF-002; reinício do servidor no meio ⇒ partida retomada. | T-010 | pytest + Playwright |
| CA-011 | RF-011 | Código entra uma vez; segundo ingresso ⇒ 409; expirado ⇒ 404; criador não ocupa as duas cadeiras; ambos recebem `match_started`. | T-011 | pytest WS |
| CA-012 | RF-012 | Dois usuários com ratings 1200 e 1250 são pareados; usuário nunca em duas partidas simultâneas da fila (teste concorrente); após 60 s oferece IA. | T-012 | pytest |
| CA-013 | RF-013 | Lance fora de turno ⇒ `not_your_turn`; não participante ⇒ `not_participant`; ilegal ⇒ `illegal_move` sem mudar estado; `expected_ply` antigo ⇒ `stale_state`; mesmo `client_move_id` ⇒ 1 registro; campos `result`/`state` enviados pelo cliente são rejeitados (422). | T-013 | pytest WS |
| CA-014 | RF-014 | Derrubar conexão e reconectar ⇒ cliente recebe lances perdidos e estado idêntico ao do servidor (hash); oponente recebe `player_connection`; após 60 s `claim_abandon` encerra; antes ⇒ `too_early`. | T-014 | pytest WS + Playwright |
| CA-015 | RF-015 | Desistência encerra e atualiza rating; desistência antes do 2º lance ⇒ `annulled` sem rating; 2ª oferta de empate em < 10 lances ⇒ rejeitada. | T-015 | pytest |
| CA-016 | RF-016 | Todas as 8 linhas vencedoras detectadas; empate em tabuleiro cheio; jogada em casa ocupada rejeitada; propriedades do doc 11 §3 passam. | T-016 | pytest + hypothesis |
| CA-017 | RF-017 | Cada regra numerada do doc 07 §3 tem ≥ 1 teste com posição; lei da maioria, dama voadora e não-promoção cobertas; perft coincide com referência (após P-07). | T-017 | pytest |
| CA-018 | RF-018 | perft(posição inicial) profundidades 1–4 = 20, 400, 8.902, 197.281; roque, en passant, promoção, afogamento, material insuficiente e repetição testados. | T-018 | pytest |
| CA-019 | RF-019 | Vitória 1200×1200 com K=40 ⇒ +20/−20; ratings e histórico gravados na mesma transação (falha simulada após cálculo ⇒ nada gravado); partida casual não altera rating. | T-019 | pytest |
| CA-020 | RF-020 | Histórico paginado e filtrado; replay reproduz estado final; usuário não vê partida privada de terceiros (403/404). | T-020 | pytest + Playwright |
| CA-021 | RF-021 | Estatísticas batem com contagem direta de `matches` em base sintética de 500 partidas. | T-021 | pytest |
| CA-022 | RF-022 | Avaliação gera mastery ≤ 0,5; pode ser pulada; idade não é parâmetro da API. | T-022 | pytest |
| CA-023 | RF-023 | Resposta correta/incorreta avaliada pelo motor; GET de exercício não expõe a resposta; dicas reduzem ganho. | T-023 | pytest |
| CA-024 | RF-024 | Análise indisponível em partida ranqueada em andamento (409); explicações só citam lances verificados; com Ollama desligado retorna template; saída de LLM com lance inventado é descartada. | T-024 | pytest |
| CA-025 | RF-025 | 5 acertos no **mesmo** exercício não concedem domínio; 5 acertos em 3 exercícios em 2 dias concedem; erro em revisão ⇒ `em revisão`. | T-025 | pytest |
| CA-026 | RF-026 | Conquista concedida uma vez mesmo com eventos repetidos; sem valor monetário (sem endpoint de troca). | T-026 | pytest |
| CA-027 | RF-027 | Mesmo desafio para todos no dia (fuso America/Sao_Paulo); uma tentativa válida contabilizada. | T-027 | pytest |
| CA-028 | RF-028 | Notificação de vez de jogar entregue via WS; nenhum e-mail de marketing sem consentimento. | T-028 | pytest |
| CA-029 | RF-029 | Exportação contém conta, perfil, prefs, partidas, progresso e **não** contém hash/tokens; link expira em 7 dias; 2º pedido em 24 h ⇒ 429. | T-029 | pytest |
| CA-030 | RF-030 | Senha errada ⇒ 401; após 14 dias (relógio simulado) não há linha em users; partidas do oponente permanecem com "Conta removida"; sessões revogadas imediatamente. | T-030 | pytest |
| CA-031 | RF-031 | Usuário comum ⇒ 403 em `/admin/*`; suspensão gera linha em `audit_log`; suspenso não consegue login. | T-031 | pytest |
| CA-032 | RF-032 | Usuário bloqueado não consegue convidar quem o bloqueou. | T-032 | pytest |
| CA-033 | RF-033 | Os três jogos exibem selo com texto no lobby e antes da partida; jogo com `age_rating` nulo não pode ser habilitado; usuário abaixo da classificação não vê o jogo. | T-033 | Playwright + pytest |
| CA-034 | RF-034 | Conta `12–15` nasce privada e fora do ranking; menor de 12 sem confirmação não acessa partidas online e é removido após 7 dias (relógio simulado); responsável altera limite de tempo e a mudança vai para `audit_log`; limite atingido bloqueia nova partida (local, IA, convite, entrada e consulta da fila) com 429 `daily_limit_reached` e `Retry-After`, sem bloquear a partida em andamento (P-23); tempo medido pelo servidor com relógio simulado, virada do dia em America/Sao_Paulo (limite do dia anterior não vale no seguinte), várias partidas sem contagem dupla, HTTP e WebSocket; responsável não vinculado ⇒ 404 igual ao inexistente; painel do responsável. | T-034 | pytest + Vitest |

## 2. Critérios por requisito não funcional
Para cada RNF-0nn (doc 03) existe o critério **CA-1nn**: *a meta proposta é atingida no cenário descrito, medida pelo teste T-1nn; evidência = relatório da execução com data, ambiente e versão.* Metas não atingidas exigem decisão registrada (ajustar meta com justificativa ou corrigir). CA-126 (custo) é verificado por planilha aprovada pelo responsável (P-06).

## 3. Critérios por fase
Ver condições de conclusão em [doc 14](14-plano-de-implementacao.md). Resumo: uma fase só termina quando todos os CA dos RF da fase estão `validado`, a matriz está atualizada, o CHANGELOG registra a entrega e não há falha de teste aberta sem issue.
