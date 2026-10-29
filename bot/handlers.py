import io
import json
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
from bot.formatter import send_formatted_reply, markdown_to_telegram_html
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
from tools.agent_manager import agent_manager
from tools.skills_manager import skills_manager
from tools.mcp_manager import mcp_manager, MCP_PRESETS
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

    def _build_agents_kb() -> InlineKeyboardMarkup:
        agents_list = agent_manager.list_agents()
        rows = []
        row = []
        for ag in agents_list:
            prefix = "✅ " if ag.get("is_active") else "🤖 "
            row.append(
                InlineKeyboardButton(
                    text=f"{prefix}{ag['name'][:18]}",
                    callback_data=f"switch_agent:{ag['slug']}"
                )
            )
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _build_skills_kb() -> InlineKeyboardMarkup:
        skills_list = skills_manager.list_skills()
        rows = []
        row = []
        for sk in skills_list[:10]:
            badge = "🟢" if sk.get("enabled") else "⚪"
            row.append(
                InlineKeyboardButton(
                    text=f"{badge} {sk['slug'][:20]}",
                    callback_data=f"toggle_skill:{sk['slug']}"
                )
            )
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def _deliver_side_effects(message: Message) -> None:
        """Sends any generated images or interactive confirmation buttons triggered during agent.chat()."""
        for img_path_str in list(agent.last_generated_images):
            p = Path(img_path_str)
            if p.exists():
                await message.answer_photo(photo=FSInputFile(str(p)), caption=f"🎨 `{p.name}`")
        agent.last_generated_images.clear()

        for pending in list(agent.last_pending_confirmations):
            kb = _build_confirmation_kb(pending["action_id"])
            await send_formatted_reply(
                message,
                f"⚠️ **نیاز به تایید امنیتی:**\n`{pending['description']}`",
                reply_markup=kb
            )
        agent.last_pending_confirmations.clear()

    @router.message(CommandStart())
    async def handle_start(message: Message):
        user_name = message.from_user.first_name if message.from_user else "Arush"
        active_ag = agent_manager.get_active_agent()
        active_pc_path = agent_manager.get_active_project_path() or "ثبت نشده (`/workspace <path>`)"
        text = (
            f"👋 **سلام {user_name}! من ایجنت مدیریت شخصی آروش هستم (نسخه کامل Phases 1–8).**\n\n"
            f"🖥️ **وضعیت سیستم:** فعال ۲۴/۷ با سیستم خودترمیم‌گر (Self-Healing)\n"
            f"🧠 **هوش اصلی:** 9Router Gateway (`{settings.AGENT_MODEL}`)\n"
            f"🤖 **ایجنت فعال فعلی:** `{active_ag['name']}` (`{active_ag['slug']}`)\n"
            f"💻 **مسیر پروژه روی PC:** `{active_pc_path}`\n\n"
            f"**دستورات جدید ایجنت، مهارت‌ها و MCP (Phase 8):**\n"
            f"• `/agents` — مدیریت و سوییچ ایجنت‌های آماده (`programmer`, `planner`, `reviewer`, `debugger`, `researcher`) و ساخت ایجنت شخصی\n"
            f"• `/workspace <pc_path>` — ثبت مسیر پروژه روی کامپیوتر شما برای ویرایش کد و اجرای دستورات مثل Claude Code\n"
            f"• `/subagent <role> <task>` — اجرای ساب‌ایجنت تخصصی مستقل روی پروژه\n"
            f"• `/cli` — مدیریت و اجرای ایجنت‌های نصبی روی PC (`claude_code`, `antigravity`, `codex`, `github_copilot`)\n"
            f"• `/skills` — مدیریت، ساخت و فعال‌سازی مهارت‌ها (`SKILL.md`)\n"
            f"• `/mcp` — مدیریت و اتصال سرورها و ابزارهای Model Context Protocol\n\n"
            f"**سایر دستورات اصلی:**\n"
            f"• `/help` — راهنمای جامع تمام دستورات\n"
            f"• `/project <name>` و `/projects` — مدیریت پروژه‌ها در Knowledge Vault\n"
            f"• `/finance [week|month]` — گزارش مالی و دفتر کل\n"
            f"• `/idea <text>` و `/search <query>` — ایده‌پرداز و جستجوی معنایی\n"
            f"• `/radar` — اسکن پروژه‌های فریلنسری + پروپوزال\n"
            f"• `/screenshot` ، `/github` ، `/imagine` ، `/bio` ، `/lab` ، `/status`"
        )
        await send_formatted_reply(message, text)

    @router.message(Command("help", "commands", "menu"))
    async def handle_help_cmd(message: Message):
        text = (
            "📖 **راهنمای جامع دستورات اسلش (Slash Commands) ایجنت آروش:**\n\n"
            "🤖 **ایجنت‌ها، فضای کدنویسی PC (Claude Code)، ساب‌ایجنت و CLI (Phase 8.1):**\n"
            "• `/agents` — لیست ایجنت‌های آماده (`programmer`, `planner`, `reviewer`, `debugger`, `researcher`) + دکمه سوییچ\n"
            "• `/agents switch <slug> [pc_path]` — تغییر ایجنت فعال و اتصال به پوشه پروژه\n"
            "• `/agents create <name> | <role> | <prompt>` — ساخت ایجنت جدید با ساختار دلخواه\n"
            "• `/workspace <pc_path>` — ذخیره مسیر پروژه روی PC (مثال: `/workspace D:\\projects\\my-app`)\n"
            "• `/workspace tree` — نمایش ساختار درختی فایل‌های پروژه فعلی روی PC\n"
            "• `/subagent <role> <task>` — اجرای ساب‌ایجنت تخصصی (مثال: `/subagent programmer Fix bug in app.py`)\n"
            "• `/cli` — لیست ایجنت‌های نصبی روی سیستم (Claude Code, Antigravity, Codex, GitHub Copilot)\n"
            "• `/cli detect` — بررسی خودکار نصب بودن و نسخه ایجنت‌های CLI روی کامپیوتر\n"
            "• `/cli run <agent> <prompt>` — ارسال تسک کدنویسی به ایجنت نصبی (مثال: `/cli run claude_code Refactor utils.py`)\n"
            "• `/cli add <name> | <binary> | <args>` — ثبت ایجنت CLI جدید روی کامپیوتر\n\n"
            "🧩 **مهارت‌ها (Skills) و پروتکل MCP (Phase 8.2 & 8.3):**\n"
            "• `/skills` — لیست تمام مهارت‌ها همراه با دکمه فعال/غیرفعال‌سازی\n"
            "• `/skills add <name> | <triggers> | <instructions>` — ساخت مهارت جدید (`SKILL.md`)\n"
            "• `/skills view <slug>` — مشاهده متن کامل دستورالعمل یک مهارت\n"
            "• `/mcp` — لیست سرورهای MCP ثبت شده و پریست‌های آماده (`filesystem`, `github`, `sqlite`, `playwright`)\n"
            "• `/mcp preset <name> [path]` — افزودن سریع سرور MCP استاندارد\n"
            "• `/mcp add <name> | <cmd_or_url> | [args]` — افزودن سرور MCP جدید (stdio یا http)\n"
            "• `/mcp discover <name>` — اتصال به سرور MCP و استخراج لیست ابزارها (`tools/list`)\n\n"
            "🗂️ **پروژه‌ها، مالی، رادار و سیستم (Phases 1–7):**\n"
            "• `/project <name>` | `/projects` | `/search <query>`\n"
            "• `/finance [week|month]` | `/idea <text>` | `/radar`\n"
            "• `/screenshot` | `/github [status|prs|ci]` | `/imagine <prompt>`\n"
            "• `/bio <note>` | `/lab <text>` | `/briefing` | `/review` | `/backup` | `/status` | `/cancel`"
        )
        await send_formatted_reply(message, text)

    # ==========================================================
    # Phase 8.1 Handlers: /agents, /workspace, /subagent, /cli
    # ==========================================================
    @router.message(Command("agents", "agent"))
    async def handle_agents_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) == 1:
            agents_list = agent_manager.list_agents()
            active_path = agent_manager.get_active_project_path() or "ثبت نشده"
            lines = [
                "🤖 **ایجنت‌های آماده و شخصی (Prebuilt & Custom Agents):**",
                f"💻 **مسیر پروژه فعال روی PC:** `{active_path}`\n"
            ]
            for ag in agents_list:
                star = "🟢 **[فعال]** " if ag.get("is_active") else "⚪ "
                tag = "Prebuilt" if ag.get("is_builtin") else "Custom"
                bound_path = f"\n   📂 مسیر اختصاصی: `{ag['project_path']}`" if ag.get("project_path") else ""
                skills_str = ", ".join(ag.get("attached_skills") or []) or "none"
                lines.append(
                    f"{star}**{ag['name']}** (`{ag['slug']}`) [{tag}]\n"
                    f"   🎯 نقش: _{ag.get('role_title', '')}_\n"
                    f"   📝 توضیح: {ag.get('description', '')}\n"
                    f"   🧩 مهارت‌ها: `{skills_str}`{bound_path}"
                )
            lines.append(
                "\n💡 **میانبرها:**\n"
                "• سوییچ: `/agents switch programmer D:\\my_project`\n"
                "• ساخت ایجنت جدید: `/agents create نام | نقش | دستورالعمل سیستمی`"
            )
            await send_formatted_reply(message, "\n\n".join(lines), reply_markup=_build_agents_kb())
            return

        sub = parts[1].lower().strip()
        rest = parts[2].strip() if len(parts) > 2 else ""

        if sub in ("switch", "use", "select"):
            sub_parts = rest.split(maxsplit=1)
            target_slug = sub_parts[0] if sub_parts else "manager"
            proj_path = sub_parts[1] if len(sub_parts) > 1 else None
            res = agent_manager.switch_agent(target_slug, project_path=proj_path)
            if res.get("status") == "not_found":
                await send_formatted_reply(message, f"❌ {res.get('error')}")
                return
            ag = res["agent"]
            await send_formatted_reply(
                message,
                f"✅ **ایجنت فعال تغییر کرد به:** `{ag['name']}` (`{ag['slug']}`)\n"
                f"🎯 **نقش:** {ag.get('role_title')}\n"
                f"💻 **مسیر پروژه فعال:** `{agent_manager.get_active_project_path() or 'پیش‌فرض'}`"
            )

        elif sub in ("path", "set_path"):
            if not rest:
                await send_formatted_reply(message, "📂 لطفاً مسیر پوشه پروژه روی کامپیوتر را وارد کنید. مثال:\n`/agents path D:\\projects\\arush-app`")
                return
            res = agent_manager.set_project_path(rest, bind_to_active_agent=True)
            if res.get("status") == "error":
                await send_formatted_reply(message, f"❌ {res['error']}")
                return
            await send_formatted_reply(
                message,
                f"✅ **مسیر پروژه روی PC ذخیره و به ایجنت فعال متصل شد:**\n"
                f"• **مسیر:** `{res['local_path']}`\n"
                f"• **استک تشخیص داده شده:** `{res['tech_stack']}`\n"
                f"• **تعداد فایل‌ها:** `{res['file_count']}`"
            )

        elif sub in ("create", "add"):
            segments = [s.strip() for s in rest.split("|")]
            if len(segments) < 2:
                await send_formatted_reply(
                    message,
                    "📝 فرمت ساخت ایجنت جدید:\n`/agents create <name> | <role_title> | <system_prompt>`"
                )
                return
            name = segments[0]
            role = segments[1] if len(segments) > 2 else "Custom Specialist Agent"
            sys_prompt = segments[2] if len(segments) > 2 else segments[1]
            ag = agent_manager.create_or_update_agent(name=name, role_title=role, system_prompt=sys_prompt, activate=True)
            await send_formatted_reply(
                message,
                f"✅ **ایجنت `{ag['name']}` (`{ag['slug']}`) ساخته و فعال شد!**\n🎯 نقش: `{ag['role_title']}`"
            )

        elif sub in ("delete", "remove"):
            res = agent_manager.delete_agent(rest)
            if res.get("status") == "deleted":
                await send_formatted_reply(message, f"🗑️ ایجنت `{res['slug']}` حذف شد.")
            else:
                await send_formatted_reply(message, f"❌ {res.get('error')}")

        else:
            # Treat `/agents <slug>` directly as switching to that agent
            res = agent_manager.switch_agent(sub, project_path=rest or None)
            if res.get("status") == "switched":
                ag = res["agent"]
                await send_formatted_reply(
                    message,
                    f"✅ **ایجنت فعال تغییر کرد به:** `{ag['name']}` (`{ag['slug']}`)\n"
                    f"💻 **مسیر پروژه:** `{agent_manager.get_active_project_path() or 'پیش‌فرض'}`"
                )
            else:
                await send_formatted_reply(message, f"❌ {res.get('error')}")

    @router.callback_query(F.data.startswith("switch_agent:"))
    async def handle_switch_agent_callback(callback: CallbackQuery):
        slug = callback.data.split(":", 1)[1]
        res = agent_manager.switch_agent(slug)
        if res.get("status") != "switched":
            await callback.answer("ایجنت یافت نشد.", show_alert=True)
            return
        ag = res["agent"]
        await callback.answer(f"ایجنت فعال: {ag['name']}")
        try:
            await callback.message.edit_reply_markup(reply_markup=_build_agents_kb())
        except Exception:
            pass
        await send_formatted_reply(
            callback.message,
            f"🤖 **ایجنت فعال تغییر کرد به:** `{ag['name']}` (`{ag['slug']}`)\n"
            f"🎯 _{ag.get('role_title', '')}_\n"
            f"💻 مسیر پروژه روی PC: `{agent_manager.get_active_project_path() or 'ثبت نشده'}`"
        )

    @router.message(Command("workspace", "path", "code"))
    async def handle_workspace_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) == 1:
            active_path = agent_manager.get_active_project_path()
            workspaces = agent_manager.list_workspaces()
            lines = [
                "💻 **مدیریت مسیر پروژه روی کامپیوتر (Claude Code Workspace):**\n",
                f"• **مسیر فعال فعلی:** `{active_path or 'هنوز ثبت نشده است'}`\n"
            ]
            if workspaces:
                lines.append("📂 **مسیرهای ذخیره شده روی PC:**")
                for w in workspaces:
                    mark = "🟢 " if w.get("is_active") else "⚪ "
                    lines.append(f"{mark}**{w['name']}** (`{w['slug']}`)\n   `{w['local_path']}` [{w.get('tech_stack', '')}]")
            lines.append(
                "\n💡 **دستورات:**\n"
                "• ثبت یا تغییر مسیر پروژه روی PC:\n  `/workspace D:\\projects\\my_app`\n"
                "• مشاهده درخت فایل‌های پروژه:\n  `/workspace tree`"
            )
            await send_formatted_reply(message, "\n".join(lines))
            return

        arg = parts[1].strip()
        if arg.lower() == "tree":
            tree_res = agent_manager.inspect_tree()
            if tree_res.get("status") == "error":
                await send_formatted_reply(message, f"❌ {tree_res['error']}")
                return
            await send_formatted_reply(
                message,
                f"📂 **ساختار درختی پروژه (`{tree_res['project_path']}`):**\n"
                f"فایل‌ها: `{tree_res['total_files']}` | پوشه‌ها: `{tree_res['total_dirs']}`\n"
                f"```\n{tree_res['tree'][:3200]}\n```"
            )
            return

        res = agent_manager.set_project_path(arg, create_if_missing=False, bind_to_active_agent=True)
        if res.get("status") == "error":
            await send_formatted_reply(message, f"❌ {res['error']}")
            return

        await send_formatted_reply(
            message,
            f"✅ **مسیر پروژه روی کامپیوتر ذخیره و فعال شد!**\n\n"
            f"• **نام:** `{res['name']}` (`{res['slug']}`)\n"
            f"• **مسیر لوکال:** `{res['local_path']}`\n"
            f"• **استک پروژه:** `{res['tech_stack']}`\n"
            f"• **تعداد فایل‌ها:** `{res['file_count']}`\n\n"
            f"🌳 **پیش‌نمایش ساختار فایل‌ها:**\n```\n{res['tree_preview'][:1200]}\n```\n"
            f"حالا می‌توانید مستقیماً در چت بگویید چه فایلی را بخوانم، ویرایش کنم، بسازم یا تست بگیرم (مشابه Claude Code)!"
        )

    @router.message(Command("subagent"))
    async def handle_subagent_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 2:
            runs = agent_manager.list_runs(limit=5)
            lines = [
                "🚀 **سیستم اجرای ساب‌ایجنت (Autonomous Sub-Agents):**\n",
                "**نحوه استفاده:**\n"
                "• `/subagent programmer <تسک کدنویسی یا ویرایش فایل>`\n"
                "• `/subagent planner <تسک طراحی معماری و پلن>`\n"
                "• `/subagent reviewer <بررسی کد و امنیت پروژه>`\n"
                "• `/subagent debugger <عیب‌یابی و رفع باگ>`\n"
            ]
            if runs:
                lines.append("📜 **آخرین ساب‌ایجنت‌های اجرا شده:**")
                for r in runs:
                    lines.append(f"• `[{r['run_type']}]` **{r['agent_slug']}** ({r['status']}): _{r['task'][:80]}_")
            await send_formatted_reply(message, "\n".join(lines))
            return

        known_slugs = {a["slug"] for a in agent_manager.list_agents()}
        if parts[1].lower() in known_slugs and len(parts) > 2:
            role_slug = parts[1].lower()
            task_text = parts[2]
        else:
            role_slug = "programmer"
            task_text = " ".join(parts[1:])

        status_msg = await message.answer(
            f"🚀 در حال اجرای ساب‌ایجنت تخصصی `{role_slug}` روی مسیر `{agent_manager.get_active_project_path() or 'پیش‌فرض'}`..."
        )
        res = await agent.run_subagent(agent_slug=role_slug, task=task_text)
        await status_msg.delete()

        if res.get("status") == "error":
            await send_formatted_reply(message, f"❌ خطا در اجرای ساب‌ایجنت `{role_slug}`:\n`{res.get('error')}`")
            return

        out_text = (
            f"🤖 **خروجی ساب‌ایجنت `{res.get('name', role_slug)}` (`{res.get('subagent')}`):**\n"
            f"📂 پروژه: `{res.get('project_path') or 'default'}`\n\n"
            f"{res.get('output', '')}"
        )
        await send_formatted_reply(message, out_text)

    @router.message(Command("cli"))
    async def handle_cli_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) == 1:
            cli_list = agent_manager.list_cli_agents()
            active_path = agent_manager.get_active_project_path() or "پیش‌فرض"
            lines = [
                "🛠️ **مدیریت ایجنت‌های CLI نصب‌شده روی کامپیوتر (External PC CLI Agents):**",
                f"📂 **مسیر اجرای فعلی:** `{active_path}`\n"
            ]
            for c in cli_list:
                det = f"✅ `{c['last_detected_path']}` ({c['last_version']})" if c.get("last_detected_path") else "⚪ بررسی نشده (`/cli detect`)"
                lines.append(
                    f"• **{c['name']}** (`{c['slug']}`)\n"
                    f"  دستور اجرایی: `{c['binary']}` | آرگومان‌ها: `{' '.join(c['args_template'])}`\n"
                    f"  وضعیت شناسایی: {det}\n"
                    f"  _{c.get('description', '')}_"
                )
            lines.append(
                "\n💡 **دستورات کاربردی:**\n"
                "• شناسایی خودکار ایجنت‌های نصب‌شده روی PC:\n  `/cli detect`\n"
                "• اجرای تسک با ایجنت نصبی (در پوشه پروژه فعال):\n"
                "  `/cli run claude_code Add unit tests for auth.py`\n"
                "  `/cli run antigravity Refactor database module`\n"
                "  `/cli run codex Fix type errors in api.py`\n"
                "  `/cli run github_copilot git undo last commit`\n"
                "• تنظیم مسیر فایل اجرایی روی ویندوز/لینوکس:\n"
                "  `/cli set_binary antigravity C:\\Path\\To\\antigravity.exe`\n"
                "• افزودن ایجنت CLI جدید:\n"
                "  `/cli add aider | aider | --message {prompt} --yes`"
            )
            await send_formatted_reply(message, "\n\n".join(lines))
            return

        sub = parts[1].lower().strip()
        rest = parts[2].strip() if len(parts) > 2 else ""

        if sub == "detect":
            status_msg = await message.answer("🔍 در حال اسکن PATH کامپیوتر برای یافتن Claude Code, Antigravity, Codex, GitHub Copilot...")
            detected = await agent_manager.detect_installed_cli_agents()
            await status_msg.delete()
            lines = ["🔍 **نتیجه بررسی ایجنت‌های CLI روی سیستم شما:**\n"]
            for c in detected:
                badge = "🟢 نصب‌شده" if c["installed"] else "🔴 یافت نشد در PATH"
                path_info = f"\n  مسیر: `{c['detected_path']}`\n  نسخه: `{c['version']}`" if c["installed"] else f"\n  باینری مورد انتظار: `{c['binary']}`"
                lines.append(f"• **{c['name']}** (`{c['slug']}`): {badge}{path_info}")
            await send_formatted_reply(message, "\n\n".join(lines))

        elif sub == "run":
            run_parts = rest.split(maxsplit=1)
            if len(run_parts) < 2:
                await send_formatted_reply(message, "⚠️ فرمت صحیح: `/cli run <agent_slug> <prompt>`\nمثال: `/cli run claude_code Fix bug in main.py`")
                return
            cli_slug, prompt_txt = run_parts[0], run_parts[1]
            status_msg = await message.answer(
                f"⚡ در حال اجرای `{cli_slug}` روی مسیر `{agent_manager.get_active_project_path() or 'فعلی'}`..."
            )
            res = await agent_manager.run_external_cli_agent(agent_name=cli_slug, prompt=prompt_txt)
            await status_msg.delete()
            if res.get("status") in ("not_found", "not_installed", "error", "disabled", "timeout"):
                await send_formatted_reply(message, f"❌ **{res.get('status')}:**\n{res.get('error')}")
                return
            output = res.get("stdout") or res.get("stderr") or "(بدون خروجی متنی)"
            reply_txt = (
                f"✅ **خروجی `{res.get('name', cli_slug)}` (Exit Code: `{res.get('exit_code')}`):**\n"
                f"📂 مسیر: `{res.get('cwd')}`\n"
                f"```\n{output[:3400]}\n```"
            )
            await send_formatted_reply(message, reply_txt)

        elif sub == "set_binary":
            b_parts = rest.split(maxsplit=1)
            if len(b_parts) < 2:
                await send_formatted_reply(message, "⚠️ فرمت صحیح: `/cli set_binary <agent_slug> <full_binary_path>`")
                return
            slug_name, bin_path = b_parts[0], b_parts[1].strip("'\"")
            existing = agent_manager.get_cli_agent(slug_name)
            updated = agent_manager.register_or_update_cli_agent(
                name=existing["name"] if existing else slug_name,
                binary=bin_path,
            )
            await send_formatted_reply(
                message,
                f"✅ مسیر فایل اجرایی برای `{updated['slug']}` تنظیم شد به:\n`{updated['binary']}`"
            )

        elif sub in ("add", "register"):
            segs = [s.strip() for s in rest.split("|")]
            if len(segs) < 2:
                await send_formatted_reply(message, "⚠️ فرمت صحیح: `/cli add <name> | <binary> | [args_template]`")
                return
            name = segs[0]
            binary = segs[1]
            args_tmpl = segs[2].split() if len(segs) > 2 and segs[2] else ["-p", "{prompt}"]
            created = agent_manager.register_or_update_cli_agent(name=name, binary=binary, args_template=args_tmpl)
            await send_formatted_reply(
                message,
                f"✅ ایجنت CLI `{created['name']}` (`{created['slug']}`) با دستور `{created['binary']}` ثبت شد!"
            )

        else:
            # Allow shorthand `/cli claude_code <prompt>`
            res = await agent_manager.run_external_cli_agent(agent_name=sub, prompt=rest)
            if res.get("status") in ("not_found", "not_installed", "error", "disabled", "timeout"):
                await send_formatted_reply(message, f"❌ {res.get('error')}")
            else:
                output = res.get("stdout") or res.get("stderr") or "(Done)"
                await send_formatted_reply(message, f"✅ **خروجی `{res.get('name', sub)}`:**\n```\n{output[:3400]}\n```")

    # ==========================================================
    # Phase 8.2 Handlers: /skills
    # ==========================================================
    @router.message(Command("skills", "skill"))
    async def handle_skills_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) == 1:
            skills_list = skills_manager.list_skills()
            lines = ["🧩 **مدیریت مهارت‌های ایجنت (Skills Registry — `SKILL.md`):**\n"]
            for sk in skills_list:
                badge = "🟢 فعال" if sk.get("enabled") else "⚪ غیرفعال"
                kind = "Built-in" if sk.get("is_builtin") else "Custom"
                lines.append(
                    f"• **{sk['name']}** (`{sk['slug']}`) — {badge} [{kind}]\n"
                    f"  _{sk.get('description', '')}_\n"
                    f"  🔑 کلیدواژه‌ها: `{sk.get('triggers') or 'همیشه در دسترس'}`"
                )
            lines.append(
                "\n💡 **دستورات مهارت‌ها:**\n"
                "• مشاهده محتوای مهارت: `/skills view <slug>`\n"
                "• ساخت مهارت جدید: `/skills add <name> | <triggers> | <instructions>`\n"
                "• تغییر وضعیت: روی دکمه‌های زیر کلیک کنید یا `/skills toggle <slug>`"
            )
            await send_formatted_reply(message, "\n\n".join(lines), reply_markup=_build_skills_kb())
            return

        sub = parts[1].lower().strip()
        rest = parts[2].strip() if len(parts) > 2 else ""

        if sub in ("view", "get", "show"):
            sk = skills_manager.get_skill(rest)
            if not sk:
                await send_formatted_reply(message, f"❌ مهارت `{rest}` یافت نشد.")
                return
            await send_formatted_reply(
                message,
                f"🧩 **مهارت: {sk['name']} (`{sk['slug']}`)**\n"
                f"📂 فایل: `{sk.get('file_path', '')}`\n\n"
                f"{sk['content'][:3500]}"
            )

        elif sub in ("add", "create"):
            segs = [s.strip() for s in rest.split("|")]
            if len(segs) < 2:
                await send_formatted_reply(
                    message,
                    "⚠️ فرمت ساخت مهارت:\n`/skills add <name> | <triggers> | <markdown_instructions>`"
                )
                return
            name = segs[0]
            triggers = segs[1] if len(segs) > 2 else ""
            content = segs[2] if len(segs) > 2 else segs[1]
            sk = skills_manager.create_or_update_skill(name=name, triggers=triggers, content=content)
            await send_formatted_reply(
                message,
                f"✅ مهارت **{sk['name']}** (`{sk['slug']}`) ذخیره و در `{sk['file_path']}` ثبت شد!"
            )

        elif sub == "toggle":
            sk = skills_manager.get_skill(rest)
            if not sk:
                await send_formatted_reply(message, f"❌ مهارت `{rest}` یافت نشد.")
                return
            updated = skills_manager.toggle_skill(rest, enabled=not bool(sk.get("enabled")))
            state_str = "🟢 فعال" if updated["skill"]["enabled"] else "⚪ غیرفعال"
            await send_formatted_reply(message, f"✅ وضعیت مهارت `{rest}` تغییر کرد به: **{state_str}**")

        elif sub in ("delete", "remove"):
            res = skills_manager.delete_skill(rest)
            if res.get("status") == "deleted":
                await send_formatted_reply(message, f"🗑️ مهارت `{res['slug']}` حذف شد.")
            else:
                await send_formatted_reply(message, f"❌ {res.get('error')}")

    @router.callback_query(F.data.startswith("toggle_skill:"))
    async def handle_toggle_skill_callback(callback: CallbackQuery):
        slug = callback.data.split(":", 1)[1]
        sk = skills_manager.get_skill(slug)
        if not sk:
            await callback.answer("مهارت یافت نشد.", show_alert=True)
            return
        res = skills_manager.toggle_skill(slug, enabled=not bool(sk.get("enabled")))
        new_state = "فعال 🟢" if res["skill"]["enabled"] else "غیرفعال ⚪"
        await callback.answer(f"مهارت {slug}: {new_state}")
        try:
            await callback.message.edit_reply_markup(reply_markup=_build_skills_kb())
        except Exception:
            pass

    # ==========================================================
    # Phase 8.3 Handlers: /mcp
    # ==========================================================
    @router.message(Command("mcp"))
    async def handle_mcp_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) == 1:
            servers = mcp_manager.list_servers()
            lines = ["🔌 **مدیریت سرورها و ابزارهای Model Context Protocol (MCP):**\n"]
            if servers:
                for s in servers:
                    badge = "🟢 فعال" if s.get("enabled") else "⚪ غیرفعال"
                    t_count = len(s.get("cached_tools") or [])
                    endpoint = s["url"] if s["transport"] == "http" else f"{s['command']} {' '.join(s['args'])}"
                    lines.append(
                        f"• **{s['name']}** (`{s['slug']}`) [{s['transport'].upper()}] — {badge}\n"
                        f"  دستور/آدرس: `{endpoint}`\n"
                        f"  ابزارهای کش‌شده: `{t_count}` | وضعیت: `{s.get('last_status', 'configured')}`"
                    )
            else:
                lines.append("⚪ هنوز سرور MCP فعالی ثبت نشده است.")

            presets_str = ", ".join(f"`{k}`" for k in MCP_PRESETS.keys())
            lines.append(
                f"\n📦 **پریست‌های آماده نصب سریع:** {presets_str}\n\n"
                "💡 **دستورات MCP:**\n"
                "• افزودن پریست آماده:\n  `/mcp preset filesystem D:\\projects`\n"
                "• افزودن سرور دلخواه (stdio یا http):\n  `/mcp add my_mcp | npx | -y @modelcontextprotocol/server-memory`\n"
                "• ایمپورت فایل کانفیگ JSON استاندارد Claude:\n  `/mcp import {\"mcpServers\": {...}}`\n"
                "• کشف و اتصال ابزارهای سرور (`tools/list`):\n  `/mcp discover <server_name>`\n"
                "• حذف سرور:\n  `/mcp remove <server_name>`"
            )
            await send_formatted_reply(message, "\n\n".join(lines))
            return

        sub = parts[1].lower().strip()
        rest = parts[2].strip() if len(parts) > 2 else ""

        if sub == "preset":
            p_parts = rest.split(maxsplit=1)
            preset_name = p_parts[0] if p_parts else "filesystem"
            target_path = p_parts[1] if len(p_parts) > 1 else agent_manager.get_active_project_path()
            res = mcp_manager.add_preset_server(preset_name=preset_name, target_path=target_path)
            if res.get("status") == "error":
                await send_formatted_reply(message, f"❌ {res['error']}")
                return
            await send_formatted_reply(
                message,
                f"✅ **سرور MCP پریست `{res['name']}` (`{res['slug']}`) ثبت شد!**\n"
                f"• دستور: `{res['command']} {' '.join(res['args'])}`\n"
                f"برای استخراج ابزارها بزنید: `/mcp discover {res['slug']}`"
            )

        elif sub == "add":
            segs = [s.strip() for s in rest.split("|")]
            if len(segs) < 2:
                await send_formatted_reply(
                    message,
                    "⚠️ فرمت افزودن سرور MCP:\n"
                    "• Stdio: `/mcp add <name> | <command> | <space_separated_args>`\n"
                    "• HTTP: `/mcp add <name> | http://localhost:8080/mcp`"
                )
                return
            name = segs[0]
            cmd_or_url = segs[1]
            args = segs[2].split() if len(segs) > 2 and segs[2] else []
            if cmd_or_url.startswith("http://") or cmd_or_url.startswith("https://"):
                srv = mcp_manager.add_or_update_server(name=name, transport="http", url=cmd_or_url)
            else:
                srv = mcp_manager.add_or_update_server(name=name, transport="stdio", command=cmd_or_url, args=args)
            await send_formatted_reply(
                message,
                f"✅ سرور MCP **{srv['name']}** (`{srv['slug']}`) با موفقیت ثبت شد!"
            )

        elif sub == "import":
            res = mcp_manager.import_mcp_json(rest)
            if res.get("status") == "error":
                await send_formatted_reply(message, f"❌ خطا در ایمپورت JSON:\n`{res['error']}`")
                return
            await send_formatted_reply(
                message,
                f"✅ تعداد `{res['count']}` سرور MCP از کانفیگ JSON ایمپورت شد:\n`{', '.join(res['imported_servers'])}`"
            )

        elif sub == "discover":
            if not rest:
                await send_formatted_reply(message, "⚠️ نام سرور MCP را وارد کنید: `/mcp discover <server_name>`")
                return
            status_msg = await message.answer(f"🔌 در حال اتصال به سرور MCP `{rest}` و دریافت لیست ابزارها...")
            res = await mcp_manager.discover_server_tools(rest)
            await status_msg.delete()
            if res.get("status") != "connected":
                await send_formatted_reply(message, f"❌ خطا در اتصال به `{rest}`:\n`{res.get('error')}`")
                return
            tool_names = [t.get("name", "") for t in res.get("tools", [])]
            await send_formatted_reply(
                message,
                f"✅ **اتصال به `{res['server']}` برقرار شد!**\n"
                f"🔧 تعداد ابزارهای کشف‌شده: `{res['tools_count']}`\n"
                f"ابزارها: `{', '.join(tool_names) or 'بدون ابزار'}`\n\n"
                f"این ابزارها اکنون به صورت خودکار در دسترس ایجنت اصلی و ساب‌ایجنت‌ها هستند."
            )

        elif sub in ("remove", "delete"):
            res = mcp_manager.remove_server(rest)
            if res.get("status") == "deleted":
                await send_formatted_reply(message, f"🗑️ سرور MCP `{res['slug']}` حذف شد.")
            else:
                await send_formatted_reply(message, f"❌ {res.get('error')}")

        elif sub == "call":
            c_parts = rest.split(maxsplit=2)
            if len(c_parts) < 2:
                await send_formatted_reply(message, "⚠️ فرمت: `/mcp call <server> <tool_name> [json_args]`")
                return
            srv_name, t_name = c_parts[0], c_parts[1]
            args_dict = {}
            if len(c_parts) > 2:
                try:
                    args_dict = json.loads(c_parts[2])
                except Exception:
                    args_dict = {}
            res = await mcp_manager.call_tool(srv_name, t_name, arguments=args_dict)
            await send_formatted_reply(
                message,
                f"🔌 **نتیجه فراخوانی MCP (`{srv_name}.{t_name}`):**\n```json\n{json.dumps(res, ensure_ascii=False, indent=2)[:3500]}\n```"
            )

    # ==========================================================
    # Phases 1–7 Existing Slash Command Handlers
    # ==========================================================
    @router.message(Command("cancel", "stop"))
    async def handle_cancel_cmd(message: Message):
        canceled = confirmation_manager.cancel_all_pending()
        agent.last_pending_confirmations.clear()
        agent.last_generated_images.clear()
        msg = "🔄 **عملیات لغو شد.** حافظه موقت و اقدامات در انتظار پاکسازی شدند."
        if canceled > 0:
            msg += f"\n• `{canceled}` اقدام امنیتی در حال انتظار لغو شد."
        await send_formatted_reply(message, msg)

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
            await send_formatted_reply(message, "📁 پروژه‌ای انتخاب نشده است. مثال: `/project crypto_bot`")
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
        await send_formatted_reply(message, txt)

    @router.message(Command("projects"))
    async def handle_projects_cmd(message: Message):
        projs = vault.list_projects()
        if not projs:
            await send_formatted_reply(message, "📁 هیچ پروژه‌ای هنوز ثبت نشده است. با `/project <name>` بسازید.")
            return
        lines = ["📁 **پروژه‌های ثبت شده در Knowledge Vault:**\n"]
        for p in projs:
            active_star = "⭐ " if p.get("is_active") else ""
            status_emoji = "🟢" if p["status"] == "in_progress" else "⚪"
            lines.append(
                f"{status_emoji} {active_star}**{p['name']}** (`{p['slug']}`) | پلتفرم: {p['platform']} | وضعیت: {p['status']}"
            )
        await send_formatted_reply(message, "\n".join(lines))

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
        await send_formatted_reply(message, "\n".join(lines))

    @router.message(Command("idea"))
    async def handle_idea_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await send_formatted_reply(message, "💡 لطفاً متن ایده خود را بعد از `/idea` بنویسید یا یک ویس بفرستید.")
            return
        status_msg = await message.answer("🧠 در حال پردازش و ساختاردهی ایده در Incubator...")
        res = await idea_incubator.incubate_transcript(parts[1])
        await status_msg.delete()
        await send_formatted_reply(message, res["formatted_markdown"])

    @router.message(Command("search"))
    async def handle_search_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await send_formatted_reply(message, "🔍 عبارت جستجو را وارد کنید. مثال: `/search رنگ دکمه‌ها در پروژه`")
            return
        query = parts[1].strip()
        q_emb = await router_client.create_embedding(query)
        results = vault.semantic_search_vault(query=query, query_embedding=q_emb, top_k=5)
        if not results:
            await send_formatted_reply(message, "🔍 نتیجه‌ای در حافظه معنایی یافت نشد.")
            return
        lines = [f"🧠 **نتایج جستجوی معنایی برای:** _{query}_\n"]
        for r in results:
            proj_tag = f" (`{r['project_slug']}`)" if r.get("project_slug") else ""
            lines.append(
                f"• **[{r['type'].upper()}] {r['title']}**{proj_tag} — شباهت: `{int(r['similarity'] * 100)}%`\n"
                f"  _{r['content'][:180]}_"
            )
        await send_formatted_reply(message, "\n\n".join(lines))

    @router.message(Command("radar"))
    async def handle_radar_cmd(message: Message):
        status_msg = await message.answer("📡 در حال اسکن مستقیم کارلنسر، پونیشا و کانال‌های تلگرام...")
        await freelance_radar.poll_sources_once()
        leads = vault.get_top_freelance_leads(min_score=0, limit=3)
        await status_msg.delete()
        if not leads:
            await send_formatted_reply(message, "📡 هنوز پروژه فریلنسری منطبقی در دیتابیس ثبت نشده است.")
            return
        for ld in leads:
            alert_txt = freelance_radar.format_telegram_alert(ld)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 مشاهده و ارسال پیشنهاد در سایت", url=ld.get("url") or "https://ponisha.ir")]
                ]
            )
            await send_formatted_reply(message, alert_txt, reply_markup=kb)

    @router.message(Command("github"))
    async def handle_github_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=2)
        sub = parts[1].lower() if len(parts) > 1 else "status"
        if sub == "prs":
            res = await github_tool.list_open_prs()
            await send_formatted_reply(message, f"🐙 **GitHub Open PRs:**\n```json\n{res}\n```")
        elif sub == "ci":
            res = await github_tool.list_workflow_runs()
            await send_formatted_reply(message, f"⚙️ **GitHub Actions CI/CD Runs:**\n```json\n{res}\n```")
        else:
            res = await github_tool.run_local_git("status", repo_path=agent_manager.get_active_project_path())
            await send_formatted_reply(
                message,
                f"🐙 **وضعیت مخزن محلی Git:**\n```\n{res.get('stdout') or res.get('stderr') or res}\n```"
            )

    @router.message(Command("imagine"))
    async def handle_imagine_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await send_formatted_reply(message, "🎨 پرامپت تصویر را وارد کنید. مثال: `/imagine futuristic Persian AI dashboard UI`")
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
            await send_formatted_reply(message, f"❌ خطا در تولید تصویر: {res.get('error')}")

    @router.message(Command("bio"))
    async def handle_bio_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            recent = vault.get_recent_bio_logs(days=7)
            lines = ["🧬 **لاگ‌های زیستی و عادت‌های ۷ روز اخیر:**\n"]
            for b in recent[:10]:
                lines.append(f"• **{b['metric_name']}**: `{b['value']} {b.get('unit', '')}` ({b['logged_at']})")
            await send_formatted_reply(message, "\n".join(lines) if len(lines) > 1 else "هنوز موردی ثبت نشده است.")
            return
        logged = life_tracker.parse_and_log_bio_note(parts[1])
        summary = ", ".join(f"{x['metric_name']}={x['value']}{x.get('unit', '')}" for x in logged)
        await send_formatted_reply(message, f"✅ **در سیستم سلامت ثبت شد:** `{summary}`")

    @router.message(Command("lab"))
    async def handle_lab_cmd(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            results = vault.get_lab_results()
            if not results:
                await send_formatted_reply(message, "🩺 برای تحلیل آزمایش، متن یا تصویر آزمایش را بفرستید. مثال: `/lab WBC 6.2 Vitamin D 18 TSH 2.1`")
                return
            lines = ["🩺 **آخرین نتایج آزمایشگاهی ثبت شده:**\n"]
            for r in results[:10]:
                badge = "🔴" if r["flag"] != "NORMAL" else "🟢"
                lines.append(f"{badge} **{r['biomarker']}**: `{r['value']} {r['unit']}` [{r['flag']}]")
            await send_formatted_reply(message, "\n".join(lines))
            return
        parsed = life_tracker.parse_and_store_lab_report(parts[1])
        lines = [f"🩺 **نتایج استخراج شده ({parsed['total_extracted']} شاخص):**\n"]
        for r in parsed["results"]:
            badge = "⚠️" if r["flag"] != "NORMAL" else "✅"
            lines.append(
                f"{badge} **{r['biomarker']}** ({r['test_category']}): `{r['value']} {r['unit']}` "
                f"(نرمال: {r['reference_min']}–{r['reference_max']}) ➔ **{r['flag']}**"
            )
        await send_formatted_reply(message, "\n".join(lines))

    @router.message(Command("briefing"))
    async def handle_briefing_cmd(message: Message):
        await send_formatted_reply(message, routine_scheduler.generate_morning_briefing())

    @router.message(Command("review"))
    async def handle_review_cmd(message: Message):
        await send_formatted_reply(message, routine_scheduler.generate_nightly_review())

    @router.message(Command("backup"))
    async def handle_backup_cmd(message: Message):
        res = run_daily_backup()
        await send_formatted_reply(
            message,
            f"💾 **بکاپ خودکار با موفقیت انجام شد:**\n"
            f"• مسیر: `{res['backup_dir']}`\n"
            f"• فایل‌ها: `{len(res['files'])}`"
        )

    @router.message(Command("status"))
    async def handle_status_cmd(message: Message):
        health = await watchdog.get_health_status()
        status_9router = "🟢 متصل" if health["ninerouter_connected"] else "🔴 قطع (بررسی NINEROUTER_URL)"
        active_proj = vault.get_active_project()
        active_str = f"`{active_proj['name']}` (`{active_proj['slug']}`)" if active_proj else "انتخاب نشده"
        active_ag = agent_manager.get_active_agent()
        active_pc_path = agent_manager.get_active_project_path() or "ثبت نشده"

        txt = (
            f"📊 **وضعیت سیستم Arush Agent (Self-Healing Watchdog):**\n\n"
            f"• **وضعیت کلی:** `{health['status'].upper()}` (Uptime: `{health['uptime_seconds']}s`)\n"
            f"• **9Router URL:** `{settings.NINEROUTER_URL}` ({status_9router})\n"
            f"• **ایجنت فعال:** `{active_ag['name']}` (`{active_ag['slug']}`)\n"
            f"• **مسیر پروژه روی PC:** `{active_pc_path}`\n"
            f"• **پروژه فعال در Vault:** {active_str}\n"
            f"• **مهارت‌های فعال:** `{len(skills_manager.list_skills(only_enabled=True))}`\n"
            f"• **سرورهای MCP فعال:** `{len(mcp_manager.list_servers(only_enabled=True))}`\n"
            f"• **مدل ایجنت:** `{settings.AGENT_MODEL}`\n"
            f"• **مدل ویس (STT):** `{settings.STT_MODEL}`\n"
            f"• **مدل تصویر:** `{settings.IMAGE_MODEL}`\n"
            f"• **مدل Embedding:** `{settings.EMBEDDING_MODEL}`\n"
            f"• **تعداد تلاش‌های اتصال مجدد:** `{health['reconnect_count']}`\n"
            f"• **مسیر داده‌ها:** `{settings.VAULT_DATA_DIR}`"
        )
        await send_formatted_reply(message, txt)

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
            f"✅ <b>عملیات تایید و اجرا شد:</b>\n<code>{rec['description']}</code>\nنتیجه: <code>{res.get('status', 'done')}</code>",
            parse_mode="HTML"
        )
        await callback.answer("اجرا شد!")

    @router.callback_query(F.data.startswith("cancel_action:"))
    async def handle_cancel_callback(callback: CallbackQuery):
        action_id = callback.data.split(":", 1)[1]
        rec = confirmation_manager.resolve_pending(action_id, approved=False)
        desc = rec["description"] if rec else action_id
        await callback.message.edit_text(f"❌ <b>عملیات لغو شد:</b> <code>{desc}</code>", parse_mode="HTML")
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
            await send_formatted_reply(message, reply)
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

            # If caption contains receipt details directly, parse and deduplicate right away
            if message.caption and any(k in message.caption for k in ("کد رهگیری", "شماره پیگیری", "کارت به کارت", "پایا", "ساتنا")):
                rec = receipt_parser.parse_and_record(message.caption, receipt_path=str(local_path))
                if rec["duplicate"]:
                    await status_msg.edit_text(
                        f"⚠️ <b>رسید تکراری تشخیص داده شد!</b>\nکد رهگیری <code>{rec['parsed']['tracking_code']}</code> قبلاً در دفتر مالی ثبت شده است.",
                        parse_mode="HTML"
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
            await send_formatted_reply(message, reply)
            await _deliver_side_effects(message)

        except Exception as e:
            err_text = str(e)[:500]
            await status_msg.edit_text(f"❌ خطا در تحلیل تصویر:\n{err_text}", parse_mode=None)

    @router.message(F.text)
    async def handle_text(message: Message):
        """Handles standard text prompts, receipt pastes, and natural language commands."""
        active_ag = agent_manager.get_active_agent()
        status_msg = await message.answer(f"🧠 در حال تفکر (`{active_ag['slug']}`)...")
        messages = [{"role": "user", "content": message.text}]

        async def update_status(text: str):
            try:
                await status_msg.edit_text(text)
            except Exception:
                pass

        try:
            reply = await agent.chat(messages, on_status_update=update_status)
            await status_msg.delete()
            await send_formatted_reply(message, reply)
            await _deliver_side_effects(message)
        except Exception as e:
            err_text = str(e)[:500]
            await status_msg.edit_text(f"❌ خطا:\n{err_text}", parse_mode=None)
