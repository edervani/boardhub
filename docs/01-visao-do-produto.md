# 01 — Visão do Produto

> Versão 0.2.0 · 2026-10-13 · Estado: **aprovado** (2026-10-13)

## 1. Visão, missão e objetivos

- **Visão:** ser um lugar onde qualquer pessoa aprende e joga jogos de tabuleiro clássicos, do primeiro movimento ao nível competitivo, sem dinheiro envolvido.
- **Missão:** oferecer partidas justas (contra IA e online) e um percurso de aprendizagem que se adapta ao desempenho real de cada jogador.
- **Objetivos da v1:**
  1. Três jogos completos e com regras validadas no servidor: jogo da velha, damas, xadrez.
  2. Partidas contra IA em ao menos três níveis por jogo.
  3. Partidas online 1×1 em tempo real com reconexão.
  4. Ranking separado por jogo e histórico de partidas.
  5. BoardHub Academy com avaliação inicial, exercícios e progressão baseada em evidências.

## 2. Público-alvo

- Iniciantes absolutos (nunca jogaram damas ou xadrez).
- Jogadores casuais que querem partidas rápidas.
- Jogadores intermediários/experientes que querem ranking e oponentes de nível compatível.
- Crianças, adolescentes, educadores e famílias. Menores usam contas com configuração protetiva e supervisão parental, com classificação indicativa por jogo (DT-015, doc 09 §10).

**A idade não determina habilidade.** Se coletada, a faixa etária pode influenciar apenas linguagem e ilustrações, nunca dificuldade ou nível.

## 3. Problemas que o produto resolve

| Problema | Resposta do BoardHub |
|----------|---------------------|
| Plataformas de xadrez são intimidadoras para iniciantes | Academy com progressão gradual e jogo da velha/damas como porta de entrada |
| Explicações de lances são técnicas demais | Mentor com explicações em linguagem simples (determinísticas, opcionalmente reformuladas por IA local) |
| Muitos jogos misturam diversão com monetização agressiva | Proibição explícita de apostas, pay-to-win e dinheiro real (§6) |
| Dependência de serviços pagos de IA | IA adversária e validação 100% locais; Ollama opcional |

## 4. Proposta de valor

Aprender e jogar três clássicos num só lugar, com adversário que se ajusta ao seu nível, explicações compreensíveis, acessibilidade (teclado, leitor de tela, movimento reduzido) e privacidade por padrão.

## 5. Escopo

### 5.1 Primeira versão (v1)
Contas; perfil; preferências (tema, animações, estilo de peças); lobby; partidas locais (2 pessoas no mesmo dispositivo) e contra IA; partidas online 1×1 por convite e por fila; três jogos; ranking por jogo (Elo para damas e xadrez; jogo da velha sem ranking competitivo — DT-008); histórico; Academy inicial; exportação e exclusão de conta.

### 5.2 Funcionalidades futuras (fase 6+)
Desafios diários, missões, conquistas, amizades e convites, chat moderado (pendente — R-012), torneios, controle de tempo avançado, temas visuais adicionais.

### 5.3 Fora de escopo (v1)
Aplicativos nativos; outras variantes de jogos; transmissão ao vivo; chat livre entre desconhecidos; integração com redes sociais; qualquer item da §6.

## 6. Modelo de negócio — permitido e proibido

**Proibido (regra inegociável, não pode ser alterada por requisito inferior):**
- Apostas em dinheiro real; depósitos, saques, carteiras financeiras.
- Prêmios em dinheiro ou conversão de moeda/pontos virtuais em dinheiro.
- Jogos de azar ou mecânicas equivalentes (caixas de recompensa pagas, sorteios pagos).
- Compra de vantagem competitiva: venda de lances, dicas durante partidas ranqueadas, níveis de força ou bônus de rating.

**Permitido:** XP, distintivos, títulos, conquistas e itens **cosméticos** sem valor monetário e não conversíveis. Eventual financiamento (doações, patrocínio institucional) exige decisão própria (P-05) e não pode violar a lista acima.

## 7. Personas e jornadas

| Persona (fictícia) | Perfil | Jornada principal |
|---------|--------|------------------|
| **Ana, 34, iniciante** | Nunca jogou xadrez | Cadastro → avaliação inicial → lições de movimento das peças → partida contra IA nível 1 → explicação pós-partida |
| **Bruno, 19, competitivo** | Joga damas há anos | Login → fila ranqueada de damas → partida online → rating atualizado → histórico |
| **Carla, 41, professora** | Usa jogos com a turma | Cria conta → explora Academy → joga partida local em tela compartilhada |
| **Davi, 27, deficiência visual** | Usa leitor de tela | Navega lobby por teclado → joga contra IA com anúncio de lances em notação textual |

## 8. Princípios de experiência

1. Clareza antes de estética: estado do jogo e turno sempre inequívocos, sem depender só de cor.
2. Respeito ao ritmo: animações opcionais; `prefers-reduced-motion` respeitado.
3. Sem padrões enganosos (dark patterns), sem pressão de compra.
4. Erros explicam o que aconteceu e o que fazer.
5. Personalização visual nunca altera a dificuldade.

## 9. Métricas de sucesso (propostas, a validar após lançamento)

| Métrica | Definição | Meta inicial proposta |
|---------|-----------|----------------------|
| Conclusão do onboarding | % de contas novas que terminam a avaliação inicial | ≥ 60% |
| Retenção D7 | % de usuários que voltam em 7 dias | Linha de base a medir |
| Partidas concluídas | % de partidas online que terminam sem abandono por falha técnica | ≥ 98% |
| Progresso na Academy | % de usuários que atingem domínio em ≥ 1 conceito em 30 dias | Linha de base a medir |
| Incidentes de segurança | Vazamentos de dados pessoais | 0 |

Métricas coletadas de forma agregada e minimizada (doc 09 §8).

## 10. Premissas, restrições e dependências

- **Premissas:** hospedagem própria (VPS/nuvem) com Docker; equipe pequena; público inicial em português.
- **Restrições:** sem APIs pagas obrigatórias; LGPD; sem monetização proibida; funcionamento integral sem Ollama.
- **Dependências:** biblioteca de regras de xadrez e motor (ex.: Stockfish, licença GPL — ver DT-005); PostgreSQL; navegador moderno.
