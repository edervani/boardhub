# 14 — Plano de Implementação

> Versão 0.1.0 · 2026-10-13 · Estado: **proposto** · Fase atual: **0 (em revisão)**

Regra: nenhuma fase começa com dependência crítica não resolvida. Cada fase termina com CHANGELOG, matriz de rastreabilidade atualizada e CA validados (doc 15 §3).

| Fase | Objetivo | Escopo (RF/RNF) | Dependências | Entregáveis | Testes | Riscos | Início | Conclusão |
|------|----------|-----------------|--------------|-------------|--------|--------|--------|-----------|
| **0** Requisitos e documentação | Especificação aprovada | Todos os documentos | — | `docs/`, arquivos raiz, `check_docs.py` | `check_docs.py` | R-001 | 2026-10-13 | Responsável aprova docs; pendências P-01, P-02, P-03, P-06 decididas |
| **1** Base técnica | Esqueleto funcional seguro | RF-001–007, RNF-010–013, 018, 019, 023, 028 | Fase 0; versões verificadas (P-02) | Backend FastAPI, frontend Vite, banco + migrações, auth completa, CI, compose | T-001–007, T-110–113, 118, 119, 128 | R-002, R-005 | Fase 0 concluída | CA-001–007 validados; CI verde |
| **2** Jogo da velha completo | Primeiro jogo ponta a ponta, inclusive online | RF-008–016, 019 (estrutura), 020, 021, RNF-001, 009, 014–017, 022 | Fase 1 | Motor + IA velha, lobby, partidas local/IA/convite/fila, WS, histórico | T-008–016, 020, 021, 101, 109, 114–117, 122 | R-003, R-004 | Fase 1 | CA-008–016, 020, 021 validados |
| **3** Academy inicial | Aprendizagem com velha | RF-022, 023, 025 (velha) | Fase 2; revisor de conteúdo (P-08) | Conceitos, exercícios, domínio, revisão espaçada | T-022, 023, 025 | R-007 | Fase 2 | CA-022, 023, 025 validados |
| **4** Damas | Segundo jogo + ranking | RF-017, 019, Academy damas, RF-024 (damas) | Fase 3; variante aprovada e regras conferidas (DT-006, P-07) | Motor damas BR, IA alfa-beta, Elo, lições | T-017, 019, 024, 102 | R-006 | Fase 3 + P-07 | CA-017, 019 validados; perft confere |
| **5** Xadrez | Terceiro jogo | RF-018, Academy xadrez, RF-024 completo | Fase 4; decisão de licença do motor (DT-005) | Integração python-chess + motor UCI, lições, Mentor; Ollama opcional | T-018, 024, 102, 125 | R-008, R-010 | Fase 4 + DT-005 | CA-018, 024 validados |
| **6** Engajamento | Retenção saudável | RF-026–028, 032, personalização avançada | Fase 5 | Conquistas, desafio diário, notificações, amizades, estilos de peças | T-026–028, 032 | R-011, R-012 | Fase 5 | CA-026–028, 032 validados |
| **7** Publicação | Pronto para público | RF-029–031, RNF restantes | Fases 1–6; jurídico (P-03, P-04) | Exportação/exclusão, moderação, teste de carga, auditoria de segurança e acessibilidade, backups, monitoramento | T-029–031, T-103–108, 114, 116, 124 | R-001–R-013 | Fase 6 | Checklist do doc 12 §12 completo |

Observação: RF-029/030 (direitos do titular) são M; podem ser antecipados para a Fase 1–2 se houver usuários reais em teste fechado — **obrigatório** antes de qualquer beta com pessoas reais.
