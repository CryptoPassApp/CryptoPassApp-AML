"""Авто-регистрация пользователей и учёт дневных лимитов."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from bot.database import SessionMaker
from bot.models import User


def _today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


class AuthMiddleware(BaseMiddleware):
    """Гарантирует наличие User в БД и вешает объект user на данные хэндлера."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        async with SessionMaker() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == tg_user.id)
            )
            user = result.scalar_one_or_none()

            today = _today_str()
            if user is None:
                user = User(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    full_name=tg_user.full_name,
                    language="ru" if (tg_user.language_code or "").startswith("ru") else "en",
                    scans_reset_at=today,
                )
                session.add(user)
                try:
                    await session.commit()
                except IntegrityError:
                    # гонка апдейтов: параллельный хэндлер уже создал этого юзера
                    await session.rollback()
                    user = (
                        await session.execute(
                            select(User).where(User.telegram_id == tg_user.id)
                        )
                    ).scalar_one()
                else:
                    await session.refresh(user)
            else:
                changed = False
                if user.username != tg_user.username or user.full_name != tg_user.full_name:
                    user.username = tg_user.username
                    user.full_name = tg_user.full_name
                    changed = True
                if user.scans_reset_at != today:
                    user.scans_today = 0
                    user.scans_reset_at = today
                    changed = True
                user.last_seen_at = datetime.utcnow()
                await session.commit()

            data["user"] = user
            data["db_session"] = session
            try:
                return await handler(event, data)
            finally:
                await session.close()


def register_middlewares(dp) -> None:
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
