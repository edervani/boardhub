# 12 — Infraestrutura e Deploy

> Versão 0.1.0 · 2026-10-13 · Estado: **proposto** · Nada foi implantado. O `docker-compose.yml` atual sobe apenas o PostgreSQL (único serviço cujo código já existe: nenhum).

## 1. Ambientes

| Ambiente | Finalidade | Dados | Acesso |
|----------|-----------|-------|--------|
| Local | Desenvolvimento | Sintéticos (script de seed) | Desenvolvedor |
| CI | Testes automatizados | Sintéticos efêmeros | Pipeline |
| Homologação | Validação pré-produção | Sintéticos; **nunca cópia de produção** | Equipe, protegido por autenticação |
| Produção | Usuários reais | Reais | Operação restrita |

## 2. Contêineres
- `backend`: imagem Python slim multi-stage, usuário não root, sistema de arquivos somente leitura exceto `/tmp`, `uvicorn` com workers conforme CPU, healthcheck em `/health/live`.
- `frontend`: build estático do Vite servido pelo proxy (sem servidor Node em produção).
- `db`: PostgreSQL oficial, volume persistente, **sem porta publicada em produção**; em desenvolvimento publicada só em `127.0.0.1`.
- `ollama` (perfil opcional `ai`): rede interna, sem porta pública.
- `proxy`: Caddy ou Nginx com TLS (Let's Encrypt) — decisão P-13.

## 3. Variáveis de ambiente
Lista completa em [`.env.example`](../.env.example). Produção: segredos injetados pelo gerenciador do provedor ou arquivos de segredos do Docker, nunca no repositório ou imagem.

## 4. Banco e migrações
- Migrações aplicadas por etapa dedicada do deploy (`alembic upgrade head`) **antes** de trocar a versão da aplicação.
- Migrações compatíveis com a versão anterior (padrão expandir → migrar → contrair) para permitir rollback da aplicação.
- Usuário do banco da aplicação sem privilégio de superusuário; usuário separado para migrações.

## 5. TLS e proxy reverso
HTTPS obrigatório, HTTP só redireciona; HSTS; WebSocket com `Upgrade` encaminhado e timeout ≥ 75 s; `X-Forwarded-For` confiado apenas do proxy; limite de corpo 1 MB.

## 6. Armazenamento
Exportações de dados (RF-029) em volume/armazenamento de objetos privado, nomes aleatórios, apagadas em 7 dias. Sem uploads de usuário na v1.

## 7. Segredos
Geração com entropia adequada (`SECRET_KEY` ≥ 32 bytes aleatórios); rotação: `SECRET_KEY` (invalida tokens CSRF — planejar), senha do banco, credenciais SMTP; registro de rotação no runbook.

## 8. Build e CI/CD (proposta — GitHub Actions ou equivalente, P-14)
Em todo PR: lint + tipagem → testes unitários → integração com PostgreSQL em serviço → E2E (Playwright) → `scripts/check_docs.py` → auditoria de dependências → varredura de segredos → build de imagens. Merge na `main` publica imagens com tag do commit; deploy em homologação automático; produção manual com aprovação.

## 9. Rollback
Imagens imutáveis por tag; rollback = reimplantar a tag anterior. Migrações destrutivas só na fase "contrair", depois de uma versão estável sem uso das colunas antigas. Backup obrigatório antes de migração de produção.

## 10. Backup e restauração
`pg_dump` diário criptografado, cópia fora do servidor, retenção 7 diários + 4 semanais + 3 mensais (proposta). Evolução: arquivamento contínuo de WAL para RPO ≤ 15 min. Teste de restauração trimestral documentado (RNF-008).

## 11. Dimensionamento inicial (estimativa a validar)
1 VPS com 2 vCPU e 4 GB RAM para backend + banco em fase beta; motor de xadrez em nível alto consome CPU — limitar análises simultâneas. Com Ollama, o modelo exige recursos adicionais significativos (GPU ou RAM conforme o modelo escolhido — P-09). Revisar após teste de carga.

## 12. Requisitos para publicação pública (bloqueantes)
1. Todos os RF prioridade M em `validado`.
2. RNF de segurança (010–013) e acessibilidade (014–015) validados.
3. Política de privacidade e termos aprovados juridicamente (P-04), decisão sobre menores (P-03).
4. Backup testado com restauração.
5. Monitoramento e alertas ativos (doc 13).
6. Revisão de segurança (ZAP baseline + revisão manual de autorização).
7. Nenhum segredo no repositório (varredura limpa).
