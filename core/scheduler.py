import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable, Awaitable, Optional, Dict, Any
from config import settings
from tools.vault import vault
from scripts.backup import run_daily_backup


class DailyRoutineScheduler:
    """
    Phase 6.3, 6.4 & Phase 7.2: Autonomous Daily Routines & Backup Scheduler.
    - 08:30 AM (`settings.MORNING_BRIEFING_TIME`): Autonomous Morning Briefing
      (active project deadlines, top freelance leads, recent bio status).
    - 10:30 PM (`settings.NIGHTLY_REVIEW_TIME`): Nightly Review Cycle
      (completed habits check, daily income/expense summary, prompt for voice reflection).
    - 03:00 AM (`settings.BACKUP_TIME`): Automated hot backup of `vault.sqlite` and `.env`.
    """

    def __init__(self):
        self._running = False
        self._last_triggered: Dict[str, str] = {}

    def _local_now(self) -> datetime:
        tz = timezone(timedelta(hours=settings.TIMEZONE_OFFSET_HOURS))
        return datetime.now(tz)

    def generate_morning_briefing(self) -> str:
        """Builds the 08:30 AM Morning Briefing message in Persian."""
        now_str = self._local_now().strftime("%Y-%m-%d %H:%M")
        projects = vault.list_projects(status="in_progress")
        leads = vault.get_top_freelance_leads(min_score=settings.RADAR_MATCH_THRESHOLD, limit=3)
        flagged_labs = vault.get_lab_results(only_flagged=True)[:3]

        lines = [
            f"🌅 **صبح بخیر آروش! گزارش صبحگاهی ({now_str})**\n",
            "📁 **پروژه‌های فعال و ددلاین‌ها:**"
        ]
        if projects:
            for p in projects[:5]:
                dl = f" | ⏳ ددلاین: `{p.get('deadline')}`" if p.get("deadline") else ""
                active_mark = "⭐ " if p.get("is_active") else "• "
                lines.append(f"{active_mark}**{p['name']}** (`{p['slug']}`) — {p.get('platform', 'direct')}{dl}")
        else:
            lines.append("• در حال حاضر پروژه فعالی ثبت نشده است.")

        lines.append("\n🎯 **بهترین فرصت‌های فریلنسری (تطابق بالا):**")
        if leads:
            for ld in leads:
                lines.append(
                    f"• **{ld['title']}** ({ld['platform']}) — تطابق: `{ld['match_score']}%` | پیشنهاد: {ld.get('suggested_bid', '-')}"
                )
        else:
            lines.append("• مورد جدیدی بالای ۸۰٪ در ۲۴ ساعت گذشته ثبت نشده است.")

        if flagged_labs:
            lines.append("\n🩺 **یادآوری سلامت (شاخص‌های آزمایشگاهی نیازمند توجه):**")
            for lab in flagged_labs:
                lines.append(f"• `{lab['biomarker']}`: {lab['value']} {lab['unit']} (**{lab['flag']}**)")

        lines.append("\n💪 روز پرانرژی و پرسودی داشته باشی! اگر برنامه خاصی برای امروز داری، ویس بفرست.")
        return "\n".join(lines)

    def generate_nightly_review(self) -> str:
        """Builds the 10:30 PM Nightly Review Cycle message in Persian."""
        now_str = self._local_now().strftime("%Y-%m-%d %H:%M")
        fin_today = vault.get_financial_summary(days=1)
        bio_today = vault.get_recent_bio_logs(days=1)

        lines = [
            f"🌙 **مرور شبانه آروش ({now_str})**\n",
            "💰 **خلاصه مالی ۲۴ ساعت گذشته:**",
            f"• ورودی امروز: `{fin_today['income_toman']:,.0f}` تومان",
            f"• خروجی امروز: `{fin_today['expense_toman']:,.0f}` تومان",
            f"• تراز خالص روز: `{fin_today['net_toman']:,.0f}` تومان ({fin_today['transaction_count']} تراکنش)\n",
            "🧬 **عادت‌ها و لاگ‌های زیستی ثبت‌شده امروز:**"
        ]
        if bio_today:
            for b in bio_today[:8]:
                lines.append(f"• ✅ **{b['metric_name']}**: `{b['value']} {b.get('unit', '')}`")
        else:
            lines.append("• هنوز لاگ خواب، ورزش یا کافئین برای امروز ثبت نشده است.")

        lines.append(
            "\n🎙️ **پرامپت بازتاب شبانه (Voice Reflection):**\n"
            "لطفاً یک ویس کوتاه بفرست و بگو:\n"
            "۱. مهم‌ترین دستاورد امروزت چه بود؟\n"
            "۲. چه ایده‌ای یا چالشی برای فردا داری؟"
        )
        return "\n".join(lines)

    async def run_loop(
        self,
        send_notification: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> None:
        self._running = True
        while self._running:
            now = self._local_now()
            date_key = now.strftime("%Y-%m-%d")
            hh_mm = now.strftime("%H:%M")

            # 1. Morning Briefing (08:30)
            if hh_mm == settings.MORNING_BRIEFING_TIME and self._last_triggered.get("morning") != date_key:
                self._last_triggered["morning"] = date_key
                if send_notification:
                    await send_notification(self.generate_morning_briefing())

            # 2. Nightly Review (22:30)
            if hh_mm == settings.NIGHTLY_REVIEW_TIME and self._last_triggered.get("nightly") != date_key:
                self._last_triggered["nightly"] = date_key
                if send_notification:
                    await send_notification(self.generate_nightly_review())

            # 3. Daily Database Backup (03:00)
            if hh_mm == settings.BACKUP_TIME and self._last_triggered.get("backup") != date_key:
                self._last_triggered["backup"] = date_key
                try:
                    run_daily_backup()
                except Exception:
                    pass

            await asyncio.sleep(30)

    def stop(self) -> None:
        self._running = False


routine_scheduler = DailyRoutineScheduler()
