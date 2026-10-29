import asyncio
import json
import re
from typing import List, Dict, Any, Optional, Callable, Awaitable
from html import unescape

try:
    import aiohttp
except ImportError:
    aiohttp = None

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

# Promotional / blog / magazine patterns that must NEVER be treated as freelance job leads
NON_PROJECT_PATTERNS = [
    r"چیست\s*[؟?]",
    r"چگونه\s+.*[؟?]",
    r"چطور\s+.*[؟?]",
    r"\bوبینار\b",
    r"\bآموزش\b",
    r"\bمقاله\b",
    r"\bخبرنامه\b",
    r"\bپادکست\b",
    r"\bکد\s*تخفیف\b",
    r"\bجشنواره\b",
    r"غول\s*تازه\s*نفس",
]

# Explicit indicators that a Telegram post is actually a freelance project / job listing
PROJECT_INTENT_INDICATORS = [
    r"بودجه",
    r"پروژه",
    r"نیازمند",
    r"استخدام",
    r"فریلنسر",
    r"کارفرما",
    r"ثبت\s*پیشنهاد",
    r"مهارت",
    r"تومان",
    r"ریال",
    r"سفارش",
    r"طراحی\s+و\s+پیاده",
    r"توسعه\s*دهنده",
]

# Word-boundary / whole-token skill patterns with realistic weights
SKILL_PATTERNS = {
    "Python": (r"(?<![a-zA-Z])python(?![a-zA-Z])|پایتون", 22),
    "Telegram Bot": (r"ربات\s*تلگرام|بات\s*تلگرام|telegram\s*bot|(?<![a-zA-Z])aiogram(?![a-zA-Z])|(?<![a-zA-Z])telethon(?![a-zA-Z])", 25),
    "AI / LLM": (r"هوش\s*مصنوعی|(?<![a-zA-Z])(?:ai|llm|gpt|claude|openai|rag|langchain)(?![a-zA-Z])|ایجنت", 22),
    "Web Scraping": (r"(?<![a-zA-Z])(?:scraping|scraper|playwright|selenium|crawler)(?![a-zA-Z])|اسکرپ|خزنده|وب\s*اسکرپینگ", 20),
    "Backend API": (r"(?<![a-zA-Z])(?:fastapi|django|flask|rest\s*api|backend)(?![a-zA-Z])|جنگو|بک‌اند|بک\s*اند", 18),
    "React / Frontend": (r"(?<![a-zA-Z])(?:react|nextjs|next\.js|typescript|dashboard)(?![a-zA-Z])|ری‌اکت|ری\s*اکت|داشبورد", 16),
    "Automation / Docker": (r"(?<![a-zA-Z])(?:docker|automation|n8n)(?![a-zA-Z])|اتوماسیون|داکر", 14),
}


def clean_html_preserving_inline(raw_html: str) -> str:
    """
    Replaces `<br>` and block-closing tags with newlines, but strips inline tags
    (`<b>`, `<strong>`, `<i>`, `<a>`, `<span>`) WITHOUT injecting newlines mid-sentence
    so leading emojis like `🔴 <b>عنوان پروژه</b>` stay on the same line.
    """
    text = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|div|li|tr|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def extract_meaningful_title(lines: List[str], fallback: str = "پروژه فریلنسری") -> str:
    """
    Skips lines that consist only of emojis, punctuation, or generic headers
    (like `🔴` or `📢 پروژه جدید:`) and extracts the real project title.
    """
    for line in lines:
        # Strip leading emojis, bullets, and symbols
        cleaned = re.sub(r"^[^\w\u0600-\u06FF]+", "", line).strip()
        # Strip common prefixes like "عنوان پروژه:" or "پروژه:"
        cleaned = re.sub(r"^(?:عنوان\s*پروژه|عنوان|نام\s*پروژه|پروژه\s*جدید)[\s:：\-]+", "", cleaned).strip()
        # Require at least 4 alphanumeric/Persian characters
        alnum_count = len(re.findall(r"[\w\u0600-\u06FF]", cleaned))
        if alnum_count >= 4:
            return cleaned[:110]
    return fallback


