import asyncio
import sys
import io
from pathlib import Path

if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from bot.commands import setup_bot_commands


async def main():
    try:
        from aiogram import Bot
        from aiogram.client.session.aiohttp import AiohttpSession
    except ImportError:
        print("❌ aiogram is not installed in the current environment.")
        sys.exit(1)

    print("=" * 60)
    print("🤖 ARUSH AGENT — TELEGRAM SLASH COMMANDS REGISTRATION")
    print("=" * 60)
    print(f"• Bot Token: {settings.TELEGRAM_BOT_TOKEN[:10]}...{settings.TELEGRAM_BOT_TOKEN[-5:]}")
    print(f"• Proxy    : {settings.TELEGRAM_PROXY or 'Direct (No Proxy)'}")
    print("\nRegistering commands across Default, Persian (fa), and English (en) scopes...")

    session = AiohttpSession(proxy=settings.TELEGRAM_PROXY) if settings.TELEGRAM_PROXY else None
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, session=session)

    try:
        success = await setup_bot_commands(bot)
        if success:
            print("\n✅ All 18 slash commands registered with Telegram successfully!")
            print("Users will now see the [/] menu button and command auto-completion in Telegram.")
        else:
            print("\n⚠️ Command registration encountered issues. Check network connection or bot token.")
    except Exception as e:
        print(f"\n❌ Failed to register commands: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
