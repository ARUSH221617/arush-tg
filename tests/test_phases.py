import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from config import settings
from core.router_client import compute_local_embedding
from core.agent import agent
from core.scheduler import routine_scheduler
from core.watchdog import watchdog
from tools.vault import ProjectVault
from tools.receipt_parser import IranianReceiptParser
from tools.idea_incubator import VoiceIdeaIncubator
from tools.freelance_radar import FreelanceRadar
from tools.computer_use import WindowsComputerController, confirmation_manager
from tools.browser_agent import AgenticBrowserController
from tools.github_tool import GitHubIntegrationTool
from tools.image_studio import ComfyUILocalRunner, ImageStudio
from tools.life_tracker import MedicalLabAndBioTracker
from scripts.backup import run_daily_backup


class TestArushPhases1To7(unittest.TestCase):
    """Comprehensive verification suite for Phases 1 through 7 of Arush Manager Agent."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.data_path = Path(self.tmp_dir.name)
        self.db_path = self.data_path / "db" / "vault.sqlite"
        self.test_vault = ProjectVault(db_path=self.db_path, data_dir=self.data_path)

    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    # ----------------------------------------------------------
    # Phase 2.1: Hierarchical Project Vault
    # ----------------------------------------------------------
    def test_phase2_1_hierarchical_project_workspace(self):
        proj = self.test_vault.switch_active_project("Crypto Dashboard UI")
        self.assertEqual(proj["slug"], "crypto_dashboard_ui")
        self.assertEqual(proj["is_active"], 1)

        proj_dir = self.data_path / "projects" / "crypto_dashboard_ui"
        self.assertTrue((proj_dir / "context.md").exists())
        self.assertTrue((proj_dir / "specs.json").exists())
        self.assertTrue((proj_dir / "assets").is_dir())

        # Save artifact and verify context.md is updated
        self.test_vault.save_artifact(
            artifact_type="client_requirement",
            title="Button Color Spec",
            content="The client requested emerald green (#10B981) primary CTA buttons in dark mode.",
            tags="ui,colors"
        )
        summary = self.test_vault.get_project_summary("crypto_dashboard_ui")
        self.assertEqual(summary["total_artifacts"], 1)
        self.assertIn("emerald green", summary["context_preview"])

    # ----------------------------------------------------------
    # Phase 2.2: Iranian Bank Receipt Parser & Deduplication
    # ----------------------------------------------------------
    def test_phase2_2_iranian_receipt_parser_and_deduplication(self):
        parser = IranianReceiptParser()
        sample_receipt = (
            "بلو بانک سامان - انتقال وجه کارت به کارت موفق\n"
            "مبلغ: ۲۵,۰۰۰,۰۰۰ ریال\n"
            "کارت مبدا: ۶۲۱۹-۸۶۱۹-****-۱۲۳۴\n"
            "کارت مقصد: ۶۰۳۷-۹۹۷۵-****-۵۶۷۸\n"
            "کد رهگیری: ۹۸۷۶۵۴۳۲۱۰۱۱\n"
            "تاریخ: ۱۴۰۵/۰۸/۰۶ ۱۴:۳۰"
        )
        parsed = parser.parse_receipt_text(sample_receipt)
        self.assertIn("BluBank", parsed["bank_name"])
        self.assertIn("Card-to-Card", parsed["transfer_type"])
        self.assertEqual(parsed["tracking_code"], "987654321011")
        self.assertEqual(parsed["amount"], 25_000_000.0)
        self.assertEqual(parsed["currency"], "Rial")
        self.assertEqual(parsed["amount_toman"], 2_500_000.0)

        # Record first time -> duplicate=False
        tx1 = self.test_vault.record_transaction(
            amount=parsed["amount"],
            currency=parsed["currency"],
            tracking_code=parsed["tracking_code"],
            description="Client milestone 1"
        )
        self.assertFalse(tx1["duplicate"])

        # Record second time with identical tracking code -> duplicate=True (deduplicated)
        tx2 = self.test_vault.record_transaction(
            amount=parsed["amount"],
            currency=parsed["currency"],
            tracking_code=parsed["tracking_code"],
            description="Duplicate upload"
        )
        self.assertTrue(tx2["duplicate"])
        self.assertEqual(tx1["id"], tx2["id"])

        # Financial summary normalizes 25,000,000 Rial -> 2,500,000 Toman
        fin = self.test_vault.get_financial_summary(days=7)
        self.assertEqual(fin["transaction_count"], 1)
        self.assertEqual(fin["income_toman"], 2_500_000.0)

    # ----------------------------------------------------------
    # Phase 2.3 & 2.4: Ideas Incubator & Semantic Vector Memory
    # ----------------------------------------------------------
    def test_phase2_3_and_2_4_incubator_and_semantic_vector_search(self):
        incubator = VoiceIdeaIncubator()
        structured = incubator._heuristic_structure(
            "می‌خوام یک ربات تلگرام هوشمند با پایتون و هوش مصنوعی برای مانیتور کردن قیمت ارز دیجیتال بسازم"
        )
        self.assertIn("core_concept", structured)
        self.assertGreaterEqual(structured["feasibility_score"], 1)
        self.assertLessEqual(structured["feasibility_score"], 10)
        self.assertTrue(len(structured["recommended_tech_stack"]) >= 2)
        self.assertTrue(len(structured["immediate_action_steps"]) >= 3)

        # Populate multiple project artifacts and run semantic vector search
        self.test_vault.save_artifact(
            artifact_type="client_requirement",
            title="Header & Button Styling",
            content="The client specifically asked for royal blue primary button colors and rounded corners.",
            project_slug="ponisha_shop",
            tags="ui,buttons,css"
        )
        self.test_vault.save_artifact(
            artifact_type="note",
            title="Database Schema",
            content="PostgreSQL tables for users, orders, and invoices with indexes.",
            project_slug="ponisha_shop",
            tags="backend,sql"
        )

        results = self.test_vault.semantic_search_vault(
            query="What did the client say about button colors?",
            project_slug="ponisha_shop",
            top_k=2
        )
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0]["title"], "Header & Button Styling")
        self.assertGreater(results[0]["similarity"], results[1]["similarity"])

    # ----------------------------------------------------------
    # Phase 3: Freelance Radar (Karlancer, Ponisha & Telegram)
    # ----------------------------------------------------------
    def test_phase3_freelance_radar_filtering_and_proposal(self):
        radar = FreelanceRadar()
        sample_json = json.dumps({
            "projects": [
                {
                    "id": "kl_5512",
                    "title": "طراحی و ساخت ربات تلگرام هوشمند با پایتون و هوش مصنوعی",
                    "description": "نیاز به یک توسعه‌دهنده ارشد Python و aiogram برای اتصال ربات به مدل‌های LLM داریم.",
                    "category": "python,bot,ai",
                    "min_budget": 12000000,
                    "max_budget": 18000000,
                    "employer_rating": 4.9
                },
                {
                    "id": "kl_5513",
                    "title": "تایپ ساده ورد",
                    "description": "تایپ ۵ صفحه متفرقه",
                    "category": "typing",
                    "min_budget": 100000,
                    "max_budget": 200000
                }
            ]
        })
        items = radar.parse_feed_items(sample_json, platform="karlancer")
        self.assertEqual(len(items), 2)
        self.assertTrue(radar.filter_lead(items[0]))
        self.assertFalse(radar.filter_lead(items[1]))

        eval_res = radar.matchmaker.score_and_draft_SyncFallback(items[0])
        self.assertGreaterEqual(eval_res["match_score"], 80)
        self.assertIn("پیشنهاد", eval_res["proposal_draft"])

        merged = {**items[0], **eval_res}
        saved = self.test_vault.save_freelance_lead(merged)
        self.assertTrue(saved["is_new"])
        alert_md = radar.format_telegram_alert(saved)
        self.assertIn("karlancer", alert_md)
        self.assertIn("https://www.karlancer.com/projects/kl_5512", alert_md)

    def test_phase3_system_one_batch_filtering(self):
        radar = FreelanceRadar()
        leads = [
            {
                "external_id": "test_lead_s1_1",
                "platform": "telegram:@python_jobs",
                "title": "پروژه ساخت ربات تلگرام با پایتون",
                "description": "نیاز به برنامه‌نویس پایتون مسلط به aiogram برای پیاده‌سازی ربات سفارش‌گیری",
                "budget_min": 5000000,
                "budget_max": 8000000,
                "currency": "Toman"
            },
            {
                "external_id": "test_lead_s1_2",
                "platform": "telegram:@news",
                "title": "مقاله آموزشی هوش مصنوعی چیست؟",
                "description": "در این وبینار رایگان به مباحث هوش مصنوعی می‌پردازیم",
                "budget_min": 0,
                "budget_max": 0,
                "currency": "Toman"
            }
        ]
        from unittest.mock import patch, AsyncMock
        mock_answers = {
            "is_job_1": {"type": "noul", "noul": 0.95},
            "matches_stack_1": {"type": "noul", "noul": 0.92},
            "is_job_2": {"type": "noul", "noul": 0.05},
            "matches_stack_2": {"type": "noul", "noul": 0.40}
        }
        with patch("core.router_client.router_client.system_one", new_callable=AsyncMock) as mock_s1:
            mock_s1.return_value = mock_answers
            filtered = asyncio.run(radar.batch_filter_leads_system_one(leads))
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0]["external_id"], "test_lead_s1_1")
            self.assertEqual(filtered[0]["system_one_is_job"], 0.95)
            self.assertEqual(filtered[0]["system_one_stack_fit"], 0.92)
            self.assertGreaterEqual(filtered[0]["match_score"], 90)

    # ----------------------------------------------------------
    # Phase 4: Visual Computer Use, Confirmation Gate, Browser & GitHub
    # ----------------------------------------------------------
    def test_phase4_computer_confirmation_browser_and_github(self):
        ctrl = WindowsComputerController()
        # Sensitive action must trigger confirmation gate first
        res = ctrl.execute_action(action="key", text="alt+f4", confirmed=False)
        self.assertEqual(res["status"], "requires_confirmation")
        action_id = res["action_id"]

        resolved = confirmation_manager.resolve_pending(action_id, approved=True)
        self.assertEqual(resolved["status"], "approved")

        # Browser launch args check
        browser = AgenticBrowserController()
        self.assertTrue(any("--profile-directory=" in arg for arg in browser.get_launch_args()))

        # Tool definitions check on main agent
        tool_names = {t["function"]["name"] for t in agent.get_tool_definitions()}
        expected_tools = {
            "powershell", "computer", "manage_project", "save_to_vault", "search_vault",
            "parse_and_record_receipt", "record_transaction", "get_financial_summary",
            "incubate_voice_idea", "scan_freelance_radar", "browser_automation",
            "github_action", "generate_image", "parse_medical_lab", "log_bio_habit"
        }
        self.assertTrue(expected_tools.issubset(tool_names))

    # ----------------------------------------------------------
    # Phase 5: Image Studio & Local ComfyUI Workflow Builder
    # ----------------------------------------------------------
    def test_phase5_image_studio_and_comfyui_graph(self):
        comfy = ComfyUILocalRunner()
        graph = comfy.build_workflow_graph(
            prompt="Modern dark mode fintech UI dashboard",
            workflow_type="flux_gguf",
            width=1344,
            height=768
        )
        self.assertIn("3", graph)
        self.assertEqual(graph["5"]["inputs"]["width"], 1344)
        self.assertEqual(graph["5"]["inputs"]["height"], 768)

        studio = ImageStudio()
        self.assertEqual(studio.resolve_model("dalle3"), "openai/dall-e-3")
        self.assertEqual(studio.resolve_model("flux-schnell"), "black-forest-labs/flux-1-schnell")

    # ----------------------------------------------------------
    # Phase 6: Medical Lab Parser, Bio-Logging & Daily Briefings
    # ----------------------------------------------------------
    def test_phase6_medical_lab_parser_and_bio_logging(self):
        tracker = MedicalLabAndBioTracker()
        # Temporarily bind global vault in life_tracker for isolated DB test
        import tools.life_tracker as lt_mod
        orig_vault = lt_mod.vault
        lt_mod.vault = self.test_vault
        try:
            lab_Sample = (
                "CBC & Metabolic Panel\n"
                "WBC: 6.4 10^3/uL\n"
                "Hemoglobin: 15.2 g/dL\n"
                "Vitamin D: 18.5 ng/mL\n"
                "TSH: 5.8 mIU/L\n"
                "FBS: 92 mg/dL\n"
            )
            report = tracker.parse_and_store_lab_report(lab_Sample, lab_date="2026-10-28")
            self.assertEqual(report["total_extracted"], 5)
            # Vitamin D (18.5 < 30 -> LOW) and TSH (5.8 > 4.5 -> HIGH) should be flagged
            self.assertEqual(report["flagged_count"], 2)
            flags = {r["biomarker"]: r["flag"] for r in report["results"]}
            self.assertEqual(flags["Vitamin D"], "LOW")
            self.assertEqual(flags["TSH"], "HIGH")
            self.assertEqual(flags["WBC"], "NORMAL")

            bio_entries = tracker.parse_and_log_bio_note("امروز ۷.۵ ساعت خوابیدم، ۲ تا قهوه خوردم و ۴۵ دقیقه ورزش کردم")
            metrics = {b["metric_name"]: b["value"] for b in bio_entries}
            self.assertEqual(metrics.get("sleep_hours"), "7.5")
            self.assertEqual(metrics.get("caffeine"), "2")
            self.assertEqual(metrics.get("workout"), "45")
        finally:
            lt_mod.vault = orig_vault

    # ----------------------------------------------------------
    # Phase 7: Automated Backups & Self-Healing Watchdog
    # ----------------------------------------------------------
    def test_phase7_backups_scheduler_and_watchdog(self):
        backup_root = self.data_path / "backups"
        env_dummy = self.data_path / ".env"
        env_dummy.write_text("NINEROUTER_URL=http://localhost:20128\n", encoding="utf-8")

        res = run_daily_backup(
            db_path=self.db_path,
            backup_root=backup_root,
            env_path=env_dummy,
            retention_days=14
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(len(res["files"]), 2)
        self.assertTrue((Path(res["backup_dir"]) / "vault.sqlite").exists())

        morning = routine_scheduler.generate_morning_briefing()
        nightly = routine_scheduler.generate_nightly_review()
        self.assertIn("گزارش صبحگاهی", morning)
        self.assertIn("مرور شبانه", nightly)

        health = asyncio.run(watchdog.get_health_status())
        self.assertEqual(health["status"], "healthy")
        self.assertTrue(health["vault_db_ok"])


if __name__ == "__main__":
    unittest.main()
