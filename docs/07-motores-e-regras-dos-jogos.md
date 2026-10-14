# 07 — Motores e Regras dos Jogos

> Versão 0.2.0 · 2026-10-13 · Estado: **aprovado** (2026-10-13) · Interface comum: [doc 04 §7](04-arquitetura-tecnica.md#7-interface-comum-dos-motores)

## 1. Princípios comuns
- Motores são **determinísticos e puros**: mesma entrada ⇒ mesma saída. Aleatoriedade (ex.: variação da IA) é injetada por semente.
- O servidor é a **única autoridade**: legalidade, fim de jogo e resultado oficial vêm do motor no backend.
- A IA generativa **nunca** produz resultado, legalidade ou rating.
- Partidas locais e online usam as **mesmas regras e a mesma `rules_version`** (DT-007).
- Estados inválidos (desserialização falha, `ply` inconsistente, hash divergente) ⇒ partida marcada `aborted` com registro em log de erro e auditoria; nunca "consertada" por suposição.
- Abandono e desistência são tratados pelo `match_service`, não pelo motor (doc 06 §3.6).
- Controle de tempo: **não implementado na v1** (partidas sem relógio, com tolerância de desconexão). Relógio é RF futuro.

## 2. Jogo da velha

- **Regras:** tabuleiro 3×3; X começa; jogadores alternam marcando uma casa vazia; vence quem completar linha, coluna ou diagonal; tabuleiro cheio sem vencedor ⇒ empate.
- **Variante:** clássica; sem variantes na v1.
- **Estado:** `{"schema_version":1,"board":"XO_X_O___","to_move":"X"}` — string de 9 caracteres, índice 0 = canto superior esquerdo, linha a linha.
- **Lance:** inteiro 0–8 (texto `"4"`).
- **Legalidade:** casa vazia, partida não encerrada, vez correta. Contagem de X = O ou O+1 é invariante.
- **Vitória/empate:** verificação das 8 linhas após cada lance.
- **Ranking:** não ranqueado (jogo resolvido: jogo perfeito sempre empata — DT-008).
- **IA:** minimax completo com memoização (espaço de estados pequeno).
  | Nível | Comportamento |
  |------|---------------|
  | 1 | Lance aleatório legal (semente registrada) |
  | 2 | Ganha se puder em 1 lance; senão aleatório |
  | 3 | Ganha/bloqueia em 1 lance; senão aleatório |
  | 4 | Minimax com 25% de chance de lance subótimo |
  | 5 | Minimax perfeito (nunca perde) |
- **Testes:** todas as posições alcançáveis (5.478) verificadas contra invariantes; nível 5 nunca perde em 1.000 partidas contra jogador aleatório e contra si mesmo empata sempre.

## 3. Damas

- **Variante proposta (DT-006, pendente de aprovação): Damas brasileiras.** Escolhida por ser a mais praticada no Brasil. As regras abaixo devem ser **conferidas contra o regulamento oficial vigente da Confederação Brasileira de Damas antes da implementação** (P-07) — este documento não foi validado contra a fonte oficial.
  1. Tabuleiro 8×8, casas escuras jogáveis, casa escura no canto inferior esquerdo de cada jogador; 12 peças por lado; **brancas começam**.
  2. Pedra move uma casa na diagonal **para frente**.
  3. Captura por salto sobre peça adversária adjacente para casa vazia; pedras capturam **para frente e para trás**.
  4. **Captura obrigatória.**
  5. **Lei da maioria:** é obrigatório escolher a sequência que captura o **maior número de peças** (dama e pedra valem igual na contagem); empate de quantidade ⇒ escolha livre.
  6. Capturas em cadeia continuam no mesmo lance; peças capturadas são removidas só ao fim da sequência e não podem ser saltadas duas vezes.
  7. **Promoção:** pedra que **termina** o lance na última fileira vira dama. Se passa pela última fileira no meio de uma captura que continua, **não** é promovida.
  8. **Dama voadora:** move e captura ao longo da diagonal por qualquer distância, podendo parar em qualquer casa vazia após a peça capturada (respeitada a lei da maioria).
  9. **Fim:** vence quem capturar ou bloquear todas as peças adversárias (adversário sem lances legais).
  10. **Empate (propostas a confirmar):** por acordo; repetição tripla da mesma posição com o mesmo jogador a mover; 20 lances consecutivos de cada lado apenas com damas, sem captura nem movimento de pedra.
- **Estado:** `{"schema_version":1,"squares":[32 posições: "w","b","W","B","."],"to_move":"w","halfmove_kings_only":0,"position_history":[hashes]}` com numeração 1–32 padrão.
- **Notação do lance:** estilo PDN: `11-15` (movimento), `15x24x31` (captura com casas de passagem).
- **Geração de lances:** busca em profundidade de todas as sequências de captura; filtra pela maioria; se não houver captura, movimentos simples.
- **IA:** minimax com poda alfa-beta, aprofundamento iterativo, tabela de transposição (Zobrist), extensão de captura (quiescência). Avaliação: material (pedra 100, dama 300 — a calibrar), avanço, controle do centro, mobilidade.
  | Nível | Profundidade/tempo | Ruído |
  |------|--------------------|------|
  | 1 | 1 meio-lance | alto (escolha ponderada aleatória) |
  | 2 | 2 | médio |
  | 3 | 4 | baixo |
  | 4 | até 8 ou 1 s | nenhum |
  | 5 | até 3 s | nenhum |
- **Testes:** posições de referência para cada regra (maioria, dama voadora, não-promoção no meio da captura, captura para trás), contagem de nós (perft) comparada com valores calculados por implementação independente (**valores de referência ainda não obtidos — P-07**), partidas IA×IA sem lances ilegais.

## 4. Xadrez

- **Regras:** Leis do Xadrez da FIDE (regras básicas de jogo), sem relógio na v1: roque, en passant, promoção (o jogador escolhe a peça), xeque-mate, afogamento, empate por material insuficiente, repetição tripla (**reivindicada** ou automática na quíntupla), regra dos 50 lances (**reivindicada**) / 75 lances (automática), acordo.
- **Implementação:** biblioteca **python-chess** (licença GPL-3.0 — ver DT-005 sobre implicações) para estado, lances legais e fim de jogo. Nenhuma regra de xadrez é reimplementada à mão.
- **Estado:** FEN + lista de lances UCI (necessária para repetição): `{"schema_version":1,"fen":"…","moves":["e2e4",…]}`.
- **Lance:** UCI (`e2e4`, `e7e8q`). Frontend pode exibir SAN.
- **IA:** motor UCI (Stockfish proposto) em subprocesso com `Skill Level`/limite de profundidade e tempo; fallback: alfa-beta simples com python-chess.
  | Nível | Configuração proposta (calibrar na Fase 5) |
  |------|-------------------|
  | 1 | Lance aleatório com preferência por capturas |
  | 2 | Busca própria profundidade 2 |
  | 3 | Motor UCI nível baixo, 100 ms |
  | 4 | Motor UCI nível médio, 500 ms |
  | 5 | Motor UCI nível alto, 2 s |
- **Análise para o Mentor:** motor UCI avalia cada posição da partida finalizada (profundidade limitada); diferença de avaliação classifica lances (imprecisão/erro/erro grave — limiares no doc 08).
- **Testes:** perft da posição inicial e de posições conhecidas (validam integração), casos de roque/en passant/promoção/afogamento, fim por material insuficiente, partidas IA×IA.

## 5. Serialização e versão das regras
- `serialize` produz JSON canônico (chaves ordenadas) para hash `state_after_hash`.
- `rules_version` (ex.: `checkers-br-1`) é gravada em cada partida. Mudar uma regra exige nova versão; partidas antigas continuam reprodutíveis com a versão antiga.

## 6. Validação no servidor — algoritmo comum
```
estado = engine.deserialize(match.state)
se match.status != in_progress: erro match_finished
se seat do usuário != estado.to_move: erro not_your_turn
lance = engine.parse_move(raw)            # erro illegal_move se não parse
se lance ∉ engine.legal_moves(estado): erro illegal_move
novo = engine.apply(estado, lance)
resultado = engine.outcome(novo)
```
