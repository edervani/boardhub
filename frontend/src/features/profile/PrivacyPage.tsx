import { useEffect, useState, type FormEvent } from "react";
import { api, errorMessage } from "../../services/api";
import type { DataExport, Me } from "../../services/types";

const date = (iso: string) => new Date(iso).toLocaleDateString("pt-BR");

interface Props {
  me: Me;
  /** Exclusão agendada: o servidor já encerrou todas as sessões. */
  onDeletionScheduled: (scheduledFor: string) => void;
  /** Exclusão cancelada: a conta voltou ao normal. */
  onDeletionCancelled: () => void;
}

/** Direitos do titular (RF-029, RF-030): exportar os próprios dados e excluir a conta. */
export function PrivacyPage({ me, onDeletionScheduled, onDeletionCancelled }: Props) {
  const [exports, setExports] = useState<DataExport[]>([]);
  const [exportMsg, setExportMsg] = useState("");
  const [exportError, setExportError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [understood, setUnderstood] = useState(false);
  const [password, setPassword] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = Boolean(me.deletion_scheduled_for);

  useEffect(() => {
    api<DataExport[]>("GET", "/me/export")
      .then(setExports)
      .catch((e: unknown) => setExportError(errorMessage(e)));
  }, []);

  async function requestExport() {
    setExportMsg(""); setExportError(""); setBusy(true);
    try {
      const created = await api<DataExport>("POST", "/me/export");
      setExports((list) => [created, ...list]);
      setExportMsg("Exportação pronta. Baixe o arquivo abaixo.");
    } catch (err) {
      setExportError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function requestDeletion(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setDeleteError(""); setBusy(true);
    try {
      const out = await api<{ scheduled_for: string }>("POST", "/me/delete", { password });
      setPassword("");
      onDeletionScheduled(out.scheduled_for);
    } catch (err) {
      setDeleteError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function cancelDeletion() {
    setDeleteError(""); setBusy(true);
    try {
      await api<void>("POST", "/me/delete/cancel");
      onDeletionCancelled();
    } catch (err) {
      setDeleteError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="privacy-title">
      <h2 id="privacy-title">Privacidade</h2>

      <section aria-labelledby="export-title">
        <h3 id="export-title">Baixar meus dados</h3>
        <p>
          Gere um arquivo JSON com os dados da sua conta: perfil, preferências, partidas e lances e
          progresso da Academy. Ele não contém senha nem dados de outras pessoas. O arquivo fica
          disponível por 7 dias e você pode pedir um novo a cada 24 horas.
        </p>
        <p><button type="button" disabled={busy} onClick={() => void requestExport()}>
          Pedir exportação dos meus dados
        </button></p>
        {exportMsg && <p role="status">{exportMsg}</p>}
        {exportError && <p role="alert">{exportError}</p>}
        {exports.length > 0 && (
          <ul aria-label="Exportações disponíveis">
            {exports.map((x) => (
              <li key={x.id}>
                <a href={`/api/v1/me/export/${x.id}`} download>
                  Baixar arquivo de {date(x.created_at)}
                </a>{" "}
                (disponível até {date(x.expires_at)})
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="delete-title">
        <h3 id="delete-title">Excluir minha conta</h3>
        {pending ? (
          <>
            <p role="status">
              A exclusão da sua conta está agendada para {date(me.deletion_scheduled_for ?? "")}.
              Até lá você pode cancelar. Depois dessa data, seus dados pessoais serão apagados e
              não poderão ser recuperados.
            </p>
            {me.deletion_by_guardian ? (
              <p>A exclusão foi pedida pelo seu responsável; só ele pode cancelá-la.</p>
            ) : (
              <p><button type="button" disabled={busy} onClick={() => void cancelDeletion()}>
                Cancelar exclusão
              </button></p>
            )}
          </>
        ) : (
          <>
            <p>
              Ao excluir a conta, você sai de todos os dispositivos agora e tem 14 dias para
              desistir. Passado esse prazo, apagamos seu perfil, preferências e progresso na
              Academy. As partidas jogadas contra outras pessoas continuam no histórico delas, com
              seu nome substituído por “Conta removida”.
            </p>
            {!confirming ? (
              <p><button type="button" className="secondary" onClick={() => setConfirming(true)}>
                Excluir minha conta…
              </button></p>
            ) : (
              <form onSubmit={(e) => void requestDeletion(e)} aria-labelledby="delete-title">
                <label htmlFor="delete-password">Confirme com a sua senha</label>
                <input id="delete-password" type="password" autoComplete="current-password"
                  required maxLength={128} value={password}
                  onChange={(e) => setPassword(e.target.value)} />
                <label>
                  <input type="checkbox" checked={understood}
                    onChange={(e) => setUnderstood(e.target.checked)} />{" "}
                  Entendo que, depois de 14 dias, a exclusão é definitiva.
                </label>
                {deleteError && <p role="alert">{deleteError}</p>}
                <p>
                  <button type="submit" disabled={!understood || !password || busy}>
                    Excluir minha conta
                  </button>{" "}
                  <button type="button" className="secondary"
                    onClick={() => { setConfirming(false); setUnderstood(false); setPassword(""); setDeleteError(""); }}>
                    Voltar
                  </button>
                </p>
              </form>
            )}
          </>
        )}
        {pending && deleteError && <p role="alert">{deleteError}</p>}
      </section>
    </section>
  );
}
