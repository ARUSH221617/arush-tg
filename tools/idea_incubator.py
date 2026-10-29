import json
import re
from typing import Dict, Any, List, Optional
from core.router_client import router_client
from tools.vault import vault

INCUBATOR_SYSTEM_PROMPT = """You are the Arush Ideas Incubator.
Transform unstructured voice memo transcripts (Persian or English) into a structured JSON object with these exact keys:
- "title": Short, punchy title for the idea
- "core_concept": Clear 2-3 sentence summary of the core product/feature concept
- "feasibility_score": Integer from 1 to 10 evaluating technical feasibility for a solo senior AI/full-stack builder
- "feasibility_rationale": 1-sentence reason for the score
- "recommended_tech_stack": Array of recommended technologies (e.g. ["Python", "FastAPI", "React", "SQLite"])
- "immediate_action_steps": Array of 3-5 concrete next steps to build an MVP
- "tags": Comma-separated keywords

Respond ONLY with valid JSON. Match the language (Persian or English) of the user's transcript for text fields.
"""


class VoiceIdeaIncubator:
    """
    Phase 2.3: Voice Memo & Ideas Incubator.
    Streams voice notes to 9Router STT (`groq/whisper-large-v3-turbo`) and
    auto-structures unstructured thoughts into:
    - Core Concept
    - Technical Feasibility Score (1-10)
    - Recommended Tech Stack
    - Immediate Action Steps
    """

    def _heuristic_structure(self, transcript: str) -> Dict[str, Any]:
        """Fallback deterministic structurer when 9Router LLM is offline."""
        clean = transcript.strip()
        words = clean.split()
        title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")
        lower = clean.lower()

        stack: List[str] = ["Python 3.11"]
        if any(k in lower for k in ("بات", "تلگرام", "bot", "telegram")):
            stack.extend(["aiogram 3.x", "Telethon"])
        if any(k in lower for k in ("وب", "سایت", "فرانت", "داشبورد", "react", "web", "dashboard", "ui")):
            stack.extend(["FastAPI", "React", "TailwindCSS"])
        if any(k in lower for k in ("هوش مصنوعی", "مدل", "ایجنت", "ai", "llm", "agent", "rag")):
            stack.extend(["9Router Gateway", "OpenAI SDK", "SQLite Vector Memory"])
        if any(k in lower for k in ("اسکرپ", "خزنده", "scrape", "crawler", "playwright")):
            stack.extend(["Playwright", "aiohttp"])
        if len(stack) == 1:
            stack.extend(["FastAPI", "SQLite", "Docker"])

        # Estimate feasibility score (1-10)
        score = 8
        if any(k in lower for k in ("blockchain", "kernel", "os", "3d engine", "موتور بازی")):
            score = 5
        elif any(k in lower for k in ("bot", "بات", "automation", "اتوماسیون", "scraper", "api")):
            score = 9

        is_persian = bool(re.search(r"[\u0600-\u06FF]", clean))
        if is_persian:
            steps = [
                "تعریف دقیق نیازمندی‌ها و ساختار دیتابیس در فایل specs.json پروژه",
                "پیاده‌سازی هسته اولیه (MVP) و تست اتصال به 9Router",
                "ساخت رابط کاربری یا دستورات تلگرام برای تعامل سریع",
                "اجرای تست‌های واحد و استقرار با Docker"
            ]
            rationale = "پروژه با استک فعلی پایتون و زیرساخت 9Router به سرعت قابل پیاده‌سازی است."
        else:
            steps = [
                "Define data schema and API contracts in the project workspace specs.json",
                "Build core MVP pipeline and integrate with 9Router gateway",
                "Expose Telegram bot commands or web UI endpoints",
                "Add automated unit tests and containerize with Docker"
            ]
            rationale = "Highly achievable solo using existing Python async and 9Router infrastructure."

        return {
            "title": title or "Voice Idea Memo",
            "core_concept": clean,
            "feasibility_score": score,
            "feasibility_rationale": rationale,
            "recommended_tech_stack": stack,
            "immediate_action_steps": steps,
            "tags": ",".join(s.lower().split()[0] for s in stack[:4])
        }

    async def incubate_transcript(
        self,
        transcript: str,
        project_slug: Optional[str] = None,
        audio_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Structures a voice transcript and saves it to the Project Knowledge Vault."""
        structured: Optional[Dict[str, Any]] = None
        try:
            raw_reply = await router_client.chat_completion(
                messages=[
                    {"role": "system", "content": INCUBATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": transcript}
                ],
                temperature=0.2
            )
            # Extract JSON block if wrapped in markdown fences
            cleaned = re.sub(r"^```(?:json)?|```$", "", raw_reply.strip(), flags=re.MULTILINE).strip()
            structured = json.loads(cleaned)
        except Exception:
            structured = None

        if not isinstance(structured, dict) or "core_concept" not in structured:
            structured = self._heuristic_structure(transcript)

        score = max(1, min(10, int(structured.get("feasibility_score", 8))))
        structured["feasibility_score"] = score
        stack = structured.get("recommended_tech_stack") or ["Python", "SQLite"]
        steps = structured.get("immediate_action_steps") or []

        formatted_md = (
            f"💡 **Incubated Idea: {structured.get('title', 'Voice Idea')}**\n\n"
            f"🎯 **Core Concept:**\n{structured.get('core_concept', transcript)}\n\n"
            f"📊 **Technical Feasibility Score:** `{score}/10`\n"
            f"_{structured.get('feasibility_rationale', '')}_\n\n"
            f"🛠️ **Recommended Tech Stack:**\n"
            + "\n".join(f"• `{tech}`" for tech in stack)
            + "\n\n🚀 **Immediate Action Steps:**\n"
            + "\n".join(f"{idx}. {step}" for idx, step in enumerate(steps, 1))
        )

        embedding = await router_client.create_embedding(f"{structured.get('title', '')}\n{transcript}")
        artifact = vault.save_artifact(
            artifact_type="idea",
            title=structured.get("title", "Voice Idea"),
            content=formatted_md,
            project_slug=project_slug,
            file_path=audio_path,
            tags=structured.get("tags", "voice,idea"),
            metadata=structured,
            embedding=embedding
        )

        return {
            "structured": structured,
            "formatted_markdown": formatted_md,
            "artifact": artifact
        }


idea_incubator = VoiceIdeaIncubator()
