import { randomBytes } from "node:crypto";
import { expect, test } from "@playwright/test";
import { PASSWORD } from "../support/env";
import { auditA11y } from "../support/a11y";
import { account, nav } from "../support/ui";

// Estas jornadas começam sem sessão (visitante).
test.use({ storageState: { cookies: [], origins: [] } });

test("lista de jogos do visitante: selos de classificação em texto (CA-033) e axe", async ({ page }, testInfo) => {
  await page.goto("/");
  const items = page.getByRole("listitem").filter({ hasText: /Jogo da velha|Damas|Xadrez/ });
  await expect(items).toHaveCount(3);
  const badges = page.locator(".badge");
  await expect(badges).toHaveCount(3);
  for (const text of await badges.allInnerTexts()) expect(text.trim().length).toBeGreaterThan(0);
  await auditA11y(page, testInfo, "lista-de-jogos-visitante");
});

test("cadastro: formulário acessível, menor de 12 anos pede responsável e conta é criada", async ({ page }, testInfo) => {
  await page.goto("/");
  await nav(page, "Criar conta").click();
  const form = page.getByRole("form", { name: "Criar conta" });
  await expect(form).toBeVisible();
  await auditA11y(page, testInfo, "cadastro");

  await form.getByLabel("Faixa etária").selectOption("under_12");
  await expect(form.getByLabel("E-mail do responsável")).toBeVisible();
  await auditA11y(page, testInfo, "cadastro-menor-de-12");
  await form.getByLabel("Faixa etária").selectOption("18_plus");

  const suffix = randomBytes(4).toString("hex");
  await form.getByLabel("E-mail", { exact: true }).fill(`e2e-ui-${suffix}@example.test`);
  await form.getByLabel("Nome de exibição").fill(`e2e_ui_${suffix}`);
  await form.getByLabel("Senha").fill(PASSWORD);
  await form.getByLabel("Senha").press("Enter"); // envio pelo teclado
  const done = page.getByRole("status");
  await expect(done).toBeVisible();
  await expect(done).not.toHaveText("");
  await auditA11y(page, testInfo, "cadastro-concluido");
});

test("login: erro acessível, entrada por teclado e saída", async ({ page }, testInfo) => {
  const acc = account();
  await page.goto("/");
  await nav(page, "Entrar").click();
  const form = page.getByRole("form", { name: "Entrar" });
  await expect(form).toBeVisible();
  await auditA11y(page, testInfo, "login");

  await form.getByLabel("E-mail").fill(acc.email);
  await form.getByLabel("Senha").fill("senha-incorreta-123");
  await form.getByLabel("Senha").press("Enter");
  await expect(page.getByRole("alert")).toBeVisible();
  await auditA11y(page, testInfo, "login-com-erro");

  await form.getByLabel("Senha").fill(acc.password);
  await form.getByLabel("Senha").press("Enter");
  await expect(nav(page, "Sair")).toBeVisible();
  await expect(page.getByRole("heading", { name: "BoardHub", level: 1 })).toBeVisible();
  await auditA11y(page, testInfo, "lista-de-jogos-autenticado");

  await nav(page, "Sair").click();
  await expect(nav(page, "Entrar")).toBeVisible();
});
