import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ProfilePage } from "../src/features/profile/ProfilePage";
import { chessMoveTexts, MoveList, toPortuguese } from "../src/features/tictactoe/MoveList";
import type { MatchView, Me, Preferences } from "../src/services/types";
import { bodyOf, mockApi } from "./helpers";

afterEach(() => { vi.unstubAllGlobals(); document.cookie = "bh_csrf=; max-age=0"; });

const prefs = (move_notation: Preferences["move_notation"]): Preferences => ({
  theme: "system", motion: "system", sound: true, move_confirmation: false, move_notation,
  piece_styles: {}, locale: "pt-BR",
});

const chess = (over: Partial<MatchView> = {}): MatchView => ({
  id: "m1", game_id: "chess", mode: "local", status: "in_progress", ply: 3,
  state: { schema_version: 1, fen: "x", moves: ["e2e4", "e7e5", "g1f3"] },
  to_move_seat: 2, legal_moves: [], result: null, end_reason: null, ai_level: null, seats: [],
  created_at: "2026-10-14T12:00:00Z", finished_at: null, san_moves: ["e4", "e5", "Nf3"], ...over,
});

test("toPortuguese troca só as letras das peças (R, D, T, C); bispo e roque ficam", () => {
  expect(toPortuguese("Nf3")).toBe("Cf3");
  expect(toPortuguese("Qxd8+")).toBe("Dxd8+");
  expect(toPortuguese("Rae1")).toBe("Tae1");
  expect(toPortuguese("Kg2")).toBe("Rg2");
  expect(toPortuguese("exd8=Q")).toBe("exd8=D");
  expect(toPortuguese("Bb5")).toBe("Bb5");
  expect(toPortuguese("O-O-O")).toBe("O-O-O");
});

test("chessMoveTexts: SAN, algébrica em português ou UCI conforme a preferência", () => {
  const m = chess();
  expect(chessMoveTexts(m, "san")).toEqual(["e4", "e5", "Nf3"]);
  expect(chessMoveTexts(m, "algebraic_pt")).toEqual(["e4", "e5", "Cf3"]);
  expect(chessMoveTexts(m, "uci")).toEqual(["e2e4", "e7e5", "g1f3"]);
});

test("a lista agrupa brancas e pretas e segue a preferência salva (padrão: português)", async () => {
  mockApi({ "GET /me/preferences": { body: prefs("algebraic_pt") } });
  render(<MoveList match={chess()} />);
  const lista = await screen.findByRole("list", { name: /Lances da partida/ });
  const itens = screen.getAllByRole("listitem").map((li) => li.textContent);
  expect(lista).toBeInTheDocument();
  expect(itens).toEqual(["e4 e5", "Cf3"]);
});

test("preferência UCI mostra as coordenadas do servidor", async () => {
  mockApi({ "GET /me/preferences": { body: prefs("uci") } });
  render(<MoveList match={chess()} />);
  expect(await screen.findByText("e2e4 e7e5")).toBeInTheDocument();
  expect(screen.getByText("g1f3")).toBeInTheDocument();
});

test("preferência SAN mostra as letras internacionais", async () => {
  mockApi({ "GET /me/preferences": { body: prefs("san") } });
  render(<MoveList match={chess()} />);
  expect(await screen.findByText("Nf3")).toBeInTheDocument();
});

test("sem preferência carregada vale o padrão e a lista aparece mesmo assim", async () => {
  mockApi({}); // GET /me/preferences responde 404
  render(<MoveList match={chess()} />);
  expect(await screen.findByText("Cf3")).toBeInTheDocument();
});

test("não aparece sem lances nem em outros jogos", () => {
  mockApi({});
  const { container, rerender } = render(<MoveList match={chess({ state: { schema_version: 1, fen: "x", moves: [] }, san_moves: [] })} />);
  expect(container).toBeEmptyDOMElement();
  rerender(<MoveList match={chess({ game_id: "checkers" })} />);
  expect(container).toBeEmptyDOMElement();
});

const me: Me = {
  id: "u1", email: "pessoa@example.test", display_name: "pessoa_teste", email_verified: true,
  age_band: "18_plus", role: "user", supervised: false,
};

test("o perfil permite escolher a notação e a envia no PUT das preferências", async () => {
  document.cookie = "bh_csrf=tok123";
  const fn = mockApi({
    "GET /me/profile": { body: { display_name: "pessoa_teste", avatar_key: "default", bio: null,
      is_public: true, show_in_ranking: false, display_name_change_allowed_at: null } },
    "GET /me/preferences": { body: prefs("algebraic_pt") },
    "PATCH /me/profile": { body: { display_name: "pessoa_teste", avatar_key: "default", bio: "",
      is_public: true, show_in_ranking: false, display_name_change_allowed_at: null } },
    "PUT /me/preferences": (init) => ({ body: bodyOf(init) }),
  });
  render(<ProfilePage me={me} />);
  const select = await screen.findByLabelText("Notação dos lances do xadrez");
  expect(select).toHaveValue("algebraic_pt");
  await userEvent.selectOptions(select, "uci");
  await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
  expect(await screen.findByText("Alterações salvas.")).toBeInTheDocument();
  const put = fn.mock.calls.find(([u, init]) => u === "/api/v1/me/preferences" && init?.method === "PUT")!;
  expect(bodyOf(put[1] as RequestInit).move_notation).toBe("uci");
});
