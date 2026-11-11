import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_session
from bot.config import settings
from bot.models import Scan, User
from bot.services.stars_payment import PLANS, scans_per_day

router = APIRouter(prefix="/api/user", tags=["user"])


class LanguageRequest(BaseModel):
    language: str


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "full_name": user.full_name,
        "language": user.language,
        "is_pro": user.is_pro_active,
        "pro_expires_at": user.pro_expires_at.isoformat() if user.pro_expires_at else None,
        "scans_today": user.scans_today or 0,
        "scans_limit": scans_per_day(user),
    }


@router.post("/language")
async def change_language(
    body: LanguageRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if body.language not in ("ru", "en"):
        raise HTTPException(status_code=400, detail="language must be 'ru' or 'en'")
    user.language = body.language
    session.add(user)
    await session.commit()
    return {"language": user.language}


@router.get("/history")
async def history(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not user.is_pro_active:
        raise HTTPException(status_code=402, detail="PRO required")

    result = await session.execute(
        select(Scan).where(Scan.user_id == user.id).order_by(Scan.id.desc()).limit(50)
    )
    scans = result.scalars().all()
    return {
        "items": [
            {
                "address": s.address,
                "risk_score": s.risk_score,
                "trust_score": s.trust_score,
                "risk_level": s.risk_level,
                "created_at": s.created_at.isoformat(),
                "is_demo": bool(s.is_demo),
            }
            for s in scans
        ]
    }


class InvoiceRequest(BaseModel):
    plan: str


@router.post("/invoice")
async def create_invoice(
    body: InvoiceRequest,
    user: User = Depends(get_current_user),
) -> dict:
    plan = PLANS.get(body.plan)
    if plan is None:
        raise HTTPException(status_code=400, detail="unknown plan")
    if not settings.bot_token:
        raise HTTPException(status_code=503, detail="bot token not configured")

    from aiogram import Bot
    from aiogram.types import LabeledPrice

    bot = Bot(token=settings.bot_token)
    try:
        link = await bot.create_invoice_link(
            title=plan["label_en"],
            description="Full access to all CryptoPass features",
            payload=json.dumps({"plan": body.plan, "tg_id": user.telegram_id}),
            currency="XTR",
            prices=[LabeledPrice(label="PRO", amount=plan["stars"])],
        )
    finally:
        await bot.session.close()
    return {"invoice_url": link, "stars": plan["stars"]}
