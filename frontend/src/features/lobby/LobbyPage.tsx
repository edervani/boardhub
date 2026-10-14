import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useWebSocket } from "../../hooks/useWebSocket";
import { api, errorMessage } from "../../services/api";
import type { ServerMessage } from "../../services/realtime";
import type { ActiveMatch, MatchView, Me, QueueStatus } from "../../services/types";
import { OnlineMatch, type BoardRenderer } from "./OnlineMatch";
import { GAME_TITLES } from "./onlineStatus";

const GAMES = ["tictactoe", "checkers", "chess"] as const;
const POLL_MS = 3000;

interface Props {
  me: Me;
  renderBoard: BoardRenderer;
  /** Intervalo de consulta da fila; reduzido nos testes. */
  pollMs?: number;
}

function GameSelect({ id, value, onChange }: { id: string; value: string; onChange: (v: string) => void }) {
  return (
    <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      {GAMES.map((g) => <option key={g} value={g}>{GAME_TITLES[g]}</option>)}
    </select>
  );
}

function activeLabel(m: ActiveMatch): string {
  const title = GAME_TITLES[m.game_id] ?? m.game_id;
  if (m.status === "waiting") return `${title} — aguardando um oponente entrar com o código`;
  return `${title} — contra ${m.opponent_name ?? "o oponente"} — ${m.your_turn ? "sua vez" : "vez do oponente"}`;
}

