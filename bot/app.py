import asyncio
import logging

try:
    from aiogram import Bot, Dispatcher
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    HAS_AIOGRAM = True
except ImportError:
    HAS_AIOGRAM = False

from config import settings
from bot.handlers import router as main_router
from bot.middlewares import WhitelistAuthMiddleware
from core.scheduler import routine_scheduler
from core.watchdog import watchdog
from tools.freelance_radar import freelance_radar

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("arush-agent")


async def start_bot():
    if not HAS_AIOGRAM:
        raise RuntimeError("aiogram is not installed in the current environment.")

    logger.info("Initializing Arush Manager Agent Telegram Bot...")

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
    dp.message.middleware(WhitelistAuthMiddleware())
    dp.callback_query.middleware(WhitelistAuthMiddleware())
    dp.include_router(main_router)

    # Register Telegram slash commands
    from bot.commands import setup_bot_commands
    try:
        await setup_bot_commands(bot)
    except Exception as e:
        logger.warning(f"Could not register slash commands with Telegram: {e}")

    async def notify_owners(text: str) -> None:
        for uid in settings.ALLOWED_TELEGRAM_USER_IDS:
            try:
                await bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Failed to send scheduled notification to {uid}: {e}")

    async def notify_high_match_lead(lead: dict) -> None:
        alert_txt = freelance_radar.format_telegram_alert(lead)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚀 ثبت فوری پیشنهاد در سایت", url=lead.get("url") or "https://ponisha.ir")]
            ]
        )
        for uid in settings.ALLOWED_TELEGRAM_USER_IDS:
            try:
                await bot.send_message(chat_id=uid, text=alert_txt, reply_markup=kb, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Failed to send radar alert to {uid}: {e}")

    # Start background daemons (Phase 3 Radar Poller, Phase 6 Daily Routines, Phase 7 Health Server)
    await watchdog.start_health_server()
    radar_task = asyncio.create_task(freelance_radar.start_background_poller(on_high_match=notify_high_match_lead))
    scheduler_task = asyncio.create_task(routine_scheduler.run_loop(send_notification=notify_owners))

    logger.info("Bot and background daemons started. Entering self-healing polling loop...")
    try:
        await watchdog.run_with_self_healing(lambda: dp.start_polling(bot))
    finally:
        freelance_radar.stop()
        routine_scheduler.stop()
        radar_task.cancel()
        scheduler_task.cancel()
        await watchdog.stop()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(start_bot())
