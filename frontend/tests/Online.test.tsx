import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../src/app/App";
import { LobbyPage } from "../src/features/lobby/LobbyPage";
import { OnlineMatch, type BoardRenderer } from "../src/features/lobby/OnlineMatch";
import { onlineStatusText } from "../src/features/lobby/onlineStatus";
import type { ActiveMatch, MatchView, Me } from "../src/services/types";
import { FakeWebSocket, bodyOf, installFakeWebSocket, mockApi, type Handler } from "./helpers";

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); document.cookie = "bh_csrf=; max-age=0"; });

const me: Me = { id: "u1", email: "a@example.test", display_name: "jogador_teste_01",
  email_verified: true, age_band: "18_plus", role: "user", supervised: false };

const ALL = ["0", "1", "2", "3", "4", "5", "6", "7", "8"];

const match = (over: Partial<MatchView> = {}): MatchView => ({
  id: "m1", game_id: "tictactoe", mode: "online_casual", status: "in_progress", ply: 0,
  state: { schema_version: 1, board: "_________", to_move: "X" }, to_move_seat: 1,
  legal_moves: ALL, result: null, end_reason: null, ai_level: null,
  created_at: "2026-10-14T00:00:00Z", finished_at: null,
  seats: [{ seat: 1, is_ai: false, is_you: true }, { seat: 2, is_ai: false, is_you: false }],
  players: [
    { seat: 1, display_name: "jogador_teste_01", connected: true, grace_deadline: null },
    { seat: 2, display_name: "jogador_teste_02", connected: true, grace_deadline: null },
  ],
  invite_code: null, invite_expires_at: null, draw_offer_by_seat: null, ...over,
});

const active = (over: Partial<ActiveMatch> = {}): ActiveMatch => ({
  id: "m1", game_id: "chess", mode: "online_casual", status: "in_progress", ply: 3, your_seat: 1,
  your_turn: true, opponent_name: "jogador_teste_02", invite_expires_at: null,
  created_at: "2026-10-14T00:00:00Z", ...over,
});

const renderBoard: BoardRenderer = ({ playable, onPlay }) => (
  <div data-testid="board" data-playable={playable.join(",")}>
    <button type="button" onClick={() => onPlay("4")}>jogar 4</button>
  </div>
);

const board = () => screen.getByTestId("board");

/** Abre a partida, espera o estado oficial do REST e abre o WebSocket. */
async function abrirPartida(over: Partial<MatchView> = {}) {
  installFakeWebSocket();
  mockApi({ "GET /matches/m1": { body: match(over) } });
  const onLeave = vi.fn();
  render(<OnlineMatch matchId="m1" renderBoard={renderBoard} onLeave={onLeave} />);
  const ws = FakeWebSocket.instances[0]!;
  await screen.findByTestId("board");
  return { ws, onLeave };
}

// ---------- textos de estado ----------

test("textos de estado da partida online cobrem os desfechos e não dependem de cor", () => {
  const base = { game_id: "chess", status: "finished", result: null, end_reason: null,
    to_move_seat: null, seats: match().seats } as const;
  expect(onlineStatusText({ ...base, status: "waiting" })).toContain("Aguardando o oponente");
  expect(onlineStatusText({ ...base, status: "in_progress", to_move_seat: 1 })).toBe("Sua vez (Brancas).");
  expect(onlineStatusText({ ...base, status: "in_progress", to_move_seat: 2 })).toBe("Vez do adversário (Pretas).");
  expect(onlineStatusText({ ...base, result: "draw", end_reason: "agreement" })).toBe("Empate por acordo.");
  expect(onlineStatusText({ ...base, result: "p1_win", end_reason: "resign" })).toBe("Você venceu: o adversário desistiu.");
  expect(onlineStatusText({ ...base, result: "p2_win", end_reason: "resign" })).toBe("Você perdeu: você desistiu.");
  expect(onlineStatusText({ ...base, result: "p1_win", end_reason: "abandon" })).toContain("abandonou");
  expect(onlineStatusText({ ...base, result: "p2_win", end_reason: "abandon" })).toBe("Você perdeu por abandono.");
  expect(onlineStatusText({ ...base, result: "p2_win", end_reason: "normal" })).toContain("Pretas");
  expect(onlineStatusText({ ...base, status: "aborted" })).toContain("cancelada");
});

