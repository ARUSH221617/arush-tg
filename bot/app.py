import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config import settings
from bot.handlers import router as main_router
from bot.middlewares import WhitelistAuthMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("arush-agent")

async def start_bot():
    logger.info("Initializing Arush Manager Agent Telegram Bot...")

    # Configure proxy if specified (for Iran network access to api.telegram.org)
    session = None
    if settings.TELEGRAM_PROXY:
        logger.info(f"Connecting to Telegram API via proxy: {settings.TELEGRAM_PROXY}")
        session = AiohttpSession(proxy=settings.TELEGRAM_PROXY)

    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )

    dp = Dispatcher()

    # Register whitelist security middleware
    dp.message.middleware(WhitelistAuthMiddleware())

    # Include routers
    dp.include_router(main_router)

    logger.info("Bot started successfully. Waiting for updates...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(start_bot())
