import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../src/app/App";
import { extractToken, GuardianPage } from "../src/features/guardian/GuardianPage";
import { LIMIT_HELP } from "../src/features/guardian/ChildPanel";
import type { Child, Me } from "../src/services/types";
import { bodyOf, mockApi } from "./helpers";

afterEach(() => { vi.unstubAllGlobals(); document.cookie = "bh_csrf=; max-age=0"; });

const child = (over: Partial<Child> = {}): Child => ({
  id: "c1", display_name: "crianca_teste", age_band: "12_15",
  settings: { allow_open_matchmaking: false, profile_public: false, show_in_ranking: false, daily_minutes_limit: 60 },
  usage_today: { used_seconds: 750, limit_seconds: 3600, resets_at: "2026-10-15T03:00:00Z" },
  deletion_scheduled_for: null, ...over,
});

const EXPORT = {
  id: "e1", status: "ready", created_at: "2026-10-14T12:00:00+00:00", expires_at: "2026-10-21T12:00:00+00:00",
};

const base = (c: Child = child()) => ({
  "GET /guardian/children": { body: [c] },
  "GET /guardian/children/c1/export": { body: [] },
});

test("lista a criança vinculada com o tempo usado hoje e o limite", async () => {
  mockApi(base());
  render(<GuardianPage />);
  expect(await screen.findByRole("heading", { level: 3, name: "crianca_teste" })).toBeInTheDocument();
  expect(screen.getByText("Hoje: 12 min de 60 min.")).toBeInTheDocument();
  const bar = screen.getByRole("progressbar", { name: "Tempo usado hoje por crianca_teste" });
  expect((bar as HTMLProgressElement).max).toBe(3600);
  expect((bar as HTMLProgressElement).value).toBe(750);
  expect(screen.getByLabelText("Limite diário de tempo (minutos)")).toHaveValue(60);
  expect(screen.queryByText(/limite de hoje foi atingido/)).not.toBeInTheDocument();
});

test("limite atingido avisa que novas partidas ficam bloqueadas e a atual pode terminar", async () => {
  mockApi(base(child({ usage_today: { used_seconds: 4000, limit_seconds: 3600, resets_at: "2026-10-15T03:00:00Z" } })));
  render(<GuardianPage />);
  expect(await screen.findByText(/limite de hoje foi atingido/)).toHaveTextContent("A partida em andamento pode terminar");
  expect((screen.getByRole("progressbar") as HTMLProgressElement).value).toBe(3600);
});

test("sem limite definido mostra só o tempo jogado", async () => {
  mockApi(base(child({
    settings: { allow_open_matchmaking: false, profile_public: false, show_in_ranking: false, daily_minutes_limit: null },
    usage_today: { used_seconds: 300, limit_seconds: null, resets_at: "2026-10-15T03:00:00Z" },
  })));
  render(<GuardianPage />);
  expect(await screen.findByText("Hoje: 5 min jogados. Sem limite diário definido.")).toBeInTheDocument();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Limite diário de tempo (minutos)")).toHaveValue(null);
});

test("salvar envia o novo limite com CSRF e mostra o estado oficial devolvido", async () => {
  document.cookie = "bh_csrf=tok123";
  const fn = mockApi({
    ...base(),
    "PUT /guardian/children/c1/settings": { body: child({
      settings: { allow_open_matchmaking: true, profile_public: false, show_in_ranking: false, daily_minutes_limit: 90 },
      usage_today: { used_seconds: 750, limit_seconds: 5400, resets_at: "2026-10-15T03:00:00Z" } }) },
  });
  render(<GuardianPage />);
  const input = await screen.findByLabelText("Limite diário de tempo (minutos)");
  await userEvent.clear(input);
  await userEvent.type(input, "90");
  await userEvent.click(screen.getByLabelText(/Liberar partidas online com desconhecidos/));
  await userEvent.click(screen.getByRole("button", { name: "Salvar configurações de crianca_teste" }));
  expect(await screen.findByText("Configurações salvas.")).toBeInTheDocument();
  const put = fn.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PUT")!;
  expect(bodyOf(put[1] as RequestInit)).toEqual({
    daily_minutes_limit: 90, allow_open_matchmaking: true, profile_public: false, show_in_ranking: false });
  expect(((put[1] as RequestInit).headers as Record<string, string>)["X-CSRF-Token"]).toBe("tok123");
  expect(screen.getByText("Hoje: 12 min de 90 min.")).toBeInTheDocument();
});

