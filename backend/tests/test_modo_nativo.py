"""Modo nativo de teste sem Docker (DT-022): frontend servido pelo backend e e-mail em arquivo."""

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.main import create_app
from app.services.mailer import FileMailer, Mail, SmtpMailer, get_mailer
from tests.helpers import PASSWORD, register

EMAIL = "jogador1@example.test"
BASE = {"secret_key": "k" * 32, "postgres_db": "d", "postgres_user": "u", "postgres_password": "p"}


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>BoardHub</title>", encoding="utf-8")
    (root / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (root / "assets" / "app.css").write_text("body{}", encoding="utf-8")
    (tmp_path / "segredo.txt").write_text("fora do dist", encoding="utf-8")
    return root


@pytest.fixture
def com_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """Define variáveis de ambiente e invalida o cache de configuração (antes e depois)."""
    def definir(**env: str) -> None:
        for key, value in env.items():
            monkeypatch.setenv(key.upper(), value)
        get_settings.cache_clear()

    get_settings.cache_clear()
    yield definir
    monkeypatch.undo()
    get_settings.cache_clear()


def _ultimo_token(arquivo: Path) -> str:
    for linha in reversed(arquivo.read_text(encoding="utf-8").splitlines()):
        msg = json.loads(linha)
        achado = re.search(r"token=([A-Za-z0-9_-]+)", msg["body"])
        if msg["to"] == EMAIL and achado:
            return achado.group(1)
    raise AssertionError("nenhum token gravado")


# ---------- frontend estático ----------

def test_desligado_por_padrao_nao_serve_nada(client: TestClient) -> None:
    assert client.get("/").status_code == 404
    assert client.get("/api/v1/health/live").status_code == 200


def test_serve_index_e_ativos_com_tipos_corretos(
    com_env: Callable[..., None], dist: Path
) -> None:
    com_env(serve_frontend_dir=str(dist))
    with TestClient(create_app()) as c:
        home = c.get("/")
        assert home.status_code == 200 and "BoardHub" in home.text
        assert home.headers["content-type"].startswith("text/html")
        js = c.get("/assets/app.js")
        assert js.status_code == 200 and js.headers["content-type"].startswith("text/javascript")
        assert c.get("/assets/app.css").headers["content-type"].startswith("text/css")
        assert c.head("/").status_code == 200


def test_fallback_do_spa_para_rotas_sem_extensao(
    com_env: Callable[..., None], dist: Path
) -> None:
    com_env(serve_frontend_dir=str(dist))
    with TestClient(create_app()) as c:
        resp = c.get("/partidas/abc")
        assert resp.status_code == 200 and "BoardHub" in resp.text


def test_arquivo_estatico_inexistente_e_404_nao_html(
    com_env: Callable[..., None], dist: Path
) -> None:
    com_env(serve_frontend_dir=str(dist))
    with TestClient(create_app()) as c:
        resp = c.get("/assets/nao-existe.js")
        assert resp.status_code == 404 and "BoardHub" not in resp.text


def test_api_inexistente_continua_404_json_e_a_api_segue_funcionando(
    com_env: Callable[..., None], dist: Path
) -> None:
    com_env(serve_frontend_dir=str(dist))
    with TestClient(create_app()) as c:
        resp = c.get("/api/v1/nao-existe")
        assert resp.status_code == 404 and resp.headers["content-type"].startswith(
            "application/json")
        assert c.get("/api/v1/health/live").json() == {"status": "ok"}
        assert c.get("/api/docs").status_code == 200


@pytest.mark.parametrize("caminho", [
    "../segredo.txt", "..%2Fsegredo.txt", "%2e%2e/segredo.txt", "..%5Csegredo.txt",
    "assets/../../segredo.txt", "%00",
])
def test_nao_sai_do_diretorio(com_env: Callable[..., None], dist: Path, caminho: str) -> None:
    com_env(serve_frontend_dir=str(dist))
    with TestClient(create_app()) as c:
        resp = c.get(f"/{caminho}")
        assert "fora do dist" not in resp.text


def test_cabecalhos_de_seguranca_tambem_no_site(
    com_env: Callable[..., None], dist: Path
) -> None:
    com_env(serve_frontend_dir=str(dist))
    with TestClient(create_app()) as c:
        resp = c.get("/")
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_diretorio_sem_index_impede_a_subida(
    com_env: Callable[..., None], tmp_path: Path
) -> None:
    com_env(serve_frontend_dir=str(tmp_path))
    with pytest.raises(RuntimeError, match="index.html"):
        create_app()


def test_cors_e_cookies_em_http_localhost(
    com_env: Callable[..., None], dist: Path, tmp_path: Path
) -> None:
    destino = tmp_path / "emails.jsonl"
    com_env(serve_frontend_dir=str(dist), frontend_origin="http://localhost:8080",
            cookie_secure="false", app_env="test", mail_backend="file",
            mail_file_path=str(destino))
    with TestClient(create_app(), base_url="http://localhost:8080") as c:
        ok = c.options("/api/v1/me", headers={"Origin": "http://localhost:8080",
                                              "Access-Control-Request-Method": "GET"})
        assert ok.headers["access-control-allow-origin"] == "http://localhost:8080"
        outra = c.options("/api/v1/me", headers={"Origin": "http://localhost:5173",
                                                 "Access-Control-Request-Method": "GET"})
        assert "access-control-allow-origin" not in outra.headers
        assert register(c).status_code == 201
        token = _ultimo_token(destino)
        assert c.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 204
        resp = c.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        cookies = resp.headers.get_list("set-cookie")
        assert cookies and all("Secure" not in cookie for cookie in cookies)
        assert all("samesite=lax" in cookie.lower() for cookie in cookies)


# ---------- validação de configuração ----------

def test_frontend_estatico_e_recusado_em_producao() -> None:
    with pytest.raises(ValidationError, match="SERVE_FRONTEND_DIR"):
        Settings(_env_file=None, app_env="production", serve_frontend_dir="/x", **BASE)  # type: ignore[call-arg]


@pytest.mark.parametrize("ambiente", ["staging", "production"])
def test_email_em_arquivo_e_recusado_fora_de_teste(ambiente: str) -> None:
    with pytest.raises(ValidationError, match="MAIL_BACKEND=file"):
        Settings(_env_file=None, app_env=ambiente, mail_backend="file",  # type: ignore[call-arg]
                 mail_file_path="/x", **BASE)


def test_email_em_arquivo_exige_caminho() -> None:
    with pytest.raises(ValidationError, match="MAIL_FILE_PATH"):
        Settings(_env_file=None, app_env="test", mail_backend="file", **BASE)  # type: ignore[call-arg]


# ---------- e-mail em arquivo ----------

def test_mailer_padrao_continua_smtp(com_env: Callable[..., None]) -> None:
    com_env()
    assert isinstance(get_mailer(), SmtpMailer)


def test_mailer_em_arquivo_grava_jsonl_e_nao_loga_dados(
    com_env: Callable[..., None], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    destino = tmp_path / "dados" / "emails.jsonl"
    com_env(app_env="test", mail_backend="file", mail_file_path=str(destino))
    mailer = get_mailer()
    assert isinstance(mailer, FileMailer)
    with caplog.at_level("DEBUG"):
        mailer.send(Mail(to="alguem@example.test", subject="Assunto", body="link?token=abc_123"))
    linhas = destino.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 1
    registro = json.loads(linhas[0])
    assert registro["to"] == "alguem@example.test" and "token=abc_123" in registro["body"]
    texto = caplog.text + " ".join(str(vars(r)) for r in caplog.records)
    assert "alguem@example.test" not in texto and "abc_123" not in texto


def test_cadastro_e_verificacao_pelo_arquivo_de_emails(
    com_env: Callable[..., None], tmp_path: Path
) -> None:
    destino = tmp_path / "emails.jsonl"
    com_env(app_env="test", mail_backend="file", mail_file_path=str(destino))
    with TestClient(create_app(), base_url="https://testserver") as c:
        assert register(c).status_code == 201
        token = _ultimo_token(destino)
        assert c.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 204
