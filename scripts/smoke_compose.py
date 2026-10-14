#!/usr/bin/env python3
"""Teste de fumaça ponta a ponta contra o ambiente do docker compose (site → API → banco → e-mail).

Cadastra uma conta sintética, confirma o e-mail pela caixa de teste, entra, joga o jogo da
velha contra a IA e confere o histórico. Sai com código != 0 em qualquer divergência.
"""

import http.cookiejar
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

WEB = "http://localhost:8080"
MAILPIT = "http://localhost:8025"
PASSWORD = "cavalo-bispo-torre-42"
EMAIL = f"fumaca-{uuid.uuid4().hex[:8]}@example.test"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(method: str, url: str, body: object = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    csrf = next((c.value for c in jar if c.name == "bh_csrf"), None)
    if csrf and method != "GET":
        req.add_header("X-CSRF-Token", csrf)
    try:
        with opener.open(req, timeout=15) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as err:
        raw = err.read()
        return err.code, (json.loads(raw) if raw else None)


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)
    print(f"ok - {msg}")


def wait_ready() -> None:
    for _ in range(60):
        try:
            status, _ = call("GET", f"{WEB}/api/v1/health/ready")
            if status == 200:
                return
        except OSError:
            pass
        time.sleep(2)
    raise AssertionError("o site não ficou pronto em 120 s")


def verification_token() -> str:
    for _ in range(20):
        _, listing = call("GET", f"{MAILPIT}/api/v1/messages")
        for msg in (listing or {}).get("messages", []):
            if any(t.get("Address") == EMAIL for t in msg.get("To", [])):
                _, full = call("GET", f"{MAILPIT}/api/v1/message/{msg['ID']}")
                m = re.search(r"token=([A-Za-z0-9_-]+)", full["Text"])
                if m:
                    return m.group(1)
        time.sleep(1)
    raise AssertionError("e-mail de verificação não chegou")


def check_jobs_service() -> None:
    """O agendador da rotina diária sobe, está saudável e não publica portas."""
    out = subprocess.run(["docker", "compose", "ps", "--format", "json", "jobs"],
                         capture_output=True, text=True, check=True).stdout
    rows = [json.loads(line) for line in out.splitlines() if line.strip()]
    check(len(rows) == 1 and rows[0].get("State") == "running", "serviço jobs em execução")
    check(rows[0].get("Health") == "healthy", "serviço jobs saudável (rotina diária executou)")
    check(not rows[0].get("Publishers"), "serviço jobs não publica portas")


def main() -> None:
    wait_ready()
    check_jobs_service()
    with urllib.request.urlopen(WEB, timeout=10) as page:
        check(b"BoardHub" in page.read(), "página inicial do site carrega")
    status, _ = call("POST", f"{WEB}/api/v1/auth/register", {
        "email": EMAIL, "password": PASSWORD, "display_name": "fumaca_" + uuid.uuid4().hex[:6],
        "age_band": "18_plus", "accept_terms_version": "2026-10-13"})
    check(status == 201, "cadastro retorna 201")
    status, _ = call("POST", f"{WEB}/api/v1/auth/verify-email", {"token": verification_token()})
    check(status == 204, "e-mail confirmado pelo link recebido")
    status, me = call("POST", f"{WEB}/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    check(status == 200 and me["email_verified"] is True, "login funciona")
    status, games = call("GET", f"{WEB}/api/v1/games")
    check(status == 200 and sorted(g["id"] for g in games) == ["checkers", "chess", "tictactoe"], "catálogo tem velha, damas e xadrez")
    status, match = call("POST", f"{WEB}/api/v1/matches",
                         {"game_id": "tictactoe", "mode": "ai", "ai_level": 5})
    check(status == 201 and match["ply"] == 0, "partida contra a IA criada")
    status, match = call("POST", f"{WEB}/api/v1/matches/{match['id']}/moves",
                         {"expected_ply": 0, "move": "4", "client_move_id": str(uuid.uuid4())})
    check(status == 200 and match["ply"] == 2, "lance aceito e a IA respondeu")
    status, page = call("GET", f"{WEB}/api/v1/me/matches")
    check(status == 200 and len(page["items"]) == 1, "histórico lista a partida")
    status, _ = call("POST", f"{WEB}/api/v1/auth/logout")
    check(status == 204, "logout")
    status, _ = call("GET", f"{WEB}/api/v1/me")
    check(status == 401, "sessão encerrada no servidor")
    print("FUMAÇA OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"FALHA: {exc}", file=sys.stderr)
        subprocess.run(["docker", "compose", "logs", "--tail=60", "backend", "web", "jobs"], check=False)
        sys.exit(1)
