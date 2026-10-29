import io
import base64
from pathlib import Path

try:
    from aiogram import Router, F, Bot
    from aiogram.types import (
        Message,
        CallbackQuery,
        BufferedInputFile,
        FSInputFile,
        InlineKeyboardMarkup,
        InlineKeyboardButton
    )
    from aiogram.filters import CommandStart, Command
    HAS_AIOGRAM = True
except ImportError:
    HAS_AIOGRAM = False
    Router = object  # type: ignore

from config import settings
from core.agent import agent
from core.router_client import router_client
from core.scheduler import routine_scheduler
from core.watchdog import watchdog
from tools.computer_use import controller as computer_ctrl, confirmation_manager
from tools.vault import vault
from tools.receipt_parser import receipt_parser
from tools.idea_incubator import idea_incubator
from tools.freelance_radar import freelance_radar
from tools.github_tool import github_tool
from tools.image_studio import image_studio
from tools.life_tracker import life_tracker
from scripts.backup import run_daily_backup

router = Router() if HAS_AIOGRAM else None


if HAS_AIOGRAM:
    def _build_confirmation_kb(action_id: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ تایید اجرای عملیات", callback_data=f"confirm_action:{action_id}"),
                    InlineKeyboardButton(text="❌ لغو", callback_data=f"cancel_action:{action_id}")
                ]
            ]
        )

    async def _deliver_side_effects(message: Message) -> None:
        """Sends any generated images or interactive confirmation buttons triggered during agent.chat()."""
        for img_path_str in list(agent.last_generated_images):
            p = Path(img_path_str)
            if p.exists():
                await message.answer_photo(photo=FSInputFile(str(p)), caption=f"🎨 `{p.name}`")
        agent.last_generated_images.clear()

        for pending in list(agent.last_pending_confirmations):
            kb = _build_confirmation_kb(pending["action_id"])
            await message.answer(
                f"⚠️ **نیاز به تایید امنیتی:**\n`{pending['description']}`",
                reply_markup=kb
            )
        agent.last_pending_confirmations.clear()

    @router.message(CommandStart())
    async def handle_start(message: Message):
        user_name = message.from_user.first_name if message.from_user else "Arush"
        text = (
            f"👋 **سلام {user_name}! من ایجنت مدیریت شخصی آروش هستم (نسخه کامل Phases 1–7).**\n\n"
            f"🖥️ **وضعیت سیستم:** فعال ۲۴/۷ با سیستم خودترمیم‌گر (Self-Healing)\n"
            f"🧠 **هوش اصلی:** 9Router Gateway (`{settings.AGENT_MODEL}`)\n\n"
            f"**دستورات اسلش پرکاربرد:**\n"
            f"• `/help` — راهنمای جامع تمام دستورات و ابزارها\n"
            f"• `/project <name>` — ساخت، سوییچ یا مشاهده خلاصه فضای کاری پروژه (Phase 2.1)\n"
            f"• `/projects` — لیست تمام پروژه‌های ثبت شده در Vault\n"
            f"• `/finance [week|month]` — گزارش مالی هفتگی/ماهانه و دفتر کل (Phase 2.2)\n"
            f"• `/idea <text>` — پردازش ایده در Incubator همراه با امتیاز امکان‌سنجی (Phase 2.3)\n"
            f"• `/search <query>` — جستجوی معنایی (Vector Embeddings) در حافظه (Phase 2.4)\n"
            f"• `/radar` — اسکن پروژه‌های کارلنسر، پونیشا و کانال‌ها + پروپوزال (Phase 3)\n"
            f"• `/screenshot` — دریافت تصویر زنده از دسکتاپ ویندوز (Phase 4.1)\n"
            f"• `/github [status|prs|ci]` — وضعیت گیت، PRها و GitHub Actions (Phase 4.3)\n"
            f"• `/imagine <prompt>` — تولید تصویر ابری یا ComfyUI لوکال (Phase 5)\n"
            f"• `/bio <note>` — ثبت خواب، کافئین، سردرد و ورزش روزانه (Phase 6.2)\n"
            f"• `/lab <text>` — تحلیل آزمایش خون و پرچم‌گذاری مقادیر غیرنرمال (Phase 6.1)\n"
            f"• `/briefing` و `/review` — گزارش صبحگاهی (08:30) و مرور شبانه (22:30) (Phase 6.3/6.4)\n"
            f"• `/backup` و `/status` — بکاپ آنی دیتابیس و وضعیت سلامت سیستم (Phase 7)\n"
            f"• `/cancel` — لغو اقدامات در انتظار تایید امنیتی"
        )
        await message.answer(text, parse_mode="Markdown")

    @router.message(Command("help", "commands", "menu"))
    async def handle_help_cmd(message: Message):
        text = (
            "📖 **راهنمای جامع دستورات اسلش (Slash Commands) ایجنت آروش:**\n\n"
            "🗂️ **پروژه‌ها و مدیریت دانش (Vault):**\n"
            "• `/project <name>` — سوییچ، ساخت یا مشاهده وضعیت فضای کاری فعال\n"
            "• `/projects` — لیست تمام پروژه‌های ثبت شده همراه با وضعیت\n"
            "• `/search <query>` — جستجوی معنایی برداری (Vector) در یادداشت‌ها و فایل‌ها\n\n"
            "💳 **دفتر کل مالی و حسابداری:**\n"
            "• `/finance [week|month]` — گزارش دخل و خرج ۷ یا ۳۰ روزه + تراز خالص\n"
            "• _(ارسال تصویر فیش بانکی/کارت به کارت جهت ثبت هوشمند با کد رهگیری)_\n\n"
            "💡 **ایده‌ها و توسعه فردی:**\n"
            "• `/idea <متن>` — تحلیل امکان‌سنجی ایده (۱-۱۰)، استک پیشنهادی و گام‌های اجرا\n"
            "• _(ارسال پیام صوتی جهت تبدیل صوت به متن و ساختاردهی در Incubator)_\n\n"
            "📡 **رادار فریلنسری و پروپوزال:**\n"
            "• `/radar` — اسکن پونیشا، کارلنسر و کانال‌ها و تولید پروپوزال پیشنهادی\n\n"
            "🖥️ **کنترل دسکتاپ و ابزارهای مهندسی:**\n"
            "• `/screenshot` — تصویر زنده از مانیتور دسکتاپ ویندوز\n"
            "• `/github [status|prs|ci]` — وضعیت مخزن Git محلی، PRها یا ورک‌فلوهای CI\n"
            "• `/imagine <prompt>` — ساخت تصویر با هوش مصنوعی (FLUX یا ComfyUI)\n\n"
            "🧬 **سلامت و روتین‌های روزمره:**\n"
            "• `/bio <note>` — ثبت ساعات خواب، قهوه، ورزش و عادات روزانه\n"
            "• `/lab <text>` — تحلیل جواب آزمایش خون و مشخص کردن موارد غیرنرمال\n"
            "• `/briefing` — دریافت گزارش صبحگاهی روزانه (ساعت 08:30)\n"
            "• `/review` — دریافت مرور شبانه عملکرد (ساعت 22:30)\n\n"
            "⚙️ **سیستم و امنیت:**\n"
            "• `/status` — وضعیت سلامت سرور خودترمیم، اتصال 9Router و آپتایم\n"
            "• `/backup` — بکاپ‌گیری گرم و آنی از دیتابیس SQLite و تنظیمات\n"
            "• `/cancel` — لغو اقدامات حساس در حال انتظار تایید امنیتی"
        )
        await message.answer(text, parse_mode="Markdown")

    @router.message(Command("cancel", "stop"))
    async def handle_cancel_cmd(message: Message):
        canceled = confirmation_manager.cancel_all_pending()
        agent.last_pending_confirmations.clear()
        agent.last_generated_images.clear()
        msg = "🔄 **عملیات لغو شد.** حافظه موقت و اقدامات در انتظار پاکسازی شدند."
        if canceled > 0:
            msg += f"\n• `{canceled}` اقدام امنیتی در حال انتظار لغو شد."
        await message.answer(msg, parse_mode="Markdown")

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

    @router.message(Command("project"))
    async def handle_project_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        arg = parts[1].strip() if len(parts) > 1 else None
        if arg:
            vault.switch_active_project(arg)
        summary = vault.get_project_summary(arg)
        if not summary:
            await message.answer("📁 پروژه‌ای انتخاب نشده است. مثال: `/project crypto_bot`", parse_mode="Markdown")
            return
        p = summary["project"]
        txt = (
            f"📂 **فضای کاری پروژه فعال: {p['name']} (`{p['slug']}`)**\n\n"
            f"• **مسیر فایل‌ها:** `{summary['workspace_dir']}`\n"
            f"• **وضعیت:** `{p['status']}` | **پلتفرم:** `{p['platform']}`\n"
            f"• **تعداد آیتم‌های ذخیره شده:** `{summary['total_artifacts']}`\n"
            f"• **درآمد ثبت شده:** `{summary['income_total']:,.0f}` تومان | **هزینه:** `{summary['expense_total']:,.0f}` تومان\n\n"
            f"📝 **پیش‌نمایش `context.md`:**\n```\n{summary['context_preview'][:500]}\n```"
        )
        await message.answer(txt, parse_mode="Markdown")

    @router.message(Command("projects"))
    async def handle_projects_cmd(message: Message):
        projs = vault.list_projects()
        if not projs:
            await message.answer("📁 هیچ پروژه‌ای هنوز ثبت نشده است. با `/project <name>` بسازید.")
            return
        lines = ["📁 **پروژه‌های ثبت شده در Knowledge Vault:**\n"]
        for p in projs:
            active_star = "⭐ " if p.get("is_active") else ""
            status_emoji = "🟢" if p["status"] == "in_progress" else "⚪"
            lines.append(
                f"{status_emoji} {active_star}**{p['name']}** (`{p['slug']}`) | پلتفرم: {p['platform']} | وضعیت: {p['status']}"
            )
        await message.answer("\n".join(lines), parse_mode="Markdown")

    @router.message(Command("finance"))
    async def handle_finance_cmd(message: Message):
        parts = (message.text or "").split()
        days = 30 if (len(parts) > 1 and parts[1].lower() in ("month", "30", "ماه")) else 7
        label = "ماهانه (۳۰ روز اخیر)" if days == 30 else "هفتگی (۷ روز اخیر)"
        summary = vault.get_financial_summary(days=days)
        lines = [
            f"💳 **گزارش دفتر مالی — {label}:**\n",
            f"• **کل ورودی (درآمد):** `{summary['income_toman']:,.0f}` تومان",
            f"• **کل خروجی (هزینه):** `{summary['expense_toman']:,.0f}` تومان",
            f"• **تراز خالص:** `{summary['net_toman']:,.0f}` تومان",
            f"• **تعداد تراکنش‌ها:** `{summary['transaction_count']}`\n"
        ]
        if summary["recent_transactions"]:
            lines.append("🧾 **آخرین تراکنش‌ها:**")
            for tx in summary["recent_transactions"][:5]:
                sign = "➕" if tx["category"] == "income" else "➖"
                tr_code = f" | کد رهگیری: `{tx['tracking_code']}`" if tx.get("tracking_code") else ""
                lines.append(f"{sign} `{tx['amount']:,.0f} {tx['currency']}` — {tx.get('description', '')}{tr_code}")
        await message.answer("\n".join(lines), parse_mode="Markdown")

    @router.message(Command("idea"))
    async def handle_idea_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("💡 لطفاً متن ایده خود را بعد از `/idea` بنویسید یا یک ویس بفرستید.")
            return
        status_msg = await message.answer("🧠 در حال پردازش و ساختاردهی ایده در Incubator...")
        res = await idea_incubator.incubate_transcript(parts[1])
        await status_msg.delete()
        await message.answer(res["formatted_markdown"], parse_mode="Markdown")

    @router.message(Command("search"))
    async def handle_search_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("🔍 عبارت جستجو را وارد کنید. مثال: `/search رنگ دکمه‌ها در پروژه`")
            return
        query = parts[1].strip()
        q_emb = await router_client.create_embedding(query)
        results = vault.semantic_search_vault(query=query, query_embedding=q_emb, top_k=5)
        if not results:
            await message.answer("🔍 نتیجه‌ای در حافظه معنایی یافت نشد.")
            return
        lines = [f"🧠 **نتایج جستجوی معنایی برای:** _{query}_\n"]
        for r in results:
            proj_tag = f" (`{r['project_slug']}`)" if r.get("project_slug") else ""
            lines.append(
                f"• **[{r['type'].upper()}] {r['title']}**{proj_tag} — شباهت: `{int(r['similarity'] * 100)}%`\n"
                f"  _{r['content'][:180]}_"
            )
        await message.answer("\n\n".join(lines), parse_mode="Markdown")

    @router.message(Command("radar"))
    async def handle_radar_cmd(message: Message):
        status_msg = await message.answer("📡 در حال اسکن مستقیم کارلنسر، پونیشا و کانال‌های تلگرام...")
        await freelance_radar.poll_sources_once()
        leads = vault.get_top_freelance_leads(min_score=0, limit=3)
        await status_msg.delete()
        if not leads:
            await message.answer("📡 هنوز پروژه فریلنسری منطبقی در دیتابیس ثبت نشده است.")
            return
        for ld in leads:
            alert_txt = freelance_radar.format_telegram_alert(ld)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 مشاهده و ارسال پیشنهاد در سایت", url=ld.get("url") or "https://ponisha.ir")]
                ]
            )
            await message.answer(alert_txt, reply_markup=kb, parse_mode="Markdown")

    @router.message(Command("github"))
    async def handle_github_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=2)
        sub = parts[1].lower() if len(parts) > 1 else "status"
        if sub == "prs":
            res = await github_tool.list_open_prs()
            await message.answer(f"🐙 **GitHub Open PRs:**\n```json\n{res}\n```", parse_mode="Markdown")
        elif sub == "ci":
            res = await github_tool.list_workflow_runs()
            await message.answer(f"⚙️ **GitHub Actions CI/CD Runs:**\n```json\n{res}\n```", parse_mode="Markdown")
        else:
            res = await github_tool.run_local_git("status")
            await message.answer(
                f"🐙 **وضعیت مخزن محلی Git:**\n```\n{res.get('stdout') or res.get('stderr') or res}\n```",
                parse_mode="Markdown"
            )

    @router.message(Command("imagine"))
    async def handle_imagine_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("🎨 پرامپت تصویر را وارد کنید. مثال: `/imagine futuristic Persian AI dashboard UI`")
            return
        status_msg = await message.answer("🎨 در حال تولید تصویر در Image Studio...")
        res = await image_studio.generate(prompt=parts[1].strip())
        await status_msg.delete()
        if res.get("status") == "success" and res.get("file_path"):
            await message.answer_photo(
                photo=FSInputFile(res["file_path"]),
                caption=f"🎨 **مدل:** `{res.get('model', res.get('engine'))}`"
            )
        else:
            await message.answer(f"❌ خطا در تولید تصویر: {res.get('error')}")

    @router.message(Command("bio"))
    async def handle_bio_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            recent = vault.get_recent_bio_logs(days=7)
            lines = ["🧬 **لاگ‌های زیستی و عادت‌های ۷ روز اخیر:**\n"]
            for b in recent[:10]:
                lines.append(f"• **{b['metric_name']}**: `{b['value']} {b.get('unit', '')}` ({b['logged_at']})")
            await message.answer("\n".join(lines) if len(lines) > 1 else "هنوز موردی ثبت نشده است.", parse_mode="Markdown")
            return
        logged = life_tracker.parse_and_log_bio_note(parts[1])
        summary = ", ".join(f"{x['metric_name']}={x['value']}{x.get('unit', '')}" for x in logged)
        await message.answer(f"✅ **در سیستم سلامت ثبت شد:** `{summary}`", parse_mode="Markdown")

    @router.message(Command("lab"))
    async def handle_lab_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            results = vault.get_lab_results()
            if not results:
                await message.answer("🩺 برای تحلیل آزمایش، متن یا تصویر آزمایش را بفرستید. مثال: `/lab WBC 6.2 Vitamin D 18 TSH 2.1`")
                return
            lines = ["🩺 **آخرین نتایج آزمایشگاهی ثبت شده:**\n"]
            for r in results[:10]:
                badge = "🔴" if r["flag"] != "NORMAL" else "🟢"
                lines.append(f"{badge} **{r['biomarker']}**: `{r['value']} {r['unit']}` [{r['flag']}]")
            await message.answer("\n".join(lines), parse_mode="Markdown")
            return
        parsed = life_tracker.parse_and_store_lab_report(parts[1])
        lines = [f"🩺 **نتایج استخراج شده ({parsed['total_extracted']} شاخص):**\n"]
        for r in parsed["results"]:
            badge = "⚠️" if r["flag"] != "NORMAL" else "✅"
            lines.append(
                f"{badge} **{r['biomarker']}** ({r['test_category']}): `{r['value']} {r['unit']}` "
                f"(نرمال: {r['reference_min']}–{r['reference_max']}) ➔ **{r['flag']}**"
            )
        await message.answer("\n".join(lines), parse_mode="Markdown")

    @router.message(Command("briefing"))
    async def handle_briefing_cmd(message: Message):
        await message.answer(routine_scheduler.generate_morning_briefing(), parse_mode="Markdown")

    @router.message(Command("review"))
    async def handle_review_cmd(message: Message):
        await message.answer(routine_scheduler.generate_nightly_review(), parse_mode="Markdown")

    @router.message(Command("backup"))
    async def handle_backup_cmd(message: Message):
        res = run_daily_backup()
        await message.answer(
            f"💾 **بکاپ خودکار با موفقیت انجام شد:**\n"
            f"• مسیر: `{res['backup_dir']}`\n"
            f"• فایل‌ها: `{len(res['files'])}`",
            parse_mode="Markdown"
        )

    @router.message(Command("status"))
    async def handle_status_cmd(message: Message):
        health = await watchdog.get_health_status()
        status_9router = "🟢 متصل" if health["ninerouter_connected"] else "🔴 قطع (بررسی NINEROUTER_URL)"
        active_proj = vault.get_active_project()
        active_str = f"`{active_proj['name']}` (`{active_proj['slug']}`)" if active_proj else "انتخاب نشده"

        txt = (
            f"📊 **وضعیت سیستم Arush Agent (Self-Healing Watchdog):**\n\n"
            f"• **وضعیت کلی:** `{health['status'].upper()}` (Uptime: `{health['uptime_seconds']}s`)\n"
            f"• **9Router URL:** `{settings.NINEROUTER_URL}` ({status_9router})\n"
            f"• **پروژه فعال فعلی:** {active_str}\n"
            f"• **مدل ایجنت:** `{settings.AGENT_MODEL}`\n"
            f"• **مدل ویس (STT):** `{settings.STT_MODEL}`\n"
            f"• **مدل تصویر:** `{settings.IMAGE_MODEL}`\n"
            f"• **مدل Embedding:** `{settings.EMBEDDING_MODEL}`\n"
            f"• **تعداد تلاش‌های اتصال مجدد:** `{health['reconnect_count']}`\n"
            f"• **مسیر داده‌ها:** `{settings.VAULT_DATA_DIR}`"
        )
        await message.answer(txt, parse_mode="Markdown")

    @router.callback_query(F.data.startswith("confirm_action:"))
    async def handle_confirm_callback(callback: CallbackQuery):
        action_id = callback.data.split(":", 1)[1]
        rec = confirmation_manager.resolve_pending(action_id, approved=True)
        if not rec:
            await callback.answer("این عملیات منقضی شده یا یافت نشد.", show_alert=True)
            return
        payload = rec["payload"]
        res = computer_ctrl.execute_action(
            action=payload.get("action"),
            coordinate=payload.get("coordinate"),
            text=payload.get("text"),
            monitor_index=payload.get("monitor_index", 1),
            confirmed=True
        )
        await callback.message.edit_text(
            f"✅ **عملیات تایید و اجرا شد:**\n`{rec['description']}`\nنتیجه: `{res.get('status', 'done')}`",
            parse_mode="Markdown"
        )
        await callback.answer("اجرا شد!")

    @router.callback_query(F.data.startswith("cancel_action:"))
    async def handle_cancel_callback(callback: CallbackQuery):
        action_id = callback.data.split(":", 1)[1]
        rec = confirmation_manager.resolve_pending(action_id, approved=False)
        desc = rec["description"] if rec else action_id
        await callback.message.edit_text(f"❌ **عملیات لغو شد:** `{desc}`", parse_mode="Markdown")
        await callback.answer("لغو شد.")

    @router.message(F.voice)
    async def handle_voice(message: Message, bot: Bot):
        """Handles incoming voice notes: downloads, transcribes via 9Router STT, and runs agent/incubator."""
        status_msg = await message.answer("🎙️ در حال دانلود و تبدیل صدا به متن...")
        try:
            voice_file = await bot.get_file(message.voice.file_id)
            local_path = settings.VAULT_DATA_DIR / "media" / f"voice_{message.message_id}.oga"
            await bot.download_file(voice_file.file_path, local_path)

            await status_msg.edit_text("⏳ در حال تبدیل گفتار به متن توسط Whisper...")
            transcript = await router_client.transcribe_audio(local_path)
            if not transcript.strip():
                await status_msg.edit_text("⚠️ صدایی در پیام صوتی تشخیص داده نشد.")
                return

            await status_msg.edit_text(f"🗣️ **متن صدا:**\n_{transcript}_\n\n🧠 در حال پردازش توسط ایجنت...")

            messages = [{"role": "user", "content": f"[Voice note from user]: {transcript}"}]

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
            await _deliver_side_effects(message)

        except Exception as e:
            err_text = str(e)[:500]
            await status_msg.edit_text(f"❌ خطا در پردازش صدا:\n{err_text}", parse_mode=None)

    @router.message(F.photo)
    async def handle_photo(message: Message, bot: Bot):
        """Handles incoming photos (Iranian bank receipts, lab reports, screenshots, wireframes)."""
        status_msg = await message.answer("🖼️ در حال دریافت و تحلیل تصویر...")
        try:
            photo = message.photo[-1]
            p_file = await bot.get_file(photo.file_id)
            local_path = settings.VAULT_DATA_DIR / "media" / f"img_{message.message_id}.jpg"
            await bot.download_file(p_file.file_path, local_path)

            # If caption contains receipt details Directly, parse and deduplicate right away
            if message.caption and any(k in message.caption for k in ("کد رهگیری", "شماره پیگیری", "کارت به کارت", "پایا", "ساتنا")):
                rec = receipt_parser.parse_and_record(message.caption, receipt_path=str(local_path))
                if rec["duplicate"]:
                    await status_msg.edit_text(
                        f"⚠️ **رسید تکراری تشخیص داده شد!**\nکد رهگیری `{rec['parsed']['tracking_code']}` قبلاً در دفتر مالی ثبت شده است.",
                        parse_mode="Markdown"
                    )
                    return

            with open(local_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")

            user_caption = (
                message.caption
                or "Analyze this image. If it's an Iranian bank receipt, call parse_and_record_receipt with all extracted text. "
                   "If it's a medical lab report, call parse_medical_lab. If it's a project screenshot, call save_to_vault."
            )

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_caption},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}}
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
            await _deliver_side_effects(message)

        except Exception as e:
            err_text = str(e)[:500]
            await status_msg.edit_text(f"❌ خطا در تحلیل تصویر:\n{err_text}", parse_mode=None)

    @router.message(F.text)
    async def handle_text(message: Message):
        """Handles standard text prompts, receipt pastes, and natural language commands."""
        status_msg = await message.answer("🧠 در حال تفکر...")
        messages = [{"role": "user", "content": message.text}]

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
            await _deliver_side_effects(message)
        except Exception as e:
            err_text = str(e)[:500]
            await status_msg.edit_text(f"❌ خطا:\n{err_text}", parse_mode=None)
