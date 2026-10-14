import { useCallback, useEffect, useRef, useState } from "react";
import {
  NO_RECONNECT_CODES,
  backoffDelay,
  clientMessage,
  parseServerMessage,
  wsUrl,
  type ServerMessage,
} from "../services/realtime";

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";

const OPEN = 1; // WebSocket.OPEN

interface Options {
  /** Só conecta enquanto verdadeiro (ex.: usuário autenticado). */
  enabled: boolean;
  onMessage: (msg: ServerMessage) => void;
  /** Chamado a cada (re)conexão; é aqui que se envia `join_match` com o último ply conhecido. */
  onOpen?: () => void;
  random?: () => number;
}

/**
 * Conexão WebSocket com reconexão exponencial (1, 2, 4, 8… até 30 s, com jitter), resposta
 * automática ao `ping` do servidor e sem reconexão quando o servidor recusa (4401/4403/4429).
 */
export function useWebSocket({ enabled, onMessage, onOpen, random }: Options) {
  const [state, setState] = useState<ConnectionState>(enabled ? "connecting" : "closed");
  const [attempt, setAttempt] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  const onOpenRef = useRef(onOpen);
  const randomRef = useRef(random);
  useEffect(() => {
    onMessageRef.current = onMessage;
    onOpenRef.current = onOpen;
    randomRef.current = random;
  });

  useEffect(() => {
    if (!enabled) { setState("closed"); return; }
    let cancelled = false;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      setState(failures === 0 ? "connecting" : "reconnecting");
      const ws = new WebSocket(wsUrl());
      socketRef.current = ws;
      ws.onopen = () => {
        failures = 0; setAttempt(0); setState("open");
        onOpenRef.current?.();
      };
      ws.onmessage = (ev: MessageEvent) => {
        const msg = parseServerMessage(ev.data);
        if (!msg) return;
        if (msg.type === "ping") { ws.send(JSON.stringify({ type: "pong" })); return; }
        onMessageRef.current(msg);
      };
      ws.onclose = (ev: CloseEvent) => {
        if (socketRef.current === ws) socketRef.current = null;
        if (cancelled) return;
        if (NO_RECONNECT_CODES.has(ev.code)) { setState("closed"); return; }
        failures += 1; setAttempt(failures); setState("reconnecting");
        timer = setTimeout(connect, backoffDelay(failures - 1, randomRef.current));
      };
    };
    connect();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      const ws = socketRef.current;
      socketRef.current = null;
      ws?.close();
    };
  }, [enabled]);

  /** Envia um comando; devolve o `id` (para casar com `reply_to`) ou null se não há conexão. */
  const send = useCallback((type: string, payload: Record<string, unknown>): string | null => {
    const ws = socketRef.current;
    if (!ws || ws.readyState !== OPEN) return null;
    const { id, json } = clientMessage(type, payload);
    ws.send(json);
    return id;
  }, []);

  return { state, attempt, send };
}
