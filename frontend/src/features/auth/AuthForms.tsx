import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../../services/api";
import type { AgeBand, Me } from "../../services/types";

const TERMS_VERSION = "2026-10-13";

export function LoginForm({ onLogin }: { onLogin: (me: Me) => void }) {
  const [error, setError] = useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      onLogin(await api<Me>("POST", "/auth/login", {
        email: String(f.get("email")), password: String(f.get("password")),
      }));
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  return (
    <form onSubmit={submit} aria-labelledby="login-title">
      <h2 id="login-title">Entrar</h2>
      <label htmlFor="email">E-mail</label>
      <input id="email" name="email" type="email" autoComplete="email" required />
      <label htmlFor="password">Senha</label>
      <input id="password" name="password" type="password" autoComplete="current-password" required />
      {error && <p role="alert">{error}</p>}
      <p><button type="submit">Entrar</button></p>
    </form>
  );
}

export function RegisterForm() {
  const [band, setBand] = useState<AgeBand>("18_plus");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const guardian = String(f.get("guardian_email") ?? "");
    try {
      const r = await api<{ status: string }>("POST", "/auth/register", {
        email: String(f.get("email")),
        password: String(f.get("password")),
        display_name: String(f.get("display_name")),
        age_band: band,
        accept_terms_version: TERMS_VERSION,
        guardian_email: guardian || null,
      });
      setDone(r.status);
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  if (done) return <p role="status">{done}</p>;
  return (
    <form onSubmit={submit} aria-labelledby="register-title">
      <h2 id="register-title">Criar conta</h2>
      <label htmlFor="r-email">E-mail</label>
      <input id="r-email" name="email" type="email" autoComplete="email" required />
      <label htmlFor="r-name">Nome de exibição</label>
      <input id="r-name" name="display_name" minLength={3} maxLength={24} required />
      <label htmlFor="r-pass">Senha</label>
      <input id="r-pass" name="password" type="password" autoComplete="new-password" required />
      <label htmlFor="r-age">Faixa etária</label>
      <select id="r-age" value={band} onChange={(e) => setBand(e.target.value as AgeBand)}>
        <option value="under_12">Menos de 12 anos</option>
        <option value="12_15">12 a 15 anos</option>
        <option value="16_17">16 a 17 anos</option>
        <option value="18_plus">18 anos ou mais</option>
      </select>
      {band === "under_12" && (
        <>
          <label htmlFor="r-guardian">E-mail do responsável</label>
          <input id="r-guardian" name="guardian_email" type="email" required />
          <p>Contas de menores de 12 anos precisam da confirmação de um responsável.</p>
        </>
      )}
      <p>Ao criar a conta você aceita os termos (versão {TERMS_VERSION}).</p>
      {error && <p role="alert">{error}</p>}
      <p><button type="submit">Criar conta</button></p>
    </form>
  );
}