test("campo em branco remove o limite (null)", async () => {
  const fn = mockApi({ ...base(), "PUT /guardian/children/c1/settings": { body: child() } });
  render(<GuardianPage />);
  await userEvent.clear(await screen.findByLabelText("Limite diário de tempo (minutos)"));
  await userEvent.click(screen.getByRole("button", { name: "Salvar configurações de crianca_teste" }));
  await screen.findByText("Configurações salvas.");
  const put = fn.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PUT")!;
  expect(bodyOf(put[1] as RequestInit).daily_minutes_limit).toBeNull();
});

test("limite fora de 15 a 600 é recusado no cliente, sem chamar o servidor", async () => {
  const fn = mockApi(base());
  render(<GuardianPage />);
  const input = await screen.findByLabelText("Limite diário de tempo (minutos)");
  for (const valor of ["10", "601"]) {
    await userEvent.clear(input);
    await userEvent.type(input, valor);
    await userEvent.click(screen.getByRole("button", { name: "Salvar configurações de crianca_teste" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(LIMIT_HELP);
  }
  expect(fn.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "PUT")).toBe(false);
});

test("erro do servidor (criança não vinculada, 404) aparece como alerta", async () => {
  mockApi({ ...base(), "PUT /guardian/children/c1/settings": { status: 404, body: {
    type: "not_found", title: "Conta supervisionada não encontrada" } } });
  render(<GuardianPage />);
  await screen.findByRole("heading", { level: 3, name: "crianca_teste" });
  await userEvent.click(screen.getByRole("button", { name: "Salvar configurações de crianca_teste" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Conta supervisionada não encontrada");
});

test("pedir exportação usa o endpoint do responsável e mostra o link de download", async () => {
  const fn = mockApi({ ...base(), "POST /guardian/children/c1/export": { status: 202, body: EXPORT } });
  render(<GuardianPage />);
  await userEvent.click(await screen.findByRole("button", { name: "Pedir exportação dos dados de crianca_teste" }));
  expect(await screen.findByText("Exportação pronta. Baixe o arquivo abaixo.")).toBeInTheDocument();
  const link = screen.getByRole("link", { name: /Baixar arquivo de/ });
  expect(link).toHaveAttribute("href", "/api/v1/guardian/children/c1/export/e1");
  expect(link).toHaveAttribute("download");
  expect(fn.mock.calls.some(([u, i]) => u === "/api/v1/guardian/children/c1/export" && i?.method === "POST")).toBe(true);
});

test("exportações já existentes são listadas", async () => {
  mockApi({ ...base(), "GET /guardian/children/c1/export": { body: [EXPORT] } });
  render(<GuardianPage />);
  const lista = await screen.findByRole("list", { name: "Exportações de crianca_teste" });
  expect(within(lista).getByRole("link")).toHaveAttribute("href", "/api/v1/guardian/children/c1/export/e1");
});

test("excluir a conta do menor exige a senha do responsável e a ciência do prazo", async () => {
  const fn = mockApi({
    ...base(),
    "POST /guardian/children/c1/delete": { status: 202, body: { scheduled_for: "2026-11-01T12:00:00+00:00" } },
    "GET /guardian/children/c1": { body: child({ deletion_scheduled_for: "2026-11-01T12:00:00+00:00" }) },
    "POST /guardian/children/c1/delete/cancel": { status: 204 },
  });
  render(<GuardianPage />);
  await userEvent.click(await screen.findByRole("button", { name: "Excluir a conta de crianca_teste…" }));
  const confirmar = screen.getByRole("button", { name: "Confirmar exclusão da conta de crianca_teste" });
  expect(confirmar).toBeDisabled();
  await userEvent.type(screen.getByLabelText("Confirme com a SUA senha (do responsável)"), "cavalo-bispo-torre-42");
  expect(confirmar).toBeDisabled(); // falta marcar a ciência
  await userEvent.click(screen.getByLabelText(/Entendo que, depois de 14 dias/));
  await userEvent.click(confirmar);
  expect(await screen.findByText(/A exclusão está agendada para/)).toBeInTheDocument();
  const post = fn.mock.calls.find(([u]) => u === "/api/v1/guardian/children/c1/delete")!;
  expect(bodyOf(post[1] as RequestInit)).toEqual({ password: "cavalo-bispo-torre-42" });
  await userEvent.click(screen.getByRole("button", { name: "Cancelar exclusão da conta de crianca_teste" }));
  await waitFor(() => expect(fn.mock.calls.some(([u]) => u === "/api/v1/guardian/children/c1/delete/cancel")).toBe(true));
});

test("senha errada do responsável mostra o erro e mantém o formulário", async () => {
  mockApi({ ...base(), "POST /guardian/children/c1/delete": { status: 403, body: {
    type: "invalid_credentials", title: "Senha incorreta" } } });
  render(<GuardianPage />);
  await userEvent.click(await screen.findByRole("button", { name: "Excluir a conta de crianca_teste…" }));
  await userEvent.type(screen.getByLabelText("Confirme com a SUA senha (do responsável)"), "errada-errada-12");
  await userEvent.click(screen.getByLabelText(/Entendo que, depois de 14 dias/));
  await userEvent.click(screen.getByRole("button", { name: "Confirmar exclusão da conta de crianca_teste" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Senha incorreta");
});

test("sem contas vinculadas explica como vincular e aceita o link do convite", async () => {
  const fn = mockApi({
    "GET /guardian/children": { body: [] },
    "POST /guardian/links/confirm": { body: child() },
    "GET /guardian/children/c1/export": { body: [] },
  });
  render(<GuardianPage />);
  expect(await screen.findByText(/Nenhuma conta vinculada/)).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Link ou código do convite recebido por e-mail"),
    "http://localhost:5173/guardian?token=AbCdEfGhIj_123-xyz");
  await userEvent.click(screen.getByRole("button", { name: "Confirmar vínculo" }));
  expect(await screen.findByText("crianca_teste agora está vinculado à sua conta.")).toBeInTheDocument();
  const post = fn.mock.calls.find(([u]) => u === "/api/v1/guardian/links/confirm")!;
  expect(bodyOf(post[1] as RequestInit)).toEqual({ token: "AbCdEfGhIj_123-xyz" });
  expect(await screen.findByRole("heading", { level: 3, name: "crianca_teste" })).toBeInTheDocument();
});

test("extractToken aceita o link inteiro ou só o código", () => {
  expect(extractToken("https://x.test/guardian?token=abc_DEF-123456")).toBe("abc_DEF-123456");
  expect(extractToken("  abc_DEF-123456  ")).toBe("abc_DEF-123456");
});

const adult: Me = {
  id: "u1", email: "responsavel@example.test", display_name: "responsavel_teste", email_verified: true,
  age_band: "18_plus", role: "user", supervised: false,
};

test("o botão Responsável aparece só para adultos com e-mail confirmado", async () => {
  mockApi({ "GET /me": { body: adult }, "GET /games": { body: [] } });
  const { unmount } = render(<App />);
  expect(await screen.findByRole("button", { name: "Responsável" })).toBeInTheDocument();
  unmount();
  mockApi({ "GET /me": { body: { ...adult, age_band: "12_15", supervised: true } }, "GET /games": { body: [] } });
  render(<App />);
  await screen.findByRole("button", { name: "Perfil" });
  expect(screen.queryByRole("button", { name: "Responsável" })).not.toBeInTheDocument();
});

test("abrir o painel pelo menu mostra a lista de filhos", async () => {
  mockApi({ "GET /me": { body: adult }, "GET /games": { body: [] }, ...base() });
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Responsável" }));
  expect(await screen.findByRole("heading", { level: 2, name: "Painel do responsável" })).toBeInTheDocument();
  expect(await screen.findByRole("heading", { level: 3, name: "crianca_teste" })).toBeInTheDocument();
});
