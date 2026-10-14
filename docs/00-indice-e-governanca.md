# 00 — Índice e Governança da Documentação

> Versão do documento: 0.2.0 · Data: 2026-10-13 · Estado: **aprovado** em 2026-10-13 pelo responsável pelo produto

## 1. Situação do projeto

Em 2026-10-13 o repositório foi criado do zero, a pedido do responsável pelo produto. Desde a Fase 1 existe código de aplicação na branch `feat/fase-1-base` (identidade, perfil, catálogo e supervisão — ver CHANGELOG). Nada foi mesclado na `main` ainda: os requisitos permanecem `aprovado` até o merge (doc 00 §4). Todo comportamento não coberto pelo CHANGELOG é **especificação**.

## 2. Índice

| Nº | Documento | Objetivo | Público-alvo |
|----|-----------|----------|--------------|
| 00 | [Índice e governança](00-indice-e-governanca.md) | Hierarquia, estados, processo de mudança | Todos |
| 01 | [Visão do produto](01-visao-do-produto.md) | Por que e para quem; escopo e proibições | Produto, todos |
| 02 | [Requisitos funcionais](02-requisitos-funcionais.md) | RF-xxx com fluxos e aceite | Dev, QA |
| 03 | [Requisitos não funcionais](03-requisitos-nao-funcionais.md) | RNF-xxx mensuráveis | Dev, Ops, QA |
| 04 | [Arquitetura técnica](04-arquitetura-tecnica.md) | Componentes, módulos, fluxos | Dev |
| 05 | [Modelagem de dados](05-modelagem-de-dados.md) | Entidades, restrições, retenção | Dev, DBA |
| 06 | [API e tempo real](06-api-e-tempo-real.md) | Contratos REST e WebSocket | Dev frontend/backend |
| 07 | [Motores e regras dos jogos](07-motores-e-regras-dos-jogos.md) | Regras, estado, IA adversária | Dev de domínio |
| 08 | [IA e BoardHub Academy](08-ia-e-boardhub-academy.md) | IA de jogo × pedagógica, Ollama | Dev, pedagogia |
| 09 | [Segurança e privacidade](09-seguranca-e-privacidade.md) | Ameaças, controles, LGPD | Dev, segurança, jurídico |
| 10 | [Interface e acessibilidade](10-interface-e-acessibilidade.md) | Design system, WCAG | Design, frontend |
| 11 | [Testes e qualidade](11-testes-e-qualidade.md) | Estratégia e matriz de rastreabilidade | QA, dev |
| 12 | [Infraestrutura e deploy](12-infraestrutura-e-deploy.md) | Ambientes, CI/CD, backup | Ops |
| 13 | [Monitoramento e operação](13-monitoramento-e-operacao.md) | Logs, métricas, runbooks | Ops |
| 14 | [Plano de implementação](14-plano-de-implementacao.md) | Fases 0–7 | Todos |
| 15 | [Critérios de aceite](15-criterios-de-aceite.md) | CA-xxx verificáveis | QA, produto |
| 16 | [Decisões técnicas](16-decisoes-tecnicas.md) | DT-xxx e pendências | Dev, produto |
| 17 | [Riscos e mitigações](17-riscos-e-mitigacoes.md) | Matriz R-xxx | Todos |
| 18 | [Glossário](18-glossario.md) | Termos | Todos |
| ADR | [ADR-0001](adr/ADR-0001-arquitetura-inicial.md) | Decisão arquitetural inicial | Dev |

Arquivos da raiz: [README](../README.md), [AGENTS](../AGENTS.md), [CONTRIBUTING](../CONTRIBUTING.md), [CHANGELOG](../CHANGELOG.md).

## 3. Hierarquia e resolução de conflitos

Em caso de contradição, prevalece o documento mais alto na lista:

1. Restrições legais e regras proibitivas (doc 01 §6, doc 09) — nunca são relaxadas por documento inferior.
2. ADRs aprovados (`docs/adr/`).
3. Requisitos aprovados (docs 02 e 03).
4. Arquitetura e contratos (docs 04–08, 10).
5. Critérios de aceite e testes (docs 11, 15).
6. Planos e operação (docs 12–14, 17).
7. README, CONTRIBUTING, comentários de código.

Conflito detectado ⇒ registrar em [16-decisoes-tecnicas.md §Pendências](16-decisoes-tecnicas.md), não resolver silenciosamente, e escalar ao responsável pelo produto.

## 4. Estados dos requisitos

| Estado | Significado | Quem muda |
|--------|-------------|-----------|
| `proposto` | Redigido, ainda não aprovado | Qualquer autor (inclusive IA) |
| `aprovado` | Aceito pelo responsável pelo produto | Somente responsável humano |
| `implementado` | Código mesclado na `main` | Autor do PR, com link |
| `validado` | Critérios de aceite comprovados com evidência | QA/revisor, com evidência |
| `obsoleto` | Substituído ou removido; ID nunca reutilizado | Responsável humano |

**Nenhum requisito é aprovado por ter sido sugerido por uma IA.** A documentação foi aprovada pelo responsável pelo produto em 2026-10-13 (v0.2.0).

## 5. Responsabilidades

| Papel | Responsabilidade |
|-------|------------------|
| Responsável pelo produto (@edervani) | Aprovar requisitos, ADRs e fases |
| Mantenedor técnico (a definir) | Coerência de 04–07, 11–13 |
| Encarregado de dados/jurídico (a definir — P-04) | Validar doc 09 §LGPD |
| Agentes de IA | Seguir [AGENTS.md](../AGENTS.md); propor, nunca aprovar |

## 6. Controle de versão e processo de alteração

1. Abrir issue/PR descrevendo a mudança, o ID afetado e o motivo.
2. Atualizar todos os documentos afetados no **mesmo PR** (requisito, critério, teste, matriz, changelog).
3. Mudança de arquitetura ⇒ novo ADR; ADRs antigos ficam com estado `substituído`, nunca são reescritos.
4. IDs (RF, RNF, CA, DT, R, ADR, T) são estáveis e nunca reutilizados.
5. Versão do documento no cabeçalho segue SemVer: mudança de requisito = minor; correção textual = patch.

## 7. Histórico de decisões relevantes

| Data | Decisão | Referência |
|------|---------|-----------|
| 2026-10-13 | Iniciar repositório novo (não havia código prévio) | Diagnóstico no relatório da Fase 0 |
| 2026-10-13 | Arquitetura de referência proposta | [ADR-0001](adr/ADR-0001-arquitetura-inicial.md) |
| 2026-10-13 | Versões de dependências não fixadas por falta de verificação | DT-012, P-02 |
| 2026-10-13 | Documentação v0.2.0 aprovada; runtimes; abertura a menores com classificação por jogo | DT-014, DT-015 |

## 8. Rastreabilidade

A matriz Requisito → Módulo → Teste → Critério → Estado → Evidência está em [11-testes-e-qualidade.md §Matriz](11-testes-e-qualidade.md#8-matriz-de-rastreabilidade). Ela é verificada automaticamente por `scripts/check_docs.py`.
