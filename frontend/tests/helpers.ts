import { vi } from "vitest";

type Reply = { status?: number; body?: unknown };
export type Handler = Reply | ((init: RequestInit | undefined) => Reply);

/** Substitui `fetch` por rotas simuladas "MÉTODO /caminho" (sem o prefixo /api/v1). */
export function mockApi(routes: Record<string, Handler>) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url.replace("/api/v1", "")}`;
    const hit = routes[key];
    const reply = typeof hit === "function" ? hit(init) : hit;
    const status = reply ? (reply.status ?? 200) : 404;
    return new Response(status === 204 ? null : JSON.stringify(reply?.body ?? {}), { status });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export const bodyOf = (init: RequestInit | undefined): Record<string, unknown> =>
  JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;

export const cellButtons = (container: HTMLElement) =>
  Array.from(container.querySelectorAll<HTMLButtonElement>('[role="group"] button'));

/** WebSocket falso: os testes abrem, derrubam e enviam mensagens como se fosse o servidor. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  constructor(readonly url: string) { FakeWebSocket.instances.push(this); }
  send(data: string) { this.sent.push(data); }
  close() {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.({ code: 1000 });
  }
  open() { this.readyState = 1; this.onopen?.(); }
  receive(msg: unknown) { this.onmessage?.({ data: JSON.stringify(msg) }); }
  drop(code = 1006) { this.readyState = 3; this.onclose?.({ code }); }
  sentMessages() {
    return this.sent.map((s) => JSON.parse(s) as { type: string; id?: string; payload?: Record<string, unknown> });
  }
}

export function installFakeWebSocket() {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
}
