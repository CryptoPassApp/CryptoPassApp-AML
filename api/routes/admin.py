import json
import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_session, require_admin_token
from bot.models import AdminLog, Scan, Subscription, User

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin_token)])

PLANS_AVAILABLE = ("pro_month", "pro_year")


@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session)) -> dict:
    users_total = (await session.execute(select(func.count(User.id)))).scalar() or 0
    pro_total = (
        await session.execute(select(func.count(User.id)).where(User.is_pro == 1))
    ).scalar() or 0
    scans_total = (await session.execute(select(func.count(Scan.id)))).scalar() or 0
    stars_total = (
        await session.execute(select(func.coalesce(func.sum(Subscription.stars_amount), 0)))
    ).scalar() or 0

    from datetime import datetime

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    scans_today = (
        await session.execute(select(func.count(Scan.id)).where(Scan.created_at >= today_start))
    ).scalar() or 0

    return {
        "users": users_total,
        "pro_subscribers": pro_total,
        "scans_today": scans_today,
        "scans_total": scans_total,
        "stars_total": stars_total,
    }


class BroadcastRequest(BaseModel):
    text: str


@router.post("/broadcast")
async def broadcast(
    body: BroadcastRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    import logging

    from aiogram import Bot
    from bot.config import settings as cfg

    logger = logging.getLogger("cryptopass.broadcast")

    result = await session.execute(select(User.telegram_id))
    tg_ids = result.scalars().all()

    success = failed = 0
    bot = Bot(token=cfg.bot_token)
    try:
        for tg_id in tg_ids:
            try:
                await bot.send_message(tg_id, body.text)
                success += 1
            except Exception as e:
                logger.warning("broadcast to %s failed: %s", tg_id, e)
                failed += 1
            await asyncio.sleep(0.05)
    finally:
        await bot.session.close()

    session.add(
        AdminLog(action="broadcast", details=json.dumps({"success": success, "failed": failed}))
    )
    await session.commit()
    return {"success": success, "failed": failed, "total": len(tg_ids)}


class GrantProRequest(BaseModel):
    telegram_id: int
    plan: str = "pro_month"


@router.post("/grant_pro")
async def grant_pro(
    body: GrantProRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    from bot.services.stars_payment import activate_pro, plan_by_id

    plan = plan_by_id(body.plan)
    if plan is None:
        return {"error": "unknown plan", "available": list(PLANS_AVAILABLE)}

    result = await session.execute(select(User).where(User.telegram_id == body.telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        return {"error": "user not found"}

    expires_at = await activate_pro(
        session, user, body.plan, f"api:{body.telegram_id}:{body.plan}", 0
    )
    session.add(
        AdminLog(
            action="grant_pro",
            details=json.dumps({"target": body.telegram_id, "plan": body.plan, "by": "api"}),
        )
    )
    await session.commit()
    return {"ok": True, "expires_at": expires_at.isoformat()}
