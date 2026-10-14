import type { APIRequestContext } from "@playwright/test";

interface MailListing { messages?: { ID: string; To: { Address: string }[] }[] }

/** Lê, na caixa de testes (Mailpit), o token do link de verificação enviado a `email`. */
export async function verificationToken(mail: APIRequestContext, email: string): Promise<string> {
  for (let i = 0; i < 30; i++) {
    const listing = (await (await mail.get("/api/v1/messages")).json()) as MailListing;
    for (const msg of listing.messages ?? []) {
      if (!msg.To.some((t) => t.Address === email)) continue;
      const full = (await (await mail.get(`/api/v1/message/${msg.ID}`)).json()) as { Text: string };
      const m = /token=([A-Za-z0-9_-]+)/.exec(full.Text);
      if (m?.[1]) return m[1];
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("e-mail de verificação não chegou à caixa de testes");
}
