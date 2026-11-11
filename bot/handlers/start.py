from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.i18n import t
from bot.keyboards import MainCB, language_menu, main_menu
from bot.models import User

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, user: User, command: CommandObject | None = None) -> None:
    lang = user.language
    name = user.full_name or message.from_user.username or message.from_user.first_name
    # Сообщение 1: приветствие
    await message.answer(
        t(lang, "start_welcome", name=name),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )
    # Сообщение 2: выбор языка с кнопками
    await message.answer(t(lang, "lang_prompt"), reply_markup=language_menu(lang))


@router.message(F.text == "/help")
@router.callback_query(MainCB.filter(F.action == "help"))
async def show_help(event: Message | CallbackQuery, user: User) -> None:
    text = t(user.language, "help_text")
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, parse_mode="Markdown", reply_markup=main_menu(user.language))
        await event.answer()
    else:
        await event.answer(text, parse_mode="Markdown", reply_markup=main_menu(user.language))


@router.callback_query(MainCB.filter(F.action == "back"))
async def back_to_menu(callback: CallbackQuery, user: User) -> None:
    await callback.message.edit_text(
        t(user.language, "start_welcome", name=user.full_name or "friend"),
        parse_mode="Markdown",
        reply_markup=main_menu(user.language),
    )
    await callback.answer()
