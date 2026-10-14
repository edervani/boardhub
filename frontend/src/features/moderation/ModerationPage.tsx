import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../../services/api";
import type { ReportQueue, ReportQueueItem } from "../../services/types";
import { REASON_LABEL } from "../social/ReportButton";

type Action = "warn" | "suspend" | "archive";
const ACTION_LABEL: Record<Action, string> = { warn: "Advertir", suspend: "Suspender", archive: "Arquivar" };

/** Fila de moderação (RF-031): só moderator/admin. O denunciante nunca é mostrado. */
export function ModerationPage() {
  const [queue, setQueue] = useState<ReportQueue | null>(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try { setQueue(await api<ReportQueue>("GET", "/admin/reports?status=open")); }
    catch (e) { setError(errorMessage(e)); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function resolve(item: ReportQueueItem, action: Action, hide: boolean) {
    setError(""); setMsg("");
    try {
      await api("POST", `/admin/reports/${item.id}/resolve`, { action, hide_content: hide });
      setMsg(`${ACTION_LABEL[action]}: denúncia resolvida.`);
      await load();
    } catch (e) { setError(errorMessage(e)); }
  }

  return (
    <section aria-labelledby="mod-title">
      <h2 id="mod-title">Moderação</h2>
      {error && <p role="alert">{error}</p>}
      {msg && <p role="status">{msg}</p>}
      {queue === null && !error && <p role="status">Carregando…</p>}
      {queue !== null && queue.items.length === 0 && <p>Nenhuma denúncia aberta.</p>}
      <ul>
        {queue?.items.map((i) => (
          <li key={i.id} className="card">
            <h3>{i.target_display_name ?? "Conta removida"}</h3>
            <p>
              Motivo: {REASON_LABEL[i.reason]} ({i.target_type === "match" ? "partida" : "perfil"}).
              Denúncias abertas contra esta conta: {i.open_reports_on_target}. Situação da conta: {i.target_status}.
            </p>
            {i.target_bio && <p>Bio: <q>{i.target_bio}</q></p>}
            {i.note && <p>Detalhes: <q>{i.note}</q></p>}
            <Actions item={i} onResolve={resolve} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function Actions({ item, onResolve }: {
  item: ReportQueueItem; onResolve: (i: ReportQueueItem, a: Action, hide: boolean) => Promise<void>;
}) {
  const [hide, setHide] = useState(false);
  const who = item.target_display_name ?? "conta";
  return (
    <>
      <label>
        <input type="checkbox" checked={hide} onChange={(e) => setHide(e.target.checked)} />{" "}
        Ocultar conteúdo (apaga a bio e, se o motivo for o apelido, troca o apelido)
      </label>
      <div>
        {(Object.keys(ACTION_LABEL) as Action[]).map((a) => (
          <button key={a} type="button" className={a === "archive" ? "secondary" : undefined}
            onClick={() => void onResolve(item, a, hide)}>
            {ACTION_LABEL[a]} {who}
          </button>
        ))}
      </div>
    </>
  );
}
