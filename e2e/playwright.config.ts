import { defineConfig, devices } from "@playwright/test";
import { AUTH_STATE, BASE_URL } from "./support/env";

// Sem retentativas de propósito: um teste instável deve aparecer, não ser escondido (AGENTS.md §9).
export default defineConfig({
  testDir: "./tests",
  globalSetup: "./support/global-setup.ts",
  fullyParallel: false,
  workers: 1, // uma conta de teste compartilhada e limites de taxa por IP no servidor
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: BASE_URL,
    locale: "pt-BR",
    storageState: AUTH_STATE,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  // RNF-016 pede Chromium, Firefox e WebKit; o CI instala e roda só o Chromium (docs/11 §E2E).
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
