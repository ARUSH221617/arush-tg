import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional

try:
    from aiogram import Bot
    from aiogram.types import BotCommand, BotCommandScopeDefault
    HAS_AIOGRAM = True
except ImportError:
    HAS_AIOGRAM = False
    Bot = object  # type: ignore

    @dataclass
    class BotCommand:  # type: ignore
        command: str
        description: str

    @dataclass
    class BotCommandScopeDefault:  # type: ignore
        type: str = "default"

logger = logging.getLogger("arush-agent.commands")

# Standard Slash Commands for Arush Manager Agent (Phases 1–8)
# Format: (command_name, fa_description, en_description)
# All command names comply with Telegram API constraints (^[a-z0-9_]{1,32}$)
# All descriptions comply with length constraints (1–256 chars)
COMMANDS_METADATA: List[Tuple[str, str, str]] = [
    ("start", "شروع و معرفی قابلیت‌های ربات", "Start agent & show overview"),
    ("help", "راهنمای کامل دستورات و میانبرها", "Command guide & usage examples"),
    ("agents", "مدیریت و سوییچ ایجنت‌ها (برنامه‌نویس، طراح و...)", "Switch, create or manage AI agents"),
    ("workspace", "ثبت و مدیریت مسیر پروژه روی کامپیوتر (Claude Code)", "Save & switch local PC project path"),
    ("subagent", "اجرای ساب‌ایجنت تخصصی روی پروژه", "Spawn autonomous sub-agent on task"),
    ("cli", "مدیریت ایجنت‌های نصبی (Claude Code, Antigravity, Codex, Copilot)", "Run/manage PC CLI agents (Claude, Codex, etc.)"),
    ("skills", "مدیریت، ساخت و فعال‌سازی مهارت‌ها (Skills)", "List, create, toggle & manage Skills"),
    ("mcp", "مدیریت سرورها و ابزارهای MCP", "Configure & call MCP servers and tools"),
    ("project", "ساخت، سوییچ یا مشاهده خلاصه پروژه", "Create, switch or inspect project"),
    ("projects", "لیست تمام پروژه‌های ثبت‌شده", "List all tracked projects in Vault"),
    ("finance", "گزارش مالی هفتگی/ماهانه و دفتر کل", "Weekly/monthly financial ledger"),
    ("idea", "پردازش و امتیازدهی به ایده در Incubator", "Incubate idea with feasibility score"),
    ("search", "جستجوی معنایی در حافظه پروژه‌ها", "Semantic search across vault memory"),
    ("radar", "اسکن فرصت‌های فریلنسری و پروپوزال", "Scan freelance gigs & draft proposals"),
    ("screenshot", "دریافت تصویر زنده از مانیتور دسکتاپ", "Capture live desktop screenshot"),
    ("github", "وضعیت مخزن Git، PRها و CI/CD", "Git status, open PRs, or CI runs"),
    ("imagine", "تولید تصویر با هوش مصنوعی (Cloud/ComfyUI)", "Generate AI image (Cloud/ComfyUI)"),
    ("bio", "ثبت خواب، کافئین، ورزش و عادات زیستی", "Log sleep, caffeine, workouts & habits"),
    ("lab", "تحلیل هوشمند برگه آزمایش خون", "Parse medical lab blood test report"),
    ("briefing", "دریافت گزارش صبحگاهی روزانه (۰۸:۳۰)", "Instant morning briefing (08:30)"),
    ("review", "دریافت مرور شبانه عملکرد (۲۲:۳۰)", "Instant nightly review (22:30)"),
    ("backup", "بکاپ‌گیری آنی از دیتابیس و تنظیمات", "Instant SQLite & .env backup"),
    ("status", "وضعیت سلامت سیستم و ارتباطات", "Watchdog, uptime & model health"),
    ("cancel", "لغو عملیات در انتظار تایید امنیتی", "Cancel pending action or operation"),
]


def get_bot_commands(language_code: Optional[str] = None):
    """
    Returns a list of BotCommand objects for the given language.
    Defaults to Persian (fa) if language_code is None or 'fa', otherwise English (en).
    """
    is_en = language_code == "en"
    return [
        BotCommand(command=cmd, description=en_desc if is_en else fa_desc)
        for cmd, fa_desc, en_desc in COMMANDS_METADATA
    ]


async def setup_bot_commands(bot: Bot) -> bool:
    """
    Registers slash commands with the Telegram Bot API across multiple scopes:
    1. Default scope (Persian)
    2. Persian language scope (language_code="fa")
    3. English language scope (language_code="en")
    """
    if not hasattr(bot, "set_my_commands"):
        logger.warning("bot instance does not support set_my_commands; skipping slash command registration.")
        return False

    success = False
    try:
        # Default fallback (Persian)
        default_commands = get_bot_commands(language_code=None)
        await bot.set_my_commands(default_commands, scope=BotCommandScopeDefault())
        logger.info(f"Registered {len(default_commands)} default slash commands with Telegram.")
        success = True
    except Exception as e:
        logger.warning(f"Failed to register default bot commands: {e}")

    try:
        # Explicit Persian language scope
        fa_commands = get_bot_commands(language_code="fa")
        await bot.set_my_commands(fa_commands, scope=BotCommandScopeDefault(), language_code="fa")
    except Exception as e:
        logger.debug(f"Optional 'fa' command scope registration note: {e}")

    try:
        # Explicit English language scope
        en_commands = get_bot_commands(language_code="en")
        await bot.set_my_commands(en_commands, scope=BotCommandScopeDefault(), language_code="en")
    except Exception as e:
        logger.debug(f"Optional 'en' command scope registration note: {e}")

    return success
