import { useEffect, useState, type FormEvent } from "react";
import { api, errorMessage } from "../../services/api";
import type { Child } from "../../services/types";
import { ChildPanel } from "./ChildPanel";

/** O convite chega por e-mail como link com `?token=`; aceita o link inteiro ou só o código. */
export function extractToken(text: string): string {
  const m = /token=([A-Za-z0-9_-]+)/.exec(text);
  return (m ? m[1] : text.trim()) ?? "";
}

/** Painel do responsável (RF-034): contas vinculadas, limite diário, tempo usado e dados do menor. */
export function GuardianPage() {
  const [children, setChildren] = useState<Child[] | null>(null);
  const [error, setError] = useState("");
  const [invite, setInvite] = useState("");
  const [inviteMsg, setInviteMsg] = useState("");
  const [inviteError, setInviteError] = useState("");

  useEffect(() => {
    api<Child[]>("GET", "/guardian/children")
      .then(setChildren)
      .catch((e: unknown) => setError(errorMessage(e)));
  }, []);

  async function confirmInvite(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setInviteMsg(""); setInviteError("");
    try {
      const linked = await api<Child>("POST", "/guardian/links/confirm", { token: extractToken(invite) });
      setChildren((list) => [...(list ?? []).filter((c) => c.id !== linked.id), linked]);
      setInvite("");
      setInviteMsg(`${linked.display_name} agora está vinculado à sua conta.`);
    } catch (err) {
      setInviteError(errorMessage(err));
    }
  }

  function replace(updated: Child) {
    setChildren((list) => (list ?? []).map((c) => (c.id === updated.id ? updated : c)));
  }

  return (
    <section aria-labelledby="guardian-title">
      <h2 id="guardian-title">Painel do responsável</h2>
      {error && <p role="alert">{error}</p>}
      {children === null && !error && <p role="status">Carregando…</p>}
      {children !== null && children.length === 0 && (
        <p>
          Nenhuma conta vinculada. Quando um menor informa o seu e-mail no cadastro, você recebe um
          convite; cole o link ou o código abaixo para confirmar o vínculo.
        </p>
      )}
      {children?.map((c) => <ChildPanel key={c.id} child={c} onChange={replace} />)}

      <form onSubmit={(e) => void confirmInvite(e)} aria-labelledby="invite-title">
        <h3 id="invite-title">Confirmar um convite</h3>
        <label htmlFor="invite-token">Link ou código do convite recebido por e-mail</label>
        <input id="invite-token" required minLength={10} maxLength={400} value={invite}
          onChange={(e) => setInvite(e.target.value)} />
        {inviteError && <p role="alert">{inviteError}</p>}
        {inviteMsg && <p role="status">{inviteMsg}</p>}
        <p><button type="submit">Confirmar vínculo</button></p>
      </form>
    </section>
  );
}
