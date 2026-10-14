import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../src/app/App";
import { PrivacyPage } from "../src/features/profile/PrivacyPage";
import type { Me } from "../src/services/types";
import { bodyOf, mockApi } from "./helpers";

afterEach(() => { vi.unstubAllGlobals(); document.cookie = "bh_csrf=; max-age=0"; });

const me: Me = {
  id: "u1", email: "pessoa@example.test", display_name: "pessoa_teste", email_verified: true,
  age_band: "18_plus", role: "user", supervised: false, deletion_scheduled_for: null,
  deletion_by_guardian: false,
};
const pendingMe: Me = { ...me, deletion_scheduled_for: "2026-11-01T12:00:00+00:00" };

const exportRow = {
  id: "11111111-1111-4111-8111-111111111111", status: "ready",
  created_at: "2026-10-14T12:00:00+00:00", expires_at: "2026-10-21T12:00:00+00:00",
};

const noop = () => undefined;

test("lista as exportações existentes com link de download autenticado por cookie", async () => {
  mockApi({ "GET /me/export": { body: [exportRow] } });
  render(<PrivacyPage me={me} onDeletionScheduled={noop} onDeletionCancelled={noop} />);
  const link = await screen.findByRole("link", { name: /Baixar arquivo de/ });
  expect(link).toHaveAttribute("href", `/api/v1/me/export/${exportRow.id}`);
  expect(link).toHaveAttribute("download");
});

