import { useCallback, useEffect, useRef, useState } from "react";
import { useWebSocket } from "../../hooks/useWebSocket";
import { api, errorMessage } from "../../services/api";
import type { ServerMessage } from "../../services/realtime";
import type { MatchView } from "../../services/types";
import { mySeat } from "./onlineStatus";

const num = (v: unknown): number | null => (typeof v === "number" ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);

/**
 * Partida online: estado oficial pelo REST ao abrir e, depois, pelo WebSocket (snapshot na
 * (re)conexão e eventos). O cliente nunca decide legalidade nem resultado (doc 04 §5).
 */
export function useOnlineMatch(matchId: string) {
  const [match, setMatchState] = useState<MatchView | null>(null);
  const [polite, setPolite] = useState("");
  const [assertive, setAssertive] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const matchRef = useRef<MatchView | null>(null);
  const pendingRef = useRef<string | null>(null);
  const sendRef = useRef<(type: string, payload: Record<string, unknown>) => string | null>(() => null);

  const setMatch = useCallback((next: MatchView | null) => {
    matchRef.current = next;
    setMatchState(next);
  }, []);

  const join = useCallback(() => {
    sendRef.current("join_match", { match_id: matchId, last_known_ply: matchRef.current?.ply ?? 0 });
  }, [matchId]);

  const handle = useCallback((msg: ServerMessage) => {
    const p = msg.payload ?? {};
    if (msg.reply_to && msg.reply_to === pendingRef.current) {
      pendingRef.current = null;
      setPending(false);
    }
    const prev = matchRef.current;
    const mine = prev ? mySeat(prev) : null;
    switch (msg.type) {
      case "match_snapshot": {
        const snap = p as unknown as MatchView;
        if (!prev || snap.ply >= prev.ply || snap.status !== prev.status) setMatch(snap);
        setError("");
        break;
      }
      case "moves_since": {
        const moves = Array.isArray(p.moves) ? p.moves.length : 0;
        if (moves > 0) setPolite(`Você perdeu ${moves} lance${moves > 1 ? "s" : ""} enquanto estava desconectado; o tabuleiro foi atualizado.`);
        break;
      }
      case "move_applied": {
        const ply = num(p.ply);
        if (!prev || ply === null || ply <= prev.ply) break; // repetido ou antigo
        if (ply > prev.ply + 1) join(); // lacuna: pede o estado oficial de novo
        setMatch({
          ...prev, ply, state: p.state as MatchView["state"], to_move_seat: num(p.next_seat),
          legal_moves: Array.isArray(p.legal_moves) ? (p.legal_moves as string[]) : [],
        });
        if (num(p.seat) !== mine) setPolite(`O adversário jogou ${str(p.move) ?? ""}. Sua vez.`);
        break;
      }
      case "match_ended": {
        if (!prev) break;
        setMatch({
          ...prev, status: "finished", result: str(p.result) as MatchView["result"],
          end_reason: str(p.end_reason), to_move_seat: null, legal_moves: [], draw_offer_by_seat: null,
        });
        setAssertive("A partida terminou.");
        break;
      }
      case "draw_offered": {
        if (!prev) break;
        const by = num(p.by_seat);
        setMatch({ ...prev, draw_offer_by_seat: by });
        setPolite(by === mine ? "Você propôs empate. Aguardando resposta." : "O adversário propôs empate. Você pode aceitar ou recusar.");
        break;
      }
      case "draw_declined": {
        if (!prev) break;
        setMatch({ ...prev, draw_offer_by_seat: null });
        setPolite(num(p.by_seat) === mine ? "Você recusou o empate." : "A proposta de empate foi recusada.");
        break;
      }
      case "player_connection": {
        if (!prev) break;
        const seat = num(p.seat);
        const players = (prev.players ?? []).map((pl) => pl.seat === seat
          ? { ...pl, connected: p.connected === true, grace_deadline: str(p.grace_deadline) } : pl);
        setMatch({ ...prev, players });
        if (seat !== mine) {
          if (p.connected === true) setPolite("O adversário voltou a se conectar.");
          else setAssertive("Adversário desconectado. Se não voltar, você poderá reivindicar a vitória após a tolerância.");
        }
        break;
      }
      case "error": {
        const title = str(p.message) ?? "Algo deu errado";
        const detail = str(p.detail);
        setError(detail ? `${title}. ${detail}` : title);
        if (p.code === "stale_state") join(); // ressincroniza com o estado oficial
        break;
      }
      default:
        break;
    }
  }, [join, setMatch]);

  const ws = useWebSocket({ enabled: true, onMessage: handle, onOpen: join });
  useEffect(() => { sendRef.current = ws.send; }, [ws.send]);

  useEffect(() => {
    let alive = true;
    api<MatchView>("GET", `/matches/${matchId}`).then(
      (m) => { if (alive && !matchRef.current) setMatch(m); },
      (e: unknown) => { if (alive) setError(errorMessage(e)); },
    );
    return () => { alive = false; };
  }, [matchId, setMatch]);

  useEffect(() => {
    if (ws.state === "reconnecting") setAssertive(`Conexão perdida. Tentando reconectar… (tentativa ${ws.attempt})`);
    else if (ws.state === "open") setAssertive((cur) => (cur.startsWith("Conexão perdida") ? "Conexão restabelecida." : cur));
  }, [ws.state, ws.attempt]);

  const command = useCallback((type: string, extra: Record<string, unknown> = {}) => {
    setError("");
    const id = sendRef.current(type, { match_id: matchId, ...extra });
    if (id === null) { setError("Sem conexão no momento. Aguarde a reconexão."); return; }
    pendingRef.current = id;
    setPending(true);
  }, [matchId]);

  const play = useCallback((move: string) => {
    const cur = matchRef.current;
    if (!cur) return;
    command("submit_move", { expected_ply: cur.ply, move, client_move_id: crypto.randomUUID() });
  }, [command]);

  return {
    match, polite, assertive, error, pending, connection: ws.state, attempt: ws.attempt,
    play,
    resign: () => command("resign"),
    offerDraw: () => command("offer_draw"),
    respondDraw: (accept: boolean) => command("respond_draw", { accept }),
    claimAbandon: () => command("claim_abandon"),
  };
}
