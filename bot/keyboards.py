from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings


class MainCB(CallbackData, prefix="main"):
    action: str
    value: str = ""


def main_menu(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text={"ru": "🚀 Открыть CryptoPass", "en": "🚀 Open CryptoPass"}[lang],
        web_app=WebAppInfo(url=settings.mini_app_url),
    )
    kb.row(
        InlineKeyboardButton(
            text={"ru": "🪪 Мой паспорт", "en": "🪪 My passport"}[lang],
            callback_data=MainCB(action="passport").pack(),
        ),
        InlineKeyboardButton(
            text={"ru": "⭐ Стать PRO", "en": "⭐ Go PRO"}[lang],
            callback_data=MainCB(action="pro").pack(),
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text={"ru": "❓ Помощь", "en": "❓ Help"}[lang],
            callback_data=MainCB(action="help").pack(),
        ),
        InlineKeyboardButton(
            text={"ru": "🌐 Язык", "en": "🌐 Language"}[lang],
            callback_data=MainCB(action="lang").pack(),
        ),
    )
    return kb.as_markup()


def scan_result(lang: str = "ru", address: str = "") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text={"ru": "🔄 Проверить ещё", "en": "🔄 Scan again"}[lang],
        callback_data=MainCB(action="scan_again").pack(),
    )
    kb.button(
        text={"ru": "🪪 Полный паспорт", "en": "🪪 Full passport"}[lang],
        callback_data=MainCB(action="passport_for", value=address).pack(),
    )
    kb.button(
        text={"ru": "📤 Поделиться", "en": "📤 Share"}[lang],
        url=f"https://t.me/share/url?url={settings.mini_app_url}",
    )
    kb.adjust(2, 1)
    return kb.as_markup()


def pro_plans(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text={"ru": "⭐ PRO на 1 неделю — 75★", "en": "⭐ PRO 1 week — 75★"}[lang],
        callback_data=MainCB(action="buy", value="pro_week").pack(),
    )
    kb.button(
        text={"ru": "⭐ PRO на 1 месяц — 150★", "en": "⭐ PRO 1 month — 150★"}[lang],
        callback_data=MainCB(action="buy", value="pro_month").pack(),
    )
    kb.button(
        text={"ru": "⭐ PRO на 1 год — 999★ (выгодно)", "en": "⭐ PRO 1 year — 999★ (best)"}[lang],
        callback_data=MainCB(action="buy", value="pro_year").pack(),
    )
    kb.button(
        text={"ru": "◀️ Назад", "en": "◀️ Back"}[lang],
        callback_data=MainCB(action="back").pack(),
    )
    kb.adjust(1)
    return kb.as_markup()


def language_menu(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский", callback_data=MainCB(action="set_lang", value="ru").pack())
    kb.button(text="🇬🇧 English", callback_data=MainCB(action="set_lang", value="en").pack())
    kb.adjust(2)
    return kb.as_markup()


def admin_panel(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text={"ru": "📊 Статистика", "en": "📊 Stats"}[lang],
        callback_data=MainCB(action="admin_stats").pack(),
    )
    kb.button(
        text={"ru": "📢 Рассылка", "en": "📢 Broadcast"}[lang],
        callback_data=MainCB(action="admin_broadcast").pack(),
    )
    kb.button(
        text={"ru": "💎 Выдать PRO", "en": "💎 Grant PRO"}[lang],
        callback_data=MainCB(action="admin_grant").pack(),
    )
    kb.adjust(1)
    return kb.as_markup()


def confirm_broadcast(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text={"ru": "✅ Отправить", "en": "✅ Send"}[lang],
        callback_data=MainCB(action="admin_broadcast_send").pack(),
    )
    kb.button(
        text={"ru": "❌ Отмена", "en": "❌ Cancel"}[lang],
        callback_data=MainCB(action="admin_cancel").pack(),
    )
    kb.adjust(2)
    return kb.as_markup()
