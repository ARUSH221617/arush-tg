import asyncio
import hashlib
import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple, Callable, Awaitable
from html import unescape

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    import telethon
    HAS_TELETHON = True
except ImportError:
    telethon = None
    HAS_TELETHON = False

from config import settings
from core.router_client import router_client
from tools.vault import vault
from tools.receipt_parser import normalize_digits

logger = logging.getLogger("arush-radar")

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
        cleaned = re.sub(r"^[^\w\u0600-\u06FF]+", "", line).strip()
        cleaned = re.sub(r"^(?:عنوان\s*پروژه|عنوان|نام\s*پروژه|پروژه\s*جدید)[\s:：\-]+", "", cleaned).strip()
        alnum_count = len(re.findall(r"[\w\u0600-\u06FF]", cleaned))
        if alnum_count >= 4:
            return cleaned[:110]
    return fallback


def compute_deterministic_lead_id(platform: str, url_or_pid: str) -> str:
    """
    Suggestion 1: Computes a deterministic, collision-resistant external_id across bot restarts.
    Replaces non-deterministic Python hash(url) with SHA-256 digest.
    """
    clean = re.sub(r"[?&]utm_[^&]+", "", str(url_or_pid)).strip().lower().rstrip("/")
    h = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]
    plat = platform.replace(":", "_").replace("@", "")
    return f"{plat}_{h}"


