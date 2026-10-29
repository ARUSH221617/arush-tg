import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings

DB_PATH = settings.VAULT_DATA_DIR / "db" / "vault.sqlite"


def slugify_skill(name: str) -> str:
    clean = re.sub(r"[^\w\u0600-\u06FF-]+", "-", name.lower().strip()).strip("-_")
    return clean or "custom-skill"


BUILTIN_SKILLS: List[Dict[str, Any]] = [
    {
        "slug": "claude-code-workflow",
        "name": "Claude Code Engineering Workflow",
        "description": "Disciplined local codebase exploration, surgical file editing, diff inspection, and test verification on PC projects.",
        "category": "engineering",
        "triggers": "code,edit,fix,refactor,implement,bug,file,project,برنامه,کد,ویرایش,باگ",
        "content": (
            "# Claude Code Engineering Workflow\n\n"
            "When working on a local PC project path:\n"
            "1. **Explore First**: Use `code_workspace` (`inspect_tree`, `grep_search`, `read_file`) to understand existing patterns and imports before modifying files.\n"
            "2. **Surgical Edits**: Prefer `edit_file` (exact search-and-replace) over overwriting large files so diffs remain minimal and reviewable.\n"
            "3. **Verify Changes**: Run tests, linters, or syntax checks via `run_in_project` (`pytest`, `python -m py_compile`, `npm test`, `git diff`) right after editing.\n"
            "4. **Summarize Clearly**: Report modified file paths, line ranges, and verification results."
        ),
    },
    {
        "slug": "clean-architecture",
        "name": "Clean Architecture & Modular Design",
        "description": "Enforces separation of concerns, SOLID principles, type annotations, and maintainable module boundaries.",
        "category": "architecture",
        "triggers": "architecture,design,plan,structure,clean,solid,معماری,ساختار,طراحی",
        "content": (
            "# Clean Architecture & Modular Design\n\n"
            "- Keep domain/business logic decoupled from transport layers (Telegram handlers, HTTP routes, CLI).\n"
            "- Use explicit Python type hints (`typing`), dataclasses/Pydantic models, and clear docstrings.\n"
            "- Handle errors gracefully with informative return payloads (`{'status': ..., 'error': ...}`) rather than unhandled crashes.\n"
            "- Ensure database operations use context managers and parameterized SQL queries."
        ),
    },
    {
        "slug": "python-async-pro",
        "name": "Python Async & Aiogram Mastery",
        "description": "Best practices for asyncio, aiogram 3.x bots, aiohttp clients, and non-blocking subprocesses.",
        "category": "python",
        "triggers": "python,asyncio,aiogram,telegram,bot,aiohttp,پایتون,تلگرام,ربات",
        "content": (
            "# Python Async & Aiogram Mastery\n\n"
            "- Never block the asyncio event loop with synchronous network or long subprocess calls; use `asyncio.create_subprocess_exec` and `aiohttp.ClientSession`.\n"
            "- Always apply timeouts (`asyncio.wait_for` or `ClientTimeout`) to external calls.\n"
            "- Keep Telegram messages under 4096 characters and provide fallback when Markdown parsing fails."
        ),
    },
    {
        "slug": "security-auditor",
        "name": "Security & Vulnerability Auditor",
        "description": "Audits code and commands for injection risks, secret leaks, unsafe deserialization, and path traversal.",
        "category": "security",
        "triggers": "security,audit,vulnerability,auth,secret,امنیت,تست نفوذ,باگ امنیتی",
        "content": (
            "# Security & Vulnerability Auditor\n\n"
            "- Never hardcode production secrets or API tokens in source code; read from environment variables or `.env`.\n"
            "- Validate and normalize file paths against the project root when requested.\n"
            "- Parameterize all SQL queries (`?` placeholders) and avoid `shell=True` with untrusted input."
        ),
    },
    {
        "slug": "test-driven-dev",
        "name": "Test-Driven Development (TDD)",
        "description": "Guides writing deterministic unit and integration tests with unittest/pytest and isolated temporary fixtures.",
        "category": "testing",
        "triggers": "test,unittest,pytest,coverage,verify,تست,آزمون",
        "content": (
            "# Test-Driven Development (TDD)\n\n"
            "- Use `tempfile.TemporaryDirectory` for database and filesystem tests so real user data is never mutated.\n"
            "- Mock external network or paid API calls using `unittest.mock.AsyncMock` / `MagicMock`.\n"
            "- Test happy paths, edge cases, and error/fallback paths."
        ),
    },
]


