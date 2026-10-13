# 18 — Glossário

> Versão 0.1.0 · 2026-10-13

| Termo | Definição |
|-------|-----------|
| **Alfa-beta (poda)** | Otimização do minimax que descarta ramos que não podem alterar a decisão. |
| **BoardHub Academy** | Sistema de aprendizagem adaptativa: lições, exercícios, domínio por conceito e revisão espaçada. |
| **Conceito** | Unidade de conhecimento de um jogo (ex.: `ch.forks`), com grau de domínio por usuário. |
| **Conquista** | Distintivo concedido por marco verificável no servidor; sem valor monetário. |
| **Dama voadora** | Na variante brasileira, dama que se move/captura por qualquer distância na diagonal. |
| **Desafio diário** | Exercício igual para todos os usuários num dia. |
| **Domínio** | Estado de um conceito comprovado por acertos variados em dias distintos (doc 08 §6). |
| **Elo** | Sistema de rating em que o ganho/perda depende da diferença entre ratings e do resultado. |
| **Estado oficial** | Estado da partida gravado no servidor (`matches.state` + `ply`); única fonte da verdade. |
| **FEN** | Notação textual de uma posição de xadrez. |
| **IA adversária** | Componente que escolhe lances contra o jogador por busca ou motor especializado. |
| **IA generativa** | Modelo de linguagem (via Ollama, opcional) que apenas reformula explicações. |
| **Idempotência** | Propriedade de uma operação repetida produzir o mesmo efeito de uma única execução (`client_move_id`). |
| **Lei da maioria** | Regra das damas brasileiras: obrigatório capturar o maior número possível de peças. |
| **Matchmaking (pareamento)** | Processo de juntar dois jogadores da fila com ratings próximos. |
| **Mentor** | Componente educacional que detecta erros com o motor e explica por templates. |
| **Minimax** | Algoritmo de busca que escolhe o lance que maximiza o pior resultado garantido. |
| **Motor de jogo** | Biblioteca determinística que valida lances, aplica-os e detecta fim de jogo. |
| **Partida** | Instância de um jogo entre dois participantes (humanos ou IA), com modo e estado. |
| **Perft** | Contagem de posições alcançáveis a certa profundidade; usada para validar geradores de lances. |
| **PDN** | Notação padrão para damas (ex.: `11-15`, `15x24`). |
| **Ply (meio-lance)** | Um lance de um único jogador; `matches.ply` conta meio-lances aplicados. |
| **Ranking** | Lista ordenada por rating, separada por jogo. |
| **Rating** | Número que estima a força de um jogador num jogo. |
| **Revisão espaçada** | Revisitar conceitos dominados em intervalos crescentes. |
| **Turno** | Momento em que um jogador específico pode jogar. |
| **UCI** | Protocolo de comunicação com motores de xadrez e notação de lances (`e2e4`). |