export function LobbyPage({ me, renderBoard, pollMs = POLL_MS }: Props) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [active, setActive] = useState<ActiveMatch[]>([]);
  const [invite, setInvite] = useState<MatchView | null>(null);
  const [queue, setQueue] = useState<QueueStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [inviteGame, setInviteGame] = useState("tictactoe");
  const [queueGame, setQueueGame] = useState("tictactoe");

  const loadActive = useCallback(async () => {
    try { setActive(await api<ActiveMatch[]>("GET", "/me/active-matches")); }
    catch (e) { setError(errorMessage(e)); }
  }, []);

  useEffect(() => { void loadActive(); }, [loadActive, openId]);

  // O servidor avisa quando um oponente entra pelo código ou o pareamento acontece.
  const onMessage = useCallback((msg: ServerMessage) => {
    if (msg.type !== "match_started") return;
    const id = msg.payload?.match_id;
    if (typeof id === "string") { setInvite(null); setQueue(null); setOpenId(id); }
  }, []);
  useWebSocket({ enabled: openId === null, onMessage });

  // Alternativa ao WebSocket: consulta a fila (também mantém a entrada viva no servidor).
  const queued = queue?.state === "queued";
  useEffect(() => {
    if (!queued) return;
    let vivo = true; // descarta respostas que chegam depois de sair da fila
    const timer = setInterval(() => {
      api<QueueStatus>("GET", "/matchmaking/queue").then((s) => {
        if (!vivo) return;
        if (s.state === "matched" && s.match_id) { setQueue(null); setOpenId(s.match_id); }
        else setQueue(s.state === "idle" ? null : s);
      }, (e: unknown) => { if (vivo) setError(errorMessage(e)); });
    }, pollMs);
    return () => { vivo = false; clearInterval(timer); };
  }, [queued, pollMs]);

  async function run(action: () => Promise<void>) {
    setError(""); setBusy(true);
    try { await action(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }

  const createInvite = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const seat = String(new FormData(e.currentTarget).get("seat") ?? "");
    void run(async () => {
      const body: Record<string, unknown> = { game_id: inviteGame, mode: "online_casual" };
      if (seat === "1" || seat === "2") body.preferred_seat = Number(seat);
      setInvite(await api<MatchView>("POST", "/matches", body));
      await loadActive();
    });
  };

  const joinByCode = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const code = String(new FormData(e.currentTarget).get("code") ?? "").trim();
    void run(async () => {
      const m = await api<MatchView>("POST", "/matches/join", { invite_code: code });
      setInvite(null); setOpenId(m.id);
    });
  };

  const enterQueue = () => void run(async () => {
    const s = await api<QueueStatus>("POST", "/matchmaking/queue", { game_id: queueGame });
    if (s.state === "matched" && s.match_id) setOpenId(s.match_id); else setQueue(s);
  });

  const leaveQueue = () => void run(async () => {
    await api<void>("DELETE", "/matchmaking/queue");
    setQueue(null);
  });

  const cancelInvite = (id: string) => void run(async () => {
    await api<void>("POST", `/matches/${id}/cancel`);
    if (invite?.id === id) setInvite(null);
    await loadActive();
  });

  if (openId) {
    return <OnlineMatch matchId={openId} renderBoard={renderBoard} onLeave={() => setOpenId(null)} />;
  }

  const onlineActive = active.filter((m) => m.mode.startsWith("online"));
  return (
    <section aria-labelledby="lobby-title">
      <h2 id="lobby-title">Jogar online</h2>
      <p>Partidas casuais entre pessoas: não valem ranking e não têm chat.</p>
      {!me.email_verified && (
        <p role="status">Confirme seu e-mail para entrar na fila de pareamento. Convites por código já funcionam.</p>
      )}
      {error && <p role="alert">{error}</p>}

      <form onSubmit={createInvite} aria-labelledby="invite-title">
        <h3 id="invite-title">Criar convite</h3>
        <label htmlFor="invite-game">Jogo do convite</label>
        <GameSelect id="invite-game" value={inviteGame} onChange={setInviteGame} />
        <label htmlFor="invite-seat">Você joga</label>
        <select id="invite-seat" name="seat" defaultValue="">
          <option value="">Sorteio</option>
          <option value="1">Primeiro</option>
          <option value="2">Segundo</option>
        </select>
        <p><button type="submit" disabled={busy}>Criar convite</button></p>
      </form>
      {invite?.invite_code && (
        <div className="card" aria-live="polite">
          <p>Código da sala: <strong className="code">{invite.invite_code}</strong></p>
          <p>Compartilhe com quem vai jogar. O código vale por 15 minutos, serve uma única vez e não será mostrado de novo. Aguardando o oponente…</p>
          <button type="button" className="secondary" disabled={busy} onClick={() => cancelInvite(invite.id)}>
            Cancelar convite
          </button>
        </div>
      )}

      <form onSubmit={joinByCode} aria-labelledby="join-title">
        <h3 id="join-title">Entrar por código</h3>
        <label htmlFor="invite-code">Código do convite</label>
        <input id="invite-code" name="code" autoComplete="off" maxLength={32} required />
        <p><button type="submit" disabled={busy}>Entrar na sala</button></p>
      </form>

      <section className="card" aria-labelledby="queue-title">
        <h3 id="queue-title">Fila de pareamento</h3>
        {queue?.state === "queued" ? (
          <>
            <p role="status" aria-live="polite">
              Procurando oponente de {GAME_TITLES[queue.game_id ?? ""] ?? "jogo"}… ({queue.waited_seconds} s)
            </p>
            {queue.offer_ai && (
              <p>Ainda sem oponente. Você pode continuar esperando, sair da fila ou jogar contra a IA na aba Jogar.</p>
            )}
            <button type="button" className="secondary" disabled={busy} onClick={leaveQueue}>Sair da fila</button>
          </>
        ) : (
          <>
            <label htmlFor="queue-game">Jogo da fila</label>
            <GameSelect id="queue-game" value={queueGame} onChange={setQueueGame} />
            <p>
              <button type="button" disabled={busy || !me.email_verified} onClick={enterQueue}>
                Entrar na fila
              </button>
            </p>
          </>
        )}
      </section>

      <section aria-labelledby="active-title">
        <h3 id="active-title">Partidas em andamento</h3>
        {onlineActive.length === 0 ? <p>Nenhuma partida online em andamento.</p> : (
          <ul>
            {onlineActive.map((m) => (
              <li key={m.id} className="card">
                {activeLabel(m)}{" "}
                {m.status === "in_progress" ? (
                  <button type="button" onClick={() => setOpenId(m.id)}>Abrir</button>
                ) : (
                  <button type="button" className="secondary" disabled={busy} onClick={() => cancelInvite(m.id)}>
                    Cancelar convite
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
