# 08 — IA e BoardHub Academy

> Versão 0.2.0 · 2026-10-13 · Estado: **aprovado** (2026-10-13)

## 1. Separação formal de responsabilidades

| Componente | Módulo | Faz | Proibido |
|-----------|--------|-----|----------|
| Motor determinístico | `game_engines/` | Legalidade, estado, fim de jogo | — |
| IA adversária | `ai/opponents/` | Escolher lances por busca/motor | Alterar regras; acessar dados pessoais |
| Mentor educacional | `ai/mentor/` | Detectar erros com o motor, classificar, montar explicação por **templates** | Inventar fatos não calculados |
| IA generativa (opcional) | `ai/llm/` | **Reformular** texto já produzido pelo Mentor | Decidir legalidade, resultado, rating, correção de exercício; receber dados pessoais |

Regra de ouro: toda afirmação factual exibida ao usuário (lance melhor, peça perdida, ameaça) vem do motor. O LLM só muda a **forma**.

## 2. IA adversária
Níveis e algoritmos por jogo no [doc 07](07-motores-e-regras-dos-jogos.md). Requisitos: limite de tempo duro (RNF-002); execução fora do loop de eventos; semente registrada para reprodutibilidade em testes; nunca usa informação oculta (não há em jogos de informação perfeita). Nível escolhido pelo usuário; sugerido pela Academy, nunca imposto pela idade.

## 3. Perfil de conhecimento
Por usuário e por jogo, um conjunto de **conceitos** (`concept_key`) com `mastery ∈ [0,1]`. Exemplos:
- Velha: `tt.win_in_one`, `tt.block`, `tt.fork`, `tt.center_corners`.
- Damas: `ck.movement`, `ck.mandatory_capture`, `ck.majority_rule`, `ck.multi_capture`, `ck.promotion`, `ck.flying_king`, `ck.exchanges`.
- Xadrez: `ch.piece_moves`, `ch.check`, `ch.mate_in_one`, `ch.castling`, `ch.en_passant`, `ch.hanging_pieces`, `ch.forks`, `ch.pins`, `ch.basic_mates`, `ch.opening_principles`.
O grafo de pré-requisitos é dado de conteúdo (`lessons.content`) revisado por pessoa com domínio do jogo (P-08).

## 4. Avaliação inicial (RF-022)
1. Autodeclaração: "nunca joguei / conheço as regras / jogo com frequência / jogo competitivamente".
2. 6–10 exercícios adaptativos (começa pelo nível sugerido pela autodeclaração; acerto ⇒ sobe, erro ⇒ desce).
3. Resultado: `mastery` inicial por conceito testado (máx. 0,5 — domínio só se comprova na prática) e nível de IA sugerido.
4. Pode ser pulada (todos os conceitos `not_started`) e refeita a cada 30 dias.
5. **Idade não é entrada do algoritmo.**

## 5. Exercícios e feedback
- Tipos: `best_move` (lista de respostas aceitas verificadas pelo motor), `mate_in_n`, `win_material`, `find_legal_moves`, `rule_quiz` (múltipla escolha sobre regras).
- Correção 100% determinística (motor). Para `best_move` em xadrez, aceita-se também qualquer lance cuja avaliação esteja dentro de tolerância do melhor (calculado ao **cadastrar** o exercício, não em tempo real).
- Dicas em 3 níveis: (1) região do tabuleiro; (2) peça a mover; (3) explicação do conceito. Uso de dicas reduz o ganho de domínio.
- Feedback de erro: por que o lance falha (refutação calculada pelo motor) + conceito relacionado.

## 6. Domínio e progressão
- Atualização após cada tentativa: `mastery ← mastery + α·(r − mastery)`, com `r=1` correto sem dica, `0,6` com dica nível 1, `0,3` com dica 2–3, `0` errado; α = 0,25 (proposta a calibrar).
- **Dominado** quando: `mastery ≥ 0,8` **e** ≥ 5 tentativas corretas em **≥ 3 exercícios distintos** **e** em ≥ 2 dias diferentes. Uma resposta isolada nunca concede domínio.
- **Revisão espaçada (adotada, simplificada):** conceito dominado volta para revisão após 3, 7, 21, 60 dias; erro na revisão ⇒ status `em revisão` e intervalo reinicia.
- Próximo exercício: conceito com pré-requisitos dominados e menor `mastery`, dificuldade alvo com taxa de acerto esperada ~70–85%.
- O usuário pode escolher livremente qualquer lição; a recomendação é sugestão.

## 7. Mentor e análise pós-partida (RF-024)
1. Disponível apenas para partidas **finalizadas** (nunca durante ranqueadas — evita trapaça).
2. Motor avalia posição antes/depois de cada lance do usuário.
3. Classificação (xadrez, perda em centipeões, propostos): imprecisão 50–99, erro 100–299, erro grave ≥ 300 ou mate perdido. Damas: perda equivalente a ≥ 1 pedra. Velha: lance que transforma posição ganha/empatada em perdida.
4. Até 3 momentos críticos; para cada: lance jogado, lance melhor, consequência concreta calculada, conceito ligado.
5. Template determinístico, ex.: "No lance {n}, você jogou {jogado}. Isso deixou {peça} em {casa} sem defesa; o adversário pode capturá-la com {refutação}. Uma opção melhor era {melhor}, que {motivo}." `motivo` vem de detectores (captura, ameaça de mate, garfo).
6. Linguagem ajustada por preferência ("simples"/"técnica"), não por idade.

## 8. Integração opcional com Ollama
- Desligada por padrão (`OLLAMA_ENABLED=false`). URL apenas de rede interna.
- Entrada: **somente** fatos estruturados do Mentor (lances, peças, conceito) + instrução de estilo. Nenhum nome, e-mail ou dado do usuário.
- Prompt de sistema fixo: reescrever sem adicionar fatos, ≤ 80 palavras, pt-BR.
- **Verificação de saída:** a resposta deve conter todos os lances/casas citados nos fatos e nenhum outro lance/casa em notação válida; senão é descartada e usa-se o template. Saída escapada como texto.
- Timeout 4 s; limite de concorrência (ex.: 2 requisições simultâneas); falha ⇒ template.
- Modelo e versão configuráveis (`OLLAMA_MODEL`), escolha pendente (P-09) — exige teste de qualidade em pt-BR.
- Resultado cacheado por (partida, momento) para não repetir custo.

## 9. Modo sem IA generativa
Todo o produto funciona com `NullProvider`: jogar, validar, exercícios, domínio, análise com templates. Testado por RNF-025.

## 10. Qualidade pedagógica e métricas
- Revisão humana de 100% das lições e de amostra de 50 explicações por jogo antes do lançamento (rubrica: correção factual, clareza, tom).
- Métricas (agregadas, anônimas): taxa de acerto por exercício (detecta exercícios ruins: < 20% ou > 98%), tempo até domínio por conceito, retenção em revisões, melhora de desempenho contra IA após lições.
- Testes: unitários do algoritmo de domínio (casos: uma resposta certa não domina; acertos no mesmo exercício não contam como distintos), verificação determinística de todas as respostas cadastradas, teste do filtro de saída do LLM com saídas adversárias simuladas (lance inventado, texto com HTML).

## 11. Personalização visual × dificuldade
Estilos de peça (infantil/intermediário/clássico) são preferências independentes. Nenhum código de IA ou Academy lê `piece_styles`. Verificado por teste (T-007).
