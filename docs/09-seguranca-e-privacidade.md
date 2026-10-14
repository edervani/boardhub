# 09 — Segurança e Privacidade

> Versão 0.2.0 · 2026-10-13 · Estado: **aprovado** (2026-10-13) · **Este documento não constitui parecer jurídico nem certifica conformidade com a LGPD.**

## 1. Ativos
Credenciais e sessões; dados pessoais (e-mail, nome de exibição); integridade de partidas e ratings; conteúdo da Academy; segredos de infraestrutura; disponibilidade do serviço.

## 2. Modelo de ameaças (STRIDE resumido)

| Ameaça | Exemplo | Controles |
|--------|---------|-----------|
| Spoofing | Força bruta de login, sequestro de sessão | SEC-01, SEC-04, SEC-08 |
| Tampering | Enviar resultado/estado falso, jogar no turno do outro | SEC-05, validação no servidor (doc 07 §6) |
| Repudiation | Moderador nega ação | SEC-11 auditoria |
| Information disclosure | Enumeração de e-mails, IDOR em partidas, logs com dados | SEC-02, SEC-05, SEC-12 |
| DoS | Inundação de WS, IA cara | SEC-06, SEC-08, limites de tempo da IA |
| Elevation of privilege | Usuário acessa `/admin` | SEC-05, papéis no servidor |
| Abuso de jogo | Uso de motor externo em ranqueadas, manipulação de rating entre contas | SEC-13 |

