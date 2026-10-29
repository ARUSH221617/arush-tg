import asyncio
import sys
from pathlib import Path
from config import settings
from core.router_client import router_client
from tools.computer_use import controller as computer_ctrl
from bot.app import start_bot

async def run_diagnostics_and_validation() -> bool:
    """
    Checks 9Router health and verifies that all default models configured in .env
    actually exist in 9Router's model registries.
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

    all_models_found = True

    # 1. Chat / Agent Model
    chat_info = validation["chat"]
    cfg_chat = chat_info["configured"]
    if chat_info["exists"]:
        print(f"  ✅ [Chat/Agent] Model verified: '{cfg_chat}'")
    else:
        all_models_found = False
        print(f"  ⚠️ [Chat/Agent] Model '{cfg_chat}' NOT found in 9Router!")
        available = chat_info["available"]
        if available:
            print(f"     Available chat models ({len(available)}):")
            for m in available[:8]:
                print(f"       • {m}")
            if len(available) > 8:
                print(f"       ... and {len(available) - 8} more.")
            print(f"     👉 Update AGENT_MODEL in your .env with one of the above.")
        else:
            print("     (No chat models returned by 9Router or auth required)")

    # 2. STT (Speech-to-Text) Model
    stt_info = validation["stt"]
    cfg_stt = stt_info["configured"]
    if stt_info["exists"]:
        print(f"  ✅ [STT Audio]  Model verified: '{cfg_stt}'")
    else:
        all_models_found = False
        print(f"  ⚠️ [STT Audio]  Model '{cfg_stt}' NOT found in 9Router!")
        available = stt_info["available"]
        if available:
            print(f"     Available STT models ({len(available)}):")
            for m in available[:6]:
                print(f"       • {m}")
            print(f"     👉 Update STT_MODEL in your .env with one of the above.")
        else:
            print("     (No STT models returned by 9Router)")

    # 3. Image Generation Model
    img_info = validation["image"]
    cfg_img = img_info["configured"]
    if img_info["exists"]:
        print(f"  ✅ [Image Gen]  Model verified: '{cfg_img}'")
    else:
        all_models_found = False
        print(f"  ⚠️ [Image Gen]  Model '{cfg_img}' NOT found in 9Router!")
        available = img_info["available"]
        if available:
            print(f"     Available image models ({len(available)}):")
            for m in available[:6]:
                print(f"       • {m}")
            print(f"     👉 Update IMAGE_MODEL in your .env with one of the above.")
        else:
            print("     (No image models returned by 9Router)")

    return True

async def main():
    print("=" * 65)
    print("🚀 ARUSH MANAGER AGENT - STARTUP SEQUENCE")
    print("=" * 65)
    print(f"• Telegram Bot    : @arush_agentbot")
    print(f"• Vault Data Dir  : {settings.VAULT_DATA_DIR}")
    print(f"• 9Router URL     : {settings.NINEROUTER_URL}")
    print(f"• Computer Target : {computer_ctrl.target_width}x{computer_ctrl.target_height}")
    
    if settings.TELEGRAM_PROXY:
        print(f"• Telegram Proxy  : {settings.TELEGRAM_PROXY}")
    else:
        print(f"• Telegram Proxy  : Direct (No Proxy configured)")

    # Run 9Router active check + model verification
    is_ready = await run_diagnostics_and_validation()

    print("\n🛡️ Whitelist Security:")
    if settings.ALLOWED_TELEGRAM_USER_IDS:
        print(f"  ✅ Authorized User IDs: {settings.ALLOWED_TELEGRAM_USER_IDS}")
    else:
        print("  ⚠️ WARNING: ALLOWED_TELEGRAM_USER_IDS is empty.")
        print("     The first user to message @arush_agentbot will be shown their ID.")

    print("\n" + "=" * 65)
    print("🤖 Starting Telegram Polling... (Press Ctrl+C to stop)")
    print("=" * 65)

    await start_bot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Arush Agent stopped by user.")
        sys.exit(0)