// ---------- partida online ----------

test("ao conectar pede o estado oficial com o último ply conhecido", async () => {
  const { ws } = await abrirPartida({ ply: 2, to_move_seat: 1 });
  expect(board()).toHaveAttribute("data-playable", ""); // ainda sem conexão: tabuleiro travado
  act(() => ws.open());
  expect(ws.sentMessages()[0]).toMatchObject({
    type: "join_match", payload: { match_id: "m1", last_known_ply: 2 } });
  expect(board()).toHaveAttribute("data-playable", ALL.join(","));
  expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Jogo da velha — contra jogador_teste_02");
});

test("o lance sai com expected_ply e client_move_id e o tabuleiro espera a confirmação", async () => {
  const { ws } = await abrirPartida();
  act(() => ws.open());
  await userEvent.click(screen.getByRole("button", { name: "jogar 4" }));
  const enviado = ws.sentMessages().find((m) => m.type === "submit_move")!;
  expect(enviado.payload).toMatchObject({ match_id: "m1", expected_ply: 0, move: "4" });
  expect(enviado.payload?.client_move_id).toMatch(/^[0-9a-f-]{36}$/);
  expect(board()).toHaveAttribute("data-playable", ""); // pendente
  act(() => ws.receive({ type: "move_applied", reply_to: enviado.id, seq: 1, payload: {
    match_id: "m1", ply: 1, seat: 1, move: "4", next_seat: 2, legal_moves: [],
    state: { schema_version: 1, board: "____X____", to_move: "O" } } }));
  expect(screen.getByText("Vez do adversário (O).")).toBeInTheDocument();
  expect(board()).toHaveAttribute("data-playable", "");
});

test("lance do adversário atualiza o estado e é anunciado ao leitor de tela", async () => {
  const { ws } = await abrirPartida({ to_move_seat: 2, legal_moves: [] });
  act(() => ws.open());
  expect(screen.getByText("Vez do adversário (O).")).toBeInTheDocument();
  const evento = { match_id: "m1", ply: 1, seat: 2, move: "4", next_seat: 1,
    legal_moves: ALL.filter((m) => m !== "4"),
    state: { schema_version: 1, board: "____O____", to_move: "X" } };
  act(() => ws.receive({ type: "move_applied", seq: 1, payload: evento }));
  expect(screen.getByText("Sua vez (X).")).toBeInTheDocument();
  expect(screen.getByText("O adversário jogou 4. Sua vez.")).toBeInTheDocument();
  expect(board()).toHaveAttribute("data-playable", ALL.filter((m) => m !== "4").join(","));
  act(() => ws.receive({ type: "move_applied", seq: 1, payload: evento })); // repetido: ignorado
  expect(screen.getByText("Sua vez (X).")).toBeInTheDocument();
});

test("lacuna na sequência de eventos pede o estado oficial de novo", async () => {
  const { ws } = await abrirPartida();
  act(() => ws.open());
  const antes = ws.sentMessages().filter((m) => m.type === "join_match").length;
  act(() => ws.receive({ type: "move_applied", payload: { match_id: "m1", ply: 3, seat: 2, move: "4",
    next_seat: 1, legal_moves: [], state: { schema_version: 1, board: "____O____", to_move: "X" } } }));
  expect(ws.sentMessages().filter((m) => m.type === "join_match")).toHaveLength(antes + 1);
});

