"""Хелперы Telegram Stars (XTR): тарифы, лимиты, активация PRO."""

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Subscription, User

PLANS: dict[str, dict[str, Any]] = {
    "pro_week": {
        "stars": 75,
        "days": 7,
        "label_ru": "PRO на 1 неделю",
        "label_en": "PRO for 1 week",
        "scans_per_day": 50,
    },
    "pro_month": {
        "stars": 150,
        "days": 30,
        "label_ru": "PRO на 1 месяц",
        "label_en": "PRO for 1 month",
        "scans_per_day": 50,
    },
    "pro_year": {
        "stars": 999,
        "days": 365,
        "label_ru": "PRO на 1 год",
        "label_en": "PRO for 1 year",
        "scans_per_day": 999,
    },
}

FREE_LIMITS: dict[str, Any] = {
    "scans_per_day": 3,
    "passport_access": False,
    "history_access": False,
    "p2p_radar_access": False,
}


def plan_by_id(plan_id: str) -> dict[str, Any] | None:
    return PLANS.get(plan_id)


def scans_per_day(user: User) -> int:
    if user.is_pro_active:
        return 999
    return int(FREE_LIMITS["scans_per_day"])


async def activate_pro(
    session: AsyncSession,
    user: User,
    plan_id: str,
    payment_id: str,
    stars: int,
) -> datetime:
    """Активирует PRO и пишет запись о подписке. Возвращает дату окончания."""
    plan = plan_by_id(plan_id)
    if plan is None:
        raise ValueError(f"unknown plan: {plan_id}")

    now = datetime.utcnow()
    base = user.pro_expires_at if (user.is_pro_active and user.pro_expires_at) else now
    expires_at = base + timedelta(days=plan["days"])

    user.is_pro = 1
    user.pro_expires_at = expires_at

    session.add(
        Subscription(
            user_id=user.id,
            telegram_payment_id=payment_id,
            stars_amount=stars,
            plan=plan_id,
            expires_at=expires_at,
        )
    )
    await session.commit()
    return expires_at


async def stars_revenue_total(session: AsyncSession) -> int:
    result = await session.execute(select(Subscription.stars_amount))
    return int(sum(result.scalars().all() or []))


def subscription_from_payload(payload: str) -> str:
    """payload инвойса -> plan_id ('pro_month' | 'pro_year')."""
    try:
        data = json.loads(payload)
        plan = data.get("plan")
        if plan in PLANS:
            return plan
    except (json.JSONDecodeError, AttributeError):
        pass
    if payload in PLANS:
        return payload
    return "pro_month"
