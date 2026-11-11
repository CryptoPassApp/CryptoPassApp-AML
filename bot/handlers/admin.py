import asyncio
import json
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.i18n import t
from bot.keyboards import MainCB, admin_panel, confirm_broadcast
from bot.models import AdminLog, Scan, Subscription, User
from bot.services.stars_payment import activate_pro, plan_by_id

logger = logging.getLogger(__name__)
router = Router(name="admin")


class BroadcastStates(StatesGroup):
    waiting_text = State()


class GrantStates(StatesGroup):
    waiting_input = State()


def _is_admin(user: User) -> bool:
    return user.telegram_id in settings.admin_ids


async def _stats_text(session: AsyncSession, lang: str) -> str:
    users_total = (await session.execute(select(func.count(User.id)))).scalar() or 0
    pro_total = (
        await session.execute(select(func.count(User.id)).where(User.is_pro == 1))
    ).scalar() or 0
    scans_total = (await session.execute(select(func.count(Scan.id)))).scalar() or 0
    stars_total = (await session.execute(select(func.coalesce(func.sum(Subscription.stars_amount), 0)))).scalar() or 0
    return t(lang, "admin_stats", users=users_total, pro=pro_total, scans_today="—", scans_total=scans_total, stars_total=stars_total)


async def _stats_today(session: AsyncSession) -> int:
    from datetime import datetime

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await session.execute(select(func.count(Scan.id)).where(Scan.created_at >= today_start))
    return result.scalar() or 0


@router.message(F.text == "/admin")
async def admin_panel_cmd(message: Message, user: User, db_session: AsyncSession) -> None:
    if not _is_admin(user):
        return
    text = await _stats_text(db_session, user.language)
    await message.answer(text, parse_mode="Markdown", reply_markup=admin_panel(user.language))


@router.callback_query(MainCB.filter(F.action == "admin_stats"))
async def admin_stats(callback: CallbackQuery, user: User, db_session: AsyncSession) -> None:
    if not _is_admin(user):
        await callback.answer()
        return
    scans_today = await _stats_today(db_session)
    users_total = (await db_session.execute(select(func.count(User.id)))).scalar() or 0
    pro_total = (
        await db_session.execute(select(func.count(User.id)).where(User.is_pro == 1))
    ).scalar() or 0
    scans_total = (await db_session.execute(select(func.count(Scan.id)))).scalar() or 0
    stars_total = (
        await db_session.execute(
            select(func.coalesce(func.sum(Subscription.stars_amount), 0))
        )
    ).scalar() or 0
    await callback.message.edit_text(
        t(
            user.language,
            "admin_stats",
            users=users_total,
            pro=pro_total,
            scans_today=scans_today,
            scans_total=scans_total,
            stars_total=stars_total,
        ),
        parse_mode="Markdown",
        reply_markup=admin_panel(user.language),
    )
    await callback.answer()


@router.callback_query(MainCB.filter(F.action == "admin_broadcast"))
async def admin_broadcast(
    callback: CallbackQuery, user: User, state: FSMContext
) -> None:
    if not _is_admin(user):
        await callback.answer()
        return
    await state.set_state(BroadcastStates.waiting_text)
    await callback.message.edit_text(t(user.language, "admin_broadcast_prompt"))
    await callback.answer()


@router.message(BroadcastStates.waiting_text, F.text)
async def broadcast_confirm_text(
    message: Message, user: User, state: FSMContext, db_session: AsyncSession
) -> None:
    if not _is_admin(user):
        return
    await state.update_data(broadcast_text=message.text)
    await state.set_state(BroadcastStates.waiting_text)
    await message.answer(
        t(user.language, "admin_broadcast_confirm", text=message.text),
        reply_markup=confirm_broadcast(user.language),
    )


@router.callback_query(MainCB.filter(F.action == "admin_broadcast_send"))
async def broadcast_send(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    db_session: AsyncSession,
    bot: Bot,
) -> None:
    if not _is_admin(user):
        await callback.answer()
        return
    data = await state.get_data()
    text = data.get("broadcast_text")
    await state.clear()
    if not text:
        await callback.answer()
        return

    result = await db_session.execute(select(User.telegram_id))
    tg_ids = result.scalars().all()

    success = failed = 0
    for tg_id in tg_ids:
        try:
            await bot.send_message(tg_id, text)
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    db_session.add(
        AdminLog(action="broadcast", details=json.dumps({"success": success, "failed": failed}))
    )
    await db_session.commit()

    await callback.message.edit_text(
        t(user.language, "admin_broadcast_sent", success=success, failed=failed)
    )
    await callback.answer()


@router.callback_query(MainCB.filter(F.action == "admin_grant"))
async def admin_grant(
    callback: CallbackQuery, user: User, state: FSMContext
) -> None:
    if not _is_admin(user):
        await callback.answer()
        return
    await state.set_state(GrantStates.waiting_input)
    await callback.message.edit_text(t(user.language, "admin_grant_prompt"), parse_mode="Markdown")
    await callback.answer()


@router.message(GrantStates.waiting_input, F.text)
async def grant_input(
    message: Message, user: User, state: FSMContext, db_session: AsyncSession
) -> None:
    if not _is_admin(user):
        return
    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[0].isdigit():
        await message.answer(t(user.language, "admin_grant_prompt"), parse_mode="Markdown")
        return

    tg_id = int(parts[0])
    plan_id = parts[1]
    plan = plan_by_id(plan_id)
    if plan is None:
        await message.answer(t(user.language, "admin_grant_prompt"), parse_mode="Markdown")
        return

    result = await db_session.execute(select(User).where(User.telegram_id == tg_id))
    target = result.scalar_one_or_none()
    if target is None:
        await message.answer(t(user.language, "error_api_unavailable"))
        return

    expires_at = await activate_pro(db_session, target, plan_id, f"manual:{tg_id}:{plan_id}", 0)
    db_session.add(
        AdminLog(
            action="grant_pro",
            details=json.dumps({"target": tg_id, "plan": plan_id, "by": user.telegram_id}),
        )
    )
    await db_session.commit()

    await message.answer(
        t(user.language, "admin_grant_done", user_id=tg_id, date=expires_at.strftime("%d.%m.%Y"))
    )
    await state.clear()