test("pedir exportação envia POST com CSRF e mostra o novo arquivo", async () => {
  document.cookie = "bh_csrf=tok123";
  const fn = mockApi({
    "GET /me/export": { body: [] },
    "POST /me/export": { status: 202, body: exportRow },
  });
  render(<PrivacyPage me={me} onDeletionScheduled={noop} onDeletionCancelled={noop} />);
  await userEvent.click(screen.getByRole("button", { name: "Pedir exportação dos meus dados" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Exportação pronta");
  expect(screen.getByRole("link", { name: /Baixar arquivo de/ })).toBeInTheDocument();
  const post = fn.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST");
  expect(((post?.[1] as RequestInit).headers as Record<string, string>)["X-CSRF-Token"]).toBe("tok123");
});

test("limite de uma exportação por dia aparece como mensagem acessível", async () => {
  mockApi({
    "GET /me/export": { body: [] },
    "POST /me/export": { status: 429, body: {
      type: "export_rate_limited", title: "Exportação já solicitada",
      detail: "Só é possível pedir uma exportação a cada 24 horas." } },
  });
  render(<PrivacyPage me={me} onDeletionScheduled={noop} onDeletionCancelled={noop} />);
  await userEvent.click(screen.getByRole("button", { name: "Pedir exportação dos meus dados" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("a cada 24 horas");
});

test("excluir a conta exige senha e confirmação explícita", async () => {
  const onScheduled = vi.fn();
  const fn = mockApi({
    "GET /me/export": { body: [] },
    "POST /me/delete": { status: 202, body: { scheduled_for: "2026-11-01T12:00:00+00:00" } },
  });
  render(<PrivacyPage me={me} onDeletionScheduled={onScheduled} onDeletionCancelled={noop} />);
  await userEvent.click(screen.getByRole("button", { name: "Excluir minha conta…" }));
  const confirmar = screen.getByRole("button", { name: "Excluir minha conta" });
  expect(confirmar).toBeDisabled();
  await userEvent.type(screen.getByLabelText("Confirme com a sua senha"), "cavalo-bispo-torre-42");
  expect(confirmar).toBeDisabled(); // falta marcar a ciência de que é definitivo
  await userEvent.click(screen.getByLabelText(/Entendo que, depois de 14 dias/));
  expect(confirmar).toBeEnabled();
  await userEvent.click(confirmar);
  await waitFor(() => expect(onScheduled).toHaveBeenCalledWith("2026-11-01T12:00:00+00:00"));
  const del = fn.mock.calls.find(([url]) => String(url).endsWith("/me/delete"));
  expect(bodyOf(del?.[1] as RequestInit)).toEqual({ password: "cavalo-bispo-torre-42" });
});

test("senha incorreta mostra o erro e não agenda a exclusão", async () => {
  const onScheduled = vi.fn();
  mockApi({
    "GET /me/export": { body: [] },
    "POST /me/delete": { status: 401, body: { type: "invalid_credentials", title: "Senha incorreta" } },
  });
  render(<PrivacyPage me={me} onDeletionScheduled={onScheduled} onDeletionCancelled={noop} />);
  await userEvent.click(screen.getByRole("button", { name: "Excluir minha conta…" }));
  await userEvent.type(screen.getByLabelText("Confirme com a sua senha"), "errada");
  await userEvent.click(screen.getByLabelText(/Entendo que/));
  await userEvent.click(screen.getByRole("button", { name: "Excluir minha conta" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Senha incorreta");
  expect(onScheduled).not.toHaveBeenCalled();
});

test("voltar descarta a senha digitada e esconde o formulário de exclusão", async () => {
  mockApi({ "GET /me/export": { body: [] } });
  render(<PrivacyPage me={me} onDeletionScheduled={noop} onDeletionCancelled={noop} />);
  await userEvent.click(screen.getByRole("button", { name: "Excluir minha conta…" }));
  await userEvent.type(screen.getByLabelText("Confirme com a sua senha"), "segredo");
  await userEvent.click(screen.getByRole("button", { name: "Voltar" }));
  expect(screen.queryByLabelText("Confirme com a sua senha")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Excluir minha conta…" }));
  expect(screen.getByLabelText("Confirme com a sua senha")).toHaveValue("");
});

test("conta em carência mostra a data e permite cancelar", async () => {
  const onCancelled = vi.fn();
  mockApi({
    "GET /me/export": { body: [] },
    "POST /me/delete/cancel": { status: 204 },
  });
  render(<PrivacyPage me={pendingMe} onDeletionScheduled={noop} onDeletionCancelled={onCancelled} />);
  expect(screen.getByRole("status")).toHaveTextContent("agendada para");
  expect(screen.queryByRole("button", { name: "Excluir minha conta…" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Cancelar exclusão" }));
  await waitFor(() => expect(onCancelled).toHaveBeenCalled());
});

test("exclusão pedida pelo responsável não oferece cancelamento ao menor", async () => {
  mockApi({ "GET /me/export": { body: [] } });
  render(<PrivacyPage me={{ ...pendingMe, deletion_by_guardian: true }}
    onDeletionScheduled={noop} onDeletionCancelled={noop} />);
  expect(screen.queryByRole("button", { name: "Cancelar exclusão" })).not.toBeInTheDocument();
  expect(screen.getByText(/só ele pode cancelá-la/)).toBeInTheDocument();
});

test("no app, conta em carência só vê Privacidade e Sair", async () => {
  mockApi({ "GET /me": { body: pendingMe }, "GET /me/export": { body: [] } });
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Privacidade" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sair" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Jogar" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Perfil" })).not.toBeInTheDocument();
});

test("no app, usuário comum abre Privacidade pelo menu e, ao excluir, sai da sessão", async () => {
  mockApi({
    "GET /me": { body: me },
    "GET /games": { body: [] },
    "GET /me/export": { body: [] },
    "POST /me/delete": { status: 202, body: { scheduled_for: "2026-11-01T12:00:00+00:00" } },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Privacidade" }));
  await userEvent.click(await screen.findByRole("button", { name: "Excluir minha conta…" }));
  await userEvent.type(screen.getByLabelText("Confirme com a sua senha"), "cavalo-bispo-torre-42");
  await userEvent.click(screen.getByLabelText(/Entendo que/));
  await userEvent.click(screen.getByRole("button", { name: "Excluir minha conta" }));
  expect(await screen.findByText(/Exclusão agendada para/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Entrar" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Perfil" })).not.toBeInTheDocument();
});
