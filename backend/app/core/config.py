"""Configuração carregada de variáveis de ambiente (doc 04 §15)."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, PostgresDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "staging", "production"] = "development"
    secret_key: str = Field(min_length=32)
    frontend_origin: str = "http://localhost:5173"
    log_level: str = "INFO"
    cookie_secure: bool = True
    session_idle_days: int = 30
    session_absolute_days: int = 90
    terms_version: str = "2026-10-13"

    # Partidas online (RF-011, RF-012, RF-014, RF-015; doc 06 §3.6)
    invite_ttl_seconds: int = Field(default=900, ge=60)
    queue_stale_seconds: int = Field(default=45, ge=5)
    online_grace_seconds: int = Field(default=60, ge=1)
    online_inactivity_seconds: int = Field(default=600, ge=30)

    # RF-034: com o limite diário esgotado, a partida em andamento pode terminar. Ligar esta
    # chave bloqueia também os lances (conflito com o pedido de bloqueio, docs/16 P-23).
    daily_limit_blocks_moves: bool = False

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = "nao-responda@example.test"
    # "file" grava as mensagens em MAIL_FILE_PATH (modo nativo de teste, DT-022): só em
    # APP_ENV development/test, porque o arquivo contém os links de verificação.
    mail_backend: Literal["smtp", "file"] = "smtp"
    mail_file_path: str = ""

    # Diretório do build do frontend servido pelo backend (modo nativo, DT-022). Vazio = desligado.
    serve_frontend_dir: str = ""

    postgres_db: str
    postgres_user: str
    postgres_password: str
    db_host: str = "localhost"
    db_port: int = 5432

    @model_validator(mode="after")
    def _only_for_local_tests(self) -> Self:
        local = self.app_env in ("development", "test")
        if self.serve_frontend_dir and not local:
            raise ValueError("SERVE_FRONTEND_DIR só é permitido com APP_ENV development ou test")
        if self.mail_backend == "file":
            if not local:
                raise ValueError("MAIL_BACKEND=file só é permitido com APP_ENV development ou test")
            if not self.mail_file_path:
                raise ValueError("MAIL_BACKEND=file exige MAIL_FILE_PATH")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.db_host,
                port=self.db_port,
                path=self.postgres_db,
            )
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
