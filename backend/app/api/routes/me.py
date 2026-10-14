"""Dados da própria conta (RF-006)."""

from fastapi import APIRouter

from app.api.deps import AccountAuth
from app.api.routes.auth import me_out
from app.schemas.auth import MeOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
def get_me(auth: AccountAuth) -> MeOut:
    return me_out(auth.user)
