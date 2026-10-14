# 16 — Decisões Técnicas

> Versão 0.2.0 · 2026-10-13 · Decisões aprovadas pelo responsável pelo produto em 2026-10-13, exceto as marcadas como condicionadas.

| ID | Data | Contexto | Decisão | Alternativas | Justificativa | Consequências | Estado |
|----|------|----------|---------|--------------|---------------|---------------|--------|
| DT-001 | 2026-10-13 | Equipe pequena, 3 jogos | Monólito modular (ADR-0001) | Microsserviços; serverless | Menor custo operacional; módulos com fronteiras claras permitem extrair depois | Disciplina de dependências obrigatória (RNF-019) | aprovada |
| DT-002 | 2026-10-13 | Backend com IA e regras | Python + FastAPI | Node/NestJS; Go | python-chess, ecossistema de IA, async nativo com WS | Busca de IA CPU-bound exige pool de processos | aprovada |
| DT-003 | 2026-10-13 | Estilo do frontend | CSS Modules + tokens CSS | Tailwind; CSS-in-JS | Sem runtime extra; temas por variáveis CSS; escopo local | Componentes do design system escritos à mão | aprovada |
| DT-004 | 2026-10-13 | Autenticação web | Sessão opaca em cookie HttpOnly com hash no banco | JWT em localStorage; JWT em cookie | Revogação imediata, sem token acessível a JS, simples | Consulta ao banco por requisição (aceitável; cache se necessário) | aprovada |
| DT-005 | 2026-10-13 | Xadrez | python-chess para regras; Stockfish via UCI para IA forte | Regras próprias; chess.js no backend Node | Não reimplementar regras complexas | **Ambos GPL-3.0.** Uso como serviço web não distribui binário ao usuário, mas a licença do projeto e qualquer distribuição de imagens precisam de análise (P-04). Alternativa caso inaceitável: motor com licença permissiva a avaliar | aprovada com condição — licença depende de P-04; **bloqueia Fase 5** |
| DT-006 | 2026-10-13 | Damas | Variante brasileira (doc 07 §3) | Damas inglesas (checkers americano); internacionais 10×10 | Mais familiar ao público brasileiro | Regras devem ser conferidas na fonte oficial (P-07) | aprovada com condição — regras dependem de P-07; **bloqueia Fase 4** |
| DT-007 | 2026-10-13 | Partida local sem duplicar regras | Partidas locais validadas pelo servidor: autenticado ⇒ partida `mode=local` persistida; visitante ⇒ endpoint sem estado `POST /engines/{game}/apply` | Portar motores para TypeScript; validar só no cliente | Uma única implementação de regras | Partida local exige conexão com o servidor | aprovada |
| DT-008 | 2026-10-13 | Ranking | Elo por jogo, inicial 1200, K 40→20 após 30 partidas; jogo da velha **sem ranking** | Glicko-2; ranking para velha | Elo é simples e explicável; velha é resolvida (empate com jogo perfeito) | Revisar para Glicko-2 se houver muita variação | aprovada |
| DT-009 | 2026-10-13 | Tempo real com várias instâncias | v1: 1 instância, salas em memória; ao escalar, barramento (Redis pub/sub ou PostgreSQL LISTEN/NOTIFY) | Sticky sessions apenas | Evitar dependência prematura | Código de salas atrás de interface `Broadcaster` | aprovada |
| DT-010 | 2026-10-13 | Partidas simultâneas | Máx. 1 partida online ativa por jogo por usuário | Ilimitado | Simplifica abandono e antiabuso | Revisar se houver modo assíncrono | aprovada |
| DT-011 | 2026-10-13 | Chaves primárias | UUID gerado na aplicação (v7 se a biblioteca suportar, senão v4) | bigserial | Não expõe volume; IDs seguros em URLs | Índices maiores | aprovada |
| DT-012 | 2026-10-13 | Versões de dependências | **Não fixadas nesta execução**: o ambiente não tinha acesso aos registros pip/npm, logo nada pôde ser verificado | Escrever versões de memória | Proibição de inventar versões | Runtimes decididos em DT-014; versões das bibliotecas verificadas e lockfiles gerados no início da Fase 1 | aprovada |
| DT-013 | 2026-10-13 | IP de usuários | Não persistir IP em banco; só em logs com retenção de 30 dias | Guardar IP por sessão | Minimização | Detecção de abuso por IP limitada aos logs recentes | aprovada |
| DT-014 | 2026-10-13 | Versões de runtime (P-02): responsável pediu "as mais utilizadas" | Python **3.13**, Node.js **24 LTS**, PostgreSQL **17** | Python 3.14/3.15; Node 26 (vira LTS em 2026-10-28); PostgreSQL 18 | Versões maduras com amplo suporte de bibliotecas. Fontes: devguide.python.org (3.13 com suporte até 2029-10); repositório nodejs/release (24 em LTS até 2028-04-30). PostgreSQL 17 escolhido pela política de 5 anos de suporte do projeto — **não verificado nesta sessão** | Revisar na Fase 7 (ex.: migrar para Node 26 LTS) | aprovada |
| DT-015 | 2026-10-13 | P-03: responsável decidiu abrir a plataforma a menores com classificação etária por jogo | Contas para todas as idades; faixa etária autodeclarada no cadastro; classificação indicativa exibida por jogo (RF-033); configuração mais protetiva para menores e supervisão parental (RF-034) | Somente adultos | Público familiar e escolar faz parte da visão | Aplica-se o ECA Digital (Lei 15.211/2025, em vigor desde 2026-03-17) e o art. 14 da LGPD; obrigações detalhadas no doc 09 §10; análise jurídica continua necessária (P-04) | aprovada |

