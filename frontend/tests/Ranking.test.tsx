import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../src/app/App";
import { LobbyPage } from "../src/features/lobby/LobbyPage";
import { OnlineMatch, type BoardRenderer } from "../src/features/lobby/OnlineMatch";
import { onlineStatusText, ratingChangeText } from "../src/features/lobby/onlineStatus";
import { ProfilePage } from "../src/features/profile/ProfilePage";
import { ratingText, streakText } from "../src/features/profile/StatsPanel";
import { RankingPage } from "../src/features/ranking/RankingPage";
import type {
  GameStats, LeaderboardPage, MatchView, Me, Profile, RatingInfo, Stats,
} from "../src/services/types";
import { FakeWebSocket, bodyOf, installFakeWebSocket, mockApi, type Handler } from "./helpers";

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); document.cookie = "bh_csrf=; max-age=0"; });

const me: Me = { id: "u1", email: "a@example.test", display_name: "jogador_teste_01",
  email_verified: true, age_band: "18_plus", role: "user", supervised: false };

const GAMES = [
  { id: "tictactoe", name: "Jogo da velha", age_rating: "L", age_rating_label: "Livre", ranked_enabled: false },
  { id: "checkers", name: "Damas", age_rating: "L", age_rating_label: "Livre", ranked_enabled: false },
  { id: "chess", name: "Xadrez", age_rating: "L", age_rating_label: "Livre", ranked_enabled: true },
];

const entry = (rank: number, name: string, rating: number, games = 12) =>
  ({ rank, display_name: name, avatar_key: "default", rating, games_played: games });

const page = (items: ReturnType<typeof entry>[], next: string | null = null): LeaderboardPage =>
  ({ game_id: "chess", min_games: 10, items, next_cursor: next });

// ---------- aba Ranking ----------

test("o ranking lista só jogos ranqueados e mostra a tabela com posição, jogador, rating e partidas", async () => {
  const fn = mockApi({
    "GET /games": { body: GAMES },
    "GET /ranking/chess?limit=20": { body: page([entry(1, "ana_xadrez", 1500), entry(2, "jogador_teste_01", 1400, 30)]) },
  });
  render(<RankingPage me={me} />);
  const tabela = await screen.findByRole("table", { name: /Ranking de Xadrez/ });
  const linhas = within(tabela).getAllByRole("row");
  expect(linhas).toHaveLength(3); // cabeçalho + 2
  expect(within(linhas[1]!).getByText("1º")).toBeInTheDocument();
  expect(within(linhas[1]!).getByText("ana_xadrez")).toBeInTheDocument();
  expect(within(linhas[1]!).getByText("1500")).toBeInTheDocument();
  expect(within(linhas[2]!).getByText("jogador_teste_01 (você)")).toBeInTheDocument();
  expect(within(tabela).getAllByRole("columnheader").map((c) => c.textContent))
    .toEqual(["Posição", "Jogador", "Rating", "Partidas"]);
  const opcoes = within(screen.getByLabelText("Jogo")).getAllByRole("option").map((o) => o.textContent);
  expect(opcoes).toEqual(["Xadrez"]); // velha e damas não têm ranking
  expect(screen.getByText(/pelo menos 10 partidas ranqueadas/)).toBeInTheDocument();
  expect(fn).toHaveBeenCalledWith("/api/v1/ranking/chess?limit=20", expect.anything());
});

test("visitante também vê o ranking e nenhum dado além do apelido", async () => {
  mockApi({
    "GET /games": { body: GAMES },
    "GET /ranking/chess?limit=20": { body: page([entry(1, "ana_xadrez", 1500)]) },
  });
  const { container } = render(<RankingPage me={null} />);
  await screen.findByRole("table");
  expect(screen.queryByText(/\(você\)/)).not.toBeInTheDocument();
  expect(container.textContent).not.toMatch(/@/);
});

