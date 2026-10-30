import asyncio
import json
import unittest
from unittest.mock import patch, AsyncMock
from pathlib import Path
import tempfile
import shutil

from tools.freelance_radar import (
    FreelanceRadar,
    parse_persian_budget,
    compute_deterministic_lead_id
)
from tools.vault import ProjectVault


class TestRadarSystemImprovements(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="arush_test_radar_"))
        self.vault = ProjectVault(
            db_path=self.test_dir / "vault.sqlite",
            data_dir=self.test_dir
        )
        self.radar = FreelanceRadar()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_persian_budget_parser_all_formats(self):
        # 1. Word multipliers (میلیون, م ت)
        b_min, b_max, curr = parse_persian_budget("پروژه پایتون با بودجه ۱۵ میلیون تومان")
        self.assertEqual(b_min, 15_000_000.0)
        self.assertEqual(b_max, 15_000_000.0)
        self.assertEqual(curr, "Toman")

        # 2. Ranges (۱۰ تا ۲۵ میلیون)
        b_min, b_max, curr = parse_persian_budget("بودجه بین ۱۰ تا ۲۵ میلیون تومان در نظر گرفته شده")
        self.assertEqual(b_min, 10_000_000.0)
        self.assertEqual(b_max, 25_000_000.0)
        self.assertEqual(curr, "Toman")

        # 3. Comma-separated digits
        b_min, b_max, curr = parse_persian_budget("مبلغ ۱۲,۵۰۰,۰۰۰ تومان")
        self.assertEqual(b_min, 12_500_000.0)
        self.assertEqual(curr, "Toman")

        # 4. Plain unformatted digits
        b_min, b_max, curr = parse_persian_budget("حداکثر سقف 20000000 تومان")
        self.assertEqual(b_max, 20_000_000.0)

        # 5. Rial conversion to Toman
        b_min, b_max, curr = parse_persian_budget("بودجه ۸۰,۰۰۰,۰۰۰ ریال")
        self.assertEqual(b_max, 8_000_000.0)

        # 6. USD Currency
        b_min, b_max, curr = parse_persian_budget("Budget: $500 - $1200 for Python scraper")
        self.assertEqual(b_min, 500.0)
        self.assertEqual(b_max, 1200.0)
        self.assertEqual(curr, "USD")

    def test_deterministic_lead_id(self):
        url1 = "https://karlancer.com/projects/kl_100?utm_source=tg&utm_medium=channel"
        url2 = "https://karlancer.com/projects/kl_100"
        id1 = compute_deterministic_lead_id("karlancer", url1)
        id2 = compute_deterministic_lead_id("karlancer", url2)
        # Tracking params are stripped, producing the exact same ID
        self.assertEqual(id1, id2)
        self.assertTrue(id1.startswith("karlancer_"))

    def test_vault_radar_crm_operations(self):
        lead_data = {
            "external_id": "test_lead_crm_1",
            "platform": "karlancer",
            "title": "طراحی بات تلگرام پیشرفته",
            "description": "نیاز به بات اختصاصی با aiogram و FastAPI",
            "budget_min": 15000000,
            "budget_max": 20000000,
            "currency": "Toman",
            "match_score": 92,
            "suggested_bid": "18,000,000 تومان",
            "suggested_timeline": "۵ روز کاری",
            "proposal_draft": "متن پروپوزال نمونه"
        }
        saved = self.vault.save_freelance_lead(lead_data)
        lead_id = saved["id"]
        self.assertTrue(saved["is_new"])

        # Fetch by ID
        fetched = self.vault.get_lead_by_id(lead_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["title"], lead_data["title"])

        # Mark notified
        self.assertTrue(self.vault.mark_lead_notified(lead_id))
        updated = self.vault.get_lead_by_id(lead_id)
        self.assertEqual(updated["notified"], 1)

        # Convert to Project
        res = self.vault.convert_lead_to_project(lead_id)
        self.assertIn("project", res)
        proj = res["project"]
        self.assertIn("طراحی بات تلگرام", proj["name"])

        # Check CRM status updated
        after_conv = self.vault.get_lead_by_id(lead_id)
        self.assertEqual(after_conv["status"], "converted")
        self.assertEqual(after_conv["converted_project_id"], proj["id"])

        # Test radar stats
        stats = self.vault.get_radar_stats()
        self.assertEqual(stats["total_leads"], 1)
        self.assertEqual(stats["converted_projects"], 1)
        self.assertEqual(stats["high_match_leads"], 1)

    def test_user_rejection_and_active_feedback(self):
        lead_data = {
            "external_id": "test_lead_reject_1",
            "platform": "ponisha",
            "title": "پروژه تایپ و ورود دستی داده‌ها",
            "description": "ورود اطلاعات فایل اکسل",
            "budget_min": 500000,
            "budget_max": 500000,
            "match_score": 10
        }
        saved = self.vault.save_freelance_lead(lead_data)
        self.vault.update_lead_status(saved["id"], status="rejected", feedback=-1, rejection_reason="Low budget entry")

        rejections = self.vault.get_recent_rejected_leads(limit=5)
        self.assertEqual(len(rejections), 1)
        self.assertEqual(rejections[0]["id"], saved["id"])
        self.assertEqual(rejections[0]["rejection_reason"], "Low budget entry")

    def test_global_rss_parsing(self):
        sample_rss = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title><![CDATA[Senior Python & AI Engineer ($80k - $120k)]]></title>
              <link>https://remoteok.com/l/99812</link>
              <description><![CDATA[We are seeking a senior Python developer to build AI agents and Telegram automations. Budget $500 - $1,500 per milestone.]]></description>
            </item>
          </channel>
        </rss>
        """
        items = self.radar.parse_global_rss(sample_rss, platform="remoteok")
        self.assertEqual(len(items), 1)
        lead = items[0]
        self.assertEqual(lead["platform"], "remoteok")
        self.assertEqual(lead["currency"], "USD")
        self.assertEqual(lead["budget_min"], 500.0)
        self.assertEqual(lead["budget_max"], 1500.0)

    def test_concurrent_system2_evaluation(self):
        leads = [
            {
                "external_id": f"test_lead_batch_{i}",
                "platform": "karlancer",
                "title": f"پروژه تست اتوماسیون پایتون {i}",
                "description": "اسکریپت‌نویسی با پایتون و وب اسکرپینگ",
                "budget_min": 5000000,
                "budget_max": 8000000,
                "currency": "Toman"
            }
            for i in range(3)
        ]
        with patch.object(self.radar.matchmaker, "evaluate_lead", new_callable=AsyncMock) as mock_eval:
            mock_eval.return_value = {
                "match_score": 85,
                "suggested_bid": "7,000,000 تومان",
                "suggested_timeline": "۵ روز کاری",
                "proposal_draft": "پروپوزال آماده"
            }
            with patch.object(self.radar, "batch_filter_leads_system_one", new_callable=AsyncMock) as mock_s1:
                mock_s1.return_value = leads
                with patch.object(self.radar, "net"):
                    # Directly test the concurrent pipeline in poll_sources_once logic
                    sem = asyncio.Semaphore(4)
                    async def _eval(ld):
                        async with sem:
                            res = await self.radar.matchmaker.evaluate_lead(ld)
                            ld.update(res)
                            return self.vault.save_freelance_lead(ld)

                    async def run_batch():
                        return await asyncio.gather(*[_eval(ld) for ld in leads])

                    evaluated = asyncio.run(run_batch())
                    self.assertEqual(len(evaluated), 3)
                    for item in evaluated:
                        self.assertEqual(item["match_score"], 85)
                        self.assertEqual(item["status"], "new")

    def test_alert_formatting_and_keyboard(self):
        lead = {
            "id": 42,
            "title": "توسعه ربات هوش مصنوعی تلگرام",
            "platform": "karlancer",
            "budget_min": 25000000,
            "budget_max": 30000000,
            "currency": "Toman",
            "employer_rating": 4.9,
            "match_score": 95,
            "suggested_bid": "27,000,000 تومان",
            "suggested_timeline": "۷ روز",
            "proposal_draft": "متن پروپوزال تست",
            "url": "https://www.karlancer.com/projects/kl_9999"
        }
        alert_md = self.radar.format_telegram_alert(lead)
        # Verify Platinum tier badge and budget formatting
        self.assertIn("فرصت طلایی فریلنسری", alert_md)
        self.assertIn("30,000,000 تومان", alert_md)
        self.assertIn("⭐ **امتیاز کارفرما:** `4.9/5`", alert_md)

        # Verify Keyboard buttons
        kb = self.radar.create_alert_keyboard(lead)
        self.assertIsNotNone(kb)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("radar:copy:42", callbacks)
        self.assertIn("radar:convert:42", callbacks)
        self.assertIn("radar:reroll:42", callbacks)
        self.assertIn("radar:reject:42", callbacks)
        self.assertIn("radar:bid:42", callbacks)

        # Batch digest
        digest = self.radar.format_batch_digest([lead])
        self.assertIn("گزارش دسته‌ای", digest)
        self.assertIn("توسعه ربات هوش مصنوعی تلگرام", digest)

    def test_karlancer_modern_api_parsing(self):
        sample_api_json = json.dumps({
            "status": "success",
            "data": {
                "id": 1,
                "category_id": None,
                "projects": {
                    "current_page": 1,
                    "data": [
                        {
                            "id": 337220,
                            "title": "تنظیمات سرور برای وردپرس",
                            "description": "راه اندازی سرور لینوکس ابری و کانفیگ وب سرور",
                            "min_budget": 1000000,
                            "max_budget": 4000000,
                            "url": "server-config-wp-2564e",
                            "skills": [{"name": "برنامه نویسی", "id": 1282}, {"name": "سرور لینوکس", "id": 2284}],
                            "country": "تهران",
                            "rate_num": 4.5
                        }
                    ]
                }
            }
        })
        items = self.radar.parse_feed_items(sample_api_json, platform="karlancer")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["title"], "تنظیمات سرور برای وردپرس")
        self.assertEqual(item["budget_min"], 1000000.0)
        self.assertEqual(item["budget_max"], 4000000.0)
        self.assertEqual(item["url"], "https://www.karlancer.com/projects/server-config-wp-2564e")
        self.assertIn("سرور لینوکس", item["category"])
        self.assertEqual(item["employer_name"], "تهران")
        self.assertEqual(item["employer_rating"], 4.5)

    def test_ponisha_modern_nextjs_parsing(self):
        sample_next_html = """
        <!DOCTYPE html><html><head>
        <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "dehydratedState": {
                "queries": [
                  {
                    "queryKey": ["search", "projects"],
                    "state": {
                      "data": {
                        "data": [
                          {
                            "id": "762687",
                            "title": "بررسی امنیتی و رفع آسیب‌پذیری سایت وردپرسی",
                            "slug": "wp-security-fix-762687",
                            "description": "وب‌سایت ما اخیراً هک شده و نیاز به پاکسازی دارد",
                            "amount_min": 6000000,
                            "amount_max": 20000000,
                            "skills": [{"id": "140", "title": "امنیت وب", "slug": "web-security"}]
                          }
                        ]
                      }
                    }
                  }
                ]
              }
            }
          }
        }
        </script>
        </head><body></body></html>
        """
        items = self.radar.parse_feed_items(sample_next_html, platform="ponisha")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["title"], "بررسی امنیتی و رفع آسیب‌پذیری سایت وردپرسی")
        self.assertEqual(item["budget_min"], 6000000.0)
        self.assertEqual(item["budget_max"], 20000000.0)
        self.assertEqual(item["url"], "https://ponisha.ir/project/762687/wp-security-fix-762687")
        self.assertIn("امنیت وب", item["category"])

    def test_telegram_skips_karlancer_and_ponisha(self):
        # 1. Skip Karlancer and Ponisha channels directly
        kl_items = self.radar.parse_telegram_channel_html("<div>some content</div>", "karlancer")
        self.assertEqual(kl_items, [])
        po_items = self.radar.parse_telegram_channel_html("<div>some content</div>", "ponisha_ir")
        self.assertEqual(po_items, [])

        # 2. In any channel, skip posts that mirror/link to karlancer or ponisha
        sample_tg_html = """
        <div data-post="python_jobs_ir/101">
            <div class="tgme_widget_message_text">
                پروژه پایتون در کارلنسر ثبت شد:
                بودجه: ۱۰ میلیون تومان
                <a href="https://www.karlancer.com/projects/sample-proj">لینک کارلنسر</a>
            </div>
        </div>
        <div data-post="python_jobs_ir/102">
            <div class="tgme_widget_message_text">
                پروژه پایتون در پونیشا ثبت شد:
                بودجه: ۱۵ میلیون تومان
                <a href="https://ponisha.ir/project/123/sample">لینک پونیشا</a>
            </div>
        </div>
        <div data-post="python_jobs_ir/103">
            <div class="tgme_widget_message_text">
                نیازمند برنامه‌نویس ارشد پایتون و جنگو برای توسعه وب‌سایت
                بودجه: ۲۰ میلیون تومان
                ارتباط با آیدی: @client_id
            </div>
        </div>
        """
        parsed = self.radar.parse_telegram_channel_html(sample_tg_html, "python_jobs_ir")
        # Should only parse item 103 (the direct telegram project), skipping 101 and 102
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["external_id"], "tg_python_jobs_ir_103")
        self.assertEqual(parsed[0]["url"], "https://t.me/python_jobs_ir/103")


if __name__ == "__main__":
    unittest.main()
