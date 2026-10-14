"""Ambiente do Alembic: a URL vem da configuração da aplicação, nunca do alembic.ini."""

from alembic import context
from sqlalchemy import Connection, create_engine, pool

from app.core.config import get_settings
from app.models import Base

target_metadata = Base.metadata


def _configure_and_run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    existing = context.config.attributes.get("connection")
    if existing is not None:  # conexão fornecida pelos testes
        _configure_and_run(existing)
        return
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        _configure_and_run(connection)


if context.is_offline_mode():
    raise SystemExit("Modo offline não é suportado; rode as migrações contra um banco.")
run_migrations_online()
