/** Protocolo do WebSocket (doc 06 §3). O servidor é a autoridade; aqui só se transporta intenção. */

export interface ServerMessage {
  type: string;
  payload?: Record<string, unknown>;
  seq?: number;
  reply_to?: string;
}

/** Códigos de fechamento em que reconectar não adianta: sessão inválida, origem ou limite de taxa. */
export const NO_RECONNECT_CODES: ReadonlySet<number> = new Set([4401, 4403, 4429]);

export const MAX_BACKOFF_MS = 30_000;

/**
 * Atraso antes da tentativa `attempt` (0 = primeira): 1, 2, 4, 8… s até 30 s, com jitter de
 * -25% a +25% (doc 06 §3.6). `random` é injetável para os testes.
 */
export function backoffDelay(attempt: number, random: () => number = Math.random): number {
  const base = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** Math.max(0, attempt));
  return Math.min(MAX_BACKOFF_MS, Math.round(base * (0.75 + 0.5 * random())));
}

export function wsUrl(loc: Pick<Location, "protocol" | "host"> = window.location): string {
  return `${loc.protocol === "https:" ? "wss:" : "ws:"}//${loc.host}/api/v1/ws`;
}

export function parseServerMessage(raw: unknown): ServerMessage | null {
  if (typeof raw !== "string") return null;
  try {
    const data: unknown = JSON.parse(raw);
    if (typeof data !== "object" || data === null) return null;
    const msg = data as Record<string, unknown>;
    if (typeof msg.type !== "string") return null;
    return msg as unknown as ServerMessage;
  } catch {
    return null;
  }
}

export function clientMessage(type: string, payload: Record<string, unknown>): { id: string; json: string } {
  const id = crypto.randomUUID();
  return { id, json: JSON.stringify({ type, id, payload }) };
}