test("snapshot do servidor substitui o estado e aviso de lances perdidos é falado", async () => {
  const { ws } = await abrirPartida();
  act(() => ws.open());
  act(() => ws.receive({ type: "moves_since", payload: { match_id: "m1", since_ply: 0, moves: [
    { ply: 0, seat: 1, move: "0" }, { ply: 1, seat: 2, move: "4" }] } }));
  expect(screen.getByText(/Você perdeu 2 lances/)).toBeInTheDocument();
  act(() => ws.receive({ type: "match_snapshot", payload: match({ ply: 2, to_move_seat: 1,
    state: { schema_version: 1, board: "X___O____", to_move: "X" } }) }));
  expect(screen.getByText("Sua vez (X).")).toBeInTheDocument();
});

test("proposta de empate do adversário é anunciada e pode ser aceita ou recusada", async () => {
  const { ws } = await abrirPartida({ game_id: "chess", state: { schema_version: 1, fen: "x" } });
  act(() => ws.open());
  act(() => ws.receive({ type: "draw_offered", payload: { match_id: "m1", by_seat: 2 } }));
  expect(screen.getByText("O adversário propôs empate. Você pode aceitar ou recusar.")).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Proposta de empate" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Aceitar empate" }));
  expect(ws.sentMessages().find((m) => m.type === "respond_draw")?.payload)
    .toEqual({ match_id: "m1", accept: true });
  act(() => ws.receive({ type: "draw_declined", payload: { match_id: "m1", by_seat: 1, reason: "declined" } }));
  expect(screen.getByText("Você recusou o empate.")).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Proposta de empate" })).not.toBeInTheDocument();
});

test("propor empate só existe em damas e xadrez", async () => {
  const velha = await abrirPartida();
  act(() => velha.ws.open());
  expect(screen.queryByRole("button", { name: "Propor empate" })).not.toBeInTheDocument();
});

test("propor empate envia offer_draw e mostra que aguarda a resposta", async () => {
  const { ws } = await abrirPartida({ game_id: "checkers", state: { schema_version: 1, squares: [] } });
  act(() => ws.open());
  await userEvent.click(screen.getByRole("button", { name: "Propor empate" }));
  expect(ws.sentMessages().some((m) => m.type === "offer_draw")).toBe(true);
  act(() => ws.receive({ type: "draw_offered", payload: { match_id: "m1", by_seat: 1 } }));
  expect(screen.getByText("Você propôs empate. Aguardando resposta.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Propor empate" })).not.toBeInTheDocument();
});

test("desistir pede confirmação e depois envia resign", async () => {
  const { ws } = await abrirPartida();
  act(() => ws.open());
  await userEvent.click(screen.getByRole("button", { name: "Desistir" }));
  expect(ws.sentMessages().some((m) => m.type === "resign")).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "Continuar jogando" }));
  await userEvent.click(screen.getByRole("button", { name: "Desistir" }));
  await userEvent.click(screen.getByRole("button", { name: "Confirmar desistência" }));
  expect(ws.sentMessages().find((m) => m.type === "resign")?.payload).toEqual({ match_id: "m1" });
});

test("fim da partida é anunciado e o tabuleiro fica somente leitura", async () => {
  const { ws } = await abrirPartida();
  act(() => ws.open());
  act(() => ws.receive({ type: "match_ended", payload: { match_id: "m1", result: "p2_win",
    end_reason: "resign", ply: 3 } }));
  expect(screen.getByText("Você perdeu: você desistiu.")).toBeInTheDocument();
  expect(screen.getByText("A partida terminou.")).toBeInTheDocument();
  expect(board()).toHaveAttribute("data-playable", "");
  expect(screen.queryByRole("button", { name: "Desistir" })).not.toBeInTheDocument();
});

