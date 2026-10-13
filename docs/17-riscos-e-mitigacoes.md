# 17 — Riscos e Mitigações

> Versão 0.1.0 · 2026-10-13 · Escala: probabilidade/impacto 1 (baixo) a 3 (alto); criticidade = P × I. Responsáveis a definir (P-01) — coluna indica o **papel**.

| ID | Categoria | Descrição | P | I | Crit. | Mitigação | Responsável | Risco residual |
|----|-----------|-----------|---|---|-------|-----------|-------------|----------------|
| R-001 | Escopo | Escopo amplo (3 jogos + Academy + online) para equipe pequena atrasa tudo | 3 | 2 | 6 | Fases incrementais; velha primeiro; fase 6 opcional para lançamento | Produto | Médio |
| R-002 | Técnico | Versões incompatíveis por não terem sido verificadas (DT-012) | 2 | 2 | 4 | P-02 no início da Fase 1; lockfiles; CI | Mantenedor | Baixo |
| R-003 | Técnico | Condições de corrida em lances/ratings corrompem partidas | 2 | 3 | 6 | Bloqueio de linha, `expected_ply`, idempotência, testes de concorrência (doc 11 §5) | Backend | Baixo |
| R-004 | Técnico | Reconexão WS instável em redes móveis | 3 | 2 | 6 | Snapshot completo, backoff, tolerância de 60 s, E2E com rede derrubada | Backend/frontend | Médio |
| R-005 | Segurança | Falha de autorização (IDOR) expõe/manipula partidas | 2 | 3 | 6 | Autorização em `services`, testes IDOR obrigatórios por endpoint | Segurança | Baixo |
| R-006 | Qualidade | Regras de damas implementadas erradas | 2 | 3 | 6 | P-07, testes por regra, perft, revisão por jogador experiente | Domínio | Baixo |
| R-007 | Pedagógico | Exercícios mal calibrados frustram ou entediam | 3 | 2 | 6 | Métricas de taxa de acerto, revisão humana, ajuste de α e dificuldade | Pedagogia | Médio |
| R-008 | Jurídico | Licença GPL de python-chess/Stockfish incompatível com o modelo de distribuição | 2 | 3 | 6 | Análise jurídica (P-04) antes da Fase 5; alternativa permissiva | Produto/jurídico | Médio |
| R-009 | Acessibilidade | Casas do tabuleiro 8×8 menores que 44 px em celulares pequenos | 3 | 2 | 6 | Seleção em duas etapas com ampliação, entrada por notação, testes em 320 px | Design | Médio |
| R-010 | Custo/desempenho | IA forte e Ollama consomem CPU/GPU além do orçamento | 2 | 2 | 4 | Limites de tempo/concorrência, Ollama opcional e desligado por padrão, cache de análises | Ops | Baixo |
| R-011 | Abuso | Trapaça com motor externo e manipulação de rating entre contas | 3 | 2 | 6 | SEC-13; sinalização para revisão humana; limites de pareamento repetido | Moderação | Médio |
| R-012 | Abuso/privacidade | Recursos sociais (chat, amizades) expõem usuários a assédio, sobretudo menores | 2 | 3 | 6 | Sem chat livre na v1; bloqueio; denúncia; decisão P-03 | Produto | Baixo |
| R-013 | Privacidade | Dados pessoais vazam em logs ou ferramentas de observabilidade | 2 | 3 | 6 | SEC-12, teste RNF-013, ferramentas auto-hospedadas | Ops | Baixo |
| R-014 | Qualidade IA | LLM produz explicação com fato falso | 3 | 2 | 6 | LLM só reformula; verificação de saída; fallback a template (doc 08 §8) | IA | Baixo |
| R-015 | Manutenção | Documentação diverge do código | 3 | 2 | 6 | AGENTS.md exige atualização no mesmo PR; `check_docs.py` no CI | Todos | Médio |
