# Contribuindo com o BoardHub

Leia antes: [AGENTS.md](AGENTS.md) (vale também para pessoas) e [docs/00](docs/00-indice-e-governanca.md).

## Padrões de código
- **Python:** formatação e lint com Ruff; tipagem estrita (mypy ou pyright — definido na Fase 1); docstrings em funções públicas de `services` e `game_engines`.
- **TypeScript:** `strict: true`; ESLint + Prettier; componentes funcionais; lógica em hooks/serviços, não em JSX.
- Nomes de código em inglês; textos de interface e documentação em português brasileiro.

## Branches
`main` protegida (sempre implantável). Trabalho em `feat/<id>-descricao`, `fix/<id>-descricao`, `docs/…`, `chore/…`, onde `<id>` é o requisito ou issue (ex.: `feat/RF-013-submit-move`).

## Commits
[Conventional Commits](https://www.conventionalcommits.org/pt-br/): `feat(matches): valida expected_ply (RF-013)`. Tipos: feat, fix, docs, test, refactor, chore, perf, security. Um assunto por commit.

## Pull requests
Descrição com: requisitos afetados (IDs), o que mudou, como foi testado (comandos e resultado), impacto em segurança/privacidade, documentos atualizados. PRs pequenos (< ~400 linhas de mudança lógica, como orientação).

## Revisão de código
≥ 1 aprovação humana; mudanças em auth, autorização, motores de regras, ratings ou migrações exigem revisor com conhecimento da área. Revisor confere: testes de comportamento e de abuso, ausência de dados sensíveis em logs, documentação sincronizada.

## Verificações obrigatórias (CI)
Lint, tipagem, testes unitários/integração/E2E, `python3 scripts/check_docs.py`, auditoria de dependências, varredura de segredos, migrações up/down. Nenhuma pode ser desativada para aprovar um PR.

## Requisitos para aceitar contribuições
Rastreável a requisito aprovado; testes passando com evidência; documentação atualizada; sem funcionalidades proibidas (doc 01 §6); sem dados pessoais reais; CHANGELOG atualizado em mudanças visíveis.

## Política de dependências
Nova dependência exige justificativa no PR (problema, alternativas, licença, manutenção ativa, tamanho). Versões fixadas em lockfiles versionados. Licenças copyleft (GPL/AGPL) exigem aprovação explícita (ver DT-005). Atualizações mensais em PR dedicado.

## Relatar vulnerabilidades
**Não abra issue pública.** Envie relato privado ao canal de segurança (a definir — P-01; até lá, contato privado com o mantenedor). Inclua passos de reprodução sem dados de terceiros. Confirmação de recebimento em até 5 dias úteis (meta proposta).
