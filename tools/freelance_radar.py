import asyncio
import json
import re
from typing import List, Dict, Any, Optional, Callable, Awaitable
from html import unescape

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    from telethon import TelegramClient, events
    HAS_TELETHON = True
except ImportError:
    HAS_TELETHON = False

from config import settings
from core.router_client import router_client
from tools.vault import vault
from tools.receipt_parser import normalize_digits

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
}


class IranianSplitNetworkClient:
    """
    Phase 3.1: Iranian Split-Network Client.
    Explicitly bypasses system environment proxies/VPNs (`trust_env=False`)
    so requests to Iranian domestic platforms (Ponisha.ir, Karlancer.com) connect
    directly without triggering VPN blocks or Cloudflare challenges.
    """

    def create_session(self, timeout_seconds: int = 20) -> "aiohttp.ClientSession":
        if aiohttp is None:
            raise RuntimeError("aiohttp is required for IranianSplitNetworkClient")
        connector = aiohttp.TCPConnector(ssl=False, limit=10)
        return aiohttp.ClientSession(
            connector=connector,
            headers=BROWSER_HEADERS,
            trust_env=False,  # CRITICAL: Ignores HTTP_PROXY / HTTPS_PROXY / ALL_PROXY VPN settings
            timeout=aiohttp.ClientTimeout(total=timeout_seconds)
        )

    async def fetch_text(self, url: str) -> str:
        async with self.create_session() as session:
            async with session.get(url, proxy=None) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Direct HTTP {resp.status} from {url}")
                return await resp.text()

    async def fetch_json(self, url: str) -> Any:
        async with self.create_session() as session:
            async with session.get(url, proxy=None) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Direct HTTP {resp.status} from {url}")
                return await resp.json()


