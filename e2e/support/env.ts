import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:8080";
export const MAILPIT_URL = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";
export const TERMS_VERSION = "2026-10-13";
/** Senha sintética só para contas @example.test deste ambiente de teste. */
export const PASSWORD = "cavalo-bispo-torre-42";

const here = dirname(fileURLToPath(import.meta.url));
export const AUTH_DIR = join(here, "..", ".auth");
export const AUTH_STATE = join(AUTH_DIR, "state.json");
export const ACCOUNT_FILE = join(AUTH_DIR, "account.json");
