import { useCallback, useState } from "react";
import { ApiError, api, errorMessage } from "../../services/api";
import type { EngineApply, MatchState, MatchView } from "../../services/types";

const newId = () => crypto.randomUUID();

/** Partida persistida no servidor (contra a IA ou local de usuário autenticado). */
export function useServerMatch() {
  const [match, setMatch] = useState<MatchView | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const start = useCallback(async (body: Record<string, unknown>) => {
    setError(""); setBusy(true);
    try { setMatch(await api<MatchView>("POST", "/matches", body)); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }, []);

  const play = useCallback(async (index: number) => {
    if (!match || busy) return;
    setError(""); setBusy(true);
    try {
      setMatch(await api<MatchView>("POST", `/matches/${match.id}/moves`, {
        expected_ply: match.ply, move: String(index), client_move_id: newId(),
      }));
    } catch (e) {
      setError(errorMessage(e));
      if (e instanceof ApiError && e.status === 409) {
        // Estado desatualizado: ressincroniza com o oficial do servidor.
        setMatch(await api<MatchView>("GET", `/matches/${match.id}`).catch(() => match));
      }
    } finally { setBusy(false); }
  }, [match, busy]);

  const resign = useCallback(async () => {
    if (!match) return;
    setError("");
    try { setMatch(await api<MatchView>("POST", `/matches/${match.id}/resign`)); }
    catch (e) { setError(errorMessage(e)); }
  }, [match]);

  const reset = useCallback(() => { setMatch(null); setError(""); }, []);
  return { match, error, busy, start, play, resign, reset };
}

const INITIAL: MatchState = { schema_version: 1, board: "_________", to_move: "X" };

/** Partida local de visitante: o estado fica no navegador, mas cada lance é validado pelo servidor. */
export function useGuestLocalMatch() {
  const [state, setState] = useState<MatchState>(INITIAL);
  const [legal, setLegal] = useState<string[]>(Array.from({ length: 9 }, (_, i) => String(i)));
  const [outcome, setOutcome] = useState<EngineApply["outcome"]>(null);
  const [error, setError] = useState("");

  const play = useCallback(async (index: number) => {
    setError("");
    try {
      const r = await api<EngineApply>("POST", "/engines/tictactoe/apply", { state, move: String(index) });
      setState(r.state); setLegal(r.legal_moves); setOutcome(r.outcome);
    } catch (e) { setError(errorMessage(e)); }
  }, [state]);

  const reset = useCallback(() => {
    setState(INITIAL); setOutcome(null); setError("");
    setLegal(Array.from({ length: 9 }, (_, i) => String(i)));
  }, []);
  return { state, legal, outcome, error, play, reset };
}
