# ADR-0001 — Arquitetura inicial do BoardHub

- **Data:** 2026-10-13
- **Estado:** aceito (2026-10-13)
- **Decisores:** responsável pelo produto (@edervani)

## Contexto
Repositório novo, sem código prévio. Produto com três jogos, IA adversária, partidas online em tempo real, Academy e requisitos fortes de segurança, privacidade e operação sem APIs pagas. Equipe presumidamente pequena e orçamento a definir (P-06).

## Alternativas consideradas
1. **Monólito modular** (React SPA + FastAPI + PostgreSQL) — escolhida.
2. **Microsserviços** (auth, partidas, IA, academy separados): isolamento, mas custo operacional, consistência distribuída e observabilidade desproporcionais ao estágio.
3. **Full-stack JavaScript** (Next.js + Node): uma linguagem só, mas ecossistema de IA/regras de xadrez mais fraco no backend e duplicação provável de motores.
4. **BaaS (Firebase/Supabase) com regras no cliente**: rápido, mas validação autoritativa de jogos ficaria fraca ou dependente de funções do fornecedor; aprisionamento.

## Decisão
Monólito modular com fronteiras explícitas (`api` → `services` → `game_engines`/`ai`/`db` → `core`), REST + WebSocket nativo, PostgreSQL como única fonte de verdade, motores puros e determinísticos no servidor, IA generativa opcional atrás de interface.

## Justificativa
Menor custo e complexidade; transações ACID simples para lances e ratings; uma única implementação de regras; módulos extraíveis no futuro.

## Consequências
- (+) Deploy simples (um contêiner de aplicação), testes de integração diretos.
- (−) Escala horizontal de WS exige barramento (DT-009) quando necessário.
- (−) IA CPU-bound compete com a API: exige pool de processos e limites.
- Requer disciplina de dependências verificada em CI (RNF-019).

## Critérios para revisão futura
Revisar com novo ADR se: > 5.000 conexões WS simultâneas sustentadas; IA consumir > 50% de CPU de forma persistente; equipe > 3 times independentes; necessidade de outro runtime para um jogo.
