# 16 — Decisões Técnicas

> Versão 0.1.0 · 2026-10-13 · Todas as decisões estão em estado **proposta** até aprovação humana.

| ID | Data | Contexto | Decisão | Alternativas | Justificativa | Consequências | Estado |
|----|------|----------|---------|--------------|---------------|---------------|--------|
| DT-001 | 2026-10-13 | Equipe pequena, 3 jogos | Monólito modular (ADR-0001) | Microsserviços; serverless | Menor custo operacional; módulos com fronteiras claras permitem extrair depois | Disciplina de dependências obrigatória (RNF-019) | proposta |
| DT-002 | 2026-10-13 | Backend com IA e regras | Python + FastAPI | Node/NestJS; Go | python-chess, ecossistema de IA, async nativo com WS | Busca de IA CPU-bound exige pool de processos | proposta |
| DT-003 | 2026-10-13 | Estilo do frontend | CSS Modules + tokens CSS | Tailwind; CSS-in-JS | Sem runtime extra; temas por variáveis CSS; escopo local | Componentes do design system escritos à mão | proposta |
| DT-004 | 2026-10-13 | Autenticação web | Sessão opaca em cookie HttpOnly com hash no banco | JWT em localStorage; JWT em cookie | Revogação imediata, sem token acessível a JS, simples | Consulta ao banco por requisição (aceitável; cache se necessário) | proposta |
| DT-005 | 2026-10-13 | Xadrez | python-chess para regras; Stockfish via UCI para IA forte | Regras próprias; chess.js no backend Node | Não reimplementar regras complexas | **Ambos GPL-3.0.** Uso como serviço web não distribui binário ao usuário, mas a licença do projeto e qualquer distribuição de imagens precisam de análise (P-04). Alternativa caso inaceitável: motor com licença permissiva a avaliar | proposta — **bloqueia Fase 5** |
| DT-006 | 2026-10-13 | Damas | Variante brasileira (doc 07 §3) | Damas inglesas (checkers americano); internacionais 10×10 | Mais familiar ao público brasileiro | Regras devem ser conferidas na fonte oficial (P-07) | proposta — **bloqueia Fase 4** |
| DT-007 | 2026-10-13 | Partida local sem duplicar regras | Partidas locais validadas pelo servidor: autenticado ⇒ partida `mode=local` persistida; visitante ⇒ endpoint sem estado `POST /engines/{game}/apply` | Portar motores para TypeScript; validar só no cliente | Uma única implementação de regras | Partida local exige conexão com o servidor | proposta |
| DT-008 | 2026-10-13 | Ranking | Elo por jogo, inicial 1200, K 40→20 após 30 partidas; jogo da velha **sem ranking** | Glicko-2; ranking para velha | Elo é simples e explicável; velha é resolvida (empate com jogo perfeito) | Revisar para Glicko-2 se houver muita variação | proposta |
| DT-009 | 2026-10-13 | Tempo real com várias instâncias | v1: 1 instância, salas em memória; ao escalar, barramento (Redis pub/sub ou PostgreSQL LISTEN/NOTIFY) | Sticky sessions apenas | Evitar dependência prematura | Código de salas atrás de interface `Broadcaster` | proposta |
| DT-010 | 2026-10-13 | Partidas simultâneas | Máx. 1 partida online ativa por jogo por usuário | Ilimitado | Simplifica abandono e antiabuso | Revisar se houver modo assíncrono | proposta |
| DT-011 | 2026-10-13 | Chaves primárias | UUID gerado na aplicação (v7 se a biblioteca suportar, senão v4) | bigserial | Não expõe volume; IDs seguros em URLs | Índices maiores | proposta |
| DT-012 | 2026-10-13 | Versões de dependências | **Não fixadas nesta execução**: o ambiente não tinha acesso aos registros pip/npm, logo nada pôde ser verificado | Escrever versões de memória | Proibição de inventar versões | Fase 1 começa verificando versões e gerando lockfiles | proposta |
| DT-013 | 2026-10-13 | IP de usuários | Não persistir IP em banco; só em logs com retenção de 30 dias | Guardar IP por sessão | Minimização | Detecção de abuso por IP limitada aos logs recentes | proposta |

## Pendências que dependem de aprovação

| ID | Pendência | Bloqueia | Recomendação |
|----|-----------|----------|--------------|
| P-01 | Nomear responsável pelo produto (aprovador) | Saída da Fase 0 | — |
| P-02 | Verificar versões de Python, Node, PostgreSQL e bibliotecas; gerar lockfiles | Fase 1 | Usar versões estáveis com suporte ativo na data |
| P-03 | Permitir menores de 18 anos? | Fase 7 (e beta) | Não permitir na v1 até análise jurídica (doc 09 §10) |
| P-04 | Encarregado de dados, política de privacidade, termos, bases legais, licença GPL | Fase 7; DT-005 | Consultoria jurídica |
| P-05 | Forma de financiamento compatível com proibições | — | Doações/patrocínio sem vantagem competitiva |
| P-06 | Orçamento mensal de infraestrutura | Fase 1 (escolha de hospedagem) | — |
| P-07 | Conferir regras de damas brasileiras no regulamento oficial e obter valores de perft de referência | Fase 4 | — |
| P-08 | Revisor com domínio dos jogos para conteúdo da Academy | Fase 3 | — |
| P-09 | Modelo Ollama em pt-BR e requisitos de hardware | Ativação do LLM | Avaliar 2–3 modelos com a rubrica do doc 08 §10 |
| P-10 | CAPTCHA acessível | Somente se houver abuso | Preferir soluções auto-hospedadas e acessíveis |
| P-11 | Origem e licença dos ativos visuais (peças, ícones) | Fase 2 | Ativos próprios ou licença permissiva |
| P-12 | Ferramenta de teste de carga | Fase 7 | — |
| P-13 | Proxy reverso (Caddy × Nginx) | Fase 7 | Caddy pela gestão automática de TLS |
| P-14 | Plataforma de CI | Fase 1 | Conforme hospedagem do repositório |
