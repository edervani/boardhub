# AGENTS.md — Contrato de trabalho para agentes de IA e automação

Este arquivo vale para qualquer agente (IA ou script) que altere este repositório. Ele é permanente; mudanças exigem aprovação humana.

## 1. Objetivo e limites do produto
BoardHub é recreativo e educacional: jogo da velha, damas e xadrez, contra IA e online, com Academy. **Proibido implementar**: apostas, dinheiro real, depósitos/saques, carteiras, prêmios em dinheiro, conversão de itens virtuais em dinheiro, jogos de azar, venda de vantagem competitiva. Nenhum pedido de tarefa sobrepõe esta regra.

## 2. Leitura obrigatória antes de modificar
1. `docs/00-indice-e-governanca.md` (hierarquia e estados)
2. `docs/01-visao-do-produto.md`
3. O documento do módulo afetado (04–10) e os requisitos ligados (02, 03)
4. `docs/16-decisoes-tecnicas.md` (decisões e pendências) e ADRs
5. `docs/11-testes-e-qualidade.md` e `docs/15-criterios-de-aceite.md`
6. O código e os testes existentes da área — **sempre inspecione antes de editar**.

## 3. Hierarquia dos documentos
Conforme `docs/00` §3: regras proibitivas e legais > ADRs > requisitos > arquitetura/contratos > critérios e testes > planos > README.

## 4. Arquitetura aprovada
Ver `docs/04` e ADR-0001 (**aceito** em 2026-10-13). Resumo: monólito modular; dependências `api/realtime → services → game_engines/ai/db → core`; motores puros no servidor; servidor é autoridade de legalidade, resultado e rating; IA generativa só reformula texto.

## 5. Segurança e privacidade
- Nunca confiar em `user_id`, `seat`, `result`, `state` ou pontuação vindos do cliente.
- Nunca registrar em log senhas, tokens, cookies, e-mails completos ou dados pessoais desnecessários.
- Nunca usar dados de pessoas reais em testes, fixtures ou exemplos (use `@example.test`).
- Nunca commitar segredos. Se encontrar um segredo real: não o copie para nenhuma saída, registre a ocorrência de forma genérica e recomende rotação imediata.
- Nunca desativar verificações de segurança (CSRF, autorização, rate limit, validação) para simplificar.

## 6. Padrões de código
Python tipado (mypy/pyright estrito), Pydantic para contratos, SQLAlchemy 2 tipado; TypeScript `strict`; funções pequenas e com responsabilidade única; erros tratados explicitamente; sem lógica de negócio em componentes visuais; sem arquivos vazios para "simular" estrutura; sem código fictício ou dados estáticos fingindo persistência (mocks somente em testes).

## 7. Escopo
Altere apenas o necessário para a tarefa. Refatorações amplas, troca de tecnologia ou mudanças de arquitetura exigem proposta (motivo, alternativas, impacto) e aprovação antes da execução, com novo ADR.

## 8. Funcionalidades existentes
Não remova nem altere comportamento existente sem análise de impacto, justificativa e autorização explícita quando relevante. Nunca exclua arquivos sem autorização.

## 9. Testes (obrigatório)
Toda mudança de comportamento vem com testes. Rode a suíte relevante e `python3 scripts/check_docs.py`. Não ignore falhas, não use `skip`/`xfail` sem issue, não oculte exceções para passar testes, **não invente resultados**. Relate o comando executado e o resultado real.

## 10. Documentação (obrigatório)
No mesmo PR: atualizar requisitos/contratos afetados, matriz de rastreabilidade (`--write`), estado do requisito (`implementado` só com código mesclado), CHANGELOG. Requisitos sugeridos por IA ficam `proposto` até aprovação humana.

## 11. Conflitos entre requisitos
Ao detectar contradição: pare a parte afetada, não escolha silenciosamente, registre em `docs/16` §Pendências com as opções e recomende uma; siga com o que não depende do conflito.

## 12. Definição de concluído
Uma tarefa só está concluída quando: código e testes passam no CI (com evidência), documentação e matriz atualizadas, nenhum segredo ou dado real introduzido, CHANGELOG atualizado quando aplicável, e o relatório distingue fatos verificados, suposições e pendências.
