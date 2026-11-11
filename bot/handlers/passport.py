import json

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from bot.keyboards import MainCB, pro_plans
from bot.models import Scan, User
from bot.services.passport_generator import render_passport_text
from bot.services.ton_api import TonAPIError, is_supported_address

router = Router(name="passport")


async def send_passport(message: Message, user: User, session: AsyncSession, address: str | None = None) -> None:
    lang = user.language

    if not user.is_pro_active:
        await message.answer(
            t(lang, "passport_pro_only"),
            parse_mode="Markdown",
            reply_markup=pro_plans(lang),
        )
        return

    if not address:
        from sqlalchemy import select

        last = await session.execute(
            select(Scan).where(Scan.user_id == user.id).order_by(Scan.id.desc()).limit(1)
        )
        row = last.scalar_one_or_none()
        if row is None:
            await message.answer(t(lang, "scan_enter_address"), parse_mode="Markdown")
            return
        address = row.address
        passport = json.loads(row.raw_data) if row.raw_data else None
        if passport:
            await message.answer(render_passport_text(passport, lang), parse_mode="Markdown")
            return

    from bot.handlers.scanner import run_scan

    if not is_supported_address(address):
        await message.answer(t(lang, "error_invalid_address"), parse_mode="Markdown")
        return

    try:
        result = await run_scan(address)
    except TonAPIError:
        await message.answer(t(lang, "error_api_unavailable"))
        return

    session.add(
        Scan(
            user_id=user.id,
            address=address,
            risk_score=result["aml"]["risk_score"],
            trust_score=result["aml"]["trust_score"],
            risk_level=result["aml"]["risk_level"],
            flags=json.dumps(result["aml"]["flags"]),
            raw_data=json.dumps(result["passport"], ensure_ascii=False, default=str),
        )
    )
    await session.commit()
    await message.answer(
        render_passport_text(result["passport"], lang),
        parse_mode="Markdown",
    )


@router.message(F.text == "/passport")
@router.callback_query(MainCB.filter(F.action == "passport"))
async def passport_command(event: Message | CallbackQuery, user: User, db_session: AsyncSession) -> None:
    if isinstance(event, CallbackQuery):
        await send_passport(event.message, user, db_session)
        await event.answer()
    else:
        await send_passport(event, user, db_session)


@router.message(F.text == "/pro")
@router.callback_query(MainCB.filter(F.action == "pro"))
async def show_pro(event: Message | CallbackQuery, user: User) -> None:
    text = t(user.language, "pro_benefits")
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, parse_mode="Markdown", reply_markup=pro_plans(user.language))
        await event.answer()
    else:
        await event.answer(text, parse_mode="Markdown", reply_markup=pro_plans(user.language))
