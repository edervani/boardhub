"""RF-006, RF-007, RF-033 e RF-034 (CA-006, CA-007, CA-033, CA-034)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import AuditLog, Game, User
from app.services import guardian_service
from tests.conftest import FakeClock, MemoryMailer
from tests.helpers import csrf, login, register

API = "/api/v1"


def novo_cliente(app: TestClient) -> TestClient:
    return TestClient(app.app, base_url="https://testserver")


def conta_logada(client: TestClient, mailer: MemoryMailer, n: int = 1, **kw: object) -> TestClient:
    """Cadastra, confirma o e-mail e autentica `client`."""
    assert register(client, n, **kw).status_code == 201
    email = f"jogador{n}@example.test"
    token = mailer.last_token(email)
    assert client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 204
    assert login(client, n).status_code == 200
    return client


# ---------- CA-006: perfil ----------

def test_editar_perfil_proprio(client: TestClient, mailer: MemoryMailer) -> None:
    conta_logada(client, mailer)
    resp = client.patch(f"{API}/me/profile", headers=csrf(client),
                        json={"bio": "Gosto de damas", "avatar_key": "torre"})
    assert resp.status_code == 200
    assert resp.json()["bio"] == "Gosto de damas"
    assert client.get(f"{API}/me/profile").json()["avatar_key"] == "torre"


def test_perfil_exige_autenticacao_e_csrf(client: TestClient, mailer: MemoryMailer) -> None:
    assert client.get(f"{API}/me/profile").status_code == 401
    conta_logada(client, mailer)
    assert client.patch(f"{API}/me/profile", json={"bio": "x"}).status_code in (400, 403)


def test_nao_existe_endpoint_para_editar_perfil_alheio(client: TestClient,
                                                       mailer: MemoryMailer) -> None:
    conta_logada(client, mailer)
    resp = client.patch(f"{API}/users/jogador_teste_02", headers=csrf(client),
                        json={"bio": "invadido"})
    assert resp.status_code in (404, 405)
    assert client.patch(f"{API}/me/profile", headers=csrf(client),
                        json={"user_id": "x", "bio": "a"}).status_code == 422


def test_bio_com_script_e_guardada_como_texto(client: TestClient, mailer: MemoryMailer) -> None:
    conta_logada(client, mailer)
    bio = "<script>alert(1)</script>"
    client.patch(f"{API}/me/profile", headers=csrf(client), json={"bio": bio})
    publico = novo_cliente(client).get(f"{API}/users/jogador_teste_01")
    assert publico.status_code == 200
    assert publico.json()["bio"] == bio  # o frontend renderiza como texto
    assert publico.headers["content-type"].startswith("application/json")


def test_bio_acima_de_160_caracteres_e_recusada(client: TestClient, mailer: MemoryMailer) -> None:
    conta_logada(client, mailer)
    resp = client.patch(f"{API}/me/profile", headers=csrf(client), json={"bio": "a" * 161})
    assert resp.status_code == 422


def test_perfil_publico_nao_expoe_email_nem_ids(client: TestClient, mailer: MemoryMailer) -> None:
    conta_logada(client, mailer)
    corpo = novo_cliente(client).get(f"{API}/users/JOGADOR_TESTE_01").json()
    assert set(corpo) == {"display_name", "avatar_key", "bio"}
    assert "example.test" not in str(corpo)


def test_perfil_privado_e_inexistente_respondem_igual(client: TestClient,
                                                      mailer: MemoryMailer) -> None:
    conta_logada(client, mailer)
    client.patch(f"{API}/me/profile", headers=csrf(client), json={"is_public": False})
    anon = novo_cliente(client)
    privado = anon.get(f"{API}/users/jogador_teste_01")
    inexistente = anon.get(f"{API}/users/ninguem_aqui")
    assert privado.status_code == inexistente.status_code == 404
    assert privado.json()["type"] == inexistente.json()["type"]
    assert anon.get(f"{API}/users/a b").status_code == 404


def test_troca_de_nome_limitada_a_cada_30_dias(client: TestClient, mailer: MemoryMailer,
                                               fake_clock: FakeClock) -> None:
    conta_logada(client, mailer)
    h = csrf(client)
    assert client.patch(f"{API}/me/profile", headers=h,
                        json={"display_name": "novo_nome_01"}).status_code == 200
    bloqueado = client.patch(f"{API}/me/profile", headers=h, json={"display_name": "outro_nome"})
    assert bloqueado.status_code == 422
    fake_clock.advance(days=31)
    login(client)  # a sessão anterior expirou por inatividade (30 dias)
    h = csrf(client)
    assert client.patch(f"{API}/me/profile", headers=h,
                        json={"display_name": "outro_nome"}).status_code == 200


def test_nome_em_uso_retorna_409_e_nome_reservado_e_recusado(client: TestClient,
                                                            mailer: MemoryMailer) -> None:
    register(client, 2)
    conta_logada(novo := novo_cliente(client), mailer)
    h = csrf(novo)
    em_uso = novo.patch(f"{API}/me/profile", headers=h, json={"display_name": "JOGADOR_TESTE_02"})
    assert em_uso.status_code == 409
    reservado = novo.patch(f"{API}/me/profile", headers=h, json={"display_name": "suporte_ajuda"})
    assert reservado.status_code == 422


def test_menor_nao_se_torna_publico_sozinho(client: TestClient, mailer: MemoryMailer) -> None:
    conta_logada(client, mailer, age_band="12_15")
    h = csrf(client)
    assert client.patch(f"{API}/me/profile", headers=h,
                        json={"is_public": True}).status_code == 403
    assert client.patch(f"{API}/me/profile", headers=h,
                        json={"is_public": False}).status_code == 200


# ---------- CA-007: preferências ----------

def test_preferencias_persistem_entre_sessoes(client: TestClient, mailer: MemoryMailer) -> None:
    conta_logada(client, mailer)
    prefs = {"theme": "dark", "motion": "reduced", "sound": False, "move_confirmation": True,
             "piece_styles": {"chess": "classico", "checkers": "infantil"}, "locale": "pt-BR"}
    assert client.put(f"{API}/me/preferences", headers=csrf(client), json=prefs).status_code == 200
    outra = novo_cliente(client)
    login(outra)
    assert outra.get(f"{API}/me/preferences").json() == prefs


def test_preferencias_padrao_seguem_o_sistema(client: TestClient, mailer: MemoryMailer) -> None:
    conta_logada(client, mailer)
    corpo = client.get(f"{API}/me/preferences").json()
    assert corpo["theme"] == "system"
    assert corpo["motion"] == "system"


@pytest.mark.parametrize("invalido", [
    {"theme": "neon"},
    {"motion": "turbo"},
    {"locale": "en-US"},
    {"piece_styles": {"go": "classico"}},
    {"piece_styles": {"chess": "dourado"}},
    {"ai_level": 5},
    {"allow_open_matchmaking": True},
])
def test_preferencias_invalidas_sao_recusadas(client: TestClient, mailer: MemoryMailer,
                                              invalido: dict[str, object]) -> None:
    conta_logada(client, mailer)
    assert client.put(f"{API}/me/preferences", headers=csrf(client),
                      json=invalido).status_code == 422


def test_estilo_de_pecas_nao_toca_controles_de_supervisao(client: TestClient,
                                                         mailer: MemoryMailer,
                                                         db: Session) -> None:
    conta_logada(client, mailer, age_band="16_17")
    client.put(f"{API}/me/preferences", headers=csrf(client),
               json={"piece_styles": {"chess": "infantil"}})
    user = db.scalar(select(User))
    assert user is not None
    db.refresh(user.preferences)
    assert user.preferences.allow_open_matchmaking is False
    assert user.preferences.daily_minutes_limit is None


# ---------- CA-033: classificação indicativa ----------

@pytest.fixture
def jogos_habilitados() -> Iterator[None]:
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE games SET enabled = true"))
        conn.execute(text("UPDATE games SET age_rating = '12' WHERE id = 'chess'"))
        conn.execute(text("UPDATE games SET age_rating = '16' WHERE id = 'checkers'"))
    yield
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE games SET enabled = false, age_rating = 'L'"))


def test_catalogo_exibe_selo_textual(client: TestClient, jogos_habilitados: None,
                                     mailer: MemoryMailer) -> None:
    conta_logada(client, mailer)
    jogos = {g["id"]: g for g in client.get(f"{API}/games").json()}
    assert set(jogos) == {"tictactoe", "checkers", "chess"}
    assert jogos["tictactoe"]["age_rating_label"] == "Livre"
    assert jogos["chess"]["age_rating_label"] == "12 anos"


def test_visitante_so_ve_jogos_livres(client: TestClient, jogos_habilitados: None) -> None:
    ids = [g["id"] for g in client.get(f"{API}/games").json()]
    assert ids == ["tictactoe"]


@pytest.mark.parametrize(("faixa", "esperado"), [
    ("under_12", {"tictactoe"}),
    ("12_15", {"tictactoe", "chess"}),
    ("16_17", {"tictactoe", "chess", "checkers"}),
    ("18_plus", {"tictactoe", "chess", "checkers"}),
])
def test_usuario_abaixo_da_classificacao_nao_ve_o_jogo(
    client: TestClient, mailer: MemoryMailer, jogos_habilitados: None,
    faixa: str, esperado: set[str],
) -> None:
    extra: dict[str, object] = {}
    if faixa == "under_12":
        extra["guardian_email"] = "resp@example.test"
    conta_logada(client, mailer, age_band=faixa, **extra)
    assert {g["id"] for g in client.get(f"{API}/games").json()} == esperado


def test_jogos_desabilitados_nao_aparecem(client: TestClient) -> None:
    assert client.get(f"{API}/games").json() == []


def test_jogo_sem_classificacao_nao_pode_ser_habilitado(db: Session) -> None:
    from sqlalchemy.exc import IntegrityError

    game = db.get(Game, "chess")
    assert game is not None
    game.age_rating = None
    game.enabled = True
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ---------- CA-034: supervisão parental ----------

def _vincular(client: TestClient, mailer: MemoryMailer, band: str = "12_15",
              ) -> tuple[TestClient, TestClient, str]:
    resp = conta_logada(novo_cliente(client), mailer, 2)
    register(client, 1, age_band=band, guardian_email="jogador2@example.test")
    token = mailer.last_token("jogador2@example.test")
    ok = resp.post(f"{API}/guardian/links/confirm", headers=csrf(resp), json={"token": token})
    assert ok.status_code == 200
    return client, resp, ok.json()["id"]


def test_responsavel_confirma_vinculo(client: TestClient, mailer: MemoryMailer,
                                      db: Session) -> None:
    _, resp, child_id = _vincular(client, mailer)
    filhos = resp.get(f"{API}/guardian/children").json()
    assert [f["id"] for f in filhos] == [child_id]
    assert filhos[0]["settings"]["profile_public"] is False
    assert db.scalar(select(AuditLog).where(AuditLog.action == "guardian_link_confirmed"))


def test_convite_so_vale_para_o_email_convidado(client: TestClient, mailer: MemoryMailer) -> None:
    register(client, 1, age_band="12_15", guardian_email="jogador2@example.test")
    token = mailer.last_token("jogador2@example.test")
    intruso = conta_logada(novo_cliente(client), mailer, 3)
    resp = intruso.post(f"{API}/guardian/links/confirm", headers=csrf(intruso),
                        json={"token": token})
    assert resp.status_code == 400
    assert intruso.get(f"{API}/guardian/children").json() == []


def test_convite_e_de_uso_unico(client: TestClient, mailer: MemoryMailer) -> None:
    _, resp, _ = _vincular(client, mailer)
    token = mailer.last_token("jogador2@example.test")
    again = resp.post(f"{API}/guardian/links/confirm", headers=csrf(resp), json={"token": token})
    assert again.status_code == 400


def test_responsavel_precisa_ser_18_mais(client: TestClient, mailer: MemoryMailer) -> None:
    jovem = conta_logada(novo_cliente(client), mailer, 2, age_band="16_17")
    register(client, 1, age_band="12_15", guardian_email="jogador2@example.test")
    token = mailer.last_token("jogador2@example.test")
    resp = jovem.post(f"{API}/guardian/links/confirm", headers=csrf(jovem), json={"token": token})
    assert resp.status_code == 422


def test_responsavel_altera_limite_e_auditoria_registra(client: TestClient, mailer: MemoryMailer,
                                                        db: Session) -> None:
    _, resp, child_id = _vincular(client, mailer)
    r = resp.put(f"{API}/guardian/children/{child_id}/settings", headers=csrf(resp),
                 json={"daily_minutes_limit": 60, "allow_open_matchmaking": True})
    assert r.status_code == 200
    assert r.json()["settings"]["daily_minutes_limit"] == 60
    log = db.scalar(select(AuditLog).where(AuditLog.action == "guardian_settings_changed"))
    assert log is not None
    assert log.details["daily_minutes_limit"] == {"from": None, "to": 60}
    assert "example.test" not in str(log.details)


def test_limite_de_tempo_fora_da_faixa_e_recusado(client: TestClient, mailer: MemoryMailer) -> None:
    _, resp, child_id = _vincular(client, mailer)
    for minutos in (5, 601):
        r = resp.put(f"{API}/guardian/children/{child_id}/settings", headers=csrf(resp),
                     json={"daily_minutes_limit": minutos})
        assert r.status_code == 422


def test_ranking_exige_perfil_publico(client: TestClient, mailer: MemoryMailer) -> None:
    _, resp, child_id = _vincular(client, mailer)
    url = f"{API}/guardian/children/{child_id}/settings"
    assert resp.put(url, headers=csrf(resp), json={"show_in_ranking": True}).status_code == 422
    ok = resp.put(url, headers=csrf(resp), json={"profile_public": True, "show_in_ranking": True})
    assert ok.status_code == 200
    off = resp.put(url, headers=csrf(resp), json={"profile_public": False})
    assert off.json()["settings"]["show_in_ranking"] is False


def test_responsavel_nao_altera_conta_nao_vinculada(client: TestClient,
                                                    mailer: MemoryMailer) -> None:
    """SEC-05 / IDOR."""
    _, _, child_id = _vincular(client, mailer)
    outro = conta_logada(novo_cliente(client), mailer, 3)
    url = f"{API}/guardian/children/{child_id}/settings"
    assert outro.put(url, headers=csrf(outro), json={"daily_minutes_limit": 600}).status_code == 404
    assert outro.delete(f"{API}/guardian/children/{child_id}/link",
                        headers=csrf(outro)).status_code == 404
    assert outro.get(f"{API}/guardian/children").json() == []


def test_menor_nao_acessa_painel_do_responsavel(client: TestClient, mailer: MemoryMailer) -> None:
    menor, _, child_id = _vincular(client, mailer)
    login(menor)
    assert menor.get(f"{API}/guardian/children").status_code in (403, 422)
    r = menor.put(f"{API}/guardian/children/{child_id}/settings", headers=csrf(menor),
                  json={"daily_minutes_limit": 600})
    assert r.status_code in (403, 404, 422)


def test_desvincular_restaura_padrao_protetivo(client: TestClient, mailer: MemoryMailer,
                                               db: Session) -> None:
    _, resp, child_id = _vincular(client, mailer)
    url = f"{API}/guardian/children/{child_id}/settings"
    resp.put(url, headers=csrf(resp), json={"profile_public": True, "allow_open_matchmaking": True,
                                            "daily_minutes_limit": 90})
    assert resp.delete(f"{API}/guardian/children/{child_id}/link",
                       headers=csrf(resp)).status_code == 204
    user = db.scalar(select(User).where(User.email == "jogador1@example.test"))
    assert user is not None
    assert user.guardian_user_id is None
    assert user.profile.is_public is False
    assert user.preferences.allow_open_matchmaking is False
    assert user.preferences.daily_minutes_limit is None
    assert resp.get(f"{API}/guardian/children").json() == []


def test_menor_de_12_sem_confirmacao_nao_joga_online(client: TestClient, mailer: MemoryMailer,
                                                     db: Session) -> None:
    from app.core.errors import ProblemError

    register(client, 1, age_band="under_12", guardian_email="jogador2@example.test")
    user = db.scalar(select(User))
    assert user is not None
    with pytest.raises(ProblemError) as exc:
        guardian_service.require_online_access(user)
    assert exc.value.status == 403


def test_menor_de_12_sem_confirmacao_e_removido_apos_7_dias(
    client: TestClient, mailer: MemoryMailer, db: Session, fake_clock: FakeClock,
) -> None:
    register(client, 1, age_band="under_12", guardian_email="jogador2@example.test")
    conta_logada(novo_cliente(client), mailer, 3)  # adulto não é afetado
    fake_clock.advance(days=6)
    assert guardian_service.purge_unconfirmed_under_12(db) == 0
    fake_clock.advance(days=2)
    assert guardian_service.purge_unconfirmed_under_12(db) == 1
    emails = {u.email for u in db.scalars(select(User))}
    assert emails == {"jogador3@example.test"}


def test_menor_de_12_confirmado_nao_e_removido(client: TestClient, mailer: MemoryMailer,
                                               db: Session, fake_clock: FakeClock) -> None:
    _vincular(client, mailer, band="under_12")
    fake_clock.advance(days=30)
    assert guardian_service.purge_unconfirmed_under_12(db) == 0
