import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useWebSocket } from "../src/hooks/useWebSocket";
import { backoffDelay, parseServerMessage, wsUrl, type ServerMessage } from "../src/services/realtime";
import { FakeWebSocket, installFakeWebSocket } from "./helpers";

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

type Send = (type: string, payload: Record<string, unknown>) => string | null;

function Probe(props: {
  onMessage?: (m: ServerMessage) => void;
  onOpen?: () => void;
  enabled?: boolean;
  sendRef?: { current: Send | null };
}) {
  const ws = useWebSocket({
    enabled: props.enabled ?? true, onMessage: props.onMessage ?? (() => {}), onOpen: props.onOpen,
    random: () => 0.5,
  });
  if (props.sendRef) props.sendRef.current = ws.send;
  return <p data-testid="state">{ws.state}:{ws.attempt}</p>;
}

const state = () => screen.getByTestId("state");

test("atraso de reconexão: 1, 2, 4, 8, 16 s e teto de 30 s, com jitter de ±25%", () => {
  const meio = () => 0.5;
  expect([0, 1, 2, 3, 4, 5, 6, 20].map((n) => backoffDelay(n, meio)))
    .toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000]);
  expect(backoffDelay(0, () => 0)).toBe(750);
  expect(backoffDelay(0, () => 1)).toBe(1250);
  expect(backoffDelay(5, () => 1)).toBe(30000); // nunca passa de 30 s
});

test("URL do WebSocket acompanha o protocolo da página", () => {
  expect(wsUrl({ protocol: "http:", host: "localhost:8080" })).toBe("ws://localhost:8080/api/v1/ws");
  expect(wsUrl({ protocol: "https:", host: "boardhub.example.test" })).toBe("wss://boardhub.example.test/api/v1/ws");
});

test("mensagens do servidor inválidas são ignoradas", () => {
  expect(parseServerMessage("{nao")).toBeNull();
  expect(parseServerMessage("[]")).toBeNull();
  expect(parseServerMessage('{"payload":{}}')).toBeNull();
  expect(parseServerMessage(42)).toBeNull();
  expect(parseServerMessage('{"type":"x","payload":{"a":1}}')).toEqual({ type: "x", payload: { a: 1 } });
});

test("conecta, avisa a abertura, entrega mensagens e responde ao ping", () => {
  installFakeWebSocket();
  const onMessage = vi.fn();
  const onOpen = vi.fn();
  render(<Probe onMessage={onMessage} onOpen={onOpen} />);
  const ws = FakeWebSocket.instances[0]!;
  expect(ws.url).toMatch(/^wss?:\/\/.+\/api\/v1\/ws$/);
  expect(state()).toHaveTextContent("connecting:0");
  act(() => ws.open());
  expect(state()).toHaveTextContent("open:0");
  expect(onOpen).toHaveBeenCalledTimes(1);
  act(() => ws.receive({ type: "ping" }));
  expect(ws.sent).toEqual([JSON.stringify({ type: "pong" })]);
  expect(onMessage).not.toHaveBeenCalled();
  act(() => ws.receive({ type: "move_applied", payload: { ply: 1 } }));
  expect(onMessage).toHaveBeenCalledWith({ type: "move_applied", payload: { ply: 1 } });
});

test("reconecta com atraso exponencial e zera a contagem ao abrir", () => {
  vi.useFakeTimers();
  installFakeWebSocket();
  const onOpen = vi.fn();
  render(<Probe onOpen={onOpen} />);
  act(() => FakeWebSocket.instances[0]!.open());
  act(() => FakeWebSocket.instances[0]!.drop(1006));
  expect(state()).toHaveTextContent("reconnecting:1");
  act(() => { vi.advanceTimersByTime(999); });
  expect(FakeWebSocket.instances).toHaveLength(1);
  act(() => { vi.advanceTimersByTime(1); });
  expect(FakeWebSocket.instances).toHaveLength(2);
  expect(state()).toHaveTextContent("reconnecting:1");
  act(() => FakeWebSocket.instances[1]!.drop(1006)); // falhou sem abrir
  expect(state()).toHaveTextContent("reconnecting:2");
  act(() => { vi.advanceTimersByTime(1999); });
  expect(FakeWebSocket.instances).toHaveLength(2);
  act(() => { vi.advanceTimersByTime(1); });
  expect(FakeWebSocket.instances).toHaveLength(3);
  act(() => FakeWebSocket.instances[2]!.open());
  expect(state()).toHaveTextContent("open:0");
  expect(onOpen).toHaveBeenCalledTimes(2); // a cada conexão, para reenviar join_match
  act(() => FakeWebSocket.instances[2]!.drop(1006));
  act(() => { vi.advanceTimersByTime(1000); }); // contagem recomeçou
  expect(FakeWebSocket.instances).toHaveLength(4);
});

test.each([4401, 4403, 4429])("código %i não tenta reconectar", (code) => {
  vi.useFakeTimers();
  installFakeWebSocket();
  render(<Probe />);
  act(() => FakeWebSocket.instances[0]!.open());
  act(() => FakeWebSocket.instances[0]!.drop(code));
  expect(state()).toHaveTextContent("closed:0");
  act(() => { vi.advanceTimersByTime(120_000); });
  expect(FakeWebSocket.instances).toHaveLength(1);
});

test("send só funciona com a conexão aberta e leva um id para casar com reply_to", () => {
  installFakeWebSocket();
  const sendRef: { current: Send | null } = { current: null };
  render(<Probe sendRef={sendRef} />);
  const ws = FakeWebSocket.instances[0]!;
  expect(sendRef.current?.("resign", { match_id: "m1" })).toBeNull(); // ainda conectando
  act(() => ws.open());
  const id = sendRef.current?.("resign", { match_id: "m1" });
  expect(id).toEqual(expect.any(String));
  expect(ws.sentMessages()).toEqual([{ type: "resign", id, payload: { match_id: "m1" } }]);
});

test("desmontar fecha a conexão e não reconecta", () => {
  vi.useFakeTimers();
  installFakeWebSocket();
  const { unmount } = render(<Probe />);
  act(() => FakeWebSocket.instances[0]!.open());
  unmount();
  expect(FakeWebSocket.instances[0]!.readyState).toBe(3);
  act(() => { vi.advanceTimersByTime(60_000); });
  expect(FakeWebSocket.instances).toHaveLength(1);
});

test("desabilitado não abre conexão", () => {
  installFakeWebSocket();
  render(<Probe enabled={false} />);
  expect(FakeWebSocket.instances).toHaveLength(0);
  expect(state()).toHaveTextContent("closed:0");
});
