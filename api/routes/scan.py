import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_session
from bot.handlers.scanner import run_scan
from bot.models import Scan, User
from bot.services.stars_payment import scans_per_day
from bot.services.ton_api import is_supported_address

router = APIRouter(prefix="/api/scan", tags=["scan"])


class ScanRequest(BaseModel):
    address: str


async def _reset_daily_counter(user: User, session: AsyncSession) -> None:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if user.scans_reset_at != today:
        user.scans_today = 0
        user.scans_reset_at = today
        session.add(user)
        await session.commit()


@router.post("")
async def run_scan_api(
    body: ScanRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    address = body.address.strip()
    if not is_supported_address(address):
        raise HTTPException(status_code=400, detail="invalid address")

    await _reset_daily_counter(user, session)
    if (user.scans_today or 0) >= scans_per_day(user):
        raise HTTPException(status_code=429, detail="daily limit reached")

    result = await run_scan(address)
    aml = result["aml"]

    user.scans_today = (user.scans_today or 0) + 1
    scan = Scan(
        user_id=user.id,
        address=address,
        risk_score=aml["risk_score"],
        trust_score=aml["trust_score"],
        risk_level=aml["risk_level"],
        flags=json.dumps(aml["flags"]),
        raw_data=json.dumps(aml, ensure_ascii=False, default=str),
    )
    session.add(scan)
    await session.commit()

    return {"scan_id": scan.id, **aml, "is_demo": False}


@router.get("/{address}")
async def last_scan(
    address: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(Scan)
        .where(Scan.user_id == user.id, Scan.address == address)
        .order_by(Scan.id.desc())
        .limit(1)
    )
    scan = result.scalar_one_or_none()
    if scan is None:
        raise HTTPException(status_code=404, detail="scan not found")
    return {
        "scan_id": scan.id,
        "address": scan.address,
        "risk_score": scan.risk_score,
        "trust_score": scan.trust_score,
        "risk_level": scan.risk_level,
        "flags": json.loads(scan.flags or "[]"),
        "created_at": scan.created_at.isoformat(),
        "is_demo": bool(scan.is_demo),
    }
