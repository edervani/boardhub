import { randomBytes } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { request } from "@playwright/test";
import { ACCOUNT_FILE, AUTH_DIR, AUTH_STATE, BASE_URL, MAILPIT_URL, PASSWORD, TERMS_VERSION } from "./env";
import { verificationToken } from "./mail";

async function waitReady(): Promise<void> {
  const api = await request.newContext({ baseURL: BASE_URL });
  for (let i = 0; i < 60; i++) {
    try {
      if ((await api.get("/api/v1/health/ready")).ok()) { await api.dispose(); return; }
    } catch { /* ainda subindo */ }
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error("o site não ficou pronto em 120 s");
}

/**
 * Cria UMA conta sintética verificada (cadastro + e-mail + login pela API) e guarda a sessão.
 * O servidor limita cadastros por IP (5/h), então os testes compartilham esta conta.
 */
export default async function globalSetup(): Promise<void> {
  await waitReady();
  const suffix = randomBytes(4).toString("hex");
  const email = `e2e-${suffix}@example.test`;
  const displayName = `e2e_${suffix}`;
  const api = await request.newContext({ baseURL: BASE_URL });
  const mail = await request.newContext({ baseURL: MAILPIT_URL });

  const reg = await api.post("/api/v1/auth/register", {
    data: { email, password: PASSWORD, display_name: displayName, age_band: "18_plus", accept_terms_version: TERMS_VERSION },
  });
  if (reg.status() !== 201) throw new Error(`cadastro falhou: HTTP ${reg.status()}`);
  const verify = await api.post("/api/v1/auth/verify-email", { data: { token: await verificationToken(mail, email) } });
  if (verify.status() !== 204) throw new Error(`verificação de e-mail falhou: HTTP ${verify.status()}`);
  const login = await api.post("/api/v1/auth/login", { data: { email, password: PASSWORD } });
  if (login.status() !== 200) throw new Error(`login falhou: HTTP ${login.status()}`);

  mkdirSync(AUTH_DIR, { recursive: true });
  await api.storageState({ path: AUTH_STATE });
  writeFileSync(ACCOUNT_FILE, JSON.stringify({ email, password: PASSWORD, displayName }));
  await api.dispose();
  await mail.dispose();
}
