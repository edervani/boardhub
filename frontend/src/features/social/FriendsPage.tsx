import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, errorMessage } from "../../services/api";
import type { BlockedUser, DirectInvitation, Friend, FriendRequests } from "../../services/types";
import { ReportButton } from "./ReportButton";

const GAMES: Record<string, string> = { tictactoe: "Jogo da velha", checkers: "Damas", chess: "Xadrez" };

/** Amigos, pedidos, convites diretos e bloqueios (RF-032). Sem chat: só convite para jogar. */
export function FriendsPage({ onMatchStarted }: { onMatchStarted: () => void }) {
  const [friends, setFriends] = useState<Friend[]>([]);
  const [requests, setRequests] = useState<FriendRequests>({ incoming: [], outgoing: [] });
  const [invites, setInvites] = useState<DirectInvitation[]>([]);
  const [blocks, setBlocks] = useState<BlockedUser[]>([]);
  const [name, setName] = useState("");
  const [game, setGame] = useState("tictactoe");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [f, r, i, b] = await Promise.all([
        api<Friend[]>("GET", "/friends"),
        api<FriendRequests>("GET", "/friends/requests"),
        api<DirectInvitation[]>("GET", "/invitations"),
        api<BlockedUser[]>("GET", "/blocks"),
      ]);
      setFriends(f); setRequests(r); setInvites(i); setBlocks(b);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>, ok: string) {
    setMsg(""); setError("");
    try { await fn(); setMsg(ok); await load(); } catch (e) { setError(errorMessage(e)); }
  }

  function addFriend(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void act(async () => {
      await api("POST", "/friends/requests", { display_name: name.trim() });
      setName("");
    }, "Pedido enviado.");
  }

  async function accept(id: string) {
    setError(""); setMsg("");
    try {
      await api("POST", `/invitations/${id}/accept`);
      onMatchStarted();
    } catch (e) {
      setError(errorMessage(e)); await load();
    }
  }

  return (
    <section aria-labelledby="friends-title">
      <h2 id="friends-title">Amigos</h2>
      <p>Aqui você só pede amizade e convida para jogar. Não há conversa livre.</p>
      {msg && <p role="status">{msg}</p>}
      {error && <p role="alert">{error}</p>}

      <form onSubmit={addFriend} aria-labelledby="add-title">
        <h3 id="add-title">Pedir amizade</h3>
        <label htmlFor="friend-name">Apelido da pessoa</label>
        <input id="friend-name" required minLength={3} maxLength={24} value={name}
          onChange={(e) => setName(e.target.value)} />
        <button type="submit">Enviar pedido</button>
      </form>

      <h3>Convites recebidos</h3>
      {invites.length === 0 ? <p>Nenhum convite no momento.</p> : (
        <ul>
          {invites.map((i) => (
            <li key={i.id}>
              {i.other.display_name} convidou você para {GAMES[i.game_id] ?? i.game_id}.{" "}
              <button type="button" onClick={() => void accept(i.id)}>
                Aceitar convite de {i.other.display_name}
              </button>{" "}
              <button type="button" className="secondary"
                onClick={() => void act(() => api("POST", `/invitations/${i.id}/decline`), "Convite recusado.")}>
                Recusar convite de {i.other.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}

      <h3>Pedidos de amizade</h3>
      {requests.incoming.length === 0 && requests.outgoing.length === 0 && <p>Nenhum pedido pendente.</p>}
      <ul>
        {requests.incoming.map((r) => (
          <li key={r.friendship_id}>
            {r.display_name} quer ser seu amigo.{" "}
            <button type="button" onClick={() => void act(() => api("POST", `/friends/requests/${r.friendship_id}/accept`), "Amizade aceita.")}>
              Aceitar pedido de {r.display_name}
            </button>{" "}
            <button type="button" className="secondary" onClick={() => void act(() => api("POST", `/friends/requests/${r.friendship_id}/decline`), "Pedido recusado.")}>
              Recusar pedido de {r.display_name}
            </button>
          </li>
        ))}
        {requests.outgoing.map((r) => (
          <li key={r.friendship_id}>
            Aguardando {r.display_name}.{" "}
            <button type="button" className="secondary" onClick={() => void act(() => api("DELETE", `/friends/${r.friendship_id}`), "Pedido cancelado.")}>
              Cancelar pedido para {r.display_name}
            </button>
          </li>
        ))}
      </ul>

      <h3>Meus amigos</h3>
      {friends.length === 0 ? <p>Você ainda não tem amigos adicionados.</p> : (
        <>
          <label htmlFor="invite-game">Jogo do convite</label>
          <select id="invite-game" value={game} onChange={(e) => setGame(e.target.value)}>
            {Object.entries(GAMES).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
          <ul>
            {friends.map((f) => (
              <li key={f.friendship_id}>
                <strong>{f.display_name}</strong>{" "}
                <button type="button" onClick={() => void act(() => api("POST", `/friends/${f.friendship_id}/invitations`, { game_id: game }), `Convite enviado para ${f.display_name}.`)}>
                  Convidar {f.display_name} para jogar
                </button>{" "}
                <button type="button" className="secondary" onClick={() => void act(() => api("DELETE", `/friends/${f.friendship_id}`), "Amizade desfeita.")}>
                  Remover {f.display_name}
                </button>{" "}
                <button type="button" className="secondary" onClick={() => void act(() => api("POST", "/blocks", { display_name: f.display_name }), `${f.display_name} bloqueado.`)}>
                  Bloquear {f.display_name}
                </button>{" "}
                <ReportButton targetType="user" targetId={f.display_name} label={`Denunciar ${f.display_name}`} />
              </li>
            ))}
          </ul>
        </>
      )}

      <h3>Pessoas bloqueadas</h3>
      {blocks.length === 0 ? <p>Você não bloqueou ninguém.</p> : (
        <ul>
          {blocks.map((b) => (
            <li key={b.block_id}>
              {b.display_name}{" "}
              <button type="button" className="secondary" onClick={() => void act(() => api("DELETE", `/blocks/${b.block_id}`), "Bloqueio removido.")}>
                Desbloquear {b.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}

      <h3>Denunciar uma pessoa</h3>
      <ReportPerson />
    </section>
  );
}

function ReportPerson() {
  const [name, setName] = useState("");
  const [go, setGo] = useState(false);
  if (go && name.trim()) {
    return <ReportButton key={name} targetType="user" targetId={name.trim()} label="Denunciar" />;
  }
  return (
    <div>
      <label htmlFor="report-name">Apelido de quem você quer denunciar</label>
      <input id="report-name" minLength={3} maxLength={24} value={name} onChange={(e) => setName(e.target.value)} />
      <button type="button" className="secondary" disabled={name.trim().length < 3} onClick={() => setGo(true)}>
        Continuar denúncia
      </button>
    </div>
  );
}
