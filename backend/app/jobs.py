"""Rotina diária de manutenção (doc 13 §5): `python -m app.jobs`.

Conclui exclusões de conta vencidas (RF-030), apaga exportações expiradas (RF-029) e remove
cadastros de menores de 12 anos sem confirmação do responsável (RF-034). Cada etapa é
independente; o código de saída é diferente de zero se alguma exclusão falhar.
"""

import sys

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import get_engine
from app.services import guardian_service, privacy_service

log = get_logger(__name__)


def run_daily(db: Session) -> int:
    """Executa as tarefas e devolve a quantidade de falhas."""
    removed_exports = privacy_service.purge_expired_exports(db)
    unconfirmed = guardian_service.purge_unconfirmed_under_12(db)
    deleted, failed = privacy_service.purge_due_deletions(db)
    log.info("rotina diária concluída", extra={
        "exports_removidos": removed_exports, "menores_sem_confirmacao": unconfirmed,
        "contas_excluidas": deleted, "falhas": failed})
    return failed


def main() -> int:
    configure_logging(get_settings().log_level)
    with Session(get_engine(), expire_on_commit=False) as db:
        return 1 if run_daily(db) else 0


if __name__ == "__main__":
    sys.exit(main())
