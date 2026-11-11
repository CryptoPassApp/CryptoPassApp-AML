import json

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from bot.keyboards import MainCB, main_menu, scan_result
from bot.models import Scan, User
from bot.services import aml_engine
from bot.services.passport_generator import build_passport, render_passport_text
from bot.services.stars_payment import scans_per_day
from bot.services.ton_api import TonAPIError, TonAPIClient, detect_network, is_supported_address
from bot.services.tron_api import TronAPIClient

router = Router(name="scanner")

LEVEL_TEXT_KEYS = {
    "clean": "scan_result_clean",
    "low": "scan_result_low",
    "medium": "scan_result_medium",
    "high": "scan_result_high",
    "critical": "scan_result_critical",
}

FLAG_LABELS = aml_engine.FLAG_LABELS


class ScanStates(StatesGroup):
    waiting_address = State()


async def _check_daily_limit(user: User, session: AsyncSession) -> bool:
    """Сбрасывает счётчик при смене суток; True если лимит ещё есть."""
    from datetime import datetime

    today = datetime.utcnow().strftime("%Y-%m-%d")
    if user.scans_reset_at != today:
        user.scans_today = 0
        user.scans_reset_at = today
        session.add(user)
        await session.commit()
    return user.scans_today < scans_per_day(user)


def _format_result(lang: str, aml: dict) -> str:
    level = aml["risk_level"]
    key = LEVEL_TEXT_KEYS.get(level, "scan_result_clean")
    flags_str = "\n".join(f"• {FLAG_LABELS.get(f, f)}" for f in aml["flags"]) or "—"
    text = t(lang, key, score=int(aml["risk_score"]), flags=flags_str)
    return text + f"\n\n⭐ Trust Score: *{int(aml['trust_score'])}/100*"


async def run_scan(address: str) -> dict:
    """Полный цикл скана: TON (TonAPI) или Tron (TronGrid/Tronscan) -> AML -> паспорт."""
    network = detect_network(address)
    if network == "tron":
        client = TronAPIClient()
    else:
        client = TonAPIClient()
    try:
        profile = await client.full_profile(address)
    finally:
        await client.close()
    aml = aml_engine.analyze_wallet(profile)
    aml["network"] = network
    passport = build_passport(profile, aml)
    return {"aml": aml, "passport": passport}


async def process_scan_message(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> None:
    address = message.text.strip()
    lang = user.language

    if not is_supported_address(address):
        await message.answer(t(lang, "error_invalid_address"), parse_mode="Markdown")
        return

    if not await _check_daily_limit(user, session):
        await message.answer(
            t(lang, "free_limit_reached", count=user.scans_today), parse_mode="Markdown"
        )
        return

    wait_msg = await message.answer(t(lang, "scan_processing", count="…"), parse_mode="Markdown")

    try:
        result = await run_scan(address)
    except TonAPIError:
        await wait_msg.edit_text(t(lang, "error_api_unavailable"))
        return

    aml = result["aml"]
    user.scans_today = (user.scans_today or 0) + 1
    session.add(
        Scan(
            user_id=user.id,
            address=address,
            risk_score=aml["risk_score"],
            trust_score=aml["trust_score"],
            risk_level=aml["risk_level"],
            flags=json.dumps(aml["flags"]),
            raw_data=json.dumps(result["passport"], ensure_ascii=False, default=str),
            is_demo=0,
        )
    )
    await session.commit()

    await wait_msg.edit_text(
        _format_result(lang, aml),
        parse_mode="Markdown",
        reply_markup=scan_result(lang, address),
    )
    if state is not None:
        await state.clear()


@router.message(ScanStates.waiting_address, F.text)
async def scan_address_input(message: Message, user: User, db_session: AsyncSession, state: FSMContext):
    # Команда вместо адреса: остаёмся в режиме ожидания и просим адрес снова
    if message.text.startswith("/"):
        await message.answer(t(user.language, "scan_enter_address"), parse_mode="Markdown")
        return
    await process_scan_message(message, user, db_session, state)


@router.message(F.text.regexp(r"^(EQ|UQ)[A-Za-z0-9_-]{46}$|^0:[0-9a-fA-F]{64}$|^T[1-9A-HJ-NP-Za-km-z]{33}$"))
async def scan_from_plain_text(message: Message, user: User, db_session: AsyncSession):
    await process_scan_message(message, user, db_session)


@router.callback_query(MainCB.filter(F.action == "scan_again"))
async def scan_again(callback: CallbackQuery, user: User, state: FSMContext):
    await state.set_state(ScanStates.waiting_address)
    await callback.message.edit_text(t(user.language, "scan_enter_address"), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(MainCB.filter(F.action == "passport_for"))
async def passport_for_address(
    callback: CallbackQuery,
    callback_data: MainCB,
    user: User,
    db_session: AsyncSession,
):
    from bot.handlers.passport import send_passport

    await send_passport(callback.message, user, db_session, callback_data.value)
    await callback.answer()
