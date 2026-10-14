import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../src/app/App";
import { RegisterForm } from "../src/features/auth/AuthForms";
import { GameList } from "../src/features/catalog/GameList";
import { api, ApiError } from "../src/services/api";

function mockFetch(routes: Record<string, { status?: number; body?: unknown }>) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const hit = routes[`${init?.method ?? "GET"} ${url.replace("/api/v1", "")}`];
    const status = hit?.status ?? 404;
    return new Response(status === 204 ? null : JSON.stringify(hit?.body ?? {}), { status });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => { vi.unstubAllGlobals(); document.cookie = "bh_csrf=; max-age=0"; });

test("exibe o nome do produto como título principal", async () => {
  mockFetch({ "GET /me": { status: 401 }, "GET /games": { status: 200, body: [] } });
  render(<App />);
  expect(await screen.findByRole("heading", { level: 1, name: "BoardHub" })).toBeInTheDocument();
});

test("visitante vê entrar e criar conta, sem perfil", async () => {
  mockFetch({ "GET /me": { status: 401 }, "GET /games": { body: [] } });
  render(<App />);
  expect(await screen.findByRole("button", { name: "Entrar" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Perfil" })).not.toBeInTheDocument();
});

test("lista de jogos mostra a classificação indicativa em texto", async () => {
  mockFetch({ "GET /games": { body: [
    { id: "chess", name: "Xadrez", age_rating: "L", age_rating_label: "Livre", ranked_enabled: false },
  ] } });
  render(<GameList />);
  expect(await screen.findByLabelText("Classificação indicativa: Livre")).toHaveTextContent("Livre");
});

test("campo do responsável só aparece para menores de 12", async () => {
  mockFetch({});
  render(<RegisterForm />);
  expect(screen.queryByLabelText("E-mail do responsável")).not.toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Faixa etária"), "under_12");
  expect(screen.getByLabelText("E-mail do responsável")).toBeRequired();
});

test("requisições que alteram dados enviam o token CSRF; GET não", async () => {
  document.cookie = "bh_csrf=abc123";
  const fn = mockFetch({ "POST /x": { status: 204 }, "GET /y": { body: {} } });
  await api("POST", "/x", {});
  await api("GET", "/y");
  const [, post] = fn.mock.calls[0] as [string, RequestInit];
  const [, get] = fn.mock.calls[1] as [string, RequestInit];
  expect((post.headers as Record<string, string>)["X-CSRF-Token"]).toBe("abc123");
  expect(post.credentials).toBe("include");
  expect((get.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
});

test("erros da API viram ApiError com o título do servidor", async () => {
  mockFetch({ "GET /z": { status: 409, body: { type: "display_name_taken", title: "Nome em uso" } } });
  await expect(api("GET", "/z")).rejects.toMatchObject({ status: 409, title: "Nome em uso" });
  await waitFor(() => expect(ApiError).toBeDefined());
});
