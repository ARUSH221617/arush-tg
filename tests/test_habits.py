import unittest
import tempfile
import shutil
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Ensure repo root is on sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from tools.vault import ProjectVault
from tools.habit_tracker import HabitEngine


class TestHabitsAndFutureHabits(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "test_vault.sqlite"
        self.vault = ProjectVault(db_path=self.db_path, data_dir=self.temp_dir)

        # Create isolated HabitEngine instance using this test vault
        import tools.habit_tracker as ht
        self.orig_vault = ht.vault
        ht.vault = self.vault
        self.engine = HabitEngine()

    def tearDown(self):
        import tools.habit_tracker as ht
        ht.vault = self.orig_vault
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_starter_habits_seeded(self):
        habits = self.vault.list_habits(status="active")
        self.assertGreaterEqual(len(habits), 4)

        future = self.vault.list_habits(status="future")
        self.assertGreaterEqual(len(future), 1)

    def test_checklist_and_toggle(self):
        today = self.engine.get_today_str()
        checklist_before = self.engine.get_daily_checklist(today)
        self.assertIn("progress_bar", checklist_before)
        first_habit = checklist_before["habits"][0]
        self.assertFalse(first_habit["is_done"])

        # Toggle completion (ON)
        res_on = self.engine.toggle_habit(first_habit["id"], date_str=today)
        self.assertTrue(res_on["is_done"])

        checklist_after = self.engine.get_daily_checklist(today)
        updated_first = next(h for h in checklist_after["habits"] if h["id"] == first_habit["id"])
        self.assertTrue(updated_first["is_done"])
        self.assertGreater(checklist_after["percentage"], 0)

        # Toggle completion (OFF)
        res_off = self.engine.toggle_habit(first_habit["id"], date_str=today)
        self.assertFalse(res_off["is_done"])

    def test_streak_calculation(self):
        habit = self.vault.create_habit(slug="meditation", title="مدیتیشن ۱۰ دقیقه‌ای")
        today_dt = datetime.strptime(self.engine.get_today_str(), "%Y-%m-%d")

        # Simulate 3 consecutive completed days (yesterday, 2 days ago, 3 days ago)
        d1 = (today_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        d2 = (today_dt - timedelta(days=2)).strftime("%Y-%m-%d")
        d3 = (today_dt - timedelta(days=3)).strftime("%Y-%m-%d")

        self.vault.record_habit_completion(habit["id"], d3, is_completed=True)
        self.vault.record_habit_completion(habit["id"], d2, is_completed=True)
        self.vault.record_habit_completion(habit["id"], d1, is_completed=True)

        # Today is not completed yet, but streak should be 3 (still alive today)
        streak_info = self.engine.calculate_streak(habit["id"], today_dt.strftime("%Y-%m-%d"))
        self.assertEqual(streak_info["current_streak"], 3)

        # Complete today as well -> streak becomes 4
        today_str = today_dt.strftime("%Y-%m-%d")
        self.vault.record_habit_completion(habit["id"], today_str, is_completed=True)
        streak_info_today = self.engine.calculate_streak(habit["id"], today_str)
        self.assertEqual(streak_info_today["current_streak"], 4)
        self.assertEqual(streak_info_today["longest_streak"], 4)

    def test_future_habits_lifecycle_and_promotion(self):
        # 1. Create a future habit for 5 days from now
        future_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        h_future = self.engine.add_habit(
            title="کدنویسی Rust روزانه",
            start_date=future_date,
            category="learning"
        )
        self.assertEqual(h_future["status"], "future")

        roadmap = self.engine.get_future_habits_roadmap()
        rust_habit = next((h for h in roadmap if h["id"] == h_future["id"]), None)
        self.assertIsNotNone(rust_habit)
        self.assertGreaterEqual(rust_habit["days_left"], 4)

        # 2. Promote habits: test when date arrives
        promoted = self.vault.promote_due_future_habits(future_date)
        promoted_ids = [p["id"] for p in promoted]
        self.assertIn(h_future["id"], promoted_ids)

        updated_h = self.vault.get_habit_by_id(h_future["id"])
        self.assertEqual(updated_h["status"], "active")

    def test_voice_matching_habits(self):
        matched = self.engine.match_and_log_voice_habits("امروز ۴۵ دقیقه ورزش کردم و آب خوردم")
        matched_slugs = [m["habit"]["slug"] for m in matched]
        self.assertTrue(any("workout" in s for s in matched_slugs))
        self.assertTrue(any("water" in s for s in matched_slugs))


if __name__ == "__main__":
    unittest.main()