test("adversário desconectado: aviso, contagem e reivindicação de abandono", async () => {
  const { ws } = await abrirPartida({ to_move_seat: 2, legal_moves: [] });
  act(() => ws.open());
  const prazo = new Date(Date.now() + 60_000).toISOString();
  act(() => ws.receive({ type: "player_connection", payload: { match_id: "m1", seat: 2,
    connected: false, grace_deadline: prazo } }));
  expect(screen.getByText(/Adversário desconectado\. Se não voltar/)).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Adversário desconectado" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Reivindicar vitória por abandono" }));
  expect(ws.sentMessages().find((m) => m.type === "claim_abandon")?.payload).toEqual({ match_id: "m1" });
  act(() => ws.receive({ type: "player_connection", payload: { match_id: "m1", seat: 2,
    connected: true, grace_deadline: null } }));
  expect(screen.getByText("O adversário voltou a se conectar.")).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Adversário desconectado" })).not.toBeInTheDocument();
});

test("erros do servidor aparecem como alerta e estado desatualizado ressincroniza", async () => {
  const { ws } = await abrirPartida();
  act(() => ws.open());
  const antes = ws.sentMessages().filter((m) => m.type === "join_match").length;
  act(() => ws.receive({ type: "error", payload: { code: "illegal_move", message: "Jogada ilegal",
    detail: "Casa ocupada.", status: 422 } }));
  expect(screen.getByText("Jogada ilegal. Casa ocupada.")).toBeInTheDocument();
  act(() => ws.receive({ type: "error", payload: { code: "stale_state", message: "Estado desatualizado",
    current_ply: 4 } }));
  expect(ws.sentMessages().filter((m) => m.type === "join_match")).toHaveLength(antes + 1);
});

test("conexão perdida trava o tabuleiro, avisa e retoma com join_match", async () => {
  const { ws } = await abrirPartida();
  act(() => ws.open());
  expect(board()).toHaveAttribute("data-playable", ALL.join(","));
  act(() => ws.drop(1006));
  expect(screen.getAllByText("Conexão perdida. Tentando reconectar… (tentativa 1)").length).toBeGreaterThan(0);
  expect(board()).toHaveAttribute("data-playable", "");
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2), { timeout: 3000 });
  const novo = FakeWebSocket.instances[1]!;
  act(() => novo.open());
  expect(novo.sentMessages()[0]).toMatchObject({ type: "join_match", payload: { match_id: "m1", last_known_ply: 0 } });
  expect(screen.getByText("Conexão restabelecida.")).toBeInTheDocument();
  expect(board()).toHaveAttribute("data-playable", ALL.join(","));
});

test("sessão recusada (4401) não fica reconectando", async () => {
  const { ws } = await abrirPartida();
  act(() => ws.open());
  act(() => ws.drop(4401));
  expect(screen.getByText(/Conexão encerrada/)).toBeInTheDocument();
  await new Promise((r) => setTimeout(r, 1500));
  expect(FakeWebSocket.instances).toHaveLength(1);
});

test("voltar ao lobby chama onLeave", async () => {
  const { onLeave } = await abrirPartida();
  await userEvent.click(screen.getByRole("button", { name: "Voltar ao lobby" }));
  expect(onLeave).toHaveBeenCalled();
});

// ---------- lobby ----------

function abrirLobby(routes: Record<string, Handler> = {}, user: Me = me) {
  installFakeWebSocket();
  const fn = mockApi({
    "GET /me/active-matches": { body: [] },
    "GET /matches/m1": { body: match() },
    ...routes,
  });
  render(<LobbyPage me={user} renderBoard={renderBoard} pollMs={20} />);
  return fn;
}

