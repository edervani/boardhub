import { expect, test } from "@playwright/test";
import { auditA11y } from "../support/a11y";
import { nav } from "../support/ui";

test("lobby (Online): seções, navegação por teclado e axe", async ({ page }, testInfo) => {
  await page.goto("/");
  await nav(page, "Online").click();
  await expect(page.getByRole("heading", { level: 2, name: "Jogar online" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 3, name: "Criar convite" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 3, name: "Fila de pareamento" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Entrar na fila" })).toBeEnabled(); // conta verificada
  await auditA11y(page, testInfo, "lobby");

  // O teclado alcança os controles do lobby (RF-008): Tab a partir do primeiro campo do convite.
  // (a opção ranqueada fica desabilitada para a velha, então o foco pula para "Você joga")
  await page.getByLabel("Jogo do convite").focus();
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toHaveAttribute("id", "invite-seat");
});

test("ranking: tabela ou estado vazio e axe", async ({ page }, testInfo) => {
  await page.goto("/");
  await nav(page, "Ranking").click();
  await expect(page.getByRole("heading", { level: 2, name: "Ranking" })).toBeVisible();
  await expect(page.getByLabel("Jogo")).toBeVisible();
  await expect(page.getByText(/Ninguém no ranking|jogador\(es\) listado\(s\)/)).toBeVisible();
  await auditA11y(page, testInfo, "ranking");
});

test("perfil: bio com <script> segue como texto (CA-006), salvar e axe", async ({ page }, testInfo) => {
  await page.goto("/");
  await nav(page, "Perfil").click();
  await expect(page.getByRole("heading", { level: 2, name: "Seu perfil" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 3, name: "Estatísticas" })).toBeVisible();
  await expect(page.getByText("Carregando estatísticas…")).toHaveCount(0);
  await auditA11y(page, testInfo, "perfil");

  const bio = "<script>window.__xss = 1</script> oi";
  await page.getByLabel("Sobre você (até 160 caracteres)").fill(bio);
  await page.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText("Alterações salvas.")).toBeVisible();

  await page.reload();
  await nav(page, "Perfil").click();
  await expect(page.getByLabel("Sobre você (até 160 caracteres)")).toHaveValue(bio);
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
  await auditA11y(page, testInfo, "perfil-salvo");
});

test("privacidade: exportação e confirmação de exclusão (sem excluir) e axe", async ({ page }, testInfo) => {
  await page.goto("/");
  await nav(page, "Privacidade").click();
  await expect(page.getByRole("heading", { level: 2, name: "Privacidade" })).toBeVisible();
  await auditA11y(page, testInfo, "privacidade");

  await page.getByRole("button", { name: "Pedir exportação dos meus dados" }).click();
  await expect(page.getByText("Exportação pronta. Baixe o arquivo abaixo.")).toBeVisible();
  await expect(page.getByRole("link", { name: /Baixar arquivo de/ }).first()).toBeVisible();
  await auditA11y(page, testInfo, "privacidade-exportacao");

  await page.getByRole("button", { name: "Excluir minha conta…" }).click();
  await expect(page.getByLabel("Confirme com a sua senha")).toBeVisible();
  await auditA11y(page, testInfo, "privacidade-confirmar-exclusao");
});

test("Academy: trilhas, lições e exercício: axe", async ({ page }, testInfo) => {
  await page.goto("/");
  await nav(page, "Academy").click();
  await expect(page.getByRole("heading", { level: 2, name: "Academy" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Trilhas" })).toBeVisible();
  await auditA11y(page, testInfo, "academy-trilhas");

  await page.getByRole("button", { name: /^Abrir trilha/ }).first().click();
  const lessons = page.getByRole("list", { name: "Lições" });
  await expect(lessons).toBeVisible();
  await auditA11y(page, testInfo, "academy-licoes");

  await lessons.getByRole("button").first().click();
  await expect(page.getByRole("button", { name: "Voltar às lições" })).toBeVisible();
  await auditA11y(page, testInfo, "academy-licao");

  await page.getByRole("button", { name: /^Exercício 1/ }).click();
  await expect(page.getByRole("heading", { level: 3, name: /exercício$/ })).toBeVisible();
  await auditA11y(page, testInfo, "academy-exercicio");
});

test.describe("tema escuro", () => {
  test.use({ colorScheme: "dark" });

  for (const [tela, rotulo] of [["Online", "dark-lobby"], ["Perfil", "dark-perfil"], ["Privacidade", "dark-privacidade"]] as const) {
    test(`${tela}: axe com prefers-color-scheme: dark`, async ({ page }, testInfo) => {
      await page.goto("/");
      await nav(page, tela).click();
      await expect(page.getByRole("heading", { level: 2 }).first()).toBeVisible();
      await auditA11y(page, testInfo, rotulo);
    });
  }

  test("jogos e tabuleiros em tema escuro: axe", async ({ page }, testInfo) => {
    await page.goto("/");
    await expect(page.locator(".badge")).toHaveCount(3);
    await auditA11y(page, testInfo, "dark-jogos");
    await nav(page, "Jogar").click();
    await page.getByLabel("Jogo", { exact: true }).selectOption("chess");
    await page.getByRole("button", { name: "Começar" }).click();
    await expect(page.getByRole("group", { name: "Tabuleiro de xadrez" })).toBeVisible();
    await auditA11y(page, testInfo, "dark-xadrez");
  });
});
