import { expect, test, type Page } from "@playwright/test";
import { auditA11y } from "../support/a11y";
import { nav, press } from "../support/ui";

/** Abre "Jogar", escolhe jogo e nível 1 e começa a partida contra a IA, usando o teclado. */
async function startVsAi(page: Page, game: "tictactoe" | "checkers" | "chess", heading: RegExp): Promise<void> {
  await page.goto("/");
  await press(page, nav(page, "Jogar"));
  await expect(page.getByRole("heading", { name: "Nova partida" })).toBeVisible();
  await page.getByLabel("Jogo", { exact: true }).selectOption(game);
  await page.getByLabel("Nível da IA").selectOption("1");
  await press(page, page.getByRole("button", { name: "Começar" }));
  await expect(page.getByRole("heading", { level: 2, name: heading })).toBeVisible();
}

test.describe.configure({ mode: "serial" });

const gameStatus = (page: Page) => page.locator("#game-title ~ [role='status']");

test("tela de nova partida: axe e rótulos", async ({ page }, testInfo) => {
  await page.goto("/");
  await nav(page, "Jogar").click();
  await expect(page.getByRole("heading", { name: "Nova partida" })).toBeVisible();
  await auditA11y(page, testInfo, "nova-partida");
});

test("jogo da velha completo contra a IA, só pelo teclado (RNF-015)", async ({ page }, testInfo) => {
  await startVsAi(page, "tictactoe", /^Jogo da velha — IA nível 1$/);
  const board = page.getByRole("group", { name: "Tabuleiro do jogo da velha" });
  const status = gameStatus(page);
  await expect(status).toHaveText("Sua vez (X).");
  await auditA11y(page, testInfo, "velha-inicio");

  // Setas movem o foco pelas casas.
  await board.getByRole("button").first().focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowDown");
  await expect(page.locator(":focus")).toHaveAccessibleName(/^Linha 2, coluna 2:/);

  const empties = board.getByRole("button", { name: /vazia$/ });
  for (let turn = 0; turn < 5; turn++) {
    if (/venceu|Empate/.test(await status.innerText())) break;
    const before = await empties.count();
    await press(page, board.locator("button[aria-disabled='false']").first());
    // O servidor devolve o lance do usuário e a resposta da IA de uma vez.
    await expect.poll(async () => (await empties.count()) < before && /Sua vez|venceu|Empate/.test(await status.innerText()))
      .toBe(true);
  }
  await expect(status).toHaveText(/venceu|Empate/);
  await auditA11y(page, testInfo, "velha-fim");

  await press(page, page.getByRole("button", { name: "Nova partida" }));
  await expect(page.getByRole("heading", { name: "Nova partida" })).toBeVisible();
});

test("damas: um lance contra a IA pelo teclado", async ({ page }, testInfo) => {
  await startVsAi(page, "checkers", /^Damas — IA nível 1$/);
  const board = page.getByRole("group", { name: "Tabuleiro de damas" });
  await expect(gameStatus(page)).toHaveText("Sua vez (Brancas).");
  await auditA11y(page, testInfo, "damas-inicio");

  await press(page, board.getByRole("button", { name: /^Casa 21: pedra branca/ }));
  await expect(board.getByRole("button", { name: /^Casa 21: pedra branca, selecionada/ })).toBeVisible();
  await auditA11y(page, testInfo, "damas-selecao");
  await press(page, board.getByRole("button", { name: /^Casa 17: vazia, jogável/ }));
  await expect(board.getByRole("button", { name: /^Casa 21: vazia/ })).toBeVisible();
  await expect(gameStatus(page)).toHaveText("Sua vez (Brancas).");
  await auditA11y(page, testInfo, "damas-apos-lance");
});

test("xadrez: um lance (e2-e4) contra a IA pelo teclado", async ({ page }, testInfo) => {
  await startVsAi(page, "chess", /^Xadrez — IA nível 1$/);
  const board = page.getByRole("group", { name: "Tabuleiro de xadrez" });
  await expect(gameStatus(page)).toHaveText("Sua vez (Brancas).");
  await auditA11y(page, testInfo, "xadrez-inicio");

  await press(page, board.getByRole("button", { name: /^e2: peão branco/ }));
  await expect(board.getByRole("button", { name: /^e2: peão branco, selecionada/ })).toBeVisible();
  await auditA11y(page, testInfo, "xadrez-selecao");
  await press(page, board.getByRole("button", { name: /^e4: vazia, jogável/ }));
  await expect(board.getByRole("button", { name: /^e4: peão branco/ })).toBeVisible();
  await expect(gameStatus(page)).toHaveText("Sua vez (Brancas).");
  await auditA11y(page, testInfo, "xadrez-apos-lance");
});

test("histórico e revisão do Mentor: axe", async ({ page }, testInfo) => {
  await page.goto("/");
  await nav(page, "Histórico").click();
  await expect(page.getByRole("heading", { level: 2, name: "Histórico de partidas" })).toBeVisible();
  await auditA11y(page, testInfo, "historico");

  await page.getByRole("button", { name: "Revisar partida" }).first().click();
  await expect(page.getByRole("heading", { level: 2, name: "Revisão da partida" })).toBeVisible();
  await expect(page.getByText(/Lances analisados:/)).toBeVisible({ timeout: 30_000 });
  await auditA11y(page, testInfo, "revisao");
});