test("criar convite mostra o código uma vez e a partida abre quando o oponente entra", async () => {
  const fn = abrirLobby({
    "POST /matches": (init) => ({ status: 201, body: match({ id: "m1", status: "waiting", to_move_seat: null,
      legal_moves: [], invite_code: "ABCD2345", invite_expires_at: "2026-10-14T00:15:00Z",
      seats: [{ seat: 1, is_ai: false, is_you: true }], echo: bodyOf(init) } as Partial<MatchView>) }),
  });
  await userEvent.selectOptions(screen.getByLabelText("Jogo do convite"), "checkers");
  await userEvent.selectOptions(screen.getByLabelText("Você joga"), "2");
  await userEvent.click(screen.getByRole("button", { name: "Criar convite" }));
  expect(await screen.findByText("ABCD2345")).toBeInTheDocument();
  const post = fn.mock.calls.find(([url, init]) => url === "/api/v1/matches" && init?.method === "POST")!;
  expect(bodyOf(post[1])).toEqual({ game_id: "checkers", mode: "online_casual", preferred_seat: 2 });
  // O servidor avisa pelo WebSocket quando o segundo jogador entra.
  act(() => FakeWebSocket.instances[0]!.receive({ type: "match_started", payload: { match_id: "m1", game_id: "checkers" } }));
  expect(await screen.findByRole("heading", { level: 2, name: /contra jogador_teste_02/ })).toBeInTheDocument();
  expect(screen.queryByText("ABCD2345")).not.toBeInTheDocument();
});

test("entrar por código abre a partida; código inválido mostra o erro", async () => {
  let resposta: { status?: number; body?: unknown } = {
    status: 404, body: { type: "invite_not_found", title: "Código inválido ou expirado" } };
  const fn = abrirLobby({ "POST /matches/join": () => resposta });
  await userEvent.type(screen.getByLabelText("Código do convite"), "ZZZZZZZZ");
  await userEvent.click(screen.getByRole("button", { name: "Entrar na sala" }));
  expect(await screen.findByText("Código inválido ou expirado")).toBeInTheDocument();
  resposta = { body: match() };
  await userEvent.clear(screen.getByLabelText("Código do convite"));
  await userEvent.type(screen.getByLabelText("Código do convite"), "ABCD2345");
  await userEvent.click(screen.getByRole("button", { name: "Entrar na sala" }));
  expect(await screen.findByRole("heading", { level: 2, name: /Jogo da velha — contra/ })).toBeInTheDocument();
  const joins = fn.mock.calls.filter(([url]) => url === "/api/v1/matches/join");
  expect(bodyOf(joins[1]![1])).toEqual({ invite_code: "ABCD2345" });
});