## Pendências que dependem de aprovação

| ID | Pendência | Bloqueia | Recomendação |
|----|-----------|----------|--------------|
| P-01 | ~~Responsável pelo produto~~ | — | **Resolvida 2026-10-13:** @edervani (aprova documentos e fases) |
| P-02 | ~~Versões das bibliotecas~~ | — | **Resolvida na Fase 1:** versões resolvidas pelo CI nos lockfiles (`backend/uv.lock`, `frontend/package-lock.json`); ex.: FastAPI 0.143.0, SQLAlchemy 2.1.4, Pydantic 2.14.1, React 19.3.0, Vite 7.3.7, Vitest 5.0.4 |
| P-03 | ~~Permitir menores?~~ | — | **Resolvida 2026-10-13:** sim, com classificação indicativa por jogo (DT-015). Requisitos legais seguem em P-04 |
| P-04 | Encarregado de dados, política de privacidade, termos, bases legais, licença GPL **e conformidade com o ECA Digital** (verificação de idade, consentimento parental, vínculo de contas de menores) | Beta com pessoas reais; Fase 7; DT-005 | Consultoria jurídica |
| P-05 | Forma de financiamento compatível com proibições | — | Doações/patrocínio sem vantagem competitiva |
| P-06 | Hospedagem e orçamento mensal — responsável ainda não definiu | Homologação e produção (não bloqueia a Fase 1, que roda local e no CI) | Decidir antes do fim da Fase 2 |
| P-07 | Conferir regras de damas brasileiras no regulamento oficial e obter valores de perft de referência | Fase 4 | — |
| P-08 | ~~Revisor de conteúdo da Academy~~ | — | **Resolvida 2026-10-13:** o próprio responsável (@edervani) |
| P-09 | Modelo Ollama em pt-BR e requisitos de hardware | Ativação do LLM | Avaliar 2–3 modelos com a rubrica do doc 08 §10 |
| P-10 | CAPTCHA acessível | Somente se houver abuso | Preferir soluções auto-hospedadas e acessíveis |
| P-11 | Origem e licença dos ativos visuais (peças, ícones) | Fase 2 | Ativos próprios ou licença permissiva |
| P-12 | Ferramenta de teste de carga | Fase 7 | — |
| P-13 | Proxy reverso (Caddy × Nginx) | Fase 7 | Caddy pela gestão automática de TLS |
| P-14 | ~~Plataforma de CI~~ | — | **Resolvida 2026-10-13:** GitHub Actions |
| P-15 | Lacunas conhecidas da Fase 1: limite diário de tempo ainda sem aplicação (sem partidas), notação de lances (RF-007), painel do responsável e E2E de CA-006/CA-033 no frontend | Aceite completo de RF-007, RF-033, RF-034 | Tratar na Fase 2 (partidas locais/IA) e Fase 7 (E2E); manter os RF em `aprovado` até lá |
