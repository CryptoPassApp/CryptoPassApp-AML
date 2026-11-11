import json
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    SuccessfulPayment,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.i18n import t
from bot.keyboards import MainCB, main_menu, pro_plans
from bot.models import User
from bot.services.stars_payment import activate_pro, plan_by_id, subscription_from_payload

logger = logging.getLogger(__name__)
router = Router(name="subscription")


@router.callback_query(MainCB.filter(F.action == "buy"))
async def buy_pro(callback: CallbackQuery, callback_data: MainCB, user: User, state: FSMContext) -> None:
    plan = plan_by_id(callback_data.value)
    if plan is None or not settings.bot_token:
        await callback.answer("Config error", show_alert=True)
        return

    await callback.message.answer_invoice(
        title=plan["label_ru"] if user.language == "ru" else plan["label_en"],
        description=(
            "Доступ ко всем функциям CryptoPass"
            if user.language == "ru"
            else "Full access to all CryptoPass features"
        ),
        payload=json.dumps({"plan": callback_data.value}),
        provider_token="",  # для XTR (Telegram Stars) токен провайдера не нужен
        currency="XTR",
        prices=[LabeledPrice(label="PRO", amount=plan["stars"])],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(
    message: Message,
    user: User,
    db_session: AsyncSession,
    state: FSMContext,
) -> None:
    payment: SuccessfulPayment = message.successful_payment
    plan_id = subscription_from_payload(payment.invoice_payload)
    plan = plan_by_id(plan_id)

    expires_at = await activate_pro(
        db_session,
        user,
        plan_id,
        payment.telegram_payment_charge_id,
        payment.total_amount,
    )
    logger.info("PRO activated: user=%s plan=%s stars=%s", user.telegram_id, plan_id, payment.total_amount)

    await message.answer(
        t(
            user.language,
            "payment_success",
            date=expires_at.strftime("%d.%m.%Y"),
        ),
        parse_mode="Markdown",
        reply_markup=main_menu(user.language),
    )


@router.callback_query(MainCB.filter(F.action == "restore"))
async def restore_pro(callback: CallbackQuery, user: User) -> None:
    status = (
        "✅ PRO активен до " + user.pro_expires_at.strftime("%d.%m.%Y")
        if user.is_pro_active
        else "❌ Активная подписка не найдена"
    )
    await callback.answer(status, show_alert=True)
