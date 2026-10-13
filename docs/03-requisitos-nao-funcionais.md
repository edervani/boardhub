# 03 — Requisitos Não Funcionais

> Versão 0.1.0 · 2026-10-13 · Estado: **proposto**

**Todas as metas numéricas abaixo são propostas a validar.** Não há medição real; os valores partem de premissas de uma instalação pequena (1 servidor de aplicação, ≤ 500 usuários simultâneos) e devem ser revistos após o teste de carga da Fase 7.

| ID | Categoria | Requisito | Métrica | Cenário de teste | Meta proposta | Teste |
|----|-----------|-----------|---------|------------------|---------------|-------|
| RNF-001 | Desempenho | Latência de validação de lance online | p95 do tempo servidor entre receber `submit_move` e enviar `move_applied` | 200 partidas simultâneas, carga sintética | ≤ 150 ms (velha/damas), ≤ 250 ms (xadrez) | T-101 |
| RNF-002 | Desempenho | Tempo de resposta da IA adversária | p95 do tempo de cálculo por nível | 100 posições de referência por jogo | Nível 1–3 ≤ 1 s; nível 4–5 ≤ 3 s | T-102 |
| RNF-003 | Desempenho | Endpoints REST | p95 de latência | 50 req/s mistas | ≤ 300 ms | T-103 |
| RNF-004 | Desempenho | Carregamento inicial do frontend | LCP em 4G simulado (Lighthouse) | Página de lobby | ≤ 2,5 s; bundle JS inicial ≤ 250 KB gzip | T-104 |
| RNF-005 | Escalabilidade | Conexões WebSocket simultâneas | Conexões estáveis por instância | Teste de carga crescente | ≥ 1.000 por instância sem erro | T-105 |
| RNF-006 | Escalabilidade | Escala horizontal | Funcionamento com 2 instâncias | Partida com jogadores em instâncias diferentes | Lances entregues a ambos (requer barramento — DT-009) | T-106 |
| RNF-007 | Disponibilidade | Disponibilidade mensal | % de minutos com `/health/ready` OK | Monitoramento externo | ≥ 99,5% (exclui manutenção anunciada) | T-107 |
| RNF-008 | Recuperação | RPO/RTO do banco | Perda máxima de dados / tempo de restauração | Exercício trimestral de restauração | RPO ≤ 24 h (v1; ≤ 15 min com WAL) · RTO ≤ 4 h | T-108 |
| RNF-009 | Recuperação | Reinício do servidor durante partida | Partidas retomáveis após reinício | Derrubar processo no meio de 20 partidas | 100% retomáveis do último lance confirmado | T-109 |
| RNF-010 | Segurança | Armazenamento de senhas | Algoritmo e parâmetros | Inspeção de código + teste | Argon2id, parâmetros ≥ recomendação OWASP vigente (verificar na Fase 1) | T-110 |
| RNF-011 | Segurança | Dependências sem vulnerabilidade crítica conhecida | Achados `pip-audit`/`npm audit` | CI em todo PR | 0 críticas/altas sem justificativa registrada | T-111 |
| RNF-012 | Segurança | Cabeçalhos de segurança | Presença de CSP, HSTS, X-Content-Type-Options, frame-ancestors | Teste automatizado de resposta | 100% das respostas HTML | T-112 |
| RNF-013 | Privacidade | Logs sem dados sensíveis | Ocorrências de senha/token/e-mail completo nos logs | Varredura de logs de testes E2E | 0 ocorrências | T-113 |
| RNF-014 | Acessibilidade | Conformidade WCAG 2.2 nível AA | Violações axe-core + auditoria manual | Todas as telas principais | 0 violações "serious/critical" no axe; checklist manual aprovado | T-114 |
| RNF-015 | Acessibilidade | Jogo completo por teclado | Partida concluída sem mouse | E2E por teclado nos 3 jogos | 100% | T-115 |
| RNF-016 | Compatibilidade | Navegadores suportados | Suíte E2E | Chromium, Firefox, WebKit nas 2 últimas versões estáveis | 100% dos testes E2E passam | T-116 |
| RNF-017 | Responsividade | Layout | Sem rolagem horizontal; tabuleiro visível inteiro | Larguras 320, 375, 768, 1280, 1920 px | 100% | T-117 |
| RNF-018 | Manutenibilidade | Qualidade estática | Lint, tipagem estrita (mypy/pyright, `tsc --strict`) | CI | 0 erros | T-118 |
| RNF-019 | Manutenibilidade | Ausência de dependências circulares | Ferramenta de grafo de importações | CI | 0 ciclos entre módulos | T-119 |
| RNF-020 | Testabilidade | Cobertura dos motores de regras | Cobertura de ramos | CI | ≥ 95% em `game_engines/` (complementar a testes de invariantes) | T-120 |
| RNF-021 | Testabilidade | Cobertura geral backend/frontend | Cobertura de linhas | CI | ≥ 80% (não é prova de qualidade isolada) | T-121 |
| RNF-022 | Integridade | Consistência de partida | Lances duplicados ou ratings divergentes | Teste de concorrência com submissões paralelas | 0 inconsistências | T-122 |
| RNF-023 | Observabilidade | Rastreabilidade de requisições | % de logs com `request_id` | Inspeção de logs | 100% dos logs de requisição | T-123 |
| RNF-024 | Usabilidade | Primeira partida | Tempo de um iniciante até iniciar partida contra IA | Teste com 5 participantes fictícios/recrutados com consentimento | Mediana ≤ 2 min | T-124 |
| RNF-025 | Custos | Operação sem APIs pagas | Funções essenciais com Ollama e internet externa desligados | Teste E2E com Ollama desabilitado | 100% das funções M operam | T-125 |
| RNF-026 | Custos | Custo de infraestrutura v1 | Custo mensal estimado | Planilha de dimensionamento | Definir orçamento (pendência P-06) | — |
| RNF-027 | Privacidade | Minimização | Campos pessoais coletados | Revisão do modelo de dados | Apenas campos justificados no doc 05 | T-127 |
| RNF-028 | Integridade | Migrações reversíveis ou com plano | Migrações com `downgrade` testado ou justificativa | CI aplica up/down em banco vazio | 100% | T-128 |

## Notas
- Cobertura de código (RNF-020/021) não substitui testes de invariantes, casos-limite e abuso (doc 11 §2).
- RNF-006 depende da decisão DT-009 (Redis pub/sub ou PostgreSQL LISTEN/NOTIFY). Na v1 com uma instância, o requisito é **adiado** mas a arquitetura não pode impedi-lo.