Limites de confiança: [doc 04 §13](04-arquitetura-tecnica.md#13-limites-de-confiança).

## 3. Controles

- **SEC-01 Senhas:** Argon2id (biblioteca `argon2-cffi` proposta), parâmetros ≥ recomendação OWASP vigente na implementação; mínimo 12 caracteres, máximo 128; checagem contra lista local de senhas comuns (sem enviar senha a terceiros); rehash automático se parâmetros mudarem.
- **SEC-02 Antienumeração:** respostas idênticas em cadastro/recuperação; perfil privado e inexistente retornam o mesmo 404.
- **SEC-03 Tokens de e-mail:** 256 bits aleatórios (`secrets`), armazenados como SHA-256, uso único, expiração curta.
- **SEC-04 Sessões:** identificador opaco de 256 bits; cookie `HttpOnly; Secure; SameSite=Lax; Path=/`; hash no banco; rotação no login e na troca de senha; expiração por inatividade e absoluta; revogação imediata.
- **SEC-05 Autorização por recurso:** cada caso de uso verifica posse/participação; testes de IDOR para todo endpoint com `{id}`. Papéis checados no servidor; a UI esconder botões não é controle.
- **SEC-06 WebSocket:** autenticação no handshake, verificação de `Origin`, limite de tamanho e taxa de mensagens, revalidação de participação por mensagem, fechamento de conexões de sessões revogadas.
- **SEC-07 CSRF:** `SameSite=Lax` + token double-submit em métodos que alteram estado; CORS restrito à origem do frontend, `allow_credentials` só para ela; nenhum `*`.
- **SEC-08 Rate limiting:** por IP e por conta (doc 06 §1); atraso progressivo em login; implementação em memória na v1, compartilhada (Redis) se houver várias instâncias.
- **SEC-09 XSS:** React escapa por padrão; proibido `dangerouslySetInnerHTML` sem sanitização aprovada; CSP sem `unsafe-inline` para scripts; textos de usuário e de LLM sempre como texto.
- **SEC-10 Injeção:** SQL apenas via SQLAlchemy com parâmetros; sem concatenação. **SSRF:** a única saída HTTP configurável é Ollama, com URL fixa em configuração (nunca vinda do usuário).
- **SEC-11 Auditoria:** ações administrativas, troca de senha, exclusão/exportação de conta gravadas em `audit_log` imutável.
- **SEC-12 Logs seguros:** proibido registrar senha, token, cookie, cabeçalho `Authorization`, corpo de requisições de auth, e-mail completo (mascarar: `a***@d***.com`), conteúdo de exportações. Filtro central no logger + teste automatizado (RNF-013). Retenção 30 dias; acesso restrito à operação.
- **SEC-13 Antitrapaça e antiabuso:** sem ajuda do Mentor em partidas ranqueadas em andamento; detecção heurística posterior (precisão acima do esperado sustentada — fase 7, apenas sinaliza para revisão humana, nunca pune automaticamente); limite de partidas ranqueadas repetidas contra o mesmo oponente; anulação de partidas abortadas cedo; CAPTCHA acessível no cadastro se houver automação maliciosa (decisão adiada, P-10).
- **SEC-14 Segredos:** apenas em variáveis de ambiente/gerenciador de segredos; `.env` real no `.gitignore`; varredura de segredos (ex.: gitleaks) no CI; rotação documentada no doc 12.
- **SEC-15 Dependências:** versões fixadas em lock; `pip-audit`/`npm audit` no CI; atualização mensal; novas dependências exigem justificativa (CONTRIBUTING).
- **SEC-16 Cabeçalhos:** HSTS, CSP, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `frame-ancestors 'none'`, `Permissions-Policy` restritiva.
- **SEC-17 Backups:** criptografados, fora do servidor principal, testados (doc 12).

## 4. Validação de entradas
Esquemas Pydantic estritos; tamanhos máximos; enums fechados; normalização Unicode (NFKC) e filtro de caracteres de controle em nomes; lances validados pelo motor.

## 5. Resposta a incidentes
1. Detecção (alerta/relato) → 2. Contenção (revogar sessões, rotacionar segredos, desabilitar recurso) → 3. Avaliação de impacto em dados pessoais → 4. Comunicação: se houver risco ou dano relevante aos titulares, comunicação à ANPD e aos titulares conforme a LGPD e regulamentação da ANPD vigente (**prazos e critérios a confirmar com o jurídico — P-04**) → 5. Correção → 6. Pós-incidente documentado. Runbook no doc 13.

## 6. Direitos dos titulares
Acesso/portabilidade (RF-029), correção (RF-006), eliminação (RF-030), informação sobre compartilhamento (política de privacidade), revogação de consentimento quando a base for consentimento. Canal de contato do encarregado a definir (P-04).

## 7. Minimização e privacidade por padrão
- Coleta só e-mail, nome de exibição e senha. Sem nome real, telefone, data de nascimento, localização precisa.
- Sem rastreadores de terceiros/analytics externos na v1.
- IP não armazenado em banco; em logs, retenção curta.
- Nenhum dado pessoal enviado ao Ollama ou a qualquer serviço externo além do provedor de e-mail (operador — exige contrato).

## 8. LGPD — análise de aplicabilidade (preliminar)
- O BoardHub trata dados pessoais de pessoas no Brasil ⇒ LGPD aplicável.
- **Bases legais propostas (a validar):** execução de contrato (conta, partidas, ranking); legítimo interesse (segurança, prevenção de fraude, logs) com teste de balanceamento documentado; consentimento para comunicações opcionais.
- Obrigações que **dependem de validação jurídica e organizacional** (não resolvidas por código): nomeação do encarregado; política de privacidade e termos; registro das operações de tratamento; contratos com operadores (hospedagem, e-mail); avaliação sobre relatório de impacto; procedimento de comunicação de incidentes.

## 9. Exclusão e exportação
Ver doc 05 §7, RF-029/RF-030 e DT-019. A exportação nunca contém hash de senha, tokens, hashes de sessão nem nome, e-mail ou id de outras pessoas (testado). Exclusão e exportação gravam `audit_log` sem dados pessoais; o registro final `account_deleted` não tem autor.

## 10. Crianças e adolescentes

**Decisão (DT-015, 2026-10-13):** a plataforma aceita usuários de todas as idades, com classificação indicativa por jogo. A idade **nunca** define dificuldade, nível ou matchmaking (doc 01 §2).

Normas aplicáveis: art. 14 da LGPD e o ECA Digital (Lei 15.211/2025), em vigor desde 2026-03-17. Os pontos abaixo resumem a leitura técnica e **não substituem parecer jurídico** (P-04).

| Obrigação (fonte) | Como o BoardHub atende |
|---|---|
| Configuração padrão mais protetiva (ECA Digital, art. 7º) | Conta de menor nasce com perfil privado, fora do ranking público, sem fila aberta com desconhecidos, sem notificações por e-mail além das transacionais |
| Classificação indicativa ostensiva no acesso (art. 8º) | RF-033: selo de classificação em cada jogo, no lobby e antes de iniciar partida. Velha, damas e xadrez sem conteúdo impróprio — proposta "Livre", a validar contra o guia de classificação indicativa vigente |
| Verificação de idade confiável para conteúdo impróprio (art. 9º) | Não há conteúdo impróprio nos jogos. Se algum dia houver, autodeclaração não basta e a verificação precisa ser redesenhada |
| Proibição de caixas de recompensa (art. 20) | Já proibidas para todos (doc 01 §6) |
| Supervisão parental (arts. 17 e 18) | RF-034: conta do responsável vinculada, limite de tempo diário, liberação de partidas online com desconhecidos |
| Sem perfilamento para publicidade (art. 22) | Não há publicidade nem perfilamento |
| Riscos de contato com adultos (art. 6º) | Sem chat livre; convites só por código ou entre amigos aprovados pelo responsável |
| Consentimento parental para menores de 12 anos (LGPD, art. 14) | Cadastro de menor de 12 só concluído após confirmação do responsável por e-mail; mecanismo final depende de P-04 |

Faixa etária coletada: autodeclarada em faixas (`<12`, `12–15`, `16–17`, `18+`), sem data de nascimento. Pontos a confirmar com o jurídico: se a lei exige vínculo obrigatório de contas até determinada idade, qual método de confirmação parental é aceitável e se a autodeclaração basta para aplicar as configurações protetivas.
