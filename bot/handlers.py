import os
import io
import base64
from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.types import Message, BufferedInputFile, FSInputFile
from aiogram.filters import CommandStart, Command
from config import settings
from core.agent import agent
from core.router_client import router_client
from tools.computer_use import controller as computer_ctrl
from tools.vault import vault

router = Router()

@router.message(CommandStart())
async def handle_start(message: Message):
    user_name = message.from_user.first_name if message.from_user else "Arush"
    text = (
        f"👋 **سلام {user_name}! من ایجنت مدیریت شخصی آروش هستم.**\n\n"
        f"🖥️ **وضعیت سیستم:** فعال روی کامپیوتر شخصی شما\n"
        f"🧠 **هوش اصلی:** Claude Agent SDK via 9Router\n\n"
        f"**کارهایی که می‌تونید انجام بدید:**\n"
        f"• 🎙️ **ویس بفرستید:** تبدیل خودکار به متن + پردازش دستورات یا ایده‌ها\n"
        f"• 🧾 **رسید بفرستید:** استخراج اطلاعات بانکی، کارت به کارت و ثبت در دفتر مالی\n"
        f"• 🖼️ **اسکرین‌شات بفرستید:** ذخیره و نمایه‌سازی در Knowledge Vault پروژه\n"
        f"• 💻 **دستورات کامپیوتر:** کنترل موس، کیبورد و اجرای اسکریپت‌ها\n\n"
        f"**دستورات سریع:**\n"
        f"/screenshot - دریافت اسکرین‌شات زنده از دسکتاپ\n"
        f"/projects - مشاهده پروژه‌های ثبت شده\n"
        f"/status - بررسی وضعیت اتصال به 9Router و دیتابیس"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("screenshot"))
async def handle_screenshot_cmd(message: Message):
    status_msg = await message.answer("📸 در حال ضبط تصویر از مانیتور...")
    try:
        pil_img, _ = computer_ctrl.capture_screenshot()
        bio = io.BytesIO()
        pil_img.save(bio, format="PNG")
        bio.seek(0)
        
        file = BufferedInputFile(bio.getvalue(), filename="desktop.png")
        await message.answer_photo(photo=file, caption="🖥️ مانیتور اصلی کامپیوتر")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ خطا در ضبط اسکرین‌شات: {str(e)}")

@router.message(Command("projects"))
async def handle_projects_cmd(message: Message):
    projs = vault.list_projects()
    if not projs:
        await message.answer("📁 هیچ پروژه‌ای هنوز ثبت نشده است.")
        return
    
    lines = ["📁 **پروژه‌های ثبت شده در Vault:**\n"]
    for p in projs:
        status_emoji = "🟢" if p["status"] == "in_progress" else "⚪"
        lines.append(f"{status_emoji} **{p['name']}** (`{p['slug']}`) | پلتفرم: {p['platform']} | وضعیت: {p['status']}")
    
    await message.answer("\n".join(lines), parse_mode="Markdown")

@router.message(Command("status"))
async def handle_status_cmd(message: Message):
    is_9router_ok = await router_client.check_health()
    status_9router = "🟢 متصل" if is_9router_ok else "🔴 قطع (بررسی NINEROUTER_URL)"
    
    txt = (
        f"📊 **وضعیت سیستم Arush Agent:**\n\n"
        f"• **9Router URL:** `{settings.NINEROUTER_URL}` ({status_9router})\n"
        f"• **مدل ایجنت:** `{settings.AGENT_MODEL}`\n"
        f"• **مدل ویس (STT):** `{settings.STT_MODEL}`\n"
        f"• **مسیر داده‌ها:** `{settings.VAULT_DATA_DIR}`\n"
    )
    await message.answer(txt, parse_mode="Markdown")

@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot):
    """Handles incoming voice notes: downloads, transcribes via 9Router STT, and runs agent."""
    status_msg = await message.answer("🎙️ در حال دانلود و تبدیل صدا به متن...")
    
    try:
        voice_file = await bot.get_file(message.voice.file_id)
        local_path = settings.VAULT_DATA_DIR / "media" / f"voice_{message.message_id}.oga"
        await bot.download_file(voice_file.file_path, local_path)

        # Transcribe via 9Router STT
        await status_msg.edit_text("⏳ در حال تبدیل گفتار به متن توسط Whisper...")
        transcript = await router_client.transcribe_audio(local_path)
        
        if not transcript.strip():
            await status_msg.edit_text("⚠️ صدایی در پیام صوتی تشخیص داده نشد.")
            return

        await status_msg.edit_text(f"🗣️ **متن صدا:**\n_{transcript}_\n\n🧠 در حال پردازش توسط ایجنت...")

        # Process with Claude Agent
        messages = [
            {
                "role": "user",
                "content": f"[Voice note from user]: {transcript}"
            }
        ]

        async def update_status(text: str):
            try:
                await status_msg.edit_text(f"🗣️ _{transcript}_\n\n{text}")
            except Exception:
                pass

        reply = await agent.chat(messages, on_status_update=update_status)
        await status_msg.delete()
        try:
            await message.answer(reply, parse_mode="Markdown")
        except Exception:
            await message.answer(reply, parse_mode=None)

    except Exception as e:
        err_text = str(e)
        if len(err_text) > 500:
            err_text = err_text[:500] + "..."
        await status_msg.edit_text(f"❌ خطا در پردازش صدا:\n{err_text}", parse_mode=None)

@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot):
    """Handles incoming photos (receipts, screenshots, wireframes, ideas)."""
    status_msg = await message.answer("🖼️ در حال دریافت و تحلیل تصویر...")
    
    try:
        # Get highest resolution photo
        photo = message.photo[-1]
        p_file = await bot.get_file(photo.file_id)
        local_path = settings.VAULT_DATA_DIR / "media" / f"img_{message.message_id}.jpg"
        await bot.download_file(p_file.file_path, local_path)

        with open(local_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")

        user_caption = message.caption or "Analyze this image. If it's a receipt, extract tracking code, amount, and date. If it's a project screenshot or idea, summarize and index it."

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_caption
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_data}"
                        }
                    }
                ]
            }
        ]

        async def update_status(text: str):
            try:
                await status_msg.edit_text(f"🖼️ {text}")
            except Exception:
                pass

        reply = await agent.chat(messages, on_status_update=update_status)
        await status_msg.delete()
        try:
            await message.answer(reply, parse_mode="Markdown")
        except Exception:
            await message.answer(reply, parse_mode=None)

    except Exception as e:
        err_text = str(e)
        if len(err_text) > 500:
            err_text = err_text[:500] + "..."
        await status_msg.edit_text(f"❌ خطا در تحلیل تصویر:\n{err_text}", parse_mode=None)

@router.message(F.text)
async def handle_text(message: Message):
    """Handles standard text prompts and commands."""
    status_msg = await message.answer("🧠 در حال تفکر...")
    
    messages = [
        {
            "role": "user",
            "content": message.text
        }
    ]

    async def update_status(text: str):
        try:
            await status_msg.edit_text(text)
        except Exception:
            pass

    try:
        reply = await agent.chat(messages, on_status_update=update_status)
        await status_msg.delete()
        try:
            await message.answer(reply, parse_mode="Markdown")
        except Exception:
            await message.answer(reply, parse_mode=None)
    except Exception as e:
        err_text = str(e)
        if len(err_text) > 500:
            err_text = err_text[:500] + "..."
        await status_msg.edit_text(f"❌ خطا:\n{err_text}", parse_mode=None)
