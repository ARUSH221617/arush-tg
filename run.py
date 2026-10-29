import asyncio
import argparse
import sys
import io

if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

from config import settings
from core.router_client import router_client
from tools.computer_use import controller as computer_ctrl
from scripts.backup import run_daily_backup

async def run_diagnostics_and_validation() -> bool:
    """
    Checks 9Router health and verifies that all default models configured in .env
    (Chat, STT, Image, Embedding) exist in 9Router's model registries.
    """
    print("\n🔍 STEP 1: Checking 9Router Connectivity...")
    is_active = await router_client.check_health()
    if not is_active:
        print("  ❌ 9Router is NOT ACTIVE or unreachable at:", settings.NINEROUTER_URL)
        print("  👉 Check that 9Router is running (e.g. `npx 9router start` or check your VPS tunnel)")
        print("  👉 Ensure NINEROUTER_URL and NINEROUTER_KEY in your .env are correct.")
        return False

    print(f"  ✅ 9Router is ACTIVE at {settings.NINEROUTER_URL}")

    print("\n🔍 STEP 2: Fetching 9Router Models & Validating Defaults from .env...")
    validation = await router_client.validate_configured_models()

    for label, key in [
        ("Chat/Agent", "chat"),
        ("STT Audio", "stt"),
        ("Image Gen", "image"),
        ("Embedding", "embedding")
    ]:
        info = validation.get(key, {})
        cfg = info.get("configured")
        if info.get("exists"):
            print(f"  ✅ [{label:10s}] Model verified: '{cfg}'")
        else:
            print(f"  ⚠️ [{label:10s}] Model '{cfg}' NOT found in 9Router (will use fallback if needed)")

    return True


async def main():
    parser = argparse.ArgumentParser(description="Arush Manager Agent Runner")
    parser.add_argument("--check-only", action="store_true", help="Run startup diagnostics and exit (used by CI/CD)")
    parser.add_argument("--backup-now", action="store_true", help="Run immediate SQLite & .env backup and exit")
    parser.add_argument("--set-commands", action="store_true", help="Register Telegram slash commands and exit")
    args = parser.parse_args()

    if args.backup_now:
        res = run_daily_backup()
        print(f"✅ Backup completed at: {res['backup_dir']}")
        return

    if args.set_commands:
        print("\n🔄 Registering Telegram bot slash commands...")
        try:
            from aiogram import Bot
            from aiogram.client.session.aiohttp import AiohttpSession
            from bot.commands import setup_bot_commands
            session = AiohttpSession(proxy=settings.TELEGRAM_PROXY) if settings.TELEGRAM_PROXY else None
            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, session=session)
            ok = await setup_bot_commands(bot)
            await bot.session.close()
            if ok:
                print("✅ Telegram slash commands registered successfully.")
            else:
                print("⚠️ Some commands could not be registered (check network or token).")
        except Exception as e:
            print(f"❌ Error during command registration: {e}")
        return

    print("=" * 65)
    print("🚀 ARUSH MANAGER AGENT - STARTUP SEQUENCE (PHASES 1–7)")
    print("=" * 65)
    print(f"• Telegram Bot    : @arush_agentbot")
    print(f"• Vault Data Dir  : {settings.VAULT_DATA_DIR}")
    print(f"• 9Router URL     : {settings.NINEROUTER_URL}")
    print(f"• ComfyUI URL     : {settings.COMFYUI_URL}")
    print(f"• Computer Target : {computer_ctrl.target_width}x{computer_ctrl.target_height}")
    print(f"• Health Endpoint : http://0.0.0.0:{settings.HEALTHCHECK_PORT}/health")

    if settings.TELEGRAM_PROXY:
        print(f"• Telegram Proxy  : {settings.TELEGRAM_PROXY}")
    else:
        print(f"• Telegram Proxy  : Direct (No Proxy configured)")

    await run_diagnostics_and_validation()

    if args.check_only:
        print("\n✅ Diagnostics check completed (--check-only).")
        return

    print("\n🛡️ Whitelist Security:")
    if settings.ALLOWED_TELEGRAM_USER_IDS:
        print(f"  ✅ Authorized User IDs: {settings.ALLOWED_TELEGRAM_USER_IDS}")
    else:
        print("  ⚠️ WARNING: ALLOWED_TELEGRAM_USER_IDS is empty.")
        print("     The first user to message @arush_agentbot will be shown their ID.")

    print("\n" + "=" * 65)
    print("🤖 Starting Telegram Polling + Freelance Radar + Scheduler...")
    print("=" * 65)

    from bot.app import start_bot
    await start_bot()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Arush Agent stopped by user.")
        sys.exit(0)
