from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_session
from api.routes.demo import DEMO_PRESETS, enrich
from bot.handlers.scanner import run_scan
from bot.models import User
from bot.services.ton_api import is_supported_address

router = APIRouter(prefix="/api/passport", tags=["passport"])


@router.get("/{address}")
async def passport(
    address: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not user.is_pro_active:
        raise HTTPException(status_code=402, detail="PRO required")

    address = address.strip()
    if address in DEMO_PRESETS or address.startswith("EQD_DEMO_"):
        return enrich(DEMO_PRESETS.get(address, DEMO_PRESETS["clean"]))

    if not is_supported_address(address):
        raise HTTPException(status_code=400, detail="invalid address")

    result = await run_scan(address)
    return result["passport"]
