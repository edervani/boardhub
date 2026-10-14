# 02 — Requisitos Funcionais

> Versão 0.2.0 · 2026-10-13 · Estado de todos os requisitos: **aprovado** (2026-10-13) · Implementação: **não iniciada**

Convenções: prioridade **M** (obrigatório v1), **S** (desejável v1), **C** (fase 6+). Testes `T-xxx` em [doc 11](11-testes-e-qualidade.md); critérios `CA-xxx` em [doc 15](15-criterios-de-aceite.md); segurança `SEC-xx` em [doc 09](09-seguranca-e-privacidade.md). Toda referência a "servidor valida" significa validação no backend, independente do que o cliente envie.

---

## Contas e identidade

### RF-001 — Cadastro de conta
- **Descrição:** visitante cria conta com e-mail, nome de exibição e senha.
- **Justificativa:** histórico, ranking e progresso exigem identidade persistente.
- **Ator:** visitante.
- **Pré-condições:** não autenticado; aceitou termos e política de privacidade (versão registrada).
- **Fluxo principal:** 1) informa e-mail, nome de exibição (3–24 caracteres, `[A-Za-z0-9_-]` e letras acentuadas), senha; 2) servidor normaliza e-mail (minúsculas, trim); 3) verifica senha (≥ 12 caracteres, não presente em lista de senhas vazadas comuns, sem limite máximo < 128); 4) grava hash Argon2id; 5) cria `users`, `user_profiles`, `user_preferences` em uma transação; 6) envia e-mail de verificação (RF-002); 7) responde 201 sem revelar dados internos.
- **Fluxos alternativos:** FA1 — e-mail já cadastrado: resposta **idêntica** à de sucesso e envio de e-mail informativo ao dono do endereço (evita enumeração). FA2 — nome de exibição em uso: 409 com sugestão.
- **Erros:** 422 validação; 429 limite de taxa; 503 serviço de e-mail indisponível (conta criada, reenvio possível).
- **Regras de negócio:** nome de exibição passa por filtro de termos ofensivos; faixa etária autodeclarada em faixas (`<12`, `12–15`, `16–17`, `18+`) é obrigatória e serve só para aplicar configurações protetivas e consentimento parental (DT-015, doc 09 §10); menor de 12 tem cadastro pendente até confirmação do responsável (RF-034). Idade nunca altera dificuldade.
- **Dados:** e-mail, nome de exibição, hash de senha, faixa etária, versão dos termos aceitos, data de criação.
- **Segurança:** SEC-01, SEC-02, SEC-08 (rate limit), SEC-12 (logs sem senha).
- **Prioridade:** M · **Dependências:** RNF-010 · **Aceite:** CA-001 · **Testes:** T-001 · **Estado:** implementado (PR #1).

### RF-002 — Verificação de e-mail
- **Descrição:** usuário confirma propriedade do e-mail por link com token de uso único.
- **Ator:** usuário registrado. **Pré-condições:** conta com `email_verified_at` nulo.
- **Fluxo principal:** token aleatório de 256 bits; armazenado somente como hash SHA-256; validade 24 h; ao abrir, servidor marca verificado e invalida token.
- **Alternativos:** reenvio (máx. 3/h); token expirado → página orienta reenvio.
- **Erros:** 400 token inválido/expirado (mensagem genérica).
- **Regras:** contas não verificadas jogam contra IA e local, mas **não** entram em partidas ranqueadas online.
- **Segurança:** SEC-03. **Prioridade:** M · **Dependências:** RF-001 · **Aceite:** CA-002 · **Testes:** T-002 · **Estado:** implementado (PR #1).

### RF-003 — Login
- **Descrição:** autenticação por e-mail e senha, gerando sessão.
- **Ator:** usuário. **Pré-condições:** conta ativa.
- **Fluxo principal:** valida credenciais em tempo aproximadamente constante; cria sessão (cookie `HttpOnly`, `Secure`, `SameSite=Lax`, identificador opaco, hash no banco — DT-004); registra `last_login_at`.
- **Alternativos:** conta desativada/suspensa → mensagem específica sem revelar motivos de moderação detalhados.
- **Erros:** 401 genérico ("e-mail ou senha incorretos"); 429 após 5 falhas/15 min por conta+IP com atraso progressivo (sem bloqueio permanente que permita negação de serviço).
- **Segurança:** SEC-01, SEC-04, SEC-08. **Prioridade:** M · **Dependências:** RF-001 · **Aceite:** CA-003 · **Testes:** T-003 · **Estado:** implementado (PR #1).

### RF-004 — Logout e gestão de sessões
- **Descrição:** encerrar a sessão atual ou todas as sessões; listar sessões ativas (dispositivo aproximado, último uso).
- **Fluxo principal:** revoga sessão no servidor e limpa cookie; "encerrar todas" revoga todas exceto a atual (opcionalmente inclusive).
- **Regras:** troca de senha revoga todas as outras sessões. Sessão expira por inatividade (30 dias, proposta) e por tempo absoluto (90 dias).
- **Segurança:** SEC-04. **Prioridade:** M · **Aceite:** CA-004 · **Testes:** T-004 · **Estado:** implementado (PR #1).

### RF-005 — Recuperação de senha
- **Fluxo principal:** solicita por e-mail → resposta sempre idêntica → token de uso único (hash armazenado, validade 30 min) → nova senha com as regras de RF-001 → revoga todas as sessões → e-mail de notificação.
- **Erros:** 400 token inválido; 429.
- **Segurança:** SEC-03, SEC-08. **Prioridade:** M · **Aceite:** CA-005 · **Testes:** T-005 · **Estado:** implementado (PR #1).

### RF-006 — Perfil do usuário
- **Descrição:** ver e editar nome de exibição, avatar predefinido (sem upload na v1 — reduz risco de conteúdo impróprio), bio curta (≤ 160 caracteres, opcional), visibilidade do perfil (público/privado).
- **Regras:** perfil público mostra apenas nome, avatar, ratings, estatísticas agregadas e conquistas; nunca e-mail. Mudança de nome de exibição limitada a 1 a cada 30 dias.
- **Erros:** 422; 409 nome em uso.
- **Segurança:** SEC-05 (autorização por recurso), SEC-09 (XSS — bio renderizada como texto).
- **Prioridade:** M · **Aceite:** CA-006 · **Testes:** T-006 · **Estado:** aprovado.

### RF-007 — Preferências
- **Descrição:** tema (claro/escuro/sistema), nível de animação (completo/reduzido/nenhum; padrão segue `prefers-reduced-motion`), estilo de peças por jogo (infantil/intermediário/clássico), som (on/off), notação de lances exibida, confirmação de jogada (on/off), idioma (pt-BR na v1).
- **Regras:** estilo de peças é **puramente visual** e não altera dificuldade, nível da IA ou matchmaking. Preferências são salvas no servidor para usuários autenticados e em `localStorage` para visitantes.
- **Notação de lances (DT-021):** `move_notation` = `algebraic_pt` (padrão: SAN com as letras das peças em português — R, D, T, B, C), `san` (SAN internacional — K, Q, R, B, N) ou `uci` (coordenadas, ex.: `g1f3`). É **só exibição** da lista de lances do xadrez: o servidor continua falando UCI (xadrez) e PDN (damas) e devolve a SAN pronta (`san_moves`); jogo da velha e damas não mudam. Visitantes (sem conta) ainda não têm `localStorage` de preferências (P-15).
- **Prioridade:** M · **Aceite:** CA-007 · **Testes:** T-007 · **Estado:** aprovado.

## Lobby e partidas

### RF-008 — Lobby
- **Descrição:** tela inicial autenticada com: escolher jogo, modo (local, contra IA, online por convite, fila), partidas em andamento do usuário, atalho para Academy.
- **Regras:** mostra no máximo 1 partida online ativa por jogo por usuário (DT-010); exibe aviso se a conta não estiver verificada (RF-002).
- **Prioridade:** M · **Dependências:** RF-003 · **Aceite:** CA-008 · **Testes:** T-008 · **Estado:** aprovado.

### RF-009 — Partida local (mesmo dispositivo)
- **Descrição:** duas pessoas alternam no mesmo navegador.
- **Fluxo principal:** cada lance é validado pelo **mesmo motor do servidor** (DT-007): usuário autenticado ⇒ partida `mode=local` persistida; visitante ⇒ endpoint sem estado `POST /engines/{game_id}/apply`; resultado **não** afeta ranking; partida pode ser salva no histórico como "local" se autenticado.
- **Regras:** visitantes podem jogar localmente sem conta.
- **Prioridade:** M · **Aceite:** CA-009 · **Testes:** T-009 · **Estado:** aprovado.

### RF-010 — Partida contra IA
- **Descrição:** usuário escolhe jogo, nível (1–5 conforme doc 07) e cor/ordem.
- **Fluxo principal:** servidor cria `matches` com `mode=ai`; cada lance do usuário é validado pelo motor; IA adversária calcula resposta com limite de tempo; estado oficial persistido a cada lance.
- **Erros:** motor indisponível/tempo excedido → IA joga o melhor lance encontrado até o limite; falha total → partida pausada com mensagem e opção de retomar.
- **Regras:** não afeta ranking competitivo; contribui para estatísticas "vs IA" e para a Academy.
- **Prioridade:** M · **Dependências:** RF-016–RF-018 · **Aceite:** CA-010 · **Testes:** T-010 · **Estado:** aprovado.

### RF-011 — Partida online por convite
- **Descrição:** usuário cria sala privada e compartilha código/link; convidado entra.
- **Fluxo principal:** código de 8 caracteres aleatórios, validade 15 min, uso único; quando o segundo jogador entra, servidor sorteia cores (ou usa escolha do criador), muda estado para `in_progress` e notifica via WebSocket.
- **Alternativos:** criador cancela antes do ingresso; código expira.
- **Erros:** 404 código inválido (genérico); 409 sala cheia; 403 tentar entrar na própria sala como segundo jogador.
- **Regras:** convite pode ser ranqueado ou casual (ranqueado exige ambos verificados).
- **Segurança:** SEC-06 (WebSocket), SEC-08. **Prioridade:** M · **Aceite:** CA-011 · **Testes:** T-011 · **Estado:** aprovado.

### RF-012 — Fila de pareamento (matchmaking)
- **Descrição:** usuário entra na fila de um jogo e é pareado com oponente de rating próximo.
- **Fluxo principal:** janela inicial ±100 de rating, ampliada em +50 a cada 10 s até ±400; após 60 s oferece jogar contra IA. Pareamento é atômico (um usuário nunca em duas partidas da fila).
- **Regras:** evitar pareamento repetido com o mesmo oponente mais de 3 vezes seguidas na mesma hora (antiabuso de rating).
- **Detalhamento da implementação (DT-019):** a fila tem duas modalidades que nunca se misturam — casual (ordem de chegada, sem rating) e ranqueada (`ranked: true`; exige conta verificada e jogo com ranking). Na ranqueada o par é o candidato de rating mais próximo dentro da janela de qualquer um dos dois; a janela cresce com a espera e é reavaliada a cada consulta da fila (`GET /matchmaking/queue`). O limite de 3 partidas por hora contra o mesmo oponente vale na fila e no convite ranqueado.
- **Prioridade:** S · **Dependências:** RF-019 · **Aceite:** CA-012 · **Testes:** T-012 · **Estado:** aprovado.

### RF-013 — Submeter jogada
- **Descrição:** jogador envia lance; servidor valida e difunde.
- **Fluxo principal:** mensagem contém `match_id`, `expected_ply` (número do lance esperado), `move` e `client_move_id` (UUID para idempotência); servidor verifica autenticação, participação, turno, `expected_ply`, legalidade pelo motor; persiste `match_moves` e novo estado na mesma transação com bloqueio de linha da partida; difunde `move_applied`; verifica fim de jogo.
- **Alternativos:** mesmo `client_move_id` reenviado → responde com o resultado já gravado sem duplicar.
- **Erros:** `not_your_turn`, `illegal_move`, `stale_state` (com estado atual para ressincronizar), `match_finished`, `not_participant`.
- **Regras:** o cliente **nunca** informa resultado, pontuação ou estado; apenas o lance.
- **Segurança:** SEC-05, SEC-06, SEC-07. **Prioridade:** M · **Aceite:** CA-013 · **Testes:** T-013 · **Estado:** aprovado.

### RF-014 — Reconexão
- **Descrição:** jogador que perde a conexão retorna à partida no estado oficial.
- **Fluxo principal:** ao reconectar, cliente envia `join_match` com último `ply` conhecido; servidor responde com snapshot completo ou lances faltantes; oponente é notificado de desconexão/reconexão.
- **Regras:** tolerância de desconexão de 60 s (proposta, configurável); excedida, o oponente pode reivindicar vitória por abandono; partidas sem relógio contam a tolerância só no turno do desconectado.
- **Prioridade:** M · **Aceite:** CA-014 · **Testes:** T-014 · **Estado:** aprovado.

### RF-015 — Desistência, abandono e empate por acordo
- **Descrição:** jogador pode desistir; propor empate (damas/xadrez); oponente aceita/recusa; abandono após tolerância.
- **Regras:** propostas de empate limitadas a 1 a cada 10 lances por jogador; desistência antes do 2º lance de cada lado em partida ranqueada → partida "anulada" sem efeito no rating (antiabuso).
- **Prioridade:** M · **Aceite:** CA-015 · **Testes:** T-015 · **Estado:** aprovado.

## Jogos

### RF-016 — Jogo da velha
Regras, estado e IA conforme [doc 07 §2](07-motores-e-regras-dos-jogos.md#2-jogo-da-velha). Vitória, empate e invalidação no servidor. **Prioridade:** M · **Aceite:** CA-016 · **Testes:** T-016 · **Estado:** aprovado.

### RF-017 — Damas
Variante **damas brasileiras** (8×8, regras internacionais de captura) conforme [doc 07 §3](07-motores-e-regras-dos-jogos.md#3-damas) — pendente de aprovação (DT-006). **Prioridade:** M · **Aceite:** CA-017 · **Testes:** T-017 · **Estado:** aprovado.

### RF-018 — Xadrez
Regras FIDE do Livro de Regras (jogo sem relógio na v1, salvo RF-015) via biblioteca consolidada, conforme [doc 07 §4](07-motores-e-regras-dos-jogos.md#4-xadrez). **Prioridade:** M · **Aceite:** CA-018 · **Testes:** T-018 · **Estado:** aprovado.

## Competição e histórico

### RF-019 — Ranking por jogo
- **Descrição:** rating Elo separado por jogo (damas, xadrez); rating inicial 1200; fator K = 40 nas primeiras 30 partidas ranqueadas, depois 20 (proposta — DT-008).
- **Fluxo principal:** ao término de partida ranqueada, servidor calcula e grava novos ratings dos dois jogadores na **mesma transação** que finaliza a partida, com registro em `rating_history`.
- **Regras:** apenas partidas online ranqueadas entre contas verificadas; partidas anuladas não contam; ranking público lista apenas perfis públicos com ≥ 10 partidas.
- **Detalhamento da implementação (DT-019):** modo `online_ranked` por convite ou fila ranqueada; a liquidação é idempotente (um ajuste por usuário e partida) e vale para vitória, derrota, desistência, abandono, acordo de empate e fim pelo motor; contra a IA, local, casual e partida anulada o rating não muda. O ranking público (`GET /ranking/{game_id}`) é paginado e traz só apelido, avatar, posição, rating e nº de partidas, respeitando `is_public`, `show_in_ranking` e o padrão protetivo de menores (RF-034). O jogo precisa ter `games.ranked_enabled`: **hoje só o xadrez** (velha: DT-008; damas: P-21).
- **Prioridade:** M · **Aceite:** CA-019 · **Testes:** T-019 · **Estado:** aprovado.

### RF-020 — Histórico e revisão de partidas
- **Descrição:** lista paginada de partidas do usuário (filtro por jogo/modo/resultado) e visualizador lance a lance.
- **Regras:** participante vê suas partidas; terceiros veem partidas de perfis públicos apenas se ambos os jogadores forem públicos (proposta).
- **Prioridade:** M · **Aceite:** CA-020 · **Testes:** T-020 · **Estado:** aprovado.

### RF-021 — Estatísticas
- **Descrição:** por jogo: partidas, vitórias, derrotas, empates, % por modo, evolução de rating, sequência atual.
- **Regras:** calculadas a partir de `matches` (fonte da verdade); caches/agregados podem ser recalculados.
- **Detalhamento da implementação (DT-019):** `GET /me/stats` devolve, por jogo visível ao usuário, vitórias/derrotas/empates totais e por modo (`ai`, `online_casual`, `online_ranked`; partida local não entra porque o mesmo usuário ocupa os dois lados; anuladas, abortadas e em andamento ficam de fora), sequência atual (últimas 100 partidas) e, nos jogos ranqueados, rating, partidas ranqueadas, se aparece no ranking e as últimas 30 variações. Só o próprio usuário consulta as suas estatísticas.
- **Prioridade:** S · **Aceite:** CA-021 · **Testes:** T-021 · **Estado:** aprovado.

## BoardHub Academy

### RF-022 — Avaliação inicial
Questionário de autodeclaração + 6–10 exercícios curtos por jogo, conforme [doc 08 §4](08-ia-e-boardhub-academy.md). Pode ser pulada; resultado é estimativa revisável. **Prioridade:** M · **Aceite:** CA-022 · **Testes:** T-022 · **Estado:** aprovado.

### RF-023 — Lições e exercícios
Lições curtas por conceito, exercícios com posição, objetivo e verificação **determinística** da resposta pelo motor. Dicas graduais (3 níveis). **Prioridade:** M · **Aceite:** CA-023 · **Testes:** T-023 · **Estado:** aprovado.

### RF-024 — Análise e explicação pós-partida (Mentor)
Após partidas contra IA ou casuais, o Mentor identifica até 3 momentos críticos (perda de avaliação acima de limiar) e gera explicação a partir de **modelos de texto determinísticos**; se Ollama estiver habilitado, reformula o texto sem alterar fatos (doc 08 §8). Em partidas ranqueadas em andamento, **nenhuma** ajuda é exibida. **Prioridade:** S · **Aceite:** CA-024 · **Testes:** T-024 · **Estado:** aprovado.

### RF-025 — Progresso de habilidades
Mostra domínio por conceito (não iniciado / em prática / dominado / em revisão), baseado em critérios do doc 08 §6. **Prioridade:** M · **Aceite:** CA-025 · **Testes:** T-025 · **Estado:** aprovado.

## Engajamento (fases posteriores)

### RF-026 — Conquistas
Distintivos por marcos verificáveis no servidor (ex.: "primeira vitória em damas"). Sem valor monetário. Concessão idempotente. **Prioridade:** C · **Aceite:** CA-026 · **Testes:** T-026 · **Estado:** aprovado.

### RF-027 — Desafio diário
Um exercício por jogo por dia (fuso America/Sao_Paulo), mesmo para todos, uma tentativa válida registrada. **Prioridade:** C · **Aceite:** CA-027 · **Testes:** T-027 · **Estado:** aprovado.

### RF-028 — Notificações
In-app (v1): convite recebido, vez de jogar, partida encerrada, oponente desconectou. E-mail apenas transacional (verificação, senha, alerta de segurança). Sem marketing sem consentimento explícito. **Prioridade:** S · **Aceite:** CA-028 · **Testes:** T-028 · **Estado:** aprovado.

## Privacidade e administração

### RF-029 — Exportação de dados pessoais
Usuário solicita exportação; servidor gera JSON com conta, perfil, preferências, partidas, progresso; disponível por link autenticado por 7 dias. Limite: 1 solicitação por 24 h. **Prioridade:** M · **Aceite:** CA-029 · **Testes:** T-029 · **Estado:** aprovado. *Implementação (Fase 7, DT-020): geração na hora; o responsável vinculado também pode exportar os dados do menor (P-22).*

### RF-030 — Exclusão de conta
Usuário confirma com senha; conta marcada para exclusão; após 14 dias (período de arrependimento — proposta) dados pessoais são apagados e partidas são **pseudonimizadas** (jogador vira "Conta removida") para preservar o histórico do oponente. Sessões revogadas imediatamente. **Prioridade:** M · **Aceite:** CA-030 · **Testes:** T-030 · **Estado:** aprovado. *Implementação (Fase 7, DT-020): na carência o login é restrito ao cancelamento (P-22); o responsável vinculado também pode excluir a conta do menor.*

### RF-031 — Denúncia e moderação
Usuário denuncia nome/bio ofensivos ou suspeita de trapaça; administrador (papel `admin`/`moderator`) revisa, oculta conteúdo, suspende conta. Toda ação administrativa é auditada (`audit_log`). **Prioridade:** S · **Aceite:** CA-031 · **Testes:** T-031 · **Estado:** aprovado.

### RF-032 — Amizades e convites diretos
Solicitar, aceitar, recusar, remover amizade; bloquear usuário (bloqueado não pode convidar). **Prioridade:** C · **Aceite:** CA-032 · **Testes:** T-032 · **Estado:** aprovado.

## Proteção de crianças e adolescentes

### RF-033 — Classificação indicativa por jogo
- **Descrição:** cada jogo tem uma classificação indicativa exibida de forma visível no lobby, na página do jogo e antes de iniciar partida.
- **Justificativa:** ECA Digital, art. 8º; decisão DT-015.
- **Ator:** qualquer visitante. **Pré-condições:** jogo habilitado.
- **Fluxo principal:** `games.age_rating` é lido do catálogo; frontend mostra o selo com texto (não só cor) e descrição acessível.
- **Erros:** jogo sem classificação definida não pode ser habilitado (restrição no banco).
- **Regras:** classificação proposta "Livre" para os três jogos, a validar (P-04). Usuário cuja faixa etária é inferior à classificação de um jogo não o vê no lobby.
- **Prioridade:** M · **Aceite:** CA-033 · **Testes:** T-033 · **Estado:** aprovado.

### RF-034 — Supervisão parental e configurações protetivas
- **Descrição:** contas de menores nascem com configuração protetiva; um responsável pode vincular sua conta para supervisionar.
- **Justificativa:** ECA Digital, arts. 7º, 17 e 18; LGPD, art. 14.
- **Ator:** responsável (usuário 18+), usuário menor.
- **Fluxo principal:** 1) menor informa e-mail do responsável no cadastro; 2) responsável recebe convite, cria ou usa sua conta 18+ e confirma o vínculo; 3) painel do responsável permite limite diário de tempo, liberar partidas online com desconhecidos, tornar perfil público/visível no ranking, ver histórico de partidas; 4) mudanças registradas em `audit_log`.
- **Alternativos:** menor de 12 sem confirmação em 7 dias ⇒ cadastro removido sem reter dados; responsável desvincula ⇒ conta volta ao padrão protetivo.
- **Erros:** responsável com faixa diferente de `18+` ⇒ 422; limite de tempo atingido ⇒ partidas novas bloqueadas com mensagem, partida em andamento pode terminar.
- **Regras:** padrão protetivo = perfil privado, fora do ranking público, sem fila aberta, convites só de amigos aprovados.
- **Detalhamento da implementação (DT-021):** o tempo é medido no servidor, só para contas de menores: cada atividade (lance, criação de partida, tentativa/dica/avaliação da Academy) soma ao dia o intervalo desde a anterior quando ele é de até 5 minutos; pausas maiores e a primeira atividade do dia valem zero. O dia civil é o de America/Sao_Paulo (como RF-027). Com o limite esgotado, criar partida (local, contra a IA ou convite), entrar por código e entrar na fila respondem **429** `daily_limit_reached` com `Retry-After` até a meia-noite de Brasília e mensagem em pt-BR; a fila nunca pareia quem esgotou o tempo. A partida em andamento pode terminar (chave `DAILY_LIMIT_BLOCKS_MOVES` para bloquear também os lances: P-23). A Academy conta no tempo, mas não é bloqueada. O painel do responsável (aba "Responsável") lista os vinculados, mostra o tempo de hoje, ajusta limite e configurações e pede exportação/exclusão do menor. "Horário permitido" não consta do requisito e não foi implementado.
- **Segurança:** SEC-05, SEC-11. **Prioridade:** M · **Dependências:** RF-001, P-04 · **Aceite:** CA-034 · **Testes:** T-034 · **Estado:** aprovado.
