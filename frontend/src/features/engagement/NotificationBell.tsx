import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../../services/api";
import type { NotificationList, NotificationPreference } from "./types";

export const POLL_MS = 60_000;

/**
 * Sino de notificações in-app (RF-028). Só avisos funcionais do jogo; cada tipo pode ser desativado.
 * O anúncio ao leitor de tela é educado (aria-live="polite") e só ocorre quando chegam avisos novos.
 */
export function NotificationBell() {
  const [list, setList] = useState<NotificationList>({ items: [], unread_count: 0 });
  const [open, setOpen] = useState(false);
  const [prefs, setPrefs] = useState<NotificationPreference[] | null>(null);
  const [error, setError] = useState("");
  const [announce, setAnnounce] = useState("");
  const last = useRef(0);

  const load = useCallback(async () => {
    try {
      const next = await api<NotificationList>("GET", "/me/notifications?limit=20");
      if (next.unread_count > last.current) {
        setAnnounce(next.unread_count === 1 ? "Você tem 1 notificação nova." : `Você tem ${next.unread_count} notificações novas.`);
      }
      last.current = next.unread_count;
      setList(next);
    } catch {
      /* o sino é secundário: falha de rede não interrompe o jogo */
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  async function toggleOpen() {
    const next = !open;
    setOpen(next);
    if (next) {
      await load();
      if (prefs === null) {
        api<{ kinds: NotificationPreference[] }>("GET", "/me/notification-preferences")
          .then((r) => setPrefs(r.kinds))
          .catch((e: unknown) => setError(errorMessage(e)));
      }
    }
  }

  async function markRead(id: string) {
    try { await api<void>("POST", `/me/notifications/${id}/read`); await load(); }
    catch (e) { setError(errorMessage(e)); }
  }

  async function markAll() {
    try { await api<void>("POST", "/me/notifications/read-all"); await load(); }
    catch (e) { setError(errorMessage(e)); }
  }

  async function setPref(kind: string, enabled: boolean) {
    try {
      const r = await api<{ kinds: NotificationPreference[] }>("PUT", "/me/notification-preferences", { kinds: { [kind]: enabled } });
      setPrefs(r.kinds);
    } catch (e) { setError(errorMessage(e)); }
  }

  const n = list.unread_count;
  return (
    <div className="notification-bell">
      <button className="secondary" aria-expanded={open} onClick={() => void toggleOpen()}>
        Notificações{n > 0 ? ` (${n} não lida${n > 1 ? "s" : ""})` : ""}
      </button>
      <p role="status" aria-live="polite" className="sr-only">{announce}</p>
      {open && (
        <section id="notif-panel" aria-label="Painel de notificações">
          {error && <p role="alert">{error}</p>}
          {list.items.length === 0 ? <p>Nenhuma notificação.</p> : (
            <ul aria-label="Notificações">
              {list.items.map((it) => (
                <li key={it.id}>
                  <strong>{it.title}</strong>{!it.read && <span> (nova)</span>}
                  <p>{it.body}</p>
                  {!it.read && <button className="secondary" onClick={() => void markRead(it.id)}>Marcar como lida</button>}
                </li>
              ))}
            </ul>
          )}
          {n > 0 && <p><button className="secondary" onClick={() => void markAll()}>Marcar todas como lidas</button></p>}
          <fieldset>
            <legend>Quais avisos você quer receber</legend>
            {(prefs ?? []).map((p) => (
              <p key={p.kind}>
                <label>
                  <input type="checkbox" checked={p.enabled} onChange={(e) => void setPref(p.kind, e.target.checked)} /> {p.label}
                </label>
              </p>
            ))}
          </fieldset>
        </section>
      )}
    </div>
  );
}
