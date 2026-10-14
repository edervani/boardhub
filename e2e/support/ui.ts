import { readFileSync } from "node:fs";
import type { Locator, Page } from "@playwright/test";
import { ACCOUNT_FILE } from "./env";

export interface Account { email: string; password: string; displayName: string }

export const account = (): Account => JSON.parse(readFileSync(ACCOUNT_FILE, "utf8")) as Account;

/** Botão da navegação principal. */
export const nav = (page: Page, name: string): Locator =>
  page.getByRole("navigation", { name: "Principal" }).getByRole("button", { name, exact: true });

/** Ativa um controle só com o teclado: foco + Enter. */
export async function press(page: Page, target: Locator): Promise<void> {
  await target.focus();
  await page.keyboard.press("Enter");
}