class IranianSplitNetworkClient:
    """
    Phase 3.1: Iranian Split-Network Client.
    Explicitly bypasses system environment proxies/VPNs (`trust_env=False`).
    """

    def create_session(self, timeout_seconds: int = 20) -> "aiohttp.ClientSession":
        if aiohttp is None:
            raise RuntimeError("aiohttp is required for IranianSplitNetworkClient")
        connector = aiohttp.TCPConnector(ssl=False, limit=10)
        return aiohttp.ClientSession(
            connector=connector,
            headers=BROWSER_HEADERS,
            trust_env=False,
            timeout=aiohttp.ClientTimeout(total=timeout_seconds)
        )

    async def fetch_text(self, url: str) -> str:
        async with self.create_session() as session:
            async with session.get(url, proxy=None) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Direct HTTP {resp.status} from {url}")
                return await resp.text()


class LeadMatchmaker:
    """
    Phase 3.4: AI Lead Matchmaker & Proposal Generator.
    Uses strict whole-word skill matching, rejects blog/promotional posts,
    and extracts embedded JSON from 9Router LLM responses reliably.
    """

    def score_and_draft_SyncFallback(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        title = lead.get("title", "")
        desc = lead.get("description", "")
        # NOTE: Do NOT include `category` or `platform` in text matching,
        # otherwise `telegram_channel` triggers false "telegram" skill matches!
        combined = f"{title}\n{desc}".lower()

        # 1. Reject blog posts, tutorials, and low-value spam
        spam_keywords = ["تایپ ساده", "کپچا", "ورود اطلاعات دستی", "ادمین اینستاگرام ساده", "بدون بودجه"]
        if any(sk in combined for sk in spam_keywords) or any(
            re.search(pat, combined, re.IGNORECASE) for pat in NON_PROJECT_PATTERNS
        ):
            return {
                "match_score": 0,
                "suggested_bid": "رد شده (محتوای غیرپروژه‌ای / آموزشی)",
                "suggested_timeline": "-",
                "proposal_draft": ""
            }

        # 2. Match skills using word boundaries (no substring false positives)
        score = 25  # Conservative base score
        matched_skills: List[str] = []
        for skill_label, (pattern, weight) in SKILL_PATTERNS.items():
            if re.search(pattern, combined, re.IGNORECASE):
                score += weight
                matched_skills.append(skill_label)

        if not matched_skills:
            return {
                "match_score": 20,
                "suggested_bid": "خارج از حوزه تخصصی",
                "suggested_timeline": "-",
                "proposal_draft": ""
            }

        # 3. Budget evaluation
        budget_max = float(lead.get("budget_max") or lead.get("budget_min") or 0.0)
        if budget_max >= settings.RADAR_MIN_BUDGET_TOMAN * 3:
            score += 12
        elif budget_max >= settings.RADAR_MIN_BUDGET_TOMAN:
            score += 6
        elif 0 < budget_max < settings.RADAR_MIN_BUDGET_TOMAN:
            score -= 30

        final_score = max(5, min(96, score))

        if budget_max > 0:
            suggested_num = int(budget_max * 0.9)
            suggested_bid = f"{suggested_num:,} تومان"
        else:
            suggested_bid = "توافقی (پس از بررسی دقیق نیازمندی‌ها)"

        suggested_timeline = "۵ تا ۷ روز کاری" if (0 < budget_max < 12_000_000) else "۷ تا ۱۲ روز کاری"
        skills_str = "، ".join(matched_skills[:4])

        proposal_draft = (
            f"سلام و وقت بخیر؛\n"
            f"توضیحات پروژه «{title}» را بررسی کردم. با توجه به تمرکز تخصصی من در زمینه ({skills_str})، "
            f"می‌توانم نیازمندی‌های این پروژه را با کدنویسی تمیز، معماری ماژولار و پایداری بالا پیاده‌سازی کنم.\n\n"
            f"✅ تعهدات اجرایی در این پروژه:\n"
            f"• پیاده‌سازی دقیق مطابق با نیازمندی‌ها همراه با تست کامل و مستندات\n"
            f"• تحویل مرحله‌ای و شفاف همراه با پشتیبانی پس از تحویل\n\n"
            f"💰 پیشنهاد قیمت: {suggested_bid}\n"
            f"⏱️ زمان‌بندی تحویل: {suggested_timeline}\n"
            f"خوشحال می‌شوم درباره جزئیات فنی پروژه گفتگو کنیم."
        )

        return {
            "match_score": final_score,
            "suggested_bid": suggested_bid,
            "suggested_timeline": suggested_timeline,
            "proposal_draft": proposal_draft
        }

    async def evaluate_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        fallback = self.score_and_draft_SyncFallback(lead)
        if fallback["match_score"] == 0:
            return fallback

        prompt = (
            f"Evaluate whether this post is a real software/AI freelance project and score its fit for Arush.\n"
            f"Portfolio: {settings.PORTFOLIO_SUMMARY}\n"
            f"Min Budget: {settings.RADAR_MIN_BUDGET_TOMAN:,.0f} Toman\n\n"
            f"Title: {lead.get('title')}\n"
            f"Description: {lead.get('description')}\n"
            f"Budget: {lead.get('budget_min')} - {lead.get('budget_max')} {lead.get('currency', 'Toman')}\n\n"
            f"If this is a blog post, news article, tutorial, or advertisement (not a real client job), "
            f"set is_real_project=false and match_score=0.\n"
            f"Return ONLY a JSON object with keys: is_real_project (bool), match_score (0-100 int), "
            f"suggested_bid (str in Persian), suggested_timeline (str in Persian), proposal_draft (Persian proposal)."
        )
        try:
            raw = await router_client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a strict freelance lead qualifier. Output valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            # Robustly extract first JSON object even if wrapped in prose or markdown fences
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                if isinstance(parsed, dict):
                    if parsed.get("is_real_project") is False:
                        return {
                            "match_score": 0,
                            "suggested_bid": "رد شده (پست غیرپروژه‌ای)",
                            "suggested_timeline": "-",
                            "proposal_draft": ""
                        }
                    if "match_score" in parsed:
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
    Phase 3: Complete Freelance Radar with strict project-intent validation,
    emoji-safe HTML title extraction, and word-boundary skill matching.
    """

    def __init__(self):
        self.net = IranianSplitNetworkClient()
        self.matchmaker = LeadMatchmaker()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def is_real_project_post(self, title: str, description: str, platform: str = "") -> bool:
        """
        Ensures a scraped post (especially from Telegram channels) is an actual freelance job listing
        and NOT a blog article, educational post, or promotional announcement.
        """
        combined = f"{title}\n{description}".strip()
        if len(combined) < 25:
            return False

        # Reject explicit blog/question/tutorial headlines
        if any(re.search(pat, combined, re.IGNORECASE) for pat in NON_PROJECT_PATTERNS):
            return False

        # For Telegram channels, require at least 2 explicit job/project indicators (or budget + 1 indicator)
        if platform.startswith("telegram:"):
            hits = sum(1 for pat in PROJECT_INTENT_INDICATORS if re.search(pat, combined, re.IGNORECASE))
            if hits < 2:
                return False

        return True

    def filter_lead_fallback(self, lead: Dict[str, Any]) -> bool:
        """
        Emergency regex fallback when System 1 is offline or unreachable:
        1. Real project intent (rejecting blog/magazine posts)
        2. Whole-word technical skill match (`SKILL_PATTERNS`)
        3. Minimum budget threshold (`settings.RADAR_MIN_BUDGET_TOMAN`)
        """
        title = lead.get("title", "")
        desc = lead.get("description", "")
        platform = lead.get("platform", "")

        if not self.is_real_project_post(title, desc, platform=platform):
            return False

        text = f"{title}\n{desc}".lower()
        has_skill_match = any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern, _ in SKILL_PATTERNS.values()
        )
        if not has_skill_match:
            return False

        budget_max = float(lead.get("budget_max") or lead.get("budget_min") or 0.0)
        if budget_max > 0 and budget_max < settings.RADAR_MIN_BUDGET_TOMAN:
            return False

        return True

    def filter_lead(self, lead: Dict[str, Any]) -> bool:
        """Backwards compatibility wrapper for single-lead synchronous screening."""
        return self.filter_lead_fallback(lead)

    async def batch_filter_leads_system_one(
        self,
        leads: List[Dict[str, Any]],
        batch_size: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Intelligently screens and detects job leads in batches of up to 20 using
        the System 1 AI model (oc/jev-1.13-free via /v1/systemone).
        Evaluates atomic questions (is_job and matches_stack) in parallel and
        composes decision logic in Python code.
        Gracefully falls back to local regex screening if System 1 is unavailable.
        """
        if not leads:
            return []

        resolved_batch_size = batch_size or getattr(settings, "RADAR_SYSTEM_ONE_BATCH_SIZE", 20)
        threshold = getattr(settings, "RADAR_SYSTEM_ONE_THRESHOLD", 0.55)
        accepted_leads: List[Dict[str, Any]] = []

        for i in range(0, len(leads), resolved_batch_size):
            chunk = leads[i : i + resolved_batch_size]

            # Format state as structured JSON array
            state_data = []
            questions = {}

            for idx, lead in enumerate(chunk, start=1):
                clean_title = (lead.get("title") or "").strip()
                clean_desc = (lead.get("description") or "").strip()[:400].replace("\n", " ")
                platform = lead.get("platform", "unknown")
                b_min = float(lead.get("budget_min") or 0.0)
                b_max = float(lead.get("budget_max") or 0.0)
                budget_str = f"{b_min:,.0f}-{b_max:,.0f} Toman" if b_max > 0 else "negotiable"

                state_data.append({
                    "id": idx,
                    "platform": platform,
                    "title": clean_title,
                    "text": clean_desc,
                    "budget": budget_str
                })

                questions[f"is_job_{idx}"] = {
                    "type": "noul",
                    "instructions": (
                        f"Is item {idx} an actual freelance project request, contract gig, or developer job vacancy "
                        f"(not an educational tutorial, blog article, webinar, news, general chat, commercial advertisement, or scam)?"
                    ),
                    "criteria": {
                        "true": "A real client project order, freelance contract work, software gig, or developer job vacancy",
                        "false": "An educational tutorial, blog article, news, general chat, server/domain advertisement, or non-work post"
                    }
                }
                questions[f"matches_stack_{idx}"] = {
                    "type": "noul",
                    "instructions": (
                        f"Does item {idx} match software development in Python, Telegram bots, AI agents/LLMs, "
                        f"web scraping, backend APIs (FastAPI/Django), or web automation?"
                    )
                }

            try:
                answers = await router_client.system_one(
                    state=state_data,
                    questions=questions,
                    model=getattr(settings, "SYSTEM_ONE_MODEL", "oc/jev-1.13-free"),
                    timeout_seconds=40
                )

                for idx, lead in enumerate(chunk, start=1):
                    is_job_prob = float(answers.get(f"is_job_{idx}", {}).get("noul", 0.0))
                    stack_prob = float(answers.get(f"matches_stack_{idx}", {}).get("noul", 0.0))

                    lead["system_one_is_job"] = is_job_prob
                    lead["system_one_stack_fit"] = stack_prob

                    # Budget constraint check
                    b_max = float(lead.get("budget_max") or lead.get("budget_min") or 0.0)
                    budget_ok = (b_max == 0.0 or b_max >= settings.RADAR_MIN_BUDGET_TOMAN)

                    # Atomic questions composed in code:
                    if is_job_prob >= threshold and stack_prob >= threshold and budget_ok:
                        composite_score = int((is_job_prob * 0.4 + stack_prob * 0.6) * 100)
                        lead["match_score"] = composite_score
                        accepted_leads.append(lead)
            except Exception:
                # Emergency fallback to regex screening if System 1 API is unreachable
                for lead in chunk:
                    if self.filter_lead_fallback(lead):
                        lead["system_one_fallback"] = True
                        accepted_leads.append(lead)

        return accepted_leads

    def parse_feed_items(self, raw_html_or_json: str, platform: str) -> List[Dict[str, Any]]:
        """Parses either JSON API payload or HTML/RSS project cards from Karlancer or Ponisha."""
        leads: List[Dict[str, Any]] = []
        content = raw_html_or_json.strip()
        if not content:
            return leads

        if content.startswith("{") or content.startswith("["):
            try:
                data = json.loads(content)
                items = data if isinstance(data, list) else (
                    data.get("data") or data.get("projects") or data.get("items") or []
                )
                if isinstance(items, dict) and "data" in items:
                    items = items["data"]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    pid = str(item.get("id") or item.get("slug") or item.get("url") or "")
                    if not pid:
                        continue
                    raw_title = str(item.get("title") or item.get("name") or "")
                    title = extract_meaningful_title([raw_title], fallback=f"Project {pid}")
                    desc = str(item.get("description") or item.get("summary") or "")
                    b_min = float(item.get("min_budget") or item.get("budget_min") or item.get("amount") or 0.0)
                    b_max = float(item.get("max_budget") or item.get("budget_max") or b_min)
                    emp_rating = item.get("employer_rating") or item.get("client_rating")
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
                        "employer_rating": float(emp_rating) if emp_rating is not None else 0.0,
                        "url": url
                    })
                return leads
            except Exception:
                pass

        rss_items = re.findall(r"<item>(.*?)</item>", content, re.DOTALL | re.IGNORECASE)
        for idx, block in enumerate(rss_items):
            t_match = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", block, re.DOTALL)
            l_match = re.search(r"<link>(.*?)</link>", block, re.DOTALL)
            d_match = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>", block, re.DOTALL)
            raw_title = unescape((t_match.group(1) or t_match.group(2) or "").strip()) if t_match else f"Project {idx}"
            title = extract_meaningful_title([raw_title], fallback=f"Project {idx}")
            link = (l_match.group(1).strip() if l_match else f"https://{platform}.ir/project/{idx}")
            desc = unescape((d_match.group(1) or d_match.group(2) or "").strip()) if d_match else ""
            clean_desc = clean_html_preserving_inline(desc)

            norm_desc = normalize_digits(f"{title} {clean_desc}")
            b_match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+)\s*تومان", norm_desc)
            budget = float(b_match.group(1).replace(",", "")) if b_match else 0.0

            leads.append({
                "external_id": f"{platform}_{abs(hash(link))}",
                "platform": platform,
                "title": title,
                "description": clean_desc[:1000],
                "category": "development",
                "budget_min": budget,
                "budget_max": budget,
                "currency": "Toman",
                "employer_name": "کارفرما",
                "employer_rating": 0.0,
                "url": link
            })

        return leads

    def parse_telegram_channel_html(self, html: str, channel_name: str) -> List[Dict[str, Any]]:
        """
        Phase 3.3: Parses public Telegram channel web preview (`https://t.me/s/<channel>`).
        Fixes:
        - Preserves inline tags (`<b>`, `<a>`) on the same line so `🔴 <b>عنوان</b>` is not split into `🔴`.
        - Uses `extract_meaningful_title` to skip emoji-only lines.
        - Extracts external Ponisha/Karlancer project URLs when embedded in the Telegram post.
        """
        leads: List[Dict[str, Any]] = []
        blocks = re.findall(
            r'data-post="([^"]+)"[^>]*>.*?<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            html,
            re.DOTALL
        )
        for post_id, raw_msg in blocks:
            clean_text = clean_html_preserving_inline(raw_msg)
            if len(clean_text) < 25:
                continue

            lines = [ln.strip() for ln in clean_text.splitlines() if ln.strip()]
            title = extract_meaningful_title(lines, fallback=f"پروژه تلگرام ({channel_name})")

            # Extract budget in Toman or Rial
            norm = normalize_digits(clean_text)
            budget = 0.0
            b_match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+)\s*(تومان|تومن|ریال)", norm)
            if b_match:
                val = float(b_match.group(1).replace(",", ""))
                budget = val / 10.0 if b_match.group(2) == "ریال" else val

            # Prefer direct link to Ponisha/Karlancer project page if present in href
            href_match = re.search(
                r'href="(https?://(?:www\.)?(?:ponisha\.ir|karlancer\.com)/[^\s"]+)"',
                raw_msg,
                re.IGNORECASE
            )
            target_url = href_match.group(1) if href_match else f"https://t.me/{post_id}"

            leads.append({
                "external_id": f"tg_{post_id.replace('/', '_')}",
                "platform": f"telegram:@{channel_name}",
                "title": title,
                "description": clean_text[:1200],
                "category": "freelance",
                "budget_min": budget,
                "budget_max": budget,
                "currency": "Toman",
                "employer_name": f"@{channel_name}",
                "employer_rating": 0.0,
                "url": target_url
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

        # 1. Deduplicate: Ignore leads already recorded in vault
        unseen_leads = vault.filter_unseen_leads(discovered)
        if not unseen_leads:
            return []

        # 2. Batch screen with System 1 AI (oc/jev-1.13-free via /v1/systemone)
        screened_leads = await self.batch_filter_leads_system_one(unseen_leads)

        # 3. For qualified leads, generate proposal & pricing using System 2 (chat completion)
        qualified_alerts: List[Dict[str, Any]] = []
        for raw_lead in screened_leads:
            eval_res = await self.matchmaker.evaluate_lead(raw_lead)
            final_score = int(eval_res.get("match_score") or raw_lead.get("match_score", 0))
            raw_lead.update(eval_res)
            raw_lead["match_score"] = final_score

            saved = vault.save_freelance_lead(raw_lead)
            if saved.get("is_new") and final_score >= settings.RADAR_MATCH_THRESHOLD:
                qualified_alerts.append(saved)

        return qualified_alerts

    async def process_custom_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        screened = await self.batch_filter_leads_system_one([lead_data])
        if screened:
            lead_data = screened[0]
        eval_res = await self.matchmaker.evaluate_lead(lead_data)
        merged = {**lead_data, **eval_res}
        saved = vault.save_freelance_lead(merged)
        return saved

    def format_telegram_alert(self, lead: Dict[str, Any]) -> str:
        b_min = float(lead.get("budget_min") or 0)
        b_max = float(lead.get("budget_max") or 0)
        budget_str = f"{b_min:,.0f} تا {b_max:,.0f} تومان" if b_max > b_min else (
            f"{b_max:,.0f} تومان" if b_max > 0 else "توافقی"
        )
        rating = float(lead.get("employer_rating") or 0.0)
        rating_str = f" | ⭐ **امتیاز کارفرما:** `{rating}/5`" if rating > 0 else ""
        url = lead.get("url") or "https://ponisha.ir"
        link_label = "مشاهده پست در تلگرام" if "t.me/" in url else "ثبت فوری پیشنهاد در سایت"

        sys1_info = ""
        if "system_one_is_job" in lead and "system_one_stack_fit" in lead:
            j_pct = int(lead["system_one_is_job"] * 100)
            f_pct = int(lead["system_one_stack_fit"] * 100)
            sys1_info = f"⚡ **تحلیل System 1:** اعتبار پروژه: `{j_pct}٪` | انطباق فنی: `{f_pct}٪`\n"

        return (
            f"🎯 **پروژه جدید فریلنسری (تطابق: {lead.get('match_score', 0)}٪)**\n\n"
            f"📌 **عنوان:** {lead.get('title')}\n"
            f"🌐 **منبع:** `{lead.get('platform')}`{rating_str}\n"
            f"{sys1_info}"
            f"💰 **بودجه کارفرما:** {budget_str}\n"
            f"💵 **پیشنهاد قیمت بهینه:** {lead.get('suggested_bid')}\n"
            f"⏱️ **زمان تحویل پیشنهادی:** {lead.get('suggested_timeline')}\n\n"
            f"📝 **متن پروپوزال آماده ارسال:**\n"
            f"```\n{lead.get('proposal_draft')}\n```\n\n"
            f"🔗 [{link_label}]({url})"
        )

    async def start_background_poller(
        self,
        on_high_match: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    ) -> None:
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