test("fila: espera, mostra o tempo, oferece alternativa e abre a partida quando pareia", async () => {
  let fila: Record<string, unknown> = { state: "queued", game_id: "tictactoe", waited_seconds: 0, offer_ai: false, match_id: null };
  abrirLobby({
    "POST /matchmaking/queue": () => ({ status: 202, body: fila }),
    "GET /matchmaking/queue": () => ({ body: fila }),
  });
  await userEvent.click(screen.getByRole("button", { name: "Entrar na fila" }));
  expect(await screen.findByText(/Procurando oponente de Jogo da velha/)).toBeInTheDocument();
  fila = { state: "queued", game_id: "tictactoe", waited_seconds: 61, offer_ai: true, match_id: null };
  expect(await screen.findByText(/Ainda sem oponente/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sair da fila" })).toBeInTheDocument();
  fila = { state: "matched", game_id: "tictactoe", waited_seconds: 0, offer_ai: false, match_id: "m1" };
  expect(await screen.findByRole("heading", { level: 2, name: /Jogo da velha — contra/ })).toBeInTheDocument();
});

test("sair da fila volta ao seletor", async () => {
  const fn = abrirLobby({
    "POST /matchmaking/queue": { status: 202, body: { state: "queued", game_id: "chess", waited_seconds: 0, offer_ai: false, match_id: null } },
    "GET /matchmaking/queue": { body: { state: "queued", game_id: "chess", waited_seconds: 1, offer_ai: false, match_id: null } },
    "DELETE /matchmaking/queue": { status: 204 },
  });
  await userEvent.selectOptions(screen.getByLabelText("Jogo da fila"), "chess");
  await userEvent.click(screen.getByRole("button", { name: "Entrar na fila" }));
  await userEvent.click(await screen.findByRole("button", { name: "Sair da fila" }));
  expect(await screen.findByRole("button", { name: "Entrar na fila" })).toBeInTheDocument();
  expect(fn.mock.calls.some(([url, init]) => url === "/api/v1/matchmaking/queue" && init?.method === "DELETE")).toBe(true);
});

test("resposta atrasada da consulta da fila não recoloca o usuário na fila depois de sair", async () => {
  const fn = abrirLobby({
    "POST /matchmaking/queue": { status: 202, body: { state: "queued", game_id: "chess", waited_seconds: 0, offer_ai: false, match_id: null } },
    "GET /matchmaking/queue": { body: { state: "queued", game_id: "chess", waited_seconds: 1, offer_ai: false, match_id: null } },
    "DELETE /matchmaking/queue": { status: 204 },
  });
  const inner = fn.getMockImplementation() as (url: string, init?: RequestInit) => Promise<Response>;
  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  let held = false;
  // A primeira consulta periódica fica retida até depois do DELETE (resposta "atrasada").
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/matchmaking/queue") && (init?.method ?? "GET") === "GET" && !held) {
      held = true;
      await gate;
    }
    return inner(url, init);
  }));
  await userEvent.click(screen.getByRole("button", { name: "Entrar na fila" }));
  await userEvent.click(await screen.findByRole("button", { name: "Sair da fila" }));
  expect(await screen.findByRole("button", { name: "Entrar na fila" })).toBeInTheDocument();
  release();
  await act(async () => { await new Promise((r) => setTimeout(r, 100)); });
  expect(screen.getByRole("button", { name: "Entrar na fila" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Sair da fila" })).not.toBeInTheDocument();
});

test("conta sem e-mail verificado vê o aviso e não entra na fila", () => {
  abrirLobby({}, { ...me, email_verified: false });
  expect(screen.getByText(/Confirme seu e-mail para entrar na fila/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Entrar na fila" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Criar convite" })).toBeEnabled();
});

test("lista só as partidas online em andamento e permite abrir ou cancelar", async () => {
  const fn = abrirLobby({
    "GET /me/active-matches": { body: [
      active(),
      active({ id: "w1", status: "waiting", opponent_name: null, your_turn: false, game_id: "checkers" }),
      active({ id: "l1", mode: "local", game_id: "tictactoe" }),
    ] },
    "POST /matches/w1/cancel": { status: 204 },
  });
  expect(await screen.findByText(/Xadrez — contra jogador_teste_02 — sua vez/)).toBeInTheDocument();
  expect(screen.getByText(/Damas — aguardando um oponente/)).toBeInTheDocument();
  expect(screen.queryByText(/^Jogo da velha —/)).not.toBeInTheDocument(); // local não entra no lobby online
  await userEvent.click(screen.getByRole("button", { name: "Cancelar convite" }));
  await waitFor(() => expect(fn.mock.calls.some(([url]) => url === "/api/v1/matches/w1/cancel")).toBe(true));
  await userEvent.click(screen.getByRole("button", { name: "Abrir" }));
  expect(await screen.findByRole("heading", { level: 2, name: /contra jogador_teste_02/ })).toBeInTheDocument();
});

test("sem partidas online o lobby diz isso", async () => {
  abrirLobby();
  expect(await screen.findByText("Nenhuma partida online em andamento.")).toBeInTheDocument();
});

test("o menu Online leva ao lobby para quem está logado", async () => {
  installFakeWebSocket();
  mockApi({ "GET /me": { body: me }, "GET /games": { body: [] }, "GET /me/active-matches": { body: [] } });
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Online" }));
  expect(await screen.findByRole("heading", { level: 2, name: "Jogar online" })).toBeInTheDocument();
});
