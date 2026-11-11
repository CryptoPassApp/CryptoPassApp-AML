from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.i18n import t
from bot.keyboards import MainCB, language_menu, main_menu
from bot.models import User

router = Router(name="language")


@router.message(F.text == "/lang")
@router.callback_query(MainCB.filter(F.action == "lang"))
async def language_menu_show(event: Message | CallbackQuery, user: User) -> None:
    text = t(user.language, "lang_prompt")
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=language_menu(user.language))
        await event.answer()
    else:
        await event.answer(text, reply_markup=language_menu(user.language))


@router.callback_query(MainCB.filter(F.action == "set_lang"))
async def set_language(
    callback: CallbackQuery,
    callback_data: MainCB,
    user: User,
    db_session,
) -> None:
    lang = callback_data.value if callback_data.value in ("ru", "en") else "en"
    user.language = lang
    db_session.add(user)
    await db_session.commit()
    # После выбора языка показываем полное главное меню
    await callback.message.edit_text(
        t(lang, "start_welcome", name=user.full_name or "friend"),
        parse_mode="Markdown",
        reply_markup=main_menu(lang),
    )
    await callback.answer()