test("carregar mais pede a próxima página com o cursor e acrescenta as linhas", async () => {
  const fn = mockApi({
    "GET /games": { body: GAMES },
    "GET /ranking/chess?limit=20": { body: page([entry(1, "ana_xadrez", 1500)], "Mg") },
    "GET /ranking/chess?limit=20&cursor=Mg": { body: page([entry(2, "bia_xadrez", 1400)]) },
  });
  render(<RankingPage me={me} />);
  await screen.findByText("ana_xadrez");
  await userEvent.click(screen.getByRole("button", { name: "Carregar mais" }));
  expect(await screen.findByText("bia_xadrez")).toBeInTheDocument();
  expect(screen.getByText("ana_xadrez")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Carregar mais" })).not.toBeInTheDocument();
  expect(fn).toHaveBeenCalledWith("/api/v1/ranking/chess?limit=20&cursor=Mg", expect.anything());
});

test("ranking vazio explica quem entra; erro do servidor vira alerta", async () => {
  mockApi({
    "GET /games": { body: GAMES },
    "GET /ranking/chess?limit=20": { body: page([]) },
  });
  const { unmount } = render(<RankingPage me={me} />);
  expect(await screen.findByText("Ninguém no ranking de Xadrez ainda.")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  unmount();
  mockApi({
    "GET /games": { body: GAMES },
    "GET /ranking/chess?limit=20": { status: 429, body: { type: "rate_limited", title: "Muitas tentativas" } },
  });
  render(<RankingPage me={me} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Muitas tentativas");
});

test("sem jogo ranqueado a aba avisa em texto", async () => {
  mockApi({ "GET /games": { body: GAMES.slice(0, 2) } });
  render(<RankingPage me={me} />);
  expect(await screen.findByText("Nenhum jogo tem ranking no momento.")).toBeInTheDocument();
});

test("o menu Ranking aparece para visitantes e abre a página", async () => {
  mockApi({
    "GET /me": { status: 401 },
    "GET /games": { body: GAMES },
    "GET /ranking/chess?limit=20": { body: page([entry(1, "ana_xadrez", 1500)]) },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Ranking" }));
  expect(await screen.findByRole("heading", { level: 2, name: "Ranking" })).toBeInTheDocument();
  expect(await screen.findByText("ana_xadrez")).toBeInTheDocument();
});

// ---------- estatísticas no perfil ----------

const rating = (over: Partial<RatingInfo> = {}): RatingInfo => ({
  rating: 1220, games_played: 1, provisional: true, listed: false, games_until_listed: 9,
  history: [{ match_id: "m1", created_at: "2026-10-14T12:00:00Z", before: 1200, after: 1220, delta: 20 }],
  ...over,
});

const xadrez = (over: Partial<GameStats> = {}): GameStats => ({
  game_id: "chess", name: "Xadrez", played: 4, wins: 2, losses: 1, draws: 1, win_rate: 0.5,
  by_mode: [
    { mode: "ai", played: 3, wins: 1, losses: 1, draws: 1, win_rate: 0.3333 },
    { mode: "online_ranked", played: 1, wins: 1, losses: 0, draws: 0, win_rate: 1 },
  ],
  streak: { kind: "win", length: 2 }, rating: rating(), ...over,
});

const profile = (over: Partial<Profile> = {}): Profile => ({
  display_name: "jogador_teste_01", avatar_key: "default", bio: null, is_public: true,
  show_in_ranking: true, display_name_change_allowed_at: null, ...over,
});

const PREFS = { theme: "system", motion: "system", sound: true, move_confirmation: false,
  piece_styles: {}, locale: "pt-BR" };

const SEM_PARTIDAS: Stats = { games: [] };

function abrirPerfil(stats: Handler, prof: Profile = profile()) {
  return mockApi({
    "GET /me/profile": { body: prof },
    "GET /me/preferences": { body: PREFS },
    "GET /me/stats": stats,
    "PATCH /me/profile": (init) => ({ body: { ...prof, ...bodyOf(init) } }),
    "PUT /me/preferences": { body: PREFS },
  });
}

test("o perfil mostra totais, modos, sequência, rating e histórico recontados pelo servidor", async () => {
  const todos: Stats = { games: [
    xadrez(),
    { ...xadrez(), game_id: "tictactoe", name: "Jogo da velha", played: 0, wins: 0, losses: 0, draws: 0,
      win_rate: null, by_mode: [], streak: { kind: "none", length: 0 }, rating: null },
  ] };
  abrirPerfil({ body: todos });
  render(<ProfilePage me={me} />);
  const cartao = (await screen.findByRole("heading", { level: 4, name: "Xadrez" })).closest("section")!;
  expect(within(cartao).getByText(/4 partida\(s\): 2 vitória\(s\), 1 derrota\(s\), 1 empate\(s\) \(50% de vitórias\)/))
    .toBeInTheDocument();
  expect(within(cartao).getByText("Sequência atual: 2 vitórias seguidas.")).toBeInTheDocument();
  const modos = within(cartao).getByRole("table", { name: /Resultados por modo em Xadrez/ });
  expect(within(modos).getByRole("rowheader", { name: "Online ranqueada" })).toBeInTheDocument();
  expect(within(modos).getByRole("rowheader", { name: "Contra a IA" })).toBeInTheDocument();
  expect(within(cartao).getByText(/Rating 1220 \(provisório\), 1 partida\(s\) ranqueada\(s\)\. Faltam 9/)).toBeInTheDocument();
  const hist = within(cartao).getByRole("table", { name: /Últimas variações de rating em Xadrez/ });
  expect(within(hist).getByText("+20")).toBeInTheDocument();
  const velha = screen.getByRole("heading", { level: 4, name: "Jogo da velha" }).closest("section")!;
  expect(within(velha).getByText("Nenhuma partida concluída ainda.")).toBeInTheDocument();
  expect(within(velha).queryByText(/Rating/)).not.toBeInTheDocument(); // velha não tem ranking
});

test("falha ao carregar as estatísticas vira alerta sem derrubar o perfil", async () => {
  abrirPerfil({ status: 500, body: { type: "error", title: "Algo deu errado" } });
  render(<ProfilePage me={me} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Algo deu errado");
  expect(screen.getByRole("heading", { level: 2, name: "Seu perfil" })).toBeInTheDocument();
});

test("textos de sequência e de rating", () => {
  expect(streakText({ kind: "none", length: 0 })).toBe("Sem partidas concluídas.");
  expect(streakText({ kind: "win", length: 1 })).toBe("1 vitória seguida.");
  expect(streakText({ kind: "loss", length: 3 })).toBe("3 derrotas seguidas.");
  expect(streakText({ kind: "draw", length: 1 })).toBe("1 empate seguido.");
  expect(streakText({ kind: "draw", length: 2 })).toBe("2 empates seguidos.");
  expect(ratingText(rating({ listed: true, games_until_listed: 0, provisional: false, games_played: 40 })))
    .toBe("Rating 1220, 40 partida(s) ranqueada(s). Você aparece no ranking.");
  expect(ratingText(rating({ games_until_listed: 0, games_played: 12 })))
    .toContain("não aparece no ranking (perfil privado ou oculto)");
});

test("adulto escolhe aparecer no ranking e o campo vai no PATCH; sem perfil público a opção trava", async () => {
  const fn = abrirPerfil({ body: SEM_PARTIDAS });
  render(<ProfilePage me={me} />);
  const caixa = await screen.findByRole("checkbox", { name: "Aparecer no ranking público" });
  expect(caixa).toBeChecked();
  await userEvent.click(caixa);
  await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await screen.findByText("Alterações salvas.");
  const patch = fn.mock.calls.find(([url, init]) => url === "/api/v1/me/profile" && init?.method === "PATCH")!;
  expect(bodyOf(patch[1])).toMatchObject({ is_public: true, show_in_ranking: false });
  await userEvent.click(screen.getByRole("checkbox", { name: "Perfil público" }));
  expect(screen.getByRole("checkbox", { name: "Aparecer no ranking público" })).toBeDisabled();
  expect(screen.getByRole("checkbox", { name: "Aparecer no ranking público" })).not.toBeChecked();
});

test("menor não envia show_in_ranking e só pode sair do ranking", async () => {
  const menor: Me = { ...me, age_band: "12_15", supervised: true };
  const fn = abrirPerfil({ body: SEM_PARTIDAS }, profile({ is_public: false, show_in_ranking: false }));
  render(<ProfilePage me={menor} />);
  const caixa = await screen.findByRole("checkbox", { name: "Aparecer no ranking público" });
  expect(caixa).toBeDisabled();
  expect(screen.getByText(/Menores só aparecem no ranking por decisão do responsável/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await screen.findByText("Alterações salvas.");
  const patch = fn.mock.calls.find(([url, init]) => url === "/api/v1/me/profile" && init?.method === "PATCH")!;
  expect(bodyOf(patch[1])).not.toHaveProperty("show_in_ranking");
});

// ---------- lobby e partida ranqueados ----------

const renderBoard: BoardRenderer = ({ playable, onPlay }) => (
  <div data-testid="board" data-playable={playable.join(",")}>
    <button type="button" onClick={() => onPlay("e2e4")}>jogar</button>
  </div>
);

const ranked = (over: Partial<MatchView> = {}): MatchView => ({
  id: "m1", game_id: "chess", mode: "online_ranked", status: "in_progress", ply: 4,
  state: { schema_version: 1, fen: "x" }, to_move_seat: 1, legal_moves: ["e2e4"], result: null,
  end_reason: null, ai_level: null, created_at: "2026-10-14T00:00:00Z", finished_at: null,
  seats: [{ seat: 1, is_ai: false, is_you: true }, { seat: 2, is_ai: false, is_you: false }],
  players: [
    { seat: 1, display_name: "jogador_teste_01", connected: true, grace_deadline: null },
    { seat: 2, display_name: "jogador_teste_02", connected: true, grace_deadline: null },
  ],
  invite_code: null, invite_expires_at: null, draw_offer_by_seat: null, ...over,
});

const caixas = () => screen.getAllByRole("checkbox", { name: "Partida ranqueada" });

function abrirLobby(routes: Record<string, Handler> = {}, user: Me = me) {
  installFakeWebSocket();
  const fn = mockApi({
    "GET /games": { body: GAMES },
    "GET /me/active-matches": { body: [] },
    "GET /matches/m1": { body: ranked() },
    ...routes,
  });
  render(<LobbyPage me={user} renderBoard={renderBoard} pollMs={20} />);
  return fn;
}

test("convite ranqueado só é oferecido para jogo com ranking e envia mode online_ranked", async () => {
  const fn = abrirLobby({
    "POST /matches": { status: 201, body: ranked({ status: "waiting", invite_code: "ABCD2345",
      to_move_seat: null, legal_moves: [], seats: [{ seat: 1, is_ai: false, is_you: true }] }) },
  });
  expect(caixas()[0]).toBeDisabled(); // jogo da velha (padrão) não tem ranking
  expect(screen.getByText("Este jogo não tem partidas ranqueadas.", { selector: "#invite-ranked-hint" }))
    .toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Jogo do convite"), "chess");
  await waitFor(() => expect(caixas()[0]).toBeEnabled());
  await userEvent.click(caixas()[0]!);
  expect(screen.getByText(/O resultado altera seu rating/, { selector: "#invite-ranked-hint" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Criar convite" }));
  expect(await screen.findByText("ABCD2345")).toBeInTheDocument();
  const post = fn.mock.calls.find(([url, init]) => url === "/api/v1/matches" && init?.method === "POST")!;
  expect(bodyOf(post[1])).toEqual({ game_id: "chess", mode: "online_ranked" });
});

test("fila ranqueada envia ranked, mostra a faixa de rating e abre a partida ao parear", async () => {
  let fila: Record<string, unknown> = { state: "queued", game_id: "chess", waited_seconds: 0,
    offer_ai: false, match_id: null, ranked: true, rating_window: 100 };
  const fn = abrirLobby({
    "POST /matchmaking/queue": () => ({ status: 202, body: fila }),
    "GET /matchmaking/queue": () => ({ body: fila }),
  });
  await userEvent.selectOptions(screen.getByLabelText("Jogo da fila"), "chess");
  await waitFor(() => expect(caixas()[1]).toBeEnabled());
  await userEvent.click(caixas()[1]!);
  await userEvent.click(screen.getByRole("button", { name: "Entrar na fila" }));
  expect(await screen.findByText(/Procurando oponente ranqueado de Xadrez/)).toBeInTheDocument();
  expect(screen.getByText(/rating próximo ao seu \(± 100\)/)).toBeInTheDocument();
  const post = fn.mock.calls.find(([url, init]) => url === "/api/v1/matchmaking/queue" && init?.method === "POST")!;
  expect(bodyOf(post[1])).toEqual({ game_id: "chess", ranked: true });
  fila = { state: "queued", game_id: "chess", waited_seconds: 25, offer_ai: false, match_id: null,
    ranked: true, rating_window: 200 };
  expect(await screen.findByText(/\(± 200\)/)).toBeInTheDocument();
  fila = { state: "matched", game_id: "chess", waited_seconds: 0, offer_ai: false, match_id: "m1", ranked: true };
  expect(await screen.findByRole("heading", { level: 2, name: /Xadrez \(ranqueada\) — contra/ })).toBeInTheDocument();
});

test("fila casual não envia ranked", async () => {
  const fn = abrirLobby({
    "POST /matchmaking/queue": { status: 202, body: { state: "queued", game_id: "tictactoe", waited_seconds: 0, offer_ai: false, match_id: null } },
  });
  await userEvent.click(screen.getByRole("button", { name: "Entrar na fila" }));
  await screen.findByText(/Procurando oponente de Jogo da velha/);
  const post = fn.mock.calls.find(([url, init]) => url === "/api/v1/matchmaking/queue" && init?.method === "POST")!;
  expect(bodyOf(post[1])).toEqual({ game_id: "tictactoe" });
});

test("conta sem e-mail verificado não vê a opção ranqueada habilitada e sabe o motivo", async () => {
  abrirLobby({}, { ...me, email_verified: false });
  const opcoes = await screen.findAllByRole("checkbox", { name: "Partida ranqueada" });
  expect(opcoes).toHaveLength(2);
  opcoes.forEach((c) => expect(c).toBeDisabled());
  expect(screen.getAllByText("Confirme seu e-mail para jogar partidas ranqueadas.")).toHaveLength(2);
});

test("ao fim da partida ranqueada o rating antes e depois é mostrado em texto", async () => {
  installFakeWebSocket();
  mockApi({ "GET /matches/m1": { body: ranked() } });
  render(<OnlineMatch matchId="m1" renderBoard={renderBoard} onLeave={() => undefined} />);
  const ws = FakeWebSocket.instances[0]!;
  await screen.findByTestId("board");
  act(() => ws.open());
  expect(screen.queryByText(/Seu rating/)).not.toBeInTheDocument();
  act(() => ws.receive({ type: "match_ended", seq: 5, payload: { match_id: "m1", result: "p1_win",
    end_reason: "resign", ply: 5, rating_changes: [
      { seat: 1, before: 1200, after: 1220 }, { seat: 2, before: 1200, after: 1180 }] } }));
  expect(screen.getByText("Seu rating: 1200 → 1220 (+20).")).toBeInTheDocument();
  expect(screen.getByText("Você venceu: o adversário desistiu.")).toBeInTheDocument();
});

test("partida anulada é explicada e não mostra variação de rating", async () => {
  installFakeWebSocket();
  mockApi({ "GET /matches/m1": { body: ranked({ ply: 2 }) } });
  render(<OnlineMatch matchId="m1" renderBoard={renderBoard} onLeave={() => undefined} />);
  const ws = FakeWebSocket.instances[0]!;
  await screen.findByTestId("board");
  act(() => ws.open());
  act(() => ws.receive({ type: "match_ended", seq: 3, payload: { match_id: "m1", result: null,
    end_reason: "annulled", ply: 3 } }));
  expect(screen.getByText("Partida anulada: terminou cedo demais e não altera o rating.")).toBeInTheDocument();
  expect(screen.getByText("A partida foi anulada.")).toBeInTheDocument();
  expect(screen.queryByText(/Seu rating/)).not.toBeInTheDocument();
});

test("ratingChangeText usa só o assento do próprio jogador", () => {
  const seats = ranked().seats;
  const rating_changes = [{ seat: 1, before: 1500, after: 1491 }, { seat: 2, before: 1300, after: 1310 }];
  expect(ratingChangeText({ seats, rating_changes })).toBe("Seu rating: 1500 → 1491 (-9).");
  expect(ratingChangeText({ seats, rating_changes: [] })).toBeNull();
  expect(ratingChangeText({ seats })).toBeNull();
  expect(onlineStatusText({ game_id: "chess", status: "annulled", result: null, end_reason: "annulled",
    to_move_seat: null, seats })).toContain("anulada");
});
