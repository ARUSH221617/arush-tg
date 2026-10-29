from typing import Callable, Dict, Any, Awaitable

try:
    from aiogram import BaseMiddleware
    from aiogram.types import TelegramObject, Message, CallbackQuery
except ImportError:
    BaseMiddleware = object  # type: ignore
    TelegramObject = Any  # type: ignore
    Message = Any  # type: ignore
    CallbackQuery = Any  # type: ignore

from config import settings


class WhitelistAuthMiddleware(BaseMiddleware):
    """Ensures only authorized Telegram user IDs can interact with the bot or click confirmation buttons."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = getattr(event, "from_user", None)
        user_id = user.id if user else None

        if not settings.ALLOWED_TELEGRAM_USER_IDS:
            return await handler(event, data)

        if user_id not in settings.ALLOWED_TELEGRAM_USER_IDS:
            if hasattr(event, "answer"):
                await event.answer(
                    f"⛔ <b>Access Denied / دسترسی غیرمجاز</b>\n\n"
                    f"This bot is locked to its host machine.\n"
                    f"Your Telegram ID: <code>{user_id}</code>\n\n"
                    f"Add this ID to <code>ALLOWED_TELEGRAM_USER_IDS</code> in <code>.env</code> to gain access.",
                    parse_mode="HTML"
                )
            return None

        return await handler(event, data)