def parse_persian_budget(text: str) -> Tuple[float, float, str]:
    """
    Suggestion 1: Robust multi-format budget extractor.
    Parses ranges, word quantifiers (میلیون, هزار, م ت, میلیارد), unformatted digits,
    comma-separated digits, and currencies (تومان, ریال, USD).
    Returns (budget_min, budget_max, currency).
    """
    if not text:
        return 0.0, 0.0, "Toman"

    norm = normalize_digits(text).strip()

    # 1. Check for USD indicators ($500, 500$, $500 - $1,000, 45 USD, 45$/hr)
    usd_range = re.search(r"\$\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:-|to|تا)\s*\$?\s*([0-9,]+(?:\.[0-9]+)?)", norm, re.IGNORECASE)
    if usd_range:
        v1 = float(usd_range.group(1).replace(",", ""))
        v2 = float(usd_range.group(2).replace(",", ""))
        return v1, v2, "USD"
    usd_single = re.search(r"(?:\$\s*([0-9,]+(?:\.[0-9]+)?)|([0-9,]+(?:\.[0-9]+)?)\s*(?:\$|usd|dollars?))", norm, re.IGNORECASE)
    if usd_single:
        raw_val = usd_single.group(1) or usd_single.group(2)
        val = float(raw_val.replace(",", ""))
        return val, val, "USD"

    # Currency determination (Rial vs Toman)
    is_rial = bool(re.search(r"\bریال\b", norm))
    divisor = 10.0 if is_rial else 1.0

    # 2. Check for ranges with word multipliers (e.g. "۱۰ تا ۲۰ میلیون", "15 الی 25 م ت")
    range_match = re.search(
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:تا|الی|-)\s*([0-9]+(?:\.[0-9]+)?)\s*(میلیون|میل|م\b|هزار|ک\b|k\b)?\s*(?:تومان|تومن|ریال)?",
        norm,
        re.IGNORECASE
    )
    if range_match:
        v1 = float(range_match.group(1))
        v2 = float(range_match.group(2))
        unit = (range_match.group(3) or "").lower()
        multiplier = 1.0
        if unit in ("میلیون", "میل", "م"):
            multiplier = 1_000_000.0
        elif unit in ("هزار", "ک", "k"):
            multiplier = 1_000.0
        elif v1 < 1000 and v2 < 1000:
            multiplier = 1_000_000.0

        b_min = (v1 * multiplier) / divisor
        b_max = (v2 * multiplier) / divisor
        return b_min, b_max, "Toman"

    # 3. Check for single numbers with word multipliers ("۱۵ میلیون", "20 م ت", "500 هزار")
    word_match = re.search(
        r"([0-9]+(?:\.[0-9]+)?)\s*(میلیون|میل|م\b|هزار|ک\b|k\b)\s*(?:تومان|تومن|ریال)?",
        norm,
        re.IGNORECASE
    )
    if word_match:
        val = float(word_match.group(1))
        unit = word_match.group(2).lower()
        multiplier = 1_000_000.0 if unit in ("میلیون", "میل", "م") else 1_000.0
        budget = (val * multiplier) / divisor
        return budget, budget, "Toman"

    # 4. Comma-separated amounts ("15,000,000 تومان")
    comma_match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+)\s*(?:تومان|تومن|ریال)?", norm)
    if comma_match:
        val = float(comma_match.group(1).replace(",", "")) / divisor
        return val, val, "Toman"

    # 5. Plain unformatted numbers ("15000000 تومان" or "5000000")
    plain_digit_match = re.search(r"\b([0-9]{6,11})\b\s*(?:تومان|تومن|ریال)?", norm)
    if plain_digit_match:
        val = float(plain_digit_match.group(1)) / divisor
        return val, val, "Toman"

    return 0.0, 0.0, "Toman"


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
    Phase 3.4 & Suggestions 5, 8: AI Lead Matchmaker & Proposal Generator.
    Uses strict whole-word skill matching, incorporates verified active skills
    and completed Vault projects, and enforces negative criteria from user feedback.
    """

    def score_and_draft_SyncFallback(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        title = lead.get("title", "")
        desc = lead.get("description", "")
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

        # 2. Match skills using word boundaries
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
        curr = lead.get("currency", "Toman")
        budget_max = float(lead.get("budget_max") or lead.get("budget_min") or 0.0)

        # Normalize USD to Toman approximation for threshold check
        effective_budget_toman = budget_max * 90_000 if curr == "USD" else budget_max
        if effective_budget_toman >= settings.RADAR_MIN_BUDGET_TOMAN * 3:
            score += 12
        elif effective_budget_toman >= settings.RADAR_MIN_BUDGET_TOMAN:
            score += 6
        elif 0 < effective_budget_toman < settings.RADAR_MIN_BUDGET_TOMAN:
            score -= 30

        final_score = max(5, min(96, score))

        if budget_max > 0:
            suggested_num = int(budget_max * 0.9)
            suggested_bid = f"${suggested_num:,}" if curr == "USD" else f"{suggested_num:,} تومان"
        else:
            suggested_bid = "توافقی (پس از بررسی دقیق نیازمندی‌ها)"

        suggested_timeline = "۵ تا ۷ روز کاری" if (0 < effective_budget_toman < 12_000_000) else "۷ تا ۱۲ روز کاری"
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
        """
        Evaluates lead using System 2 with rich context injection (active skills,
        past completed projects from Vault, and negative feedback exclusions).
        """
        fallback = self.score_and_draft_SyncFallback(lead)
        if fallback["match_score"] == 0:
            return fallback

        # Collect active skills from SkillsManager (Suggestion 5)
        active_skills_list = []
        try:
            from tools.skills_manager import skills_manager
            enabled = skills_manager.list_skills(only_enabled=True)
            active_skills_list = [f"• {s['name']}: {s.get('description', '')}" for s in enabled[:4]]
        except Exception:
            pass

        # Collect recent completed projects from Vault (Suggestion 5)
        past_projects_list = []
        try:
            projs = vault.list_projects()
            past_projects_list = [f"• {p['name']} ({p.get('platform', 'direct')})" for p in projs[:3]]
        except Exception:
            pass

        # Collect user-rejected leads as negative criteria (Suggestion 8)
        negative_examples = []
        try:
            rejected = vault.get_recent_rejected_leads(limit=6)
            negative_examples = [r.get("title", "") for r in rejected if r.get("title")]
        except Exception:
            pass

        skills_block = ("Verified Active Skills:\n" + "\n".join(active_skills_list)) if active_skills_list else ""
        projs_block = ("Completed Portfolio Projects in Vault:\n" + "\n".join(past_projects_list)) if past_projects_list else ""
        neg_block = ("Avoid/Negative Topics recently rejected by user:\n" + ", ".join(negative_examples)) if negative_examples else ""

        prompt = (
            f"Evaluate whether this post is a real software/AI freelance project and score its fit for Arush.\n"
            f"Portfolio: {settings.PORTFOLIO_SUMMARY}\n"
            f"{skills_block}\n"
            f"{projs_block}\n"
            f"{neg_block}\n"
            f"Min Budget: {settings.RADAR_MIN_BUDGET_TOMAN:,.0f} Toman\n\n"
            f"Title: {lead.get('title')}\n"
            f"Description: {lead.get('description')}\n"
            f"Budget: {lead.get('budget_min')} - {lead.get('budget_max')} {lead.get('currency', 'Toman')}\n\n"
            f"If this is a blog post, news article, tutorial, advertisement, or matches negative rejected topics, "
            f"set is_real_project=false and match_score=0.\n"
            f"Draft a personalized, technically authoritative Persian proposal that specifically references Arush's technical "
            f"expertise and offers concrete architectural milestones. Do not write generic boilerplate.\n"
            f"Return ONLY a JSON object with keys: is_real_project (bool), match_score (0-100 int), "
            f"suggested_bid (str in Persian), suggested_timeline (str in Persian), proposal_draft (Persian proposal)."
        )
        try:
            raw = await router_client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are an elite software freelance lead qualifier and proposal strategist. Output valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                if isinstance(parsed, dict):
                    if parsed.get("is_real_project") is False:
                        return {
                            "match_score": 0,
                            "suggested_bid": "رد شده (پست غیرپروژه‌ای یا نامنطبق)",
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
        except Exception as e:
            logger.debug(f"LLM lead evaluation fallback: {e}")

        return fallback


class TelethonChannelListener:
    """
    Suggestion 2: Real-time MTProto Telegram Channel & Group Stream Listener.
    Allows zero-delay lead detection without periodic HTTP scraping delays.
    Falls back gracefully if credentials are not configured.
    """

    def __init__(self, radar_instance: "FreelanceRadar"):
        self.radar = radar_instance
        self.client = None
        self._running = False

    async def start(self, on_new_lead: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None) -> bool:
        if not HAS_TELETHON:
            logger.info("Telethon is not installed; relying on resilient HTTP web preview poller.")
            return False

        api_id = getattr(settings, "TELEGRAM_API_ID", None)
        api_hash = getattr(settings, "TELEGRAM_API_HASH", None)
        if not api_id or not api_hash:
            logger.info("TELEGRAM_API_ID / TELEGRAM_API_HASH not configured; relying on resilient HTTP web preview poller.")
            return False

        try:
            from telethon import TelegramClient, events
            session_name = getattr(settings, "TELEGRAM_SESSION_NAME", "arush_radar_session")
            self.client = TelegramClient(session_name, api_id, api_hash)
            await self.client.connect()
            if not await self.client.is_user_authorized():
                logger.info("Telethon client session not yet authorized; skipping MTProto stream listener.")
                return False

            channels = [ch.lstrip("@") for ch in settings.TELEGRAM_FREELANCE_CHANNELS]

            @self.client.on(events.NewMessage(chats=channels))
            async def _on_channel_post(event):
                raw_text = event.raw_text or ""
                if len(raw_text) < 25:
                    return

                chat = await event.get_chat()
                ch_title = getattr(chat, "username", None) or getattr(chat, "title", "channel")
                post_url = f"https://t.me/{ch_title}/{event.id}"
                ext_id = f"tg_{ch_title}_{event.id}"

                lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
                title = extract_meaningful_title(lines, fallback=f"پروژه تلگرام (@{ch_title})")
                b_min, b_max, curr = parse_persian_budget(raw_text)

                lead = {
                    "external_id": ext_id,
                    "platform": f"telegram:@{ch_title}",
                    "title": title,
                    "description": raw_text[:1200],
                    "category": "freelance",
                    "budget_min": b_min,
                    "budget_max": b_max,
                    "currency": curr,
                    "employer_name": f"@{ch_title}",
                    "employer_rating": 0.0,
                    "url": post_url
                }

                processed = await self.radar.process_custom_lead(lead)
                if processed.get("is_new") and processed.get("match_score", 0) >= settings.RADAR_MATCH_THRESHOLD:
                    if on_new_lead:
                        await on_new_lead(processed)

            self._running = True
            logger.info("Telethon real-time freelance channel listener connected successfully.")
            return True
        except Exception as e:
            logger.warning(f"Could not initialize Telethon real-time stream: {e}")
            return False

    async def stop(self):
        self._running = False
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass


class FreelanceRadar:
    """
    Phase 3 & Advanced Radar:
    - Iranian Split-Network scraping (Karlancer, Ponisha)
    - Public Telegram Channel web preview parser + Real-time Telethon listener
    - Global RSS feeds (RemoteOK, WeWorkRemotely, Upwork)
    - Deterministic SHA-256 deduplication
    - Advanced Persian Budget parsing
    - Concurrent System 2 proposal synthesis with Semaphores
    - Source Health Diagnostics & Observability
    - Semi-automated 1-click browser bidding preparation
    """

    def __init__(self):
        self.net = IranianSplitNetworkClient()
        self.matchmaker = LeadMatchmaker()
        self.telethon_listener = TelethonChannelListener(self)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._telethon_started = False

        # Suggestion 10: Source health telemetry
        self.source_health: Dict[str, Dict[str, Any]] = {
            "karlancer": {"status": "ok", "last_poll": None, "leads_found": 0, "errors": 0, "last_error": None},
            "ponisha": {"status": "ok", "last_poll": None, "leads_found": 0, "errors": 0, "last_error": None},
            "telegram": {"status": "ok", "last_poll": None, "leads_found": 0, "errors": 0, "last_error": None},
            "global_rss": {"status": "ok", "last_poll": None, "leads_found": 0, "errors": 0, "last_error": None},
        }

    def get_health_report(self) -> Dict[str, Dict[str, Any]]:
        """Returns structured health and diagnostics status for all radar sources."""
        return self.source_health

    def is_real_project_post(self, title: str, description: str, platform: str = "") -> bool:
        """Ensures a scraped post is an actual project/gig and not blog/promotional noise."""
        combined = f"{title}\n{description}".strip()
        if len(combined) < 25:
            return False

        if any(re.search(pat, combined, re.IGNORECASE) for pat in NON_PROJECT_PATTERNS):
            return False

        if platform.startswith("telegram:"):
            hits = sum(1 for pat in PROJECT_INTENT_INDICATORS if re.search(pat, combined, re.IGNORECASE))
            if hits < 2:
                return False

        return True

    def filter_lead_fallback(self, lead: Dict[str, Any]) -> bool:
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

        curr = lead.get("currency", "Toman")
        budget_max = float(lead.get("budget_max") or lead.get("budget_min") or 0.0)
        effective_budget = budget_max * 90_000 if curr == "USD" else budget_max
        if effective_budget > 0 and effective_budget < settings.RADAR_MIN_BUDGET_TOMAN:
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
        Intelligently screens and detects job leads in batches using System 1 AI.
        Integrates negative user feedback criteria dynamically (Suggestion 8).
        """
        if not leads:
            return []

        resolved_batch_size = batch_size or getattr(settings, "RADAR_SYSTEM_ONE_BATCH_SIZE", 20)
        threshold = getattr(settings, "RADAR_SYSTEM_ONE_THRESHOLD", 0.55)
        accepted_leads: List[Dict[str, Any]] = []

        # Query negative feedback examples from Vault
        rejected_titles: List[str] = []
        try:
            recent_rejections = vault.get_recent_rejected_leads(limit=5)
            rejected_titles = [r.get("title", "") for r in recent_rejections if r.get("title")]
        except Exception:
            pass

        neg_clause = ""
        if rejected_titles:
            neg_clause = f" Negative criteria: The user recently rejected: ({', '.join(rejected_titles[:3])})."

        for i in range(0, len(leads), resolved_batch_size):
            chunk = leads[i : i + resolved_batch_size]

            state_data = []
            questions = {}

            for idx, lead in enumerate(chunk, start=1):
                clean_title = (lead.get("title") or "").strip()
                clean_desc = (lead.get("description") or "").strip()[:400].replace("\n", " ")
                platform = lead.get("platform", "unknown")
                b_min = float(lead.get("budget_min") or 0.0)
                b_max = float(lead.get("budget_max") or 0.0)
                curr = lead.get("currency", "Toman")
                budget_str = f"{b_min:,.0f}-{b_max:,.0f} {curr}" if b_max > 0 else "negotiable"

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
                        f"(not an educational tutorial, blog article, webinar, news, general chat, commercial advertisement, or scam)?{neg_clause}"
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

                    curr = lead.get("currency", "Toman")
                    b_max = float(lead.get("budget_max") or lead.get("budget_min") or 0.0)
                    eff_b = b_max * 90_000 if curr == "USD" else b_max
                    budget_ok = (eff_b == 0.0 or eff_b >= settings.RADAR_MIN_BUDGET_TOMAN)

                    if is_job_prob >= threshold and stack_prob >= threshold and budget_ok:
                        composite_score = int((is_job_prob * 0.4 + stack_prob * 0.6) * 100)
                        lead["match_score"] = composite_score
                        accepted_leads.append(lead)
            except Exception as e:
                logger.debug(f"System 1 batch evaluation fallback: {e}")
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
                    ext_id = compute_deterministic_lead_id(platform, pid)
                    leads.append({
                        "external_id": ext_id,
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
            except Exception as e:
                logger.debug(f"JSON feed parsing notice for {platform}: {e}")

        # RSS / XML feed fallback
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

            b_min, b_max, curr = parse_persian_budget(f"{title}\n{clean_desc}")
            ext_id = compute_deterministic_lead_id(platform, link)

            leads.append({
                "external_id": ext_id,
                "platform": platform,
                "title": title,
                "description": clean_desc[:1000],
                "category": "development",
                "budget_min": b_min,
                "budget_max": b_max,
                "currency": curr,
                "employer_name": "کارفرما",
                "employer_rating": 0.0,
                "url": link
            })

        return leads

    def parse_telegram_channel_html(self, html: str, channel_name: str) -> List[Dict[str, Any]]:
        """Parses public Telegram channel web preview (`https://t.me/s/<channel>`)."""
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

            # Extract budget with advanced Persian and range support (Suggestion 1)
            b_min, b_max, curr = parse_persian_budget(clean_text)

            href_match = re.search(
                r'href="(https?://(?:www\.)?(?:ponisha\.ir|karlancer\.com)/[^\s"]+)"',
                raw_msg,
                re.IGNORECASE
            )
            target_url = href_match.group(1) if href_match else f"https://t.me/{post_id}"
            ext_id = f"tg_{post_id.replace('/', '_')}"

            leads.append({
                "external_id": ext_id,
                "platform": f"telegram:@{channel_name}",
                "title": title,
                "description": clean_text[:1200],
                "category": "freelance",
                "budget_min": b_min,
                "budget_max": b_max,
                "currency": curr,
                "employer_name": f"@{channel_name}",
                "employer_rating": 0.0,
                "url": target_url
            })
        return leads

    def parse_global_rss(self, xml_content: str, platform: str = "remote_global") -> List[Dict[str, Any]]:
        """
        Suggestion 4: Parses international RSS/Atom feeds (RemoteOK, WeWorkRemotely, Upwork RSS).
        Extracts remote jobs and USD compensations.
        """
        leads: List[Dict[str, Any]] = []
        items = re.findall(r"<item>(.*?)</item>", xml_content, re.DOTALL | re.IGNORECASE)
        for idx, block in enumerate(items):
            t_match = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", block, re.DOTALL)
            l_match = re.search(r"<link>(.*?)</link>", block, re.DOTALL)
            d_match = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>", block, re.DOTALL)

            raw_title = unescape((t_match.group(1) or t_match.group(2) or "").strip()) if t_match else f"Remote Gig {idx}"
            title = extract_meaningful_title([raw_title], fallback=f"Remote Project {idx}")
            link = l_match.group(1).strip() if l_match else f"https://{platform}.com/{idx}"
            raw_desc = unescape((d_match.group(1) or d_match.group(2) or "").strip()) if d_match else ""
            clean_desc = clean_html_preserving_inline(raw_desc)

            b_min, b_max, curr = parse_persian_budget(f"{title}\n{clean_desc}")
            ext_id = compute_deterministic_lead_id(platform, link)

            leads.append({
                "external_id": ext_id,
                "platform": platform,
                "title": title,
                "description": clean_desc[:1200],
                "category": "global_freelance",
                "budget_min": b_min,
                "budget_max": b_max,
                "currency": curr,
                "employer_name": platform.replace("_", " ").title(),
                "employer_rating": 0.0,
                "url": link
            })
        return leads

    async def poll_sources_once(self) -> List[Dict[str, Any]]:
        """
        Polls Karlancer, Ponisha, Telegram channels, and Global RSS feeds.
        Tracks diagnostics and processes qualified leads concurrently with Semaphores.
        """
        import datetime
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        discovered: List[Dict[str, Any]] = []

        # 1. Domestic Platforms (Split-Network)
        domestic_sources = [
            ("karlancer", "https://www.karlancer.com/api/public/projects?page=1"),
            ("ponisha", "https://ponisha.ir/search/projects/feed"),
        ]
        for platform, url in domestic_sources:
            try:
                raw = await self.net.fetch_text(url)
                items = self.parse_feed_items(raw, platform=platform)
                discovered.extend(items)
                self.source_health[platform]["status"] = "ok"
                self.source_health[platform]["last_poll"] = now_str
                self.source_health[platform]["leads_found"] += len(items)
            except Exception as e:
                self.source_health[platform]["status"] = "warning"
                self.source_health[platform]["errors"] += 1
                self.source_health[platform]["last_error"] = str(e)
                logger.warning(f"Failed to poll {platform}: {e}")

        # 2. Telegram Channels (via Proxy or Web Preview)
        for channel in settings.TELEGRAM_FREELANCE_CHANNELS:
            ch_clean = channel.lstrip("@")
            try:
                async with aiohttp.ClientSession(headers=BROWSER_HEADERS) as session:
                    async with session.get(
                        f"https://t.me/s/{ch_clean}",
                        proxy=settings.TELEGRAM_PROXY,
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            tg_items = self.parse_telegram_channel_html(html, ch_clean)
                            discovered.extend(tg_items)
                            self.source_health["telegram"]["status"] = "ok"
                            self.source_health["telegram"]["leads_found"] += len(tg_items)
                        else:
                            self.source_health["telegram"]["status"] = "warning"
                            self.source_health["telegram"]["errors"] += 1
                self.source_health["telegram"]["last_poll"] = now_str
            except Exception as e:
                self.source_health["telegram"]["status"] = "warning"
                self.source_health["telegram"]["errors"] += 1
                self.source_health["telegram"]["last_error"] = str(e)
                logger.warning(f"Failed to poll Telegram channel @{ch_clean}: {e}")

        # 3. Global Remote/USD Feeds (Suggestion 4)
        if getattr(settings, "RADAR_ENABLE_GLOBAL_SOURCES", True):
            global_feeds = getattr(settings, "RADAR_GLOBAL_RSS_FEEDS", [])
            for feed_url in global_feeds:
                try:
                    async with aiohttp.ClientSession(headers=BROWSER_HEADERS) as session:
                        async with session.get(feed_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                            if resp.status == 200:
                                xml_text = await resp.text()
                                feed_plat = "remoteok" if "remoteok" in feed_url else "weworkremotely"
                                g_items = self.parse_global_rss(xml_text, platform=feed_plat)
                                discovered.extend(g_items)
                                self.source_health["global_rss"]["status"] = "ok"
                                self.source_health["global_rss"]["leads_found"] += len(g_items)
                    self.source_health["global_rss"]["last_poll"] = now_str
                except Exception as e:
                    self.source_health["global_rss"]["status"] = "warning"
                    self.source_health["global_rss"]["errors"] += 1
                    self.source_health["global_rss"]["last_error"] = str(e)
                    logger.debug(f"Global RSS poll note for {feed_url}: {e}")

        # 4. Deduplicate unseen leads
        unseen_leads = vault.filter_unseen_leads(discovered)
        if not unseen_leads:
            return []

        # 5. Batch screen with System 1 AI
        screened_leads = await self.batch_filter_leads_system_one(unseen_leads)
        if not screened_leads:
            return []

        # 6. Concurrent System 2 Evaluation with asyncio.gather & Semaphore (Suggestion 3)
        concurrency = getattr(settings, "RADAR_CONCURRENT_EVALS", 4)
        sem = asyncio.Semaphore(concurrency)

        async def _eval_and_save(raw_lead: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            async with sem:
                eval_res = await self.matchmaker.evaluate_lead(raw_lead)
                final_score = int(eval_res.get("match_score") or raw_lead.get("match_score", 0))
                raw_lead.update(eval_res)
                raw_lead["match_score"] = final_score

                saved = vault.save_freelance_lead(raw_lead)
                if saved.get("is_new") and final_score >= settings.RADAR_MATCH_THRESHOLD:
                    return saved
                return None

        tasks = [_eval_and_save(ld) for ld in screened_leads]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        qualified_alerts: List[Dict[str, Any]] = [
            r for r in results if isinstance(r, dict)
        ]

        return qualified_alerts

    async def process_custom_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Manually processes a single lead (e.g. from /radar evaluate or custom inputs)."""
        screened = await self.batch_filter_leads_system_one([lead_data])
        if screened:
            lead_data = screened[0]
        eval_res = await self.matchmaker.evaluate_lead(lead_data)
        merged = {**lead_data, **eval_res}
        saved = vault.save_freelance_lead(merged)
        return saved

    def format_telegram_alert(self, lead: Dict[str, Any]) -> str:
        """
        Formats alert with Platinum tier badge, employer reputation,
        System 1 confidence stats, and customized proposal (Suggestion 9).
        """
        b_min = float(lead.get("budget_min") or 0)
        b_max = float(lead.get("budget_max") or 0)
        curr = lead.get("currency", "Toman")
        if curr == "USD":
            budget_str = f"${b_min:,.0f} تا ${b_max:,.0f}" if b_max > b_min else (
                f"${b_max:,.0f}" if b_max > 0 else "توافقی (ارزی)"
            )
        else:
            budget_str = f"{b_min:,.0f} تا {b_max:,.0f} تومان" if b_max > b_min else (
                f"{b_max:,.0f} تومان" if b_max > 0 else "توافقی"
            )

        score = lead.get("match_score", 0)
        is_platinum = score >= 90 or (b_max >= 25_000_000 and curr == "Toman") or (b_max >= 300 and curr == "USD")
        badge = "💎 **فرصت طلایی فریلنسری (تطابق فوق‌العاده: " if is_platinum else "🎯 **پروژه جدید فریلنسری (تطابق: "

        rating = float(lead.get("employer_rating") or 0.0)
        rating_str = f" | ⭐ **امتیاز کارفرما:** `{rating}/5`" if rating > 0 else ""
        url = lead.get("url") or "https://ponisha.ir"
        link_label = "مشاهده در تلگرام" if "t.me/" in url else "صفحه پروژه در سایت"

        sys1_info = ""
        if "system_one_is_job" in lead and "system_one_stack_fit" in lead:
            j_pct = int(lead["system_one_is_job"] * 100)
            f_pct = int(lead["system_one_stack_fit"] * 100)
            sys1_info = f"⚡ **تحلیل System 1:** اعتبار پروژه: `{j_pct}٪` | انطباق فنی: `{f_pct}٪`\n"

        return (
            f"{badge}{score}٪)**\n\n"
            f"📌 **عنوان:** {lead.get('title')}\n"
            f"🌐 **منبع:** `{lead.get('platform')}`{rating_str}\n"
            f"{sys1_info}"
            f"💰 **بودجه کارفرما:** {budget_str}\n"
            f"💵 **پیشنهاد قیمت بهینه:** {lead.get('suggested_bid')}\n"
            f"⏱️ **زمان تحویل پیشنهادی:** {lead.get('suggested_timeline')}\n\n"
            f"📝 **متن پروپوزال پیشنهادی:**\n"
            f"```\n{lead.get('proposal_draft')}\n```\n\n"
            f"🔗 [{link_label}]({url})"
        )

    def create_alert_keyboard(self, lead: Dict[str, Any]):
        """Suggestion 6: Builds an interactive CRM inline keyboard for Telegram."""
        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        except ImportError:
            return None

        lead_id = lead.get("id") or 0
        url = lead.get("url") or "https://ponisha.ir"
        site_label = "🚀 مشاهده در سایت" if "t.me/" not in url else "🚀 مشاهده پست در تلگرام"

        buttons = [
            [InlineKeyboardButton(text=site_label, url=url)],
            [
                InlineKeyboardButton(text="📋 کپی پروپوزال", callback_data=f"radar:copy:{lead_id}"),
                InlineKeyboardButton(text="📁 تبدیل به پروژه", callback_data=f"radar:convert:{lead_id}")
            ],
            [
                InlineKeyboardButton(text="🔄 بازنویسی کوتاه", callback_data=f"radar:reroll:{lead_id}"),
                InlineKeyboardButton(text="❌ رد کردن", callback_data=f"radar:reject:{lead_id}")
            ]
        ]
        if "t.me/" not in url:
            buttons.append([InlineKeyboardButton(text="🌐 پیش‌نویس مرورگر", callback_data=f"radar:bid:{lead_id}")])

        return InlineKeyboardMarkup(inline_keyboard=buttons)

    def format_batch_digest(self, leads: List[Dict[str, Any]]) -> str:
        """Suggestion 9: Formats an anti-spam digest message when multiple leads arrive at once."""
        lines = [
            f"📡 **گزارش دسته‌ای فرصت‌های فریلنسری جدید ({len(leads)} پروژه منطبق):**\n"
        ]
        for idx, ld in enumerate(leads, start=1):
            b_max = float(ld.get("budget_max") or 0)
            curr = ld.get("currency", "Toman")
            b_str = f"{b_max:,.0f} {curr}" if b_max > 0 else "توافقی"
            lines.append(
                f"{idx}. **{ld['title']}**\n"
                f"   • تطابق: `{ld.get('match_score', 0)}%` | بودجه: `{b_str}` | منبع: `{ld.get('platform')}`\n"
                f"   • [مشاهده پروژه]({ld.get('url', '#')})"
            )
        lines.append("\n💡 برای مدیریت پروپوزال و تبدیل به پروژه، از دستور `/radar` استفاده کنید.")
        return "\n".join(lines)

    async def prepare_browser_bid(self, lead_id: int) -> Dict[str, Any]:
        """
        Suggestion 7: Pre-fills proposal form via Playwright Browser Agent.
        Opens project URL, verifies login, fills bid inputs, captures screenshot for human confirmation.
        """
        lead = vault.get_lead_by_id(lead_id)
        if not lead:
            return {"status": "error", "error": f"Lead {lead_id} not found"}

        url = lead.get("url")
        if not url or "t.me/" in url:
            return {"status": "skipped", "message": "Lead is from Telegram; direct website bid form not applicable."}

        try:
            from tools.browser_agent import browser_agent
            task_instructions = (
                f"Navigate to {url}. If a proposal or bid submission form is visible on this page, "
                f"prepare the proposal draft: Bid '{lead.get('suggested_bid')}', Timeline '{lead.get('suggested_timeline')}'. "
                f"Do NOT click final submit without user approval."
            )
            res = await browser_agent.execute_browser_task(task_instructions)
            return res
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def start_background_poller(
        self,
        on_high_match: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        on_batch_match: Optional[Callable[[List[Dict[str, Any]]], Awaitable[None]]] = None
    ) -> None:
        """Starts periodic poller and real-time Telethon MTProto listener."""
        self._running = True
        logger.info("Freelance Radar background poller activated.")

        # Attempt to start real-time Telethon listener if configured
        if not self._telethon_started:
            try:
                await self.telethon_listener.start(on_new_lead=on_high_match)
                self._telethon_started = True
            except Exception as e:
                logger.debug(f"Telethon stream listener startup note: {e}")

        while self._running:
            try:
                alerts = await self.poll_sources_once()
                if alerts:
                    # Separate platinum (urgent) from standard leads (Suggestion 9)
                    platinum_leads = [
                        ld for ld in alerts
                        if ld.get("match_score", 0) >= 90 or float(ld.get("budget_max", 0)) >= 25_000_000 or ld.get("currency") == "USD"
                    ]
                    standard_leads = [ld for ld in alerts if ld not in platinum_leads]

                    # Notify platinum leads immediately
                    if on_high_match:
                        for ld in platinum_leads:
                            await on_high_match(ld)

                    # Notify standard leads (batch digest if >= 2, single alert if 1)
                    if len(standard_leads) >= 2 and on_batch_match:
                        await on_batch_match(standard_leads)
                    elif on_high_match:
                        for ld in standard_leads:
                            await on_high_match(ld)
            except Exception as e:
                logger.warning(f"Error in Freelance Radar poller cycle: {e}")

            await asyncio.sleep(settings.RADAR_POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        if self.telethon_listener:
            asyncio.create_task(self.telethon_listener.stop())


freelance_radar = FreelanceRadar()
