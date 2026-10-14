# BoardHub

Plataforma pública, **recreativa e educacional**, de jogos de tabuleiro — jogo da velha, damas e xadrez — com contas individuais, partidas contra IA e online, ranking, estatísticas e a **BoardHub Academy** (aprendizagem adaptativa).

> Sem apostas, sem dinheiro real, sem vantagens compradas. Ver [visão do produto §6](docs/01-visao-do-produto.md#6-modelo-de-negócio--permitido-e-proibido).

## Estado atual do desenvolvimento

**Fase 0 concluída — especificação aprovada em 2026-10-13.** Próxima: Fase 1 (base técnica).

| Item | Estado |
|------|--------|
| Documentação técnica (`docs/`) | **Aprovada** (v0.2.0) |
| Backend, frontend, jogos, IA, Academy | **Não implementados** (apenas planejados) |
| `docker-compose.yml` | Sobe somente PostgreSQL para a Fase 1 |
| Testes | Apenas verificação automática da documentação (`scripts/check_docs.py`) |

Nenhuma funcionalidade listada abaixo existe ainda.

## Funcionalidades planejadas
- **v1:** cadastro/login, perfil, preferências (tema, animações, estilo de peças), lobby, partidas locais, contra IA (5 níveis) e online (convite e fila), três jogos com validação no servidor, ranking Elo (damas, xadrez), histórico, Academy inicial, exportação e exclusão de conta.
- **Posteriores:** conquistas, desafio diário, notificações ampliadas, amizades, personalização avançada.

Detalhes: [plano de implementação](docs/14-plano-de-implementacao.md).

## Tecnologias (arquitetura de referência — proposta)
React + TypeScript + Vite · Python + FastAPI · REST + WebSocket · PostgreSQL · SQLAlchemy + Alembic · pytest · Vitest · Playwright · Docker Compose · Ollama (opcional) · python-chess + motor UCI.
**Versões ainda não verificadas** (ver [DT-012](docs/16-decisoes-tecnicas.md)).

## Requisitos mínimos (para a Fase 1 em diante)
Git; Docker com Docker Compose v2; Python 3.13; Node.js 24 LTS; PostgreSQL 17 (via Compose). Ver DT-014. Para rodar as verificações da documentação hoje: apenas Python 3.

## Instalação e configuração
```bash
git clone <url-do-repositório> boardhub && cd boardhub
cp .env.example .env      # edite os valores; nunca versione o .env
```

## Execução local
Hoje só existe o banco:
```bash
docker compose up -d db
docker compose ps         # aguarde "healthy"
```
Backend e frontend serão adicionados na Fase 1; este README será atualizado então.

## Testes
```bash
python3 scripts/check_docs.py          # verifica documentação (links, IDs, matriz)
python3 scripts/check_docs.py --write  # regenera a matriz de rastreabilidade
```

## Banco de dados
PostgreSQL via Compose, porta publicada apenas em `127.0.0.1`. Credenciais vêm do `.env`. Modelo de dados: [docs/05](docs/05-modelagem-de-dados.md). Migrações (Alembic) serão criadas na Fase 1.

## Documentação
Comece por [docs/00-indice-e-governanca.md](docs/00-indice-e-governanca.md). Agentes de IA: leiam [AGENTS.md](AGENTS.md). Contribuições: [CONTRIBUTING.md](CONTRIBUTING.md).

## Solução de problemas
- **`db` não fica healthy:** `docker compose logs db`; verifique se `POSTGRES_PASSWORD` está definido no `.env`.
- **Porta 5432 ocupada:** altere `DB_HOST_PORT` no `.env`.
- **`check_docs.py` falha:** a saída lista arquivo e problema (link quebrado, ID duplicado, requisito sem teste); corrija e rode novamente.
