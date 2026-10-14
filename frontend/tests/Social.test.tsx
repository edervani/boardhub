import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../src/app/App";
import { ModerationPage } from "../src/features/moderation/ModerationPage";
import { FriendsPage } from "../src/features/social/FriendsPage";
import { ReportButton } from "../src/features/social/ReportButton";
import type { Me } from "../src/services/types";
import { bodyOf, mockApi } from "./helpers";

afterEach(() => { vi.unstubAllGlobals(); document.cookie = "bh_csrf=; max-age=0"; });

const me: Me = {
  id: "u1", email: "pessoa@example.test", display_name: "pessoa_teste", email_verified: true,
  age_band: "18_plus", role: "user", supervised: false, deletion_scheduled_for: null,
  deletion_by_guardian: false,
};

const person = (n: string) => ({ display_name: n, avatar_key: "default" });

const friendsRoutes = {
  "GET /friends": { body: [{ ...person("amigo_teste"), friendship_id: "f1", since: "2026-10-14T12:00:00Z" }] },
  "GET /friends/requests": { body: { incoming: [{ ...person("pedinte_teste"), friendship_id: "f2", created_at: "2026-10-14T12:00:00Z" }], outgoing: [] } },
  "GET /invitations": { body: [{ id: "i1", game_id: "chess", status: "pending", created_at: "2026-10-14T12:00:00Z", expires_at: null, match_id: null, other: person("amigo_teste") }] },
  "GET /blocks": { body: [] },
};

test("Amigos lista amigos, pedidos e convites só com apelidos e sem chat", async () => {
  mockApi(friendsRoutes);
  render(<FriendsPage onMatchStarted={() => undefined} />);
  expect(await screen.findByText("amigo_teste", { selector: "strong" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Aceitar pedido de pedinte_teste" })).toBeInTheDocument();
  expect(screen.getByText(/convidou você para Xadrez/)).toBeInTheDocument();
  expect(screen.getByText(/Não há conversa livre/)).toBeInTheDocument();
  expect(document.body.textContent).not.toContain("@");
});

test("pedir amizade envia o apelido com CSRF", async () => {
  document.cookie = "bh_csrf=tok1";
  const fn = mockApi({
    ...friendsRoutes,
    "POST /friends/requests": { status: 201, body: { ...person("novo_amigo"), friendship_id: "f3", created_at: "2026-10-14T12:00:00Z" } },
  });
  render(<FriendsPage onMatchStarted={() => undefined} />);
  await userEvent.type(await screen.findByLabelText("Apelido da pessoa"), "novo_amigo");
  await userEvent.click(screen.getByRole("button", { name: "Enviar pedido" }));
  expect(await screen.findByText("Pedido enviado.")).toBeInTheDocument();
  const call = fn.mock.calls.find(([u, i]) => String(u).endsWith("/friends/requests") && i?.method === "POST");
  expect(bodyOf(call?.[1])).toEqual({ display_name: "novo_amigo" });
  expect((call?.[1]?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("tok1");
});

test("aceitar convite entra na partida; erro do servidor aparece em alerta", async () => {
  const started = vi.fn();
  mockApi({ ...friendsRoutes, "POST /invitations/i1/accept": { body: { id: "m1" } } });
  render(<FriendsPage onMatchStarted={started} />);
  await userEvent.click(await screen.findByRole("button", { name: "Aceitar convite de amigo_teste" }));
  await waitFor(() => expect(started).toHaveBeenCalled());
});

test("convite expirado mostra a mensagem do servidor", async () => {
  mockApi({ ...friendsRoutes, "POST /invitations/i1/accept": { status: 404, body: { type: "invitation_not_found", title: "Convite não encontrado ou expirado" } } });
  render(<FriendsPage onMatchStarted={() => undefined} />);
  await userEvent.click(await screen.findByRole("button", { name: "Aceitar convite de amigo_teste" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Convite não encontrado ou expirado");
});

test("denunciar partida oferece só motivos aplicáveis e envia a denúncia", async () => {
  document.cookie = "bh_csrf=tok2";
  const fn = mockApi({ "POST /reports": { status: 201, body: { id: "r1", status: "open", created_at: "x" } } });
  render(<ReportButton targetType="match" targetId="m-123" label="Denunciar o oponente" />);
  await userEvent.click(screen.getByRole("button", { name: "Denunciar o oponente" }));
  expect(screen.queryByRole("option", { name: "Apelido ofensivo" })).not.toBeInTheDocument();
  await userEvent.type(screen.getByLabelText(/Detalhes/), "jogou rápido demais");
  await userEvent.click(screen.getByRole("button", { name: "Enviar denúncia" }));
  expect(await screen.findByText(/Denúncia enviada/)).toBeInTheDocument();
  expect(bodyOf(fn.mock.calls[0]?.[1])).toEqual({
    target_type: "match", target_id: "m-123", reason: "cheating", note: "jogou rápido demais",
  });
});

const item = {
  id: "r1", status: "open", target_type: "user", reason: "offensive_bio", note: "<b>texto</b>",
  created_at: "2026-10-14T12:00:00Z", target_user_id: "u9", target_display_name: "alvo_teste",
  target_bio: "bio ofensiva", target_status: "active", match_id: null, open_reports_on_target: 2,
  resolution_action: null, resolved_at: null,
};

test("fila de moderação mostra o conteúdo como texto e resolve com a ação escolhida", async () => {
  document.cookie = "bh_csrf=tok3";
  const fn = mockApi({
    "GET /admin/reports?status=open": { body: { items: [item], total: 1 } },
    "POST /admin/reports/r1/resolve": { body: { ...item, status: "resolved" } },
  });
  render(<ModerationPage />);
  expect(await screen.findByRole("heading", { name: "alvo_teste" })).toBeInTheDocument();
  expect(screen.getByText("<b>texto</b>")).toBeInTheDocument(); // texto, não HTML
  expect(document.querySelector("li b")).toBeNull();
  expect(document.body.textContent).not.toMatch(/denunciante/i);
  await userEvent.click(screen.getByLabelText(/Ocultar conteúdo/));
  await userEvent.click(screen.getByRole("button", { name: "Suspender alvo_teste" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Suspender: denúncia resolvida."));
  const post = fn.mock.calls.find(([, i]) => i?.method === "POST");
  expect(bodyOf(post?.[1])).toEqual({ action: "suspend", hide_content: true });
});

test("403 da moderação aparece como alerta", async () => {
  mockApi({ "GET /admin/reports?status=open": { status: 403, body: { type: "forbidden", title: "Acesso restrito à moderação" } } });
  render(<ModerationPage />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Acesso restrito à moderação");
});

test("abas Amigos e Moderação respeitam o papel", async () => {
  mockApi({ "GET /me": { body: me }, ...friendsRoutes });
  const { unmount } = render(<App />);
  expect(await screen.findByRole("button", { name: "Amigos" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Moderação" })).not.toBeInTheDocument();
  unmount();
  mockApi({ "GET /me": { body: { ...me, role: "moderator" } }, ...friendsRoutes });
  render(<App />);
  expect(await screen.findByRole("button", { name: "Moderação" })).toBeInTheDocument();
});