class SkillsManager:
    """
    Phase 8.2: Skills System Manager.
    Stores skills both as `SKILL.md` files (with YAML frontmatter) in `data/skills/{slug}/SKILL.md`
    and in SQLite (`skills` table) for fast querying, toggling, and agent attachment.
    """

    def __init__(self, db_path: Path = DB_PATH, data_dir: Optional[Path] = None):
        self.db_path = db_path
        self.data_dir = data_dir or settings.VAULT_DATA_DIR
        self.skills_dir = self.data_dir / "skills"
        self._init_db()
        self._seed_builtin_skills()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    category TEXT DEFAULT 'general',
                    triggers TEXT DEFAULT '',
                    content TEXT NOT NULL,
                    file_path TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1,
                    is_builtin INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def _write_skill_markdown(
        self,
        slug: str,
        name: str,
        description: str,
        category: str,
        triggers: str,
        enabled: bool,
        content: str,
    ) -> Path:
        skill_folder = self.skills_dir / slug
        skill_folder.mkdir(parents=True, exist_ok=True)
        md_path = skill_folder / "SKILL.md"
        frontmatter = (
            f"---\n"
            f"name: {slug}\n"
            f"title: {name}\n"
            f"description: {description}\n"
            f"category: {category}\n"
            f"triggers: {triggers}\n"
            f"enabled: {str(enabled).lower()}\n"
            f"---\n\n"
        )
        body = content.strip()
        md_path.write_text(frontmatter + body + "\n", encoding="utf-8")
        return md_path

    @staticmethod
    def parse_skill_markdown(raw_md: str) -> Dict[str, Any]:
        """Parses a SKILL.md string with optional YAML frontmatter."""
        meta: Dict[str, str] = {}
        body = raw_md.strip()
        if body.startswith("---"):
            parts = body.split("---", 2)
            if len(parts) >= 3:
                fm_lines = parts[1].strip().splitlines()
                for line in fm_lines:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip().lower()] = v.strip().strip("'\"")
                body = parts[2].strip()
        return {
            "slug": slugify_skill(meta.get("name") or meta.get("title") or "custom-skill"),
            "name": meta.get("title") or meta.get("name") or "Custom Skill",
            "description": meta.get("description") or "User-defined skill",
            "category": meta.get("category") or "general",
            "triggers": meta.get("triggers") or "",
            "enabled": meta.get("enabled", "true").lower() != "false",
            "content": body,
        }

    def _seed_builtin_skills(self) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            for item in BUILTIN_SKILLS:
                slug = item["slug"]
                cursor.execute("SELECT id FROM skills WHERE slug = ?", (slug,))
                if cursor.fetchone():
                    continue
                md_path = self._write_skill_markdown(
                    slug=slug,
                    name=item["name"],
                    description=item["description"],
                    category=item["category"],
                    triggers=item["triggers"],
                    enabled=True,
                    content=item["content"],
                )
                cursor.execute(
                    """
                    INSERT INTO skills (slug, name, description, category, triggers, content, file_path, enabled, is_builtin)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1)
                    """,
                    (
                        slug,
                        item["name"],
                        item["description"],
                        item["category"],
                        item["triggers"],
                        item["content"],
                        str(md_path),
                    ),
                )
            conn.commit()

    def list_skills(self, only_enabled: bool = False) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if only_enabled:
                cursor.execute("SELECT * FROM skills WHERE enabled = 1 ORDER BY is_builtin DESC, slug ASC")
            else:
                cursor.execute("SELECT * FROM skills ORDER BY is_builtin DESC, slug ASC")
            return [dict(r) for r in cursor.fetchall()]

    def get_skill(self, name_or_slug: str) -> Optional[Dict[str, Any]]:
        if not name_or_slug:
            return None
        slug = slugify_skill(name_or_slug)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM skills WHERE slug = ? OR LOWER(name) = LOWER(?)",
                (slug, name_or_slug.strip()),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_or_update_skill(
        self,
        name: str,
        content: str,
        description: str = "",
        category: str = "general",
        triggers: str = "",
        enabled: bool = True,
    ) -> Dict[str, Any]:
        # Support passing raw SKILL.md with frontmatter directly in content
        if content.strip().startswith("---") and not description:
            parsed = self.parse_skill_markdown(content)
            name = name or parsed["name"]
            description = parsed["description"]
            category = parsed["category"]
            triggers = triggers or parsed["triggers"]
            content = parsed["content"]

        slug = slugify_skill(name)
        desc = description or f"Custom skill: {name}"
        md_path = self._write_skill_markdown(
            slug=slug,
            name=name,
            description=desc,
            category=category,
            triggers=triggers,
            enabled=enabled,
            content=content,
        )

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, is_builtin FROM skills WHERE slug = ?", (slug,))
            existing = cursor.fetchone()
            now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            if existing:
                cursor.execute(
                    """
                    UPDATE skills
                    SET name = ?, description = ?, category = ?, triggers = ?,
                        content = ?, file_path = ?, enabled = ?, updated_at = ?
                    WHERE slug = ?
                    """,
                    (name, desc, category, triggers, content, str(md_path), 1 if enabled else 0, now_str, slug),
                )
                status = "updated"
            else:
                cursor.execute(
                    """
                    INSERT INTO skills (slug, name, description, category, triggers, content, file_path, enabled, is_builtin)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (slug, name, desc, category, triggers, content, str(md_path), 1 if enabled else 0),
                )
                status = "created"
            conn.commit()
            cursor.execute("SELECT * FROM skills WHERE slug = ?", (slug,))
            skill_dict = dict(cursor.fetchone())
            skill_dict["status"] = status
            return skill_dict

    def toggle_skill(self, name_or_slug: str, enabled: bool) -> Dict[str, Any]:
        sk = self.get_skill(name_or_slug)
        if not sk:
            return {"status": "not_found", "error": f"Skill '{name_or_slug}' not found."}
        slug = sk["slug"]
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skills SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
                (1 if enabled else 0, slug),
            )
            conn.commit()
        self._write_skill_markdown(
            slug=slug,
            name=sk["name"],
            description=sk["description"],
            category=sk["category"],
            triggers=sk["triggers"],
            enabled=enabled,
            content=sk["content"],
        )
        updated = self.get_skill(slug) or {}
        return {"status": "updated", "skill": updated}

    def delete_skill(self, name_or_slug: str) -> Dict[str, Any]:
        sk = self.get_skill(name_or_slug)
        if not sk:
            return {"status": "not_found", "error": f"Skill '{name_or_slug}' not found."}
        slug = sk["slug"]
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM skills WHERE slug = ?", (slug,))
            conn.commit()
        md_file = self.skills_dir / slug / "SKILL.md"
        if md_file.exists():
            try:
                md_file.unlink()
                md_file.parent.rmdir()
            except Exception:
                pass
        return {"status": "deleted", "slug": slug}

    def match_skills_for_prompt(
        self,
        prompt: str = "",
        explicit_skills: Optional[List[str]] = None,
        max_skills: int = 4,
    ) -> List[Dict[str, Any]]:
        """Returns explicitly attached skills plus enabled skills whose triggers match the user prompt."""
        enabled_skills = self.list_skills(only_enabled=True)
        by_slug = {s["slug"]: s for s in enabled_skills}
        matched: List[Dict[str, Any]] = []
        seen = set()

        for exp in explicit_skills or []:
            s_slug = slugify_skill(exp)
            if s_slug in by_slug and s_slug not in seen:
                matched.append(by_slug[s_slug])
                seen.add(s_slug)

        if prompt:
            p_lower = prompt.lower()
            for sk in enabled_skills:
                if sk["slug"] in seen:
                    continue
                triggers = [t.strip().lower() for t in (sk.get("triggers") or "").split(",") if t.strip()]
                if any(trig in p_lower for trig in triggers):
                    matched.append(sk)
                    seen.add(sk["slug"])
                    if len(matched) >= max_skills:
                        break

        return matched[:max_skills]

    def build_skills_prompt_block(
        self,
        prompt: str = "",
        explicit_skills: Optional[List[str]] = None,
    ) -> str:
        """Builds the active skills instruction block injected into the agent system prompt."""
        matched = self.match_skills_for_prompt(prompt=prompt, explicit_skills=explicit_skills)
        if not matched:
            return ""
        blocks = ["\n### Active Skills & Specialized Guidelines:"]
        for sk in matched:
            blocks.append(f"\n#### Skill: {sk['name']} (`{sk['slug']}`)\n{sk['content']}")
        return "\n".join(blocks)


skills_manager = SkillsManager()
