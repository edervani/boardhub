"""RNF-028: migrações sobem, descem e correspondem aos modelos."""

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.conftest import alembic_config


def test_upgrade_downgrade_upgrade_e_sem_divergencia_com_modelos() -> None:
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    command.check(cfg)  # falha se os modelos divergirem das migrações


def test_catalogo_semeado_com_classificacao(db: Session) -> None:
    rows = db.execute(text("SELECT id, age_rating FROM games ORDER BY id")).all()
    assert [(r.id, r.age_rating) for r in rows] == [
        ("checkers", "L"),
        ("chess", "L"),
        ("tictactoe", "L"),
    ]


def test_jogo_sem_classificacao_nao_pode_ser_habilitado(db: Session) -> None:
    """CA-033: restrição no banco."""
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO games (id, name, enabled, ranked_enabled, rules_version, age_rating) "
                "VALUES ('teste', 'Teste', true, false, 'teste-1', NULL)"
            )
        )
    db.rollback()


def test_email_precisa_estar_em_minusculas(db: Session) -> None:
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO users (id, email, password_hash, role, status, age_band, "
                "terms_version, created_at, updated_at) VALUES (gen_random_uuid(), "
                "'Pessoa@Example.test', 'x', 'user', 'active', '18_plus', 'v1', now(), now())"
            )
        )
    db.rollback()