class LeadMatchmaker:
    """
    Phase 3.4: AI Lead Matchmaker & Proposal Generator.
    Evaluates freelance projects against Arush's portfolio profile, calculates a match score (0-100),
    suggests bid & timeline, and drafts a tailored Persian proposal.
    """

    def score_and_draft_SyncFallback(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic portfolio matcher & Persian proposal generator."""
        title = lead.get("title", "")
        desc = lead.get("description", "")
        cat = lead.get("category", "")
        combined = f"{title} {desc} {cat}".lower()

        # Check spam / low-quality indicators
        spam_keywords = ["تایپ ساده", "کپچا", "ورود اطلاعات دستی", "ادمین اینستاگرام ساده", "بدون بودجه"]
        if any(sk in combined for sk in spam_keywords):
            return {
                "match_score": 15,
                "suggested_bid": "رد شده (Spam/Low Value)",
                "suggested_timeline": "-",
                "proposal_draft": ""
            }

        high_value_keywords = {
            "python": 25, "پایتون": 25,
            "bot": 22, "ربات": 22, "بات": 22, "تلگرام": 20, "telegram": 20, "aiogram": 20,
            "ai": 25, "هوش مصنوعی": 25, "llm": 25, "gpt": 22, "claude": 22, "ایجنت": 25, "agent": 25,
            "scrape": 20, "scraping": 20, "اسکرپ": 20, "خزنده": 20, "playwright": 20, "سلنیوم": 18,
            "fastapi": 18, "django": 18, "جنگو": 18, "api": 15,
            "react": 18, "ری‌اکت": 18, "داشبورد": 15, "dashboard": 15,
            "docker": 12, "اتوماسیون": 18, "automation": 18
        }

        score = 40
        matched_skills: List[str] = []
        for kw, weight in high_value_keywords.items():
            if kw in combined:
                score += weight
                matched_skills.append(kw)

        budget_max = float(lead.get("budget_max") or lead.get("budget_min") or 0.0)
        if budget_max >= settings.RADAR_MIN_BUDGET_TOMAN:
            score += 10
        elif 0 < budget_max < settings.RADAR_MIN_BUDGET_TOMAN:
            score -= 25

        employer_rating = float(lead.get("employer_rating") or 0.0)
        if employer_rating >= 4.5:
            score += 5

        final_score = max(5, min(98, score))

        # Calculate suggested bid & timeline
        if budget_max > 0:
            suggested_num = int(budget_max * 0.9)
            suggested_bid = f"{suggested_num:,} تومان"
        else:
            suggested_bid = "۸,۵۰۰,۰۰۰ تومان (پیشنهادی بر اساس اسکوپ)"

        suggested_timeline = "۵ تا ۷ روز کاری" if budget_max < 15_000_000 else "۱۰ تا ۱۴ روز کاری"
        skills_str = "، ".join(matched_skills[:4]) if matched_skills else "پایتون، معماری نرم‌افزار و هوش مصنوعی"

        proposal_draft = (
            f"سلام و وقت بخیر؛\n"
            f"توضیحات پروژه «{title}» را با دقت بررسی کردم. با توجه به تجربه تخصصی من در پیاده‌سازی پروژه‌های مشابه "
            f"با استفاده از ({skills_str})، می‌توانم این سیستم را با معماری ماژولار، کدنویسی تمیز و سرعت بالا پیاده‌سازی کنم.\n\n"
            f"✅ ویژگی‌های تحویلی در این پروژه:\n"
            f"• پیاده‌سازی کامل و بهینه همراه با داکر (Docker) و مستندات فنی\n"
            f"• مدیریت خطا، امنیت بالا و تست کامل پیش از تحویل نهایی\n"
            f"• پشتیبانی کامل پس از تحویل جهت اطمینان از پایداری سیستم\n\n"
            f"💰 مبلغ پیشنهادی: {suggested_bid}\n"
            f"⏱️ زمان تحویل: {suggested_timeline}\n"
            f"در صورت تمایل، آماده گفتگو درباره جزئیات فنی و شروع فوری پروژه هستم."
        )

        return {
            "match_score": final_score,
            "suggested_bid": suggested_bid,
            "suggested_timeline": suggested_timeline,
            "proposal_draft": proposal_draft
        }

    async def evaluate_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates a lead via 9Router LLM if available, falling back to deterministic scoring."""
        fallback = self.score_and_draft_SyncFallback(lead)
        prompt = (
            f"Evaluate this freelance project against Arush's portfolio.\n"
            f"Portfolio: {settings.PORTFOLIO_SUMMARY}\n"
            f"Min Budget: {settings.RADAR_MIN_BUDGET_TOMAN:,.0f} Toman\n\n"
            f"Project Title: {lead.get('title')}\n"
            f"Description: {lead.get('description')}\n"
            f"Category: {lead.get('category')}\n"
            f"Budget: {lead.get('budget_min')} - {lead.get('budget_max')} {lead.get('currency', 'Toman')}\n"
            f"Employer Rating: {lead.get('employer_rating', 'N/A')}\n\n"
            f"Return JSON with keys: match_score (0-100 int), suggested_bid (str in Persian), "
            f"suggested_timeline (str in Persian), proposal_draft (winning Persian proposal)."
        )
        try:
            raw = await router_client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are an elite freelance proposal strategist. Respond only in valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "match_score" in parsed:
                return {
                    "match_score": int(parsed.get("match_score", fallback["match_score"])),
                    "suggested_bid": parsed.get("suggested_bid") or fallback["suggested_bid"],
                    "suggested_timeline": parsed.get("suggested_timeline") or fallback["suggested_timeline"],
                    "proposal_draft": parsed.get("proposal_draft") or fallback["proposal_draft"]
                }
        except Exception:
            pass

        return fallback


class FreelanceRadar:
    """
    Phase 3: Complete Freelance Radar covering:
    - 3.1 Iranian Split-Network Client (.ir direct without VPN)
    - 3.2 Karlancer & Ponisha Project Feed Scraper (10-min background poller + category/budget filters)
    - 3.3 Telegram Freelance Channel Monitor (Telethon + public web preview parser)
    - 3.4 AI Lead Matchmaker & Proposal Generator (instant Telegram alerts with one-click bid link)
    """

    def __init__(self):
        self.net = IranianSplitNetworkClient()
        self.matchmaker = LeadMatchmaker()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def filter_lead(self, lead: Dict[str, Any]) -> bool:
        """
        Filters leads by configured categories (`settings.RADAR_CATEGORIES`)
        and minimum budget (`settings.RADAR_MIN_BUDGET_TOMAN`).
        """
        text = f"{lead.get('title', '')} {lead.get('description', '')} {lead.get('category', '')}".lower()
        categories = [c.lower() for c in settings.RADAR_CATEGORIES]
        persian_equivalents = [
            "پایتون", "ری اکت", "ربات", "بات", "تلگرام", "هوش مصنوعی",
            "اسکرپ", "خزنده", "وب", "جنگو", "اتوماسیون", "ای پی آی"
        ]
        category_match = any(c in text for c in categories) or any(p in text for p in persian_equivalents)
        if not category_match:
            return False

        budget_max = float(lead.get("budget_max") or lead.get("budget_min") or 0.0)
        # If budget is specified (> 0), enforce minimum budget filter
        if budget_max > 0 and budget_max < settings.RADAR_MIN_BUDGET_TOMAN:
            return False

        return True

    def parse_feed_items(self, raw_html_or_json: str, platform: str) -> List[Dict[str, Any]]:
        """Parses either JSON API payload or HTML/RSS project cards from Karlancer or Ponisha."""
        leads: List[Dict[str, Any]] = []
        content = raw_html_or_json.strip()
        if not content:
            return leads

        # Try JSON API format first (e.g. Karlancer API / Ponisha JSON)
        if content.startswith("{") or content.startswith("["):
            try:
                data = json.loads(content)
                items = data if isinstance(data, list) else data.get("data") or data.get("projects") or data.get("items") or []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    pid = str(item.get("id") or item.get("slug") or item.get("url") or "")
                    if not pid:
                        continue
                    title = str(item.get("title") or item.get("name") or "")
                    desc = str(item.get("description") or item.get("summary") or "")
                    b_min = float(item.get("min_budget") or item.get("budget_min") or item.get("amount") or 0.0)
                    b_max = float(item.get("max_budget") or item.get("budget_max") or b_min)
                    emp_rating = float(item.get("employer_rating") or item.get("client_rating") or 4.5)
                    url = str(item.get("url") or (
                        f"https://www.karlancer.com/projects/{pid}" if platform == "karlancer"
                        else f"https://ponisha.ir/project/{pid}"
                    ))
                    leads.append({
                        "external_id": f"{platform}_{pid}",
                        "platform": platform,
                        "title": title,
                        "description": desc,
                        "category": str(item.get("category") or "software"),
                        "budget_min": b_min,
                        "budget_max": b_max,
                        "currency": "Toman",
                        "employer_name": str(item.get("employer_name") or "کارفرما"),
                        "employer_rating": emp_rating,
                        "url": url
                    })
                return leads
            except Exception:
                pass

        # Fallback: Parse RSS `<item>` blocks or HTML project anchors
        rss_items = re.findall(r"<item>(.*?)</item>", content, re.DOTALL | re.IGNORECASE)
        for idx, block in enumerate(rss_items):
            t_match = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", block, re.DOTALL)
            l_match = re.search(r"<link>(.*?)</link>", block, re.DOTALL)
            d_match = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>", block, re.DOTALL)
            title = unescape((t_match.group(1) or t_match.group(2) or "").strip()) if t_match else f"Project {idx}"
            link = (l_match.group(1).strip() if l_match else f"https://{platform}.ir/project/{idx}")
            desc = unescape((d_match.group(1) or d_match.group(2) or "").strip()) if d_match else ""
            clean_desc = re.sub(r"<[^>]+>", " ", desc).strip()

            # Extract budget from text if present
            norm_desc = normalize_digits(f"{title} {clean_desc}")
            b_match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+)\s*تومان", norm_desc)
            budget = float(b_match.group(1).replace(",", "")) if b_match else 0.0

            leads.append({
                "external_id": f"{platform}_{ abs(hash(link)) }",
                "platform": platform,
                "title": title,
                "description": clean_desc[:1000],
                "category": "development",
                "budget_min": budget,
                "budget_max": budget,
                "currency": "Toman",
                "employer_name": "کارفرما",
                "employer_rating": 4.5,
                "url": link
            })

        return leads

    def parse_telegram_channel_html(self, html: str, channel_name: str) -> List[Dict[str, Any]]:
        """Phase 3.3: Parses public Telegram channel web preview (`https://t.me/s/<channel>`) for job posts."""
        leads: List[Dict[str, Any]] = []
        blocks = re.findall(
            r'data-post="([^"]+)"[^>]*>.*?<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            html,
            re.DOTALL
        )
        for post_id, raw_msg in blocks:
            clean_text = unescape(re.sub(r"<[^>]+>", "\n", raw_msg)).strip()
            if len(clean_text) < 25:
                continue
            lines = [ln.strip() for ln in clean_text.splitlines() if ln.strip()]
            title = lines[0][:100] if lines else f"Telegram Job {post_id}"
            norm = normalize_digits(clean_text)
            b_match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+)\s*تومان", norm)
            budget = float(b_match.group(1).replace(",", "")) if b_match else 0.0
            leads.append({
                "external_id": f"tg_{post_id.replace('/', '_')}",
                "platform": f"telegram:@{channel_name}",
                "title": title,
                "description": clean_text[:1200],
                "category": "telegram_channel",
                "budget_min": budget,
                "budget_max": budget,
                "currency": "Toman",
                "employer_name": f"@{channel_name}",
                "employer_rating": 4.6,
                "url": f"https://t.me/{post_id}"
            })
        return leads

    async def poll_sources_once(self) -> List[Dict[str, Any]]:
        """Polls Karlancer, Ponisha, and configured Telegram freelance channels once."""
        discovered: List[Dict[str, Any]] = []
        sources = [
            ("karlancer", "https://www.karlancer.com/api/public/projects?page=1"),
            ("ponisha", "https://ponisha.ir/search/projects/feed"),
        ]
        for platform, url in sources:
            try:
                raw = await self.net.fetch_text(url)
                items = self.parse_feed_items(raw, platform=platform)
                discovered.extend(items)
            except Exception:
                pass

        for channel in settings.TELEGRAM_FREELANCE_CHANNELS:
            try:
                # Public t.me/s/ preview works without Telethon session login
                async with aiohttp.ClientSession(headers=BROWSER_HEADERS) as session:
                    async with session.get(
                        f"https://t.me/s/{channel.lstrip('@')}",
                        proxy=settings.TELEGRAM_PROXY,
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            discovered.extend(self.parse_telegram_channel_html(html, channel.lstrip("@")))
            except Exception:
                pass

        qualified_alerts: List[Dict[str, Any]] = []
        for raw_lead in discovered:
            if not self.filter_lead(raw_lead):
                continue
            eval_res = await self.matchmaker.evaluate_lead(raw_lead)
            raw_lead.update(eval_res)
            saved = vault.save_freelance_lead(raw_lead)
            if saved.get("is_new") and saved.get("match_score", 0) >= settings.RADAR_MATCH_THRESHOLD:
                qualified_alerts.append(saved)

        return qualified_alerts

    async def process_custom_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates and stores a single project lead (used by tests, manual `/radar`, or Telethon listener)."""
        eval_res = await self.matchmaker.evaluate_lead(lead_data)
        merged = {**lead_data, **eval_res}
        saved = vault.save_freelance_lead(merged)
        return saved

    def format_telegram_alert(self, lead: Dict[str, Any]) -> str:
        """Formats a high-match freelance lead alert with Persian proposal and employer details."""
        b_min = float(lead.get("budget_min") or 0)
        b_max = float(lead.get("budget_max") or 0)
        budget_str = f"{b_min:,.0f} تا {b_max:,.0f} تومان" if b_max > b_min else (
            f"{b_max:,.0f} تومان" if b_max > 0 else "توافقی"
        )
        return (
            f"🎯 **پروژه جدید فریلنسری (تطابق: {lead.get('match_score', 0)}٪)**\n\n"
            f"📌 **عنوان:** {lead.get('title')}\n"
            f"🌐 **پلتفرم:** `{lead.get('platform')}` | ⭐ **امتیاز کارفرما:** `{lead.get('employer_rating', 4.5)}/5`\n"
            f"💰 **بودجه کارفرما:** {budget_str}\n"
            f"💵 **پیشنهاد قیمت بهینه:** {lead.get('suggested_bid')}\n"
            f"⏱️ **زمان تحویل پیشنهادی:** {lead.get('suggested_timeline')}\n\n"
            f"📝 **متن پروپوزال آماده ارسال:**\n"
            f"```\n{lead.get('proposal_draft')}\n```\n\n"
            f"🔗 [ثبت فوری پیشنهاد در سایت]({lead.get('url', 'https://ponisha.ir')})"
        )

    async def start_background_poller(
        self,
        on_high_match: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    ) -> None:
        """Starts the periodic 10-minute background poller and optional Telethon listener."""
        self._running = True
        while self._running:
            try:
                alerts = await self.poll_sources_once()
                if on_high_match:
                    for lead in alerts:
                        await on_high_match(lead)
            except Exception:
                pass
            await asyncio.sleep(settings.RADAR_POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()


freelance_radar = FreelanceRadar()
