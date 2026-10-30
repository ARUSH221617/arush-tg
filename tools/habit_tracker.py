import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from config import settings
from tools.vault import vault


class HabitEngine:
    """
    Habits & Future Habits Engine for Arush Manager Agent.
    Manages:
    - Active daily habit checklists with interactive Telegram buttons
    - Future habit incubator & roadmap (scheduled start dates, prerequisites, levels)
    - Streak calculations (current streak, longest streak, 30-day consistency rate)
    - Integration with Morning Briefing (08:30) and Nightly Review (22:30)
    - Autonomous promotion of future habits when their start date arrives
    - Voice / natural language matching for auto-completion
    """

    def __init__(self):
        self._ensure_starter_habits_seeded()

    def _local_now(self) -> datetime:
        tz = timezone(timedelta(hours=settings.TIMEZONE_OFFSET_HOURS))
        return datetime.now(tz)

    def get_today_str(self) -> str:
        return self._local_now().strftime("%Y-%m-%d")

    def _ensure_starter_habits_seeded(self):
        """Seeds standard starter habits and a future habit in roadmap if vault is empty."""
        try:
            existing = vault.list_habits()
            if not existing:
                today_str = self.get_today_str()
                # 1. Active starter habits
                starters = [
                    {
                        "slug": "deep_work",
                        "title": "۴۵ دقیقه تمرکز عمیق (Deep Work)",
                        "description": "کار روی تسک اصلی بدون تلفن و حواس‌پرتی",
                        "category": "productivity",
                        "target_value": 45,
                        "unit": "دقیقه",
                        "time_of_day": "morning",
                        "priority": 1,
                        "level": 1
                    },
                    {
                        "slug": "workout",
                        "title": "ورزش و فعالیت بدنی",
                        "description": "۳۰ دقیقه تمرین کششی یا هوازی/باشگاه",
                        "category": "fitness",
                        "target_value": 30,
                        "unit": "دقیقه",
                        "time_of_day": "morning",
                        "priority": 2,
                        "level": 1
                    },
                    {
                        "slug": "water_intake",
                        "title": "نوشیدن ۲.۵ لیتر آب",
                        "description": "حفظ هیدراتاسیون در طول روز کاری",
                        "category": "health",
                        "target_value": 2.5,
                        "unit": "لیتر",
                        "time_of_day": "anytime",
                        "priority": 3,
                        "level": 1
                    },
                    {
                        "slug": "read_book",
                        "title": "مطالعه ۲۰ صفحه کتاب تخصصی",
                        "description": "مطالعه کتاب‌های مهندسی یا توسعه فردی",
                        "category": "learning",
                        "target_value": 20,
                        "unit": "صفحه",
                        "time_of_day": "evening",
                        "priority": 4,
                        "level": 1
                    },
                    {
                        "slug": "night_reflection",
                        "title": "خاموشی قبل ۱۲ و مرور شبانه",
                        "description": "ارسال ویس بازتاب و خواب به‌موقع",
                        "category": "mindfulness",
                        "target_value": 1,
                        "unit": "جلسه",
                        "time_of_day": "evening",
                        "priority": 5,
                        "level": 1
                    }
                ]
                for s in starters:
                    vault.create_habit(
                        slug=s["slug"],
                        title=s["title"],
                        description=s["description"],
                        category=s["category"],
                        target_value=s["target_value"],
                        unit=s["unit"],
                        time_of_day=s["time_of_day"],
                        status="active",
                        start_date=today_str,
                        priority=s["priority"],
                        level=s["level"]
                    )

                # 2. Future habit sample in roadmap (starts in 14 days)
                future_date = (self._local_now() + timedelta(days=14)).strftime("%Y-%m-%d")
                vault.create_habit(
                    slug="running_5k",
                    title="دویدن ۵ کیلومتر در هفته",
                    description="هدف هوازی ارتقای استقامت پس از تثبیت استریک ورزش",
                    category="fitness",
                    target_value=5,
                    unit="کیلومتر",
                    time_of_day="morning",
                    status="future",
                    start_date=future_date,
                    priority=2,
                    level=2
                )
        except Exception:
            pass

    def calculate_streak(self, habit_id: int, current_date_str: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculates:
        - current_streak: contiguous completed days working backwards.
        - longest_streak: all-time contiguous completed days.
        - completion_rate_30d: percentage of completed days in the last 30 days.
        - total_completed: total days completed.
        """
        target_date_str = current_date_str or self.get_today_str()
        target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")

        records = vault.get_all_completions_for_habit(habit_id)
        completed_dates = {r["date"] for r in records if r["is_completed"] == 1}

        # 1. Current Streak
        current_streak = 0
        cursor_dt = target_dt

        # If today is not completed, streak is still preserved if yesterday was completed
        if cursor_dt.strftime("%Y-%m-%d") not in completed_dates:
            cursor_dt -= timedelta(days=1)

        while cursor_dt.strftime("%Y-%m-%d") in completed_dates:
            current_streak += 1
            cursor_dt -= timedelta(days=1)

        # 2. Longest Streak
        longest_streak = 0
        sorted_dates = sorted(
            [datetime.strptime(d, "%Y-%m-%d") for d in completed_dates]
        )
        if sorted_dates:
            temp_streak = 1
            longest_streak = 1
            for i in range(1, len(sorted_dates)):
                diff = (sorted_dates[i] - sorted_dates[i - 1]).days
                if diff == 1:
                    temp_streak += 1
                    if temp_streak > longest_streak:
                        longest_streak = temp_streak
                elif diff > 1:
                    temp_streak = 1

        # 3. 30-Day Completion Rate
        start_30d = target_dt - timedelta(days=29)
        completed_30d = sum(
            1 for d in completed_dates
            if start_30d <= datetime.strptime(d, "%Y-%m-%d") <= target_dt
        )
        rate_30d = round((completed_30d / 30.0) * 100, 1)

        return {
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "completion_rate_30d": rate_30d,
            "total_completed": len(completed_dates)
        }

    def get_daily_checklist(self, date_str: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetches today's active habits with their status, streak, progress bar and summary.
        """
        target_date = date_str or self.get_today_str()
        habits = vault.get_today_habits_with_completions(target_date)

        enriched = []
        completed_count = 0

        for h in habits:
            is_done = bool(h.get("is_done_today"))
            if is_done:
                completed_count += 1
            streak_info = self.calculate_streak(h["id"], target_date)
            enriched.append({
                **h,
                "is_done": is_done,
                "current_streak": streak_info["current_streak"],
                "longest_streak": streak_info["longest_streak"],
                "completion_rate_30d": streak_info["completion_rate_30d"]
            })

        total = len(enriched)
        pct = round((completed_count / total * 100)) if total > 0 else 0

        # Build progress bar: e.g. [██████░░░░]
        filled_blocks = int(pct / 10)
        empty_blocks = 10 - filled_blocks
        progress_bar = f"[{'█' * filled_blocks}{'░' * empty_blocks}] {completed_count}/{total} ({pct}%)"

        return {
            "date": target_date,
            "total": total,
            "completed_count": completed_count,
            "pending_count": total - completed_count,
            "percentage": pct,
            "progress_bar": progress_bar,
            "habits": enriched
        }

    def toggle_habit(
        self,
        habit_id: int,
        date_str: Optional[str] = None,
        source: str = "telegram_button"
    ) -> Dict[str, Any]:
        """Toggles completion status for a habit on given date."""
        target_date = date_str or self.get_today_str()
        res = vault.toggle_habit_completion(habit_id, target_date, source=source)
        streak_info = self.calculate_streak(habit_id, target_date)
        habit = vault.get_habit_by_id(habit_id)
        return {
            "habit": habit,
            "completion": res,
            "is_done": bool(res.get("is_completed")),
            "streak": streak_info
        }

    def add_habit(
        self,
        title: str,
        category: str = "productivity",
        frequency: str = "daily",
        target_value: float = 1.0,
        unit: str = "",
        time_of_day: str = "anytime",
        start_date: Optional[str] = None,
        description: str = "",
        priority: int = 2,
        level: int = 1,
        prerequisite_habit_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Creates an active or future habit.
        If start_date is set in the future (after today), status is automatically set to 'future'.
        """
        today_str = self.get_today_str()
        s_date = start_date.strip() if start_date else today_str

        # Generate a unique slug from title
        clean = re.sub(r"[^\w\u0600-\u06FF]+", "_", title.lower().strip()).strip("_")
        base_slug = clean[:30] or "habit"
        slug = base_slug
        counter = 1
        while vault.get_habit_by_slug(slug):
            slug = f"{base_slug}_{counter}"
            counter += 1

        status = "future" if s_date > today_str else "active"

        created = vault.create_habit(
            slug=slug,
            title=title,
            description=description,
            category=category,
            frequency=frequency,
            target_value=target_value,
            unit=unit,
            time_of_day=time_of_day,
            status=status,
            start_date=s_date,
            priority=priority,
            level=level,
            prerequisite_habit_id=prerequisite_habit_id
        )
        return created

    def get_future_habits_roadmap(self) -> List[Dict[str, Any]]:
        """Retrieves all queued future habits with days remaining and prerequisite details."""
        today_dt = self._local_now()
        future_habits = vault.list_habits(status="future")
        enriched = []

        for h in future_habits:
            s_date = h.get("start_date") or ""
            days_left = 0
            if s_date:
                try:
                    s_dt = datetime.strptime(s_date, "%Y-%m-%d")
                    days_left = (s_dt.date() - today_dt.date()).days
                except Exception:
                    days_left = 0

            prereq_title = None
            if h.get("prerequisite_habit_id"):
                prereq = vault.get_habit_by_id(h["prerequisite_habit_id"])
                if prereq:
                    prereq_title = prereq.get("title")

            enriched.append({
                **h,
                "days_left": max(0, days_left),
                "prerequisite_title": prereq_title
            })

        return sorted(enriched, key=lambda x: x.get("start_date", ""))

    def promote_due_habits(self) -> List[Dict[str, Any]]:
        """Checks and activates future habits whose start_date has arrived."""
        today_str = self.get_today_str()
        promoted = vault.promote_due_future_habits(today_str)
        return promoted

    def format_future_habits_roadmap(self) -> str:
        """Builds a formatted Persian markdown summary of future habits."""
        roadmap = self.get_future_habits_roadmap()
        if not roadmap:
            return (
                "🔮 **نقشه راه عادات آینده (Habit Incubator):**\n\n"
                "• در حال حاضر هیچ عادت آینده‌ای در صف ثبت نشده است.\n\n"
                "💡 **افزودن عادت جدید برای آینده:**\n"
                "`/habits add دویدن ۵ کیلومتر 2026-11-15`\n"
                "یا به صورت متنی/صوتی: *«می‌خوام از اول ماه بعد عادت زبان خوندن رو شروع کنم»*"
            )

        lines = [
            "🔮 **نقشه راه عادات آینده (Habit Incubator & Roadmap):**\n"
            "این عادات برنامه‌ریزی شده‌اند و در تاریخ مشخص‌شده به‌صورت خودکار وارد چک‌لیست روزانه خواهند شد:\n"
        ]

        for idx, h in enumerate(roadmap, start=1):
            days_text = f"⏳ **{h['days_left']} روز دیگر**" if h["days_left"] > 0 else "🚀 آماده فعال‌سازی امروز"
            lines.append(
                f"{idx}. **{h['title']}** (سطح {h.get('level', 1)})\n"
                f"   • تاریخ شروع: `{h['start_date']}` ({days_text})\n"
                f"   • دسته‌بندی: `{h.get('category', 'routine')}` | هدف: `{h.get('target_value', 1)} {h.get('unit', '')}`"
            )
            if h.get("prerequisite_title"):
                lines.append(f"   • 🔗 پیش‌نیاز: تکمیل استریک «{h['prerequisite_title']}»")
            if h.get("description"):
                lines.append(f"   • توضیحات: _{h['description']}_")
            lines.append("")

        lines.append("💡 برای اضافه کردن عادت آینده:\n`/habits add <نام> [YYYY-MM-DD]`")
        return "\n".join(lines)

    def format_habits_stats(self) -> str:
        """Builds statistics and performance report across all active habits."""
        today_str = self.get_today_str()
        active_habits = vault.list_habits(status="active")
        if not active_habits:
            return "📊 هنوز عادتی در سیستم ثبت نشده است."

        lines = [f"📊 **آمار عملکرد و استریک‌های عادت ({today_str}):**\n"]

        total_streak_sum = 0
        total_rate_sum = 0.0

        for h in active_habits:
            streak = self.calculate_streak(h["id"], today_str)
            curr = streak["current_streak"]
            best = streak["longest_streak"]
            rate = streak["completion_rate_30d"]
            total_streak_sum += curr
            total_rate_sum += rate

            flame = "🔥" if curr >= 7 else ("⚡" if curr > 0 else "⚪")
            lines.append(
                f"• {flame} **{h['title']}**\n"
                f"  استریک فعلی: `{curr}` روز | رکورد: `{best}` روز | پایبندی ۳۰ روزه: `{rate}%`"
            )

        avg_rate = round(total_rate_sum / len(active_habits), 1) if active_habits else 0.0
        lines.append(f"\n📈 **میانگین پایبندی کل سیستم:** `{avg_rate}%`")
        lines.append(f"🎯 **تعداد عادات فعال:** `{len(active_habits)}`")

        future_count = len(vault.list_habits(status="future"))
        if future_count > 0:
            lines.append(f"🔮 **عادات آینده در صف:** `{future_count}` مورد (`/habits future`)")

        return "\n".join(lines)

    def match_and_log_voice_habits(self, text: str) -> List[Dict[str, Any]]:
        """
        Parses spoken or written notes and automatically matches them against active habits.
        Marks matches completed for today.
        """
        today_str = self.get_today_str()
        active_habits = vault.list_habits(status="active")
        matched = []

        norm = text.lower()

        # Keyword mapping for common habits
        alias_map = {
            "deep_work": ["deep work", "تمرکز", "دیپ‌ورک", "کار عمیق", "کد زدم", "تمرکز عمیق"],
            "workout": ["ورزش", "باشگاه", "تمرین", "gym", "workout", "شنا", "دویدم", "هوازی", "حرکات کششی"],
            "water_intake": ["آب خوردم", "نوشیدن آب", "آب", "water", "لیتر آب"],
            "read_book": ["کتاب", "مطالعه", "خوندم", "صفحه کتاب", "book", "reading"],
            "night_reflection": ["مرور شبانه", "ویس شبانه", "خاموشی", "reflection", "خوابیدم"]
        }

        for h in active_habits:
            slug = h.get("slug", "")
            title = h.get("title", "").lower()
            hit = False

            # Check direct title or slug
            if slug and slug in norm:
                hit = True
            elif any(w in norm for w in title.split() if len(w) >= 4):
                hit = True

            # Check aliases
            if not hit and slug in alias_map:
                if any(alias in norm for alias in alias_map[slug]):
                    hit = True

            if hit:
                res = vault.record_habit_completion(
                    habit_id=h["id"],
                    date_str=today_str,
                    value=float(h.get("target_value", 1.0)),
                    is_completed=True,
                    source="voice_nlp"
                )
                matched.append({
                    "habit": h,
                    "completion": res
                })

        return matched


habit_engine = HabitEngine()

