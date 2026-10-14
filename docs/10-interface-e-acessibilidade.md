# 10 — Interface e Acessibilidade

> Versão 0.2.0 · 2026-10-13 · Estado: **aprovado** (2026-10-13) · Meta: WCAG 2.2 nível AA (RNF-014)

## 1. Princípios visuais
Clareza do tabuleiro acima de tudo; hierarquia simples; uma ação primária por tela; feedback imediato; ornamentos opcionais. Sem padrões enganosos: nada de contagens regressivas falsas, botões de "comprar" disfarçados ou confirmações culpabilizantes.

## 2. Design system
Tokens CSS (`frontend/src/styles/tokens.css`) consumidos por componentes em `components/`. Estilo: CSS Modules (DT-003).

| Token | Claro | Escuro | Uso |
|-------|-------|--------|-----|
| `--bg` | #FAFAF7 | #15171A | Fundo |
| `--surface` | #FFFFFF | #1F2226 | Cartões |
| `--text` | #1B1D20 | #ECEDEE | Texto |
| `--text-muted` | #5A5F66 | #A6ABB2 | Secundário |
| `--accent` | #2F5BD3 | #8FA9FF | Ação primária |
| `--danger` | #B42318 | #FF8A80 | Erros |
| `--success` | #1F7A3D | #6FD08F | Vitória/sucesso |
| `--focus` | #F2A900 | #FFD24D | Anel de foco 3 px |

Contraste: texto normal ≥ 4,5:1, componentes de UI e peças ≥ 3:1 — valores acima devem ser **medidos** antes do aceite (ferramenta de contraste no CI de componentes). Tipografia: fonte do sistema (sem dependência externa), escala 14/16/20/24/32 px, altura de linha 1,5; números tabulares em placares e relógios.

Componentes: Button, IconButton (sempre com rótulo acessível), TextField, Select, Toggle, Dialog (foco preso e retorno de foco), Toast (região `aria-live`), Tabs, Card, Board, Piece, MoveList, PlayerBadge, TurnIndicator, ConnectionBanner, Skeleton, EmptyState.

Estados de interação obrigatórios: padrão, hover, foco visível, ativo, desabilitado (com motivo), carregando, erro.

## 3. Temas
Claro, escuro e "sistema" (`prefers-color-scheme`). Troca sem recarregar, persistida (RF-007). Tabuleiros têm paletas próprias por tema com contraste entre casas e peças ≥ 3:1.

## 4. Responsividade
Mobile-first. Tabuleiro quadrado ocupa `min(100vw − 32px, 100vh − cabeçalho − controles)`; em ≥ 1024 px, lista de lances e painel lateral à direita. Alvos de toque ≥ 44×44 px (casas do tabuleiro em 320 px de largura: 8×8 = ~36 px — **conflito**: mitigado por modo "toque em duas etapas" com casa ampliada e opção de entrada por notação; registrado R-009).

## 5. Tabuleiros
- Grade semântica: `role="grid"`, cada casa `role="gridcell"` com rótulo ("e4, cavalo branco", "casa 15, vazia").
- Interação: clicar/tocar origem e destino **ou** arrastar; teclado: setas movem foco, Enter/Espaço seleciona origem e destino, Esc cancela.
- Destaques: último lance, lances legais da peça selecionada, xeque — sempre com **forma** (contorno, ponto, ícone) além da cor.
- Coordenadas visíveis (opção); orientação do tabuleiro conforme o lado do jogador.
- Entrada alternativa por texto (notação) para quem usa leitor de tela.

## 6. Animações
Níveis: completo / reduzido / nenhum. Padrão segue `prefers-reduced-motion`. Duração máx. 200 ms para movimento de peça; nenhuma animação em loop infinito; nada pisca mais de 3 vezes por segundo. Efeitos de comemoração são desligáveis.

## 7. Teclado e leitores de tela
Ordem de foco lógica; link "pular para o tabuleiro"; atalhos documentados e desativáveis; anúncios `aria-live="polite"` para lance do adversário ("Adversário jogou cavalo para f3"), `assertive` para fim de partida e perda de conexão. Testes com NVDA + Firefox e VoiceOver + Safari na Fase 7.

## 8. Mensagens
Erros dizem o que houve e o que fazer: "Esse lance não é permitido: a captura é obrigatória (peça em 22 pode capturar)." Sem códigos técnicos para o usuário (o `request_id` aparece em "detalhes" para suporte).

## 9. Indicadores de turno e estados
TurnIndicator com texto ("Sua vez" / "Vez do adversário"), ícone e cor. Carregamento: skeleton do tabuleiro; IA pensando: "IA pensando…" com indicador não intermitente. Estados vazios: histórico sem partidas mostra chamada para jogar. Fim de partida: diálogo com resultado em texto, motivo e ações (revanche, análise, lobby).

## 10. Reconexão
ConnectionBanner persistente: "Conexão perdida. Tentando reconectar… (tentativa 2)"; tabuleiro bloqueado para lances; quando o oponente cai: "Adversário desconectado. Você poderá reivindicar vitória em 0:45" com contagem acessível (anúncio a cada 15 s, não a cada segundo).

## 11. Personalização das peças
Três estilos por jogo (infantil — formas arredondadas e cores vivas; intermediário; clássico — Staunton para xadrez). Todos precisam manter peças distinguíveis por **forma**, não apenas cor. Prévia antes de aplicar. Independente da dificuldade (doc 08 §11). Ativos visuais devem ser originais ou de licença compatível documentada (P-11).

## 12. Experiência de aprendizagem
Lições curtas (≤ 3 min), um conceito por vez; tabuleiro interativo na própria lição; barra de progresso por conceito com rótulo textual ("Em prática — 3 de 5 acertos"); dicas por botão explícito; sem penalização visual humilhante por erro.

## 13. Critérios de validação
axe-core em todas as rotas no E2E (0 violações sérias/críticas); checklist manual WCAG 2.2 AA por tela; partida completa só por teclado nos 3 jogos (RNF-015); teste em 320 px; teste com zoom 200% sem perda de função; teste com `prefers-reduced-motion: reduce`.
