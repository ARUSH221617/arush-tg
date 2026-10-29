from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from config import settings

class WhitelistAuthMiddleware(BaseMiddleware):
    """Ensures only the authorized user can interact with the bot and control the PC."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            
            # If no allowed IDs configured yet, allow the first user and notify them
            if not settings.ALLOWED_TELEGRAM_USER_IDS:
                return await handler(event, data)

            if user_id not in settings.ALLOWED_TELEGRAM_USER_IDS:
                await event.answer(
                    f"⛔ **Access Denied / دسترسی غیرمجاز**\n\n"
                    f"This bot is locked to its host machine.\n"
                    f"Your Telegram ID: `{user_id}`\n\n"
                    f"Add this ID to `ALLOWED_TELEGRAM_USER_IDS` in `.env` to gain access.",
                    parse_mode="Markdown"
                )
                return

        return await handler(event, data)
