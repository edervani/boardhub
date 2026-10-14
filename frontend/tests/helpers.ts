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
