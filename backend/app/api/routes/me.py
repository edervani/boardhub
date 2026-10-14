"""Dados da própria conta (RF-006)."""

from fastapi import APIRouter

from app.api.deps import CurrentAuth
from app.api.routes.auth import me_out
from app.schemas.auth import MeOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
def get_me(auth: CurrentAuth) -> MeOut:
    return me_out(auth.user)
