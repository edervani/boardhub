import { useEffect, useState, type FormEvent } from "react";
import { api, errorMessage } from "../../services/api";
import type { Child, DataExport } from "../../services/types";

const BAND: Record<string, string> = { under_12: "menor de 12 anos", "12_15": "12 a 15 anos", "16_17": "16 e 17 anos" };
const date = (iso: string) => new Date(iso).toLocaleDateString("pt-BR");
const minutes = (seconds: number) => Math.floor(seconds / 60);

export const LIMIT_HELP = "Informe de 15 a 600 minutos ou deixe em branco para não limitar.";

interface Props {
  child: Child;
  /** O servidor devolveu o estado oficial do menor (após salvar ou pedir exclusão). */
  onChange: (child: Child) => void;
}

/** Configurações, tempo de hoje e direitos do titular de um menor vinculado (RF-034, RF-029/030). */
export function ChildPanel({ child, onChange }: Props) {
  const s = child.settings;
  const [limit, setLimit] = useState(s.daily_minutes_limit === null ? "" : String(s.daily_minutes_limit));
  const [open, setOpen] = useState(s.allow_open_matchmaking);
  const [isPublic, setIsPublic] = useState(s.profile_public);
  const [ranking, setRanking] = useState(s.show_in_ranking);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [exports, setExports] = useState<DataExport[]>([]);
  const [exportMsg, setExportMsg] = useState("");
  const [exportError, setExportError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [understood, setUnderstood] = useState(false);
  const [password, setPassword] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [busy, setBusy] = useState(false);
  const base = `/guardian/children/${child.id}`;
  const u = child.usage_today;
  const exhausted = u.limit_seconds !== null && u.used_seconds >= u.limit_seconds;
  const pendingDeletion = Boolean(child.deletion_scheduled_for);

  useEffect(() => {
    api<DataExport[]>("GET", `${base}/export`)
      .then(setExports)
      .catch((e: unknown) => setExportError(errorMessage(e)));
  }, [base]);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setMsg(""); setError("");
    const trimmed = limit.trim();
    const value = trimmed === "" ? null : Number(trimmed);
    if (value !== null && (!Number.isInteger(value) || value < 15 || value > 600)) {
      setError(LIMIT_HELP);
      return;
    }
    setBusy(true);
    try {
      const saved = await api<Child>("PUT", `${base}/settings`, {
        daily_minutes_limit: value, allow_open_matchmaking: open,
        profile_public: isPublic, show_in_ranking: isPublic && ranking,
      });
      onChange(saved);
      setMsg("Configurações salvas.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function requestExport() {
    setExportMsg(""); setExportError(""); setBusy(true);
    try {
      const created = await api<DataExport>("POST", `${base}/export`);
      setExports((list) => [created, ...list]);
      setExportMsg("Exportação pronta. Baixe o arquivo abaixo.");
    } catch (err) {
      setExportError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function reload() {
    onChange(await api<Child>("GET", base));
  }

  async function requestDeletion(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setDeleteError(""); setBusy(true);
    try {
      await api<{ scheduled_for: string }>("POST", `${base}/delete`, { password });
      setPassword(""); setConfirming(false); setUnderstood(false);
      await reload();
    } catch (err) {
      setDeleteError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function cancelDeletion() {
    setDeleteError(""); setBusy(true);
    try {
      await api<void>("POST", `${base}/delete/cancel`);
      await reload();
    } catch (err) {
      setDeleteError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card" aria-labelledby={`child-${child.id}`}>
      <h3 id={`child-${child.id}`}>{child.display_name}</h3>
      <p>Conta supervisionada ({BAND[child.age_band] ?? child.age_band}).</p>

      <section aria-labelledby={`usage-${child.id}`}>
        <h4 id={`usage-${child.id}`}>Tempo de jogo hoje</h4>
        <p role="status">
          {u.limit_seconds === null
            ? `Hoje: ${minutes(u.used_seconds)} min jogados. Sem limite diário definido.`
            : `Hoje: ${minutes(u.used_seconds)} min de ${minutes(u.limit_seconds)} min.`}
        </p>
        {u.limit_seconds !== null && (
          <progress max={u.limit_seconds} value={Math.min(u.used_seconds, u.limit_seconds)}
            aria-label={`Tempo usado hoje por ${child.display_name}`} />
        )}
        {exhausted && (
          <p>
            O limite de hoje foi atingido: novas partidas ficam bloqueadas até amanhã. A partida em
            andamento pode terminar.
          </p>
        )}
        <p>O dia conta pelo horário de Brasília e o tempo zera à meia-noite.</p>
      </section>

      <form onSubmit={(e) => void save(e)} aria-labelledby={`settings-${child.id}`} noValidate>
        <h4 id={`settings-${child.id}`}>Configurações de {child.display_name}</h4>
        <label htmlFor={`limit-${child.id}`}>Limite diário de tempo (minutos)</label>
        <input id={`limit-${child.id}`} type="number" inputMode="numeric" min={15} max={600} step={1}
          value={limit} aria-describedby={`limit-help-${child.id}`}
          onChange={(e) => setLimit(e.target.value)} />
        <p id={`limit-help-${child.id}`}>{LIMIT_HELP}</p>
        <label>
          <input type="checkbox" checked={open} onChange={(e) => setOpen(e.target.checked)} />{" "}
          Liberar partidas online com desconhecidos (fila aberta)
        </label>
        <label>
          <input type="checkbox" checked={isPublic}
            onChange={(e) => { setIsPublic(e.target.checked); if (!e.target.checked) setRanking(false); }} />{" "}
          Perfil público
        </label>
        <label>
          <input type="checkbox" checked={isPublic && ranking} disabled={!isPublic}
            onChange={(e) => setRanking(e.target.checked)} />{" "}
          Aparecer no ranking público
        </label>
        {error && <p role="alert">{error}</p>}
        {msg && <p role="status">{msg}</p>}
        <p><button type="submit" disabled={busy}>Salvar configurações de {child.display_name}</button></p>
      </form>

      <section aria-labelledby={`export-${child.id}`}>
        <h4 id={`export-${child.id}`}>Dados de {child.display_name}</h4>
        <p>
          Gere um arquivo JSON com os dados da conta do menor. O arquivo fica disponível por 7 dias
          e um novo pode ser pedido a cada 24 horas.
        </p>
        <p><button type="button" disabled={busy} onClick={() => void requestExport()}>
          Pedir exportação dos dados de {child.display_name}
        </button></p>
        {exportMsg && <p role="status">{exportMsg}</p>}
        {exportError && <p role="alert">{exportError}</p>}
        {exports.length > 0 && (
          <ul aria-label={`Exportações de ${child.display_name}`}>
            {exports.map((x) => (
              <li key={x.id}>
                <a href={`/api/v1${base}/export/${x.id}`} download>Baixar arquivo de {date(x.created_at)}</a>{" "}
                (disponível até {date(x.expires_at)})
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby={`delete-${child.id}`}>
        <h4 id={`delete-${child.id}`}>Excluir a conta de {child.display_name}</h4>
        {pendingDeletion ? (
          <>
            <p role="status">
              A exclusão está agendada para {date(child.deletion_scheduled_for ?? "")}. Até lá você
              pode cancelar; depois disso os dados pessoais são apagados e não podem ser recuperados.
            </p>
            <p><button type="button" disabled={busy} onClick={() => void cancelDeletion()}>
              Cancelar exclusão da conta de {child.display_name}
            </button></p>
          </>
        ) : !confirming ? (
          <p><button type="button" className="secondary" onClick={() => setConfirming(true)}>
            Excluir a conta de {child.display_name}…
          </button></p>
        ) : (
          <form onSubmit={(e) => void requestDeletion(e)} aria-labelledby={`delete-${child.id}`}>
            <p>
              A conta é encerrada agora e há 14 dias para desistir. Depois disso, o perfil, as
              preferências e o progresso na Academy são apagados.
            </p>
            <label htmlFor={`pw-${child.id}`}>Confirme com a SUA senha (do responsável)</label>
            <input id={`pw-${child.id}`} type="password" autoComplete="current-password" required
              maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)} />
            <label>
              <input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} />{" "}
              Entendo que, depois de 14 dias, a exclusão é definitiva.
            </label>
            {deleteError && <p role="alert">{deleteError}</p>}
            <p>
              <button type="submit" disabled={!understood || !password || busy}>
                Confirmar exclusão da conta de {child.display_name}
              </button>{" "}
              <button type="button" className="secondary"
                onClick={() => { setConfirming(false); setUnderstood(false); setPassword(""); setDeleteError(""); }}>
                Voltar
              </button>
            </p>
          </form>
        )}
        {pendingDeletion && deleteError && <p role="alert">{deleteError}</p>}
      </section>
    </article>
  );
}
