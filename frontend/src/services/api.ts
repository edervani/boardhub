/** Cliente REST. O servidor é a autoridade; aqui só se transporta a intenção do usuário. */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly type: string,
    readonly title: string,
    readonly detail?: string,
  ) {
    super(title);
  }
}

function csrfToken(): string {
  const match = document.cookie.split("; ").find((c) => c.startsWith("bh_csrf="));
  return match ? decodeURIComponent(match.slice("bh_csrf=".length)) : "";
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  const resp = await fetch(`/api/v1${path}`, {
    method,
    headers,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (resp.status === 204) return undefined as T;
  const data: unknown = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const p = data as { type?: string; title?: string; detail?: string };
    throw new ApiError(resp.status, p.type ?? "error", p.title ?? "Algo deu errado", p.detail);
  }
  return data as T;
}

export const errorMessage = (e: unknown): string =>
  e instanceof ApiError ? [e.title, e.detail].filter(Boolean).join(". ") : "Algo deu errado. Tente de novo.";
