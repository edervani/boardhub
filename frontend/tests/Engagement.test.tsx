import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { AchievementsPage } from "../src/features/engagement/AchievementsPage";
import { DailyPage } from "../src/features/engagement/DailyPage";
import { NotificationBell } from "../src/features/engagement/NotificationBell";
import { bodyOf, mockApi } from "./helpers";

afterEach(() => { vi.unstubAllGlobals(); document.cookie = "bh_csrf=; max-age=0"; });

const note = (over: Record<string, unknown> = {}) => ({
  id: "n1", kind: "your_turn", title: "Sua vez de jogar", body: "Seu oponente jogou. É a sua vez em Xadrez.",
  created_at: "2026-10-14T15:00:00Z", read: false, ...over,
});
const PREFS = { kinds: [
  { kind: "your_turn", label: "Vez de jogar numa partida online", enabled: true },
  { kind: "match_ended", label: "Partida online encerrada", enabled: true },
] };

test("sino mostra a contagem, anuncia com aria-live educado e marca como lida", async () => {
  let unread = true;
  const fn = mockApi({
    "GET /me/notifications?limit=20": () => ({ body: { items: [note({ read: !unread })], unread_count: unread ? 1 : 0 } }),
    "GET /me/notification-preferences": { body: PREFS },
    "POST /me/notifications/n1/read": () => { unread = false; return { status: 204 }; },
  });
  render(<NotificationBell />);
  const button = await screen.findByRole("button", { name: "Notificações (1 não lida)" });
  const live = screen.getByRole("status");
  expect(live).toHaveAttribute("aria-live", "polite");
  await waitFor(() => expect(live).toHaveTextContent("Você tem 1 notificação nova."));
  await userEvent.click(button);
  expect(await screen.findByText("Sua vez de jogar")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Marcar como lida" }));
  expect(await screen.findByRole("button", { name: "Notificações" })).toBeInTheDocument();
  expect(fn.mock.calls.some(([u]) => String(u).endsWith("/n1/read"))).toBe(true);
});

test("preferências permitem desativar um tipo de aviso", async () => {
  const fn = mockApi({
    "GET /me/notifications?limit=20": { body: { items: [], unread_count: 0 } },
    "GET /me/notification-preferences": { body: PREFS },
    "PUT /me/notification-preferences": (init) => ({
      body: { kinds: PREFS.kinds.map((k) => ({ ...k, enabled: (bodyOf(init).kinds as Record<string, boolean>)[k.kind] ?? k.enabled })) },
    }),
  });
  render(<NotificationBell />);
  await userEvent.click(await screen.findByRole("button", { name: "Notificações" }));
  expect(screen.getByText("Nenhuma notificação.")).toBeInTheDocument();
  const box = await screen.findByLabelText("Vez de jogar numa partida online");
  await userEvent.click(box);
  await waitFor(() => expect(box).not.toBeChecked());
  const put = fn.mock.calls.find(([, init]) => init?.method === "PUT")!;
  expect(bodyOf(put[1])).toEqual({ kinds: { your_turn: false } });
});

const exercise = {
  id: "tt-quiz-1", game_id: "tictactoe", lesson_id: "tt-l1", concept_key: "tt.rules", concept_title: "Regras",
  type: "rule_quiz", difficulty: 1, prompt: "Quantas casas tem o tabuleiro?", position: null, legal_moves: [],
  options: [{ id: "a", text: "Nove" }, { id: "b", text: "Dez" }], hints_used: 0, hints_available: 0,
};
const daily = (status: string) => ({
  body: {
    day: "2026-10-14", resets_at: "2026-10-15T03:00:00Z", completed_total: 3,
    challenges: [{ game_id: "tictactoe", game_name: "Jogo da velha", day: "2026-10-14", resets_at: "2026-10-15T03:00:00Z",
      status, correct: status === "answered" ? true : null, exercise, explanation: status === "answered" ? "São 3 por 3." : null }],
  },
});

test("desafio do dia: responde uma vez e mostra a explicação, sem cobrança por faltar", async () => {
  const fn = mockApi({
    "GET /daily-challenge": daily("pending"),
    "POST /daily-challenge/tictactoe/attempt": { body: { correct: true, feedback: "Certo!", explanation: "São 3 por 3.", completed_total: 4 } },
  });
  render(<DailyPage />);
  expect(await screen.findByRole("heading", { level: 3, name: "Jogo da velha" })).toBeInTheDocument();
  expect(screen.getByText(/Se você faltar um dia, nada se perde/)).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Nove"));
  await userEvent.click(screen.getByRole("button", { name: "Responder" }));
  expect(await screen.findByText("São 3 por 3.")).toBeInTheDocument();
  expect(screen.getByText(/Desafios respondidos até agora: 4/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Responder" })).toBeDisabled();
  const post = fn.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(bodyOf(post[1])).toEqual({ answer: "a" });
});

test("desafio já respondido abre bloqueado", async () => {
  mockApi({ "GET /daily-challenge": daily("answered") });
  render(<DailyPage />);
  expect(await screen.findByText("São 3 por 3.")).toBeInTheDocument();
  expect(screen.getByRole("group")).toBeDisabled();
});

test("conquistas: mostra progresso das pendentes e a data das conquistadas", async () => {
  mockApi({
    "GET /me/achievements": { body: { definition_version: "1.0.0", earned_count: 1, items: [
      { key: "first_match", title: "Primeira partida", description: "Terminou a sua primeira partida.", game_id: null, earned: true, earned_at: "2026-10-14T15:00:00Z", progress: 1, target: 1 },
      { key: "matches_10", title: "Dez partidas", description: "Terminou 10 partidas.", game_id: null, earned: false, earned_at: null, progress: 4, target: 10 },
    ] } },
  });
  render(<AchievementsPage />);
  expect(await screen.findByRole("heading", { level: 3, name: /Primeira partida/ })).toBeInTheDocument();
  expect(screen.getByText(/1 de 2 conquistas/)).toBeInTheDocument();
  expect(screen.getByText("Progresso: 4 de 10")).toBeInTheDocument();
  expect((screen.getByLabelText("Progresso: 4 de 10") as HTMLProgressElement).value).toBe(4);
});
