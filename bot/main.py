import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.database import SessionMaker, init_db
from bot.handlers import admin, language, passport, scanner, start, subscription
from bot.middleware import register_middlewares
from bot.services.ton_api import TonAPIClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


async def main() -> None:
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")

    await init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    ton_client = TonAPIClient()
    dp["ton_client"] = ton_client

    dp.include_routers(
        start.router,
        admin.router,
        subscription.router,
        language.router,
        passport.router,
        scanner.router,
    )
    register_middlewares(dp)

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        await ton_client.close()
        await SessionMaker.close_all()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as e:
        raise e
