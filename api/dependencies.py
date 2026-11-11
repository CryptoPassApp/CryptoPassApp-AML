"""Проверка Telegram WebApp initData и admin-токена."""

import hashlib
import hmac
import json
from typing import Any
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database import SessionMaker
from bot.models import User


def validate_init_data(init_data: str) -> dict[str, Any]:
    """Валидация initData по официальному алгоритму Telegram WebApp.

    secret_key = HMAC_SHA256(bot_token, key="WebAppData")
    hash = HMAC_SHA256(data_check_string, key=secret_key)

    Значения в initData приходят URL-encoded, подпись считается по
    декодированным значениям (parse_qsl), как описано в документации Telegram.
    """
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    if not parsed:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid initData")

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing hash")

    data_check_string = "\n".join(f"{k}={parsed[k]}" for k in sorted(parsed))

    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Signature mismatch")

    try:
        user_data = json.loads(parsed.get("user", "{}"))
    except json.JSONDecodeError:
        user_data = {}
    return {"user": user_data, "auth_date": parsed.get("auth_date")}


async def get_session() -> AsyncSession:
    async with SessionMaker() as session:
        yield session


async def get_tg_user(
    x_telegram_init_data: str = Header(default=""),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    # Локальная отладка без Telegram: DEV_BYPASS_AUTH=true создаёт тестового юзера
    if settings.dev_bypass_auth:
        return {
            "user": {
                "id": 900000001,
                "username": "dev_tester",
                "first_name": "Dev",
                "language_code": "ru",
            },
            "auth_date": None,
        }

    init_data = x_telegram_init_data
    if not init_data and authorization.startswith("tma "):
        init_data = authorization[4:]
    if not init_data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing initData")
    return validate_init_data(init_data)


async def get_current_user(
    tg_data: dict[str, Any] = Depends(get_tg_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    tg_user = tg_data.get("user") or {}
    telegram_id = tg_user.get("id")
    if not telegram_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No user in initData")

    result = await session.execute(select(User).where(User.telegram_id == int(telegram_id)))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=int(telegram_id),
            username=tg_user.get("username"),
            full_name=" ".join(
                filter(None, [tg_user.get("first_name"), tg_user.get("last_name")])
            )
            or None,
            language="ru" if (tg_user.get("language_code") or "").startswith("ru") else "en",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def require_admin_token(x_admin_token: str = Header(default="")) -> None:
    if not settings.api_secret_key or x_admin_token != settings.api_secret_key:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
