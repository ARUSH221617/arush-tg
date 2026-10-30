import asyncio
import difflib
import fnmatch
import json
import os
import platform
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Awaitable, Dict, List, Optional

from config import settings
from tools.skills_manager import skills_manager

DB_PATH = settings.VAULT_DATA_DIR / "db" / "vault.sqlite"

IGNORED_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
}


def slugify_identifier(name: str, default: str = "custom_agent") -> str:
    clean = re.sub(r"[^\w\u0600-\u06FF-]+", "_", name.lower().strip()).strip("_-")
    return clean or default


# =====================================================================
# 1. Prebuilt Persona Agents Definitions (Programmer, Planner, etc.)
# =====================================================================
PREBUILT_AGENTS: List[Dict[str, Any]] = [
    {
        "slug": "manager",
        "name": "Arush Executive Manager",
        "role_title": "Autonomous Co-Founder & Full-System Orchestrator",
        "description": "Default executive agent with access to all Vault, Finance, Radar, Desktop, Code, Sub-Agent, Skills, and MCP tools.",
        "system_prompt": (
            "You are Arush Manager Agent, an autonomous executive co-founder and full-stack orchestrator. "
            "Coordinate complex tasks, manage projects, delegate specialized coding/planning work to sub-agents "
            "or local CLI agents (Claude Code, Antigravity, Codex, GitHub Copilot), and keep workspaces organized."
        ),
        "structure_template": (
            "1. **Executive Summary / Action Taken**\n"
            "2. **Technical / Project Details**\n"
            "3. **Verification & Next Steps**"
        ),
        "preferred_model": settings.AGENT_MODEL,
        "attached_skills": ["claude-code-workflow", "clean-architecture"],
        "is_active": 1,
    },
    {
        "slug": "programmer",
        "name": "Claude Code Programmer",
        "role_title": "Senior Autonomous Full-Stack & Systems Engineer",
        "description": "Prebuilt coding agent that operates directly on your saved PC project path — inspects trees, greps code, performs surgical file edits, writes new modules, and runs tests/git commands just like Claude Code.",
        "system_prompt": (
            "You are the Prebuilt Programmer Agent (Claude Code Mode). Your primary workspace is the user's "
            "saved PC project directory. Always:\n"
            "1. Inspect the project structure and read target files before making edits.\n"
            "2. Use `code_workspace` operations (`read_file`, `edit_file`, `multi_edit_file`, `write_file`, `grep_search`, `glob_files`, `run_in_project`) to implement production-grade code.\n"
            "3. Never leave placeholder TODOs; write complete, working implementations.\n"
            "4. Run syntax checks or tests inside the project directory via `run_in_project` after editing."
        ),
        "structure_template": (
            "1. **Codebase Analysis & Root Cause**\n"
            "2. **Files Created / Modified (with Diff Summary)**\n"
            "3. **Test & Command Verification Output**"
        ),
        "preferred_model": settings.AGENT_MODEL,
        "attached_skills": ["claude-code-workflow", "clean-architecture", "python-async-pro", "test-driven-dev"],
        "is_active": 0,
    },
    {
        "slug": "planner",
        "name": "Software Architect & Planner",
        "role_title": "Principal Systems Architect & Technical Product Planner",
        "description": "Prebuilt planning agent that inspects your PC project directory, designs system architecture, breaks features into concrete milestones, and saves structured `plan.md` roadmaps.",
        "system_prompt": (
            "You are the Prebuilt Planner & Software Architect Agent. When given a feature request or project path:\n"
            "1. Explore the existing codebase tree and key configuration files using `code_workspace`.\n"
            "2. Identify architectural dependencies, edge cases, data models, and API contracts.\n"
            "3. Produce a step-by-step implementation blueprint with file-by-file change specs and verification criteria.\n"
            "4. When requested, save the blueprint directly to `plan.md` in the project directory or spawn the `programmer` sub-agent to execute it."
        ),
        "structure_template": (
            "1. **Architectural Overview & Scope**\n"
            "2. **Component & Data Model Design**\n"
            "3. **Step-by-Step Implementation Checklist (File-by-File)**\n"
            "4. **Risks, Edge Cases & Verification Plan**"
        ),
        "preferred_model": settings.AGENT_MODEL,
        "attached_skills": ["clean-architecture", "claude-code-workflow"],
        "is_active": 0,
    },
    {
        "slug": "reviewer",
        "name": "Code Reviewer & Security Auditor",
        "role_title": "Staff Code Reviewer & AppSec Engineer",
        "description": "Prebuilt review agent that audits git diffs and project files for bugs, race conditions, security vulnerabilities, and performance bottlenecks.",
        "system_prompt": (
            "You are the Prebuilt Code Reviewer & Security Auditor Agent. Inspect the user's PC project directory, "
            "run `git diff` / `git status` via `code_workspace`, read modified files, and perform a rigorous review "
            "covering correctness, security, performance, and maintainability."
        ),
        "structure_template": (
            "1. **Review Verdict & Risk Score**\n"
            "2. **Critical & High-Priority Findings (File:Line)**\n"
            "3. **Concrete Patch Recommendations**"
        ),
        "preferred_model": settings.AGENT_MODEL,
        "attached_skills": ["security-auditor", "clean-architecture"],
        "is_active": 0,
    },
    {
        "slug": "debugger",
        "name": "Autonomous Debugger & Fixer",
        "role_title": "Root-Cause Diagnostics & Bug Resolution Specialist",
        "description": "Prebuilt debugging agent that reproduces errors in your PC project, traces stack frames, applies minimal surgical fixes, and verifies test suites pass.",
        "system_prompt": (
            "You are the Prebuilt Debugger Agent. Reproduce issues using `run_in_project`, trace stack traces using "
            "`grep_search` and `read_file`, apply targeted fixes with `edit_file`, and re-run the failing command or test until green."
        ),
        "structure_template": (
            "1. **Root Cause Diagnosis**\n"
            "2. **Surgical Fix Applied**\n"
            "3. **Reproduction & Test Verification**"
        ),
        "preferred_model": settings.AGENT_MODEL,
        "attached_skills": ["claude-code-workflow", "test-driven-dev"],
        "is_active": 0,
    },
    {
        "slug": "researcher",
        "name": "Deep Technical Researcher",
        "role_title": "Principal AI & Systems Research Analyst",
        "description": "Prebuilt research agent that synthesizes technical documentation, Vault memory, MCP knowledge sources, and codebase patterns into clear reports.",
        "system_prompt": (
            "You are the Prebuilt Technical Researcher Agent. Gather evidence across the Project Knowledge Vault, "
            "connected MCP servers, and local project files to provide thorough, well-structured technical answers."
        ),
        "structure_template": (
            "1. **Key Findings & Synthesis**\n"
            "2. **Detailed Comparison / Deep Dive**\n"
            "3. **Actionable Recommendations**"
        ),
        "preferred_model": settings.AGENT_MODEL,
        "attached_skills": ["clean-architecture"],
        "is_active": 0,
    },
]


# =====================================================================
# 2. Pre-configured External PC CLI Agents (Claude Code, Antigravity, Codex, Copilot)
# =====================================================================
PRECONFIGURED_CLI_AGENTS: List[Dict[str, Any]] = [
    {
        "slug": "claude_code",
        "name": "Claude Code CLI",
        "binary": "claude",
        "alt_binaries": ["claude.cmd", "claude.exe", "npx @anthropic-ai/claude-code"],
        "args_template": ["-p", "{prompt}", "--output-format", "text"],
        "auto_approve_args": ["--dangerously-skip-permissions"],
        "version_arg": "--version",
        "description": "Anthropic Claude Code CLI agent installed on PC (`claude -p`). Executes autonomous multi-file coding tasks in your project directory.",
    },
    {
        "slug": "antigravity",
        "name": "Antigravity Agent",
        "binary": "antigravity",
        "alt_binaries": ["agy", "antigravity.cmd", "antigravity.exe", "agy.cmd"],
        "args_template": ["-p", "{prompt}"],
        "auto_approve_args": ["--dangerously-skip-permissions"],
        "version_arg": "--version",
        "description": "Antigravity AI coding agent installed on PC. Runs agentic code generation and workspace tasks locally.",
    },
    {
        "slug": "codex",
        "name": "OpenAI Codex CLI",
        "binary": "codex",
        "alt_binaries": ["codex.cmd", "codex.exe", "npx @openai/codex"],
        "args_template": ["-q", "{prompt}"],
        "auto_approve_args": ["--approval-mode", "full-auto"],
        "version_arg": "--version",
        "description": "OpenAI Codex CLI agent installed on PC (`codex -q`). Runs local terminal and code editing tasks.",
    },
    {
        "slug": "github_copilot",
        "name": "GitHub Copilot CLI",
        "binary": "gh",
        "alt_binaries": ["copilot", "github-copilot-cli", "gh.exe"],
        "args_template": ["copilot", "suggest", "-t", "shell", "{prompt}"],
        "auto_approve_args": [],
        "version_arg": "--version",
        "description": "GitHub Copilot CLI (`gh copilot` / `copilot`) installed on PC for command & code suggestions and explanations.",
    },
]


class AgentAndWorkspaceManager:
    """
    Phase 8.1: Unified Manager for:
    1. Saved PC Project Paths & Claude Code File/Code Operations (`CodeWorkspaceEngine`)
    2. Prebuilt & Custom Persona Agents (`programmer`, `planner`, `reviewer`, `debugger`, `researcher`, etc.)
    3. Autonomous Sub-Agent Spawning (`spawn_subagent`, `spawn_parallel_subagents`)
    4. External Local PC CLI Agents (`claude_code`, `antigravity`, `codex`, `github_copilot`, + custom CLI agents)
    """

    def __init__(self, db_path: Path = DB_PATH, data_dir: Optional[Path] = None):
        self.db_path = db_path
        self.data_dir = data_dir or settings.VAULT_DATA_DIR
        self._init_db()
        self._seed_defaults()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 1. PC Project Workspaces table (stores paths on the user's PC)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS pc_workspaces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    tech_stack TEXT DEFAULT '',
                    git_branch TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    is_active INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # 2. Prebuilt & Custom Persona Agents table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    role_title TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    system_prompt TEXT NOT NULL,
                    structure_template TEXT DEFAULT '',
                    preferred_model TEXT DEFAULT '',
                    attached_skills_json TEXT DEFAULT '[]',
                    project_path TEXT DEFAULT '',
                    is_builtin INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # 3. External Local PC CLI Agents table (Claude Code, Antigravity, Codex, GitHub Copilot, etc.)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS external_cli_agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    binary TEXT NOT NULL,
                    alt_binaries_json TEXT DEFAULT '[]',
                    args_template_json TEXT DEFAULT '[]',
                    auto_approve_args_json TEXT DEFAULT '[]',
                    env_json TEXT DEFAULT '{}',
                    default_project_path TEXT DEFAULT '',
                    auto_approve INTEGER DEFAULT 0,
                    version_arg TEXT DEFAULT '--version',
                    description TEXT DEFAULT '',
                    is_builtin INTEGER DEFAULT 0,
                    enabled INTEGER DEFAULT 1,
                    last_detected_path TEXT DEFAULT '',
                    last_version TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # 4. Sub-Agent & CLI Execution History table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS subagent_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_type TEXT DEFAULT 'subagent',
                    agent_slug TEXT NOT NULL,
                    task TEXT NOT NULL,
                    project_path TEXT DEFAULT '',
                    status TEXT DEFAULT 'completed',
                    result_summary TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def _seed_defaults(self) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()

            for ag in PREBUILT_AGENTS:
                cursor.execute("SELECT id FROM agents WHERE slug = ?", (ag["slug"],))
                if not cursor.fetchone():
                    cursor.execute(
                        """
                        INSERT INTO agents (
                            slug, name, role_title, description, system_prompt,
                            structure_template, preferred_model, attached_skills_json,
                            is_builtin, is_active
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                        """,
                        (
                            ag["slug"],
                            ag["name"],
                            ag["role_title"],
                            ag["description"],
                            ag["system_prompt"],
                            ag["structure_template"],
                            ag["preferred_model"],
                            json.dumps(ag["attached_skills"]),
                            ag["is_active"],
                        ),
                    )

            for cli in PRECONFIGURED_CLI_AGENTS:
                cursor.execute("SELECT id FROM external_cli_agents WHERE slug = ?", (cli["slug"],))
                if not cursor.fetchone():
                    cursor.execute(
                        """
                        INSERT INTO external_cli_agents (
                            slug, name, binary, alt_binaries_json, args_template_json,
                            auto_approve_args_json, version_arg, description, is_builtin, enabled, auto_approve
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1)
                        """,
                        (
                            cli["slug"],
                            cli["name"],
                            cli["binary"],
                            json.dumps(cli["alt_binaries"]),
                            json.dumps(cli["args_template"]),
                            json.dumps(cli["auto_approve_args"]),
                            cli["version_arg"],
                            cli["description"],
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE external_cli_agents
                        SET auto_approve_args_json = ?,
                            alt_binaries_json = ?,
                            auto_approve = 1
                        WHERE slug = ? AND is_builtin = 1
                        """,
                        (
                            json.dumps(cli["auto_approve_args"]),
                            json.dumps(cli["alt_binaries"]),
                            cli["slug"],
                        ),
                    )

            conn.commit()

    # =====================================================================
    # PART A: PC Project Path Saving & Claude Code File/Workspace Operations
    # =====================================================================
    def set_project_path(
        self,
        path_str: str,
        name: Optional[str] = None,
        create_if_missing: bool = False,
        bind_to_active_agent: bool = True,
    ) -> Dict[str, Any]:
        """
        Saves a project path on the user's PC, sets it as the active coding workspace,
        and optionally binds it to the currently active agent.
        """
        raw_cleaned = path_str.strip().strip("'\"")
        if not raw_cleaned:
            return {"status": "error", "error": "Project path cannot be empty."}

        target_path = Path(raw_cleaned).expanduser()
        try:
            target_path = target_path.resolve()
        except Exception:
            pass

        if not target_path.exists():
            if create_if_missing:
                try:
                    target_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    return {"status": "error", "error": f"Could not create directory '{target_path}': {e}"}
            else:
                return {
                    "status": "error",
                    "error": f"Directory does not exist on PC: '{target_path}'. Pass create_if_missing=True to create it.",
                }

        if not target_path.is_dir():
            return {"status": "error", "error": f"Path is not a directory: '{target_path}'"}

        proj_name = name or target_path.name or "pc_project"
        slug = slugify_identifier(proj_name, default="pc_project")
        detected_stack = self._detect_tech_stack(target_path)
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE pc_workspaces SET is_active = 0")
            cursor.execute("SELECT id FROM pc_workspaces WHERE slug = ? OR local_path = ?", (slug, str(target_path)))
            existing = cursor.fetchone()
            if existing:
                cursor.execute(
                    """
                    UPDATE pc_workspaces
                    SET name = ?, local_path = ?, tech_stack = ?, is_active = 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (proj_name, str(target_path), detected_stack, now_str, existing["id"]),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO pc_workspaces (slug, name, local_path, tech_stack, is_active)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (slug, proj_name, str(target_path), detected_stack),
                )

            if bind_to_active_agent:
                cursor.execute(
                    "UPDATE agents SET project_path = ?, updated_at = ? WHERE is_active = 1",
                    (str(target_path), now_str),
                )

            conn.commit()

        tree_info = self.inspect_tree(str(target_path), max_depth=2)
        return {
            "status": "saved_and_activated",
            "slug": slug,
            "name": proj_name,
            "local_path": str(target_path),
            "tech_stack": detected_stack,
            "file_count": tree_info.get("total_files", 0),
            "tree_preview": tree_info.get("tree", "")[:1500],
        }

    @staticmethod
    def _detect_tech_stack(root: Path) -> str:
        indicators = []
        if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
            indicators.append("Python")
        if (root / "package.json").exists():
            indicators.append("Node.js/TypeScript")
        if (root / "Cargo.toml").exists():
            indicators.append("Rust")
        if (root / "go.mod").exists():
            indicators.append("Go")
        if (root / "Dockerfile").exists() or (root / "docker-compose.yml").exists():
            indicators.append("Docker")
        if (root / ".git").exists():
            indicators.append("Git")
        return ", ".join(indicators) if indicators else "General Codebase"

    def get_active_project_path(self) -> Optional[str]:
        """Returns the bound PC project path for the active agent or the active PC workspace."""
        active_agent = self.get_active_agent()
        if active_agent and active_agent.get("project_path"):
            p = Path(active_agent["project_path"])
            if p.exists() and p.is_dir():
                return str(p)

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT local_path FROM pc_workspaces WHERE is_active = 1 ORDER BY updated_at DESC LIMIT 1")
            row = cursor.fetchone()
            if row and row["local_path"]:
                return row["local_path"]

            cursor.execute("SELECT local_path FROM pc_workspaces ORDER BY updated_at DESC LIMIT 1")
            row2 = cursor.fetchone()
            if row2 and row2["local_path"]:
                return row2["local_path"]

        return None

    def list_workspaces(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pc_workspaces ORDER BY is_active DESC, updated_at DESC")
            return [dict(r) for r in cursor.fetchall()]

    def switch_workspace(self, name_or_slug_or_path: str) -> Dict[str, Any]:
        cleaned = name_or_slug_or_path.strip()
        slug = slugify_identifier(cleaned, default="")
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM pc_workspaces WHERE slug = ? OR LOWER(name) = LOWER(?) OR local_path = ?",
                (slug, cleaned, cleaned),
            )
            row = cursor.fetchone()
            if row:
                ws = dict(row)
                cursor.execute("UPDATE pc_workspaces SET is_active = 0")
                cursor.execute("UPDATE pc_workspaces SET is_active = 1 WHERE id = ?", (ws["id"],))
                cursor.execute("UPDATE agents SET project_path = ? WHERE is_active = 1", (ws["local_path"],))
                conn.commit()
                ws["is_active"] = 1
                return {"status": "switched", "workspace": ws}

        # If not found in DB, treat as a new PC directory path
        return self.set_project_path(cleaned)

    def _resolve_target_file(self, file_path: str, explicit_root: Optional[str] = None) -> Path:
        root_str = explicit_root or self.get_active_project_path()
        p = Path(file_path).expanduser()
        if p.is_absolute():
            return p.resolve()
        if root_str:
            return (Path(root_str) / p).resolve()
        return (Path.cwd() / p).resolve()

    def inspect_tree(self, path_str: Optional[str] = None, max_depth: int = 3, max_entries: int = 200) -> Dict[str, Any]:
        """Generates a directory tree of the active PC project workspace (like Claude Code `LS`/`Tree`)."""
        root_str = path_str or self.get_active_project_path()
        if not root_str:
            return {
                "status": "error",
                "error": "No active PC project path set. Use set_project_path or `/workspace <path>` first.",
            }
        root = Path(root_str)
        if not root.exists() or not root.is_dir():
            return {"status": "error", "error": f"Project path does not exist: {root}"}

        lines: List[str] = [f"📁 {root.name}/ ({root})"]
        total_files = 0
        total_dirs = 0

        def _walk(current: Path, prefix: str, depth: int):
            nonlocal total_files, total_dirs
            if depth > max_depth or len(lines) >= max_entries:
                return
            try:
                entries = sorted(
                    [e for e in current.iterdir() if e.name not in IGNORED_DIRS],
                    key=lambda x: (not x.is_dir(), x.name.lower()),
                )
            except PermissionError:
                return

            for idx, entry in enumerate(entries):
                if len(lines) >= max_entries:
                    lines.append(f"{prefix}... (truncated)")
                    return
                is_last = idx == len(entries) - 1
                connector = "└── " if is_last else "├── "
                if entry.is_dir():
                    total_dirs += 1
                    lines.append(f"{prefix}{connector}📂 {entry.name}/")
                    next_prefix = prefix + ("    " if is_last else "│   ")
                    _walk(entry, next_prefix, depth + 1)
                else:
                    total_files += 1
                    lines.append(f"{prefix}{connector}{entry.name}")

        _walk(root, "", 1)
        return {
            "status": "success",
            "project_path": str(root),
            "total_files": total_files,
            "total_dirs": total_dirs,
            "tree": "\n".join(lines),
        }

    def read_file(
        self,
        file_path: str,
        start_line: int = 1,
        end_line: int = 300,
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reads a file in the PC project with 1-indexed line numbers (like Claude Code `Read`)."""
        target = self._resolve_target_file(file_path, explicit_root=project_path)
        if not target.exists():
            return {"status": "error", "error": f"File not found: {target}"}
        if not target.is_file():
            return {"status": "error", "error": f"Path is not a file: {target}"}

        try:
            text = target.read_text(encoding="utf-8", errors="replace")
            all_lines = text.splitlines()
            total = len(all_lines)
            s_idx = max(1, start_line)
            e_idx = min(total, max(s_idx, end_line))
            selected = all_lines[s_idx - 1 : e_idx]
            numbered = "\n".join(f"{i}: {line}" for i, line in enumerate(selected, start=s_idx))
            return {
                "status": "success",
                "file_path": str(target),
                "total_lines": total,
                "start_line": s_idx,
                "end_line": e_idx,
                "content": numbered,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def write_file(
        self,
        file_path: str,
        content: str,
        create_dirs: bool = True,
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates or overwrites a file in the PC project workspace and returns a unified diff."""
        target = self._resolve_target_file(file_path, explicit_root=project_path)
        try:
            if create_dirs:
                target.parent.mkdir(parents=True, exist_ok=True)
            old_lines = (
                target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                if target.exists()
                else []
            )
            existed = target.exists()
            target.write_text(content, encoding="utf-8")
            new_lines = content.splitlines(keepends=True)
            diff_str = "".join(
                difflib.unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=f"a/{target.name}" if existed else "/dev/null",
                    tofile=f"b/{target.name}",
                    n=3,
                )
            )
            return {
                "status": "updated" if existed else "created",
                "file_path": str(target),
                "lines_written": len(new_lines),
                "diff": diff_str[:4000],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def edit_file(
        self,
        file_path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Surgical search-and-replace file editor (like Claude Code `Edit`).
        Verifies `old_text` exists, replaces it with `new_text`, saves the file, and returns the unified diff.
        """
        target = self._resolve_target_file(file_path, explicit_root=project_path)
        if not target.exists() or not target.is_file():
            return {"status": "error", "error": f"File not found: {target}"}
        if not old_text:
            return {"status": "error", "error": "old_text cannot be empty for edit_file."}

        try:
            original = target.read_text(encoding="utf-8")
        except Exception as e:
            return {"status": "error", "error": f"Could not read file: {e}"}

        occurrences = original.count(old_text)
        if occurrences == 0:
            return {
                "status": "error",
                "error": f"old_text was not found in '{target.name}'. Read the file first to verify exact lines and indentation.",
            }
        if occurrences > 1 and not replace_all:
            return {
                "status": "error",
                "error": (
                    f"old_text matched {occurrences} locations in '{target.name}'. "
                    f"Include more surrounding context lines to make it unique, or set replace_all=True."
                ),
            }

        updated = original.replace(old_text, new_text) if replace_all else original.replace(old_text, new_text, 1)
        target.write_text(updated, encoding="utf-8")

        diff_str = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"a/{target.name}",
                tofile=f"b/{target.name}",
                n=3,
            )
        )
        return {
            "status": "edited",
            "file_path": str(target),
            "replacements": occurrences if replace_all else 1,
            "diff": diff_str[:4000],
        }

    def multi_edit_file(
        self,
        file_path: str,
        edits: List[Dict[str, str]],
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Applies multiple sequential edits (`[{'old_text': ..., 'new_text': ...}]`) atomically to a single file."""
        target = self._resolve_target_file(file_path, explicit_root=project_path)
        if not target.exists() or not target.is_file():
            return {"status": "error", "error": f"File not found: {target}"}

        try:
            original = target.read_text(encoding="utf-8")
        except Exception as e:
            return {"status": "error", "error": str(e)}

        working = original
        applied = 0
        for idx, ed in enumerate(edits):
            o_txt = ed.get("old_text", "")
            n_txt = ed.get("new_text", "")
            if not o_txt or o_txt not in working:
                return {
                    "status": "error",
                    "error": f"Edit #{idx + 1} failed: old_text not found in {target.name}. No changes were written.",
                }
            working = working.replace(o_txt, n_txt, 1)
            applied += 1

        target.write_text(working, encoding="utf-8")
        diff_str = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                working.splitlines(keepends=True),
                fromfile=f"a/{target.name}",
                tofile=f"b/{target.name}",
                n=3,
            )
        )
        return {
            "status": "edited",
            "file_path": str(target),
            "edits_applied": applied,
            "diff": diff_str[:4000],
        }

    def grep_search(
        self,
        pattern: str,
        file_glob: str = "*",
        case_sensitive: bool = False,
        max_results: int = 50,
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Searches across files in the PC project workspace for regex/text matches (like Claude Code `Grep`)."""
        root_str = project_path or self.get_active_project_path()
        if not root_str:
            return {"status": "error", "error": "No active PC project path set."}
        root = Path(root_str)
        if not root.exists():
            return {"status": "error", "error": f"Project path not found: {root}"}

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error:
            regex = re.compile(re.escape(pattern), flags)

        matches: List[Dict[str, Any]] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
            for fname in filenames:
                if file_glob != "*" and not fnmatch.fnmatch(fname, file_glob):
                    continue
                fpath = Path(dirpath) / fname
                try:
                    if fpath.stat().st_size > 2_000_000:
                        continue
                    text = fpath.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                for line_no, line in enumerate(text.splitlines(), start=1):
                    if regex.search(line):
                        rel = str(fpath.relative_to(root))
                        matches.append({"file": rel, "line": line_no, "text": line.strip()[:250]})
                        if len(matches) >= max_results:
                            return {
                                "status": "success",
                                "project_path": str(root),
                                "matches_count": len(matches),
                                "truncated": True,
                                "matches": matches,
                            }

        return {
            "status": "success",
            "project_path": str(root),
            "matches_count": len(matches),
            "truncated": False,
            "matches": matches,
        }

    def glob_files(
        self,
        pattern: str = "**/*",
        max_results: int = 100,
        project_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Finds files by glob pattern inside the PC project path (like Claude Code `Glob`)."""
        root_str = project_path or self.get_active_project_path()
        if not root_str:
            return {"status": "error", "error": "No active PC project path set."}
        root = Path(root_str)
        if not root.exists():
            return {"status": "error", "error": f"Project path not found: {root}"}

        results: List[str] = []
        for p in root.glob(pattern):
            if any(part in IGNORED_DIRS for part in p.parts):
                continue
            if p.is_file():
                results.append(str(p.relative_to(root)))
                if len(results) >= max_results:
                    break
        return {"status": "success", "project_path": str(root), "count": len(results), "files": results}

    async def run_in_project(
        self,
        command: str,
        project_path: Optional[str] = None,
        timeout_seconds: int = 60,
    ) -> Dict[str, Any]:
        """Executes a shell/PowerShell/bash command directly inside the saved PC project directory."""
        cwd_str = project_path or self.get_active_project_path()
        if not cwd_str:
            return {"status": "error", "error": "No active PC project path set. Set a project path first."}
        cwd = Path(cwd_str)
        if not cwd.exists() or not cwd.is_dir():
            return {"status": "error", "error": f"Project directory does not exist: {cwd}"}

        is_windows = platform.system().lower().startswith("win")
        try:
            if is_windows and shutil.which("powershell.exe"):
                # In PowerShell, invoking an executable path with quotes requires the call operator (&)
                ps_command = command.strip()
                if ps_command.startswith('"') and not ps_command.startswith('&'):
                    ps_command = f"& {ps_command}"
                proc = await asyncio.create_subprocess_exec(
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    ps_command,
                    cwd=str(cwd),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    cwd=str(cwd),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                proc.kill()
                return {"status": "timeout", "cwd": str(cwd), "error": f"Command timed out after {timeout_seconds}s"}

            return {
                "status": "success" if proc.returncode == 0 else "failed",
                "exit_code": proc.returncode,
                "cwd": str(cwd),
                "stdout": stdout_b.decode("utf-8", errors="replace").strip()[:8000],
                "stderr": stderr_b.decode("utf-8", errors="replace").strip()[:4000],
            }
        except Exception as e:
            return {"status": "error", "cwd": str(cwd), "error": str(e)}

    # =====================================================================
    # PART B: Prebuilt & Custom Persona Agents Management
    # =====================================================================
    def _agent_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        try:
            d["attached_skills"] = json.loads(d.get("attached_skills_json") or "[]")
        except Exception:
            d["attached_skills"] = []
        d["is_builtin"] = bool(d.get("is_builtin", 0))
        d["is_active"] = bool(d.get("is_active", 0))
        return d

    def list_agents(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM agents ORDER BY is_active DESC, is_builtin DESC, id ASC")
            return [self._agent_row_to_dict(r) for r in cursor.fetchall()]

    def get_agent(self, name_or_slug: str) -> Optional[Dict[str, Any]]:
        if not name_or_slug:
            return None
        slug = slugify_identifier(name_or_slug, default="")
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM agents WHERE slug = ? OR LOWER(name) = LOWER(?)",
                (slug, name_or_slug.strip()),
            )
            row = cursor.fetchone()
            return self._agent_row_to_dict(row) if row else None

    def get_active_agent(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM agents WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            if row:
                return self._agent_row_to_dict(row)
            cursor.execute("SELECT * FROM agents WHERE slug = 'manager' LIMIT 1")
            row2 = cursor.fetchone()
            return self._agent_row_to_dict(row2) if row2 else PREBUILT_AGENTS[0]

    def switch_agent(self, name_or_slug: str, project_path: Optional[str] = None) -> Dict[str, Any]:
        ag = self.get_agent(name_or_slug)
        if not ag:
            return {
                "status": "not_found",
                "error": f"Agent '{name_or_slug}' not found. Available: {[a['slug'] for a in self.list_agents()]}",
            }
        slug = ag["slug"]
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE agents SET is_active = 0")
            if project_path:
                cursor.execute(
                    "UPDATE agents SET is_active = 1, project_path = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
                    (project_path, slug),
                )
            else:
                cursor.execute(
                    "UPDATE agents SET is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
                    (slug,),
                )
            conn.commit()

        if project_path:
            self.set_project_path(project_path, bind_to_active_agent=True)

        updated = self.get_agent(slug) or ag
        return {"status": "switched", "agent": updated}

    def create_or_update_agent(
        self,
        name: str,
        system_prompt: str,
        role_title: str = "Specialized AI Agent",
        description: str = "",
        structure_template: str = "",
        preferred_model: str = "",
        attached_skills: Optional[List[str]] = None,
        project_path: str = "",
        activate: bool = False,
    ) -> Dict[str, Any]:
        slug = slugify_identifier(name)
        skills_json = json.dumps(attached_skills or [], ensure_ascii=False)
        model = preferred_model or settings.AGENT_MODEL
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM agents WHERE slug = ?", (slug,))
            existing = cursor.fetchone()
            if existing:
                cursor.execute(
                    """
                    UPDATE agents
                    SET name = ?, role_title = ?, description = ?, system_prompt = ?,
                        structure_template = ?, preferred_model = ?, attached_skills_json = ?,
                        project_path = ?, updated_at = ?
                    WHERE slug = ?
                    """,
                    (
                        name,
                        role_title or existing["role_title"],
                        description or existing["description"],
                        system_prompt,
                        structure_template or existing["structure_template"],
                        model,
                        skills_json if attached_skills is not None else existing["attached_skills_json"],
                        project_path or existing["project_path"],
                        now_str,
                        slug,
                    ),
                )
                status = "updated"
            else:
                cursor.execute(
                    """
                    INSERT INTO agents (
                        slug, name, role_title, description, system_prompt,
                        structure_template, preferred_model, attached_skills_json,
                        project_path, is_builtin, is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
                    """,
                    (
                        slug,
                        name,
                        role_title,
                        description or f"Custom agent: {name}",
                        system_prompt,
                        structure_template,
                        model,
                        skills_json,
                        project_path,
                    ),
                )
                status = "created"
            conn.commit()

        if activate:
            self.switch_agent(slug, project_path=project_path or None)

        ag = self.get_agent(slug) or {}
        ag["status"] = status
        return ag

    def delete_agent(self, name_or_slug: str) -> Dict[str, Any]:
        ag = self.get_agent(name_or_slug)
        if not ag:
            return {"status": "not_found", "error": f"Agent '{name_or_slug}' not found."}
        if ag.get("is_builtin"):
            return {"status": "error", "error": f"Cannot delete prebuilt agent '{ag['slug']}'."}
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM agents WHERE slug = ?", (ag["slug"],))
            if ag.get("is_active"):
                cursor.execute("UPDATE agents SET is_active = 1 WHERE slug = 'manager'")
            conn.commit()
        return {"status": "deleted", "slug": ag["slug"]}

    def build_active_agent_prompt_context(self, user_prompt: str = "") -> str:
        """
        Builds the dynamic system prompt addendum combining:
        - Active Persona Agent role, instructions & output structure
        - Bound PC Project Path (if configured)
        - Triggered & attached Skills from SkillsManager
        """
        ag = self.get_active_agent()
        active_path = self.get_active_project_path()
        parts: List[str] = []

        parts.append(
            f"\n### Active Agent Persona: {ag['name']} (`{ag['slug']}`) — {ag.get('role_title', '')}\n"
            f"{ag.get('system_prompt', '')}"
        )
        if ag.get("structure_template"):
            parts.append(f"\n#### Expected Response Structure:\n{ag['structure_template']}")

        if active_path:
            parts.append(
                f"\n### Active PC Project Workspace:\n"
                f"- **Saved Local PC Path:** `{active_path}`\n"
                f"- You can read, edit, create, search files, and run terminal/test commands in this directory using `code_workspace` or delegate to external CLI agents (`run_external_cli_agent`)."
            )

        skills_block = skills_manager.build_skills_prompt_block(
            prompt=user_prompt,
            explicit_skills=ag.get("attached_skills") or [],
        )
        if skills_block:
            parts.append(skills_block)

        return "\n".join(parts)

    # =====================================================================
    # PART C: External Local PC CLI Agents (Claude Code, Antigravity, Codex, Copilot)
    # =====================================================================
    def _cli_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        for key, target in (
            ("alt_binaries_json", "alt_binaries"),
            ("args_template_json", "args_template"),
            ("auto_approve_args_json", "auto_approve_args"),
        ):
            try:
                d[target] = json.loads(d.get(key) or "[]")
            except Exception:
                d[target] = []
        try:
            d["env"] = json.loads(d.get("env_json") or "{}")
        except Exception:
            d["env"] = {}
        d["auto_approve"] = bool(d.get("auto_approve", 0))
        d["enabled"] = bool(d.get("enabled", 1))
        d["is_builtin"] = bool(d.get("is_builtin", 0))
        return d

    def list_cli_agents(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM external_cli_agents ORDER BY is_builtin DESC, id ASC")
            return [self._cli_row_to_dict(r) for r in cursor.fetchall()]

    def get_cli_agent(self, name_or_slug: str) -> Optional[Dict[str, Any]]:
        if not name_or_slug:
            return None
        slug = slugify_identifier(name_or_slug, default="")
        aliases = {
            "claude": "claude_code",
            "claudecode": "claude_code",
            "claude-code": "claude_code",
            "agy": "antigravity",
            "openai_codex": "codex",
            "copilot": "github_copilot",
            "gh_copilot": "github_copilot",
            "gh-copilot": "github_copilot",
        }
        resolved_slug = aliases.get(slug, slug)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM external_cli_agents WHERE slug = ? OR LOWER(name) = LOWER(?) OR LOWER(binary) = LOWER(?)",
                (resolved_slug, name_or_slug.strip(), name_or_slug.strip()),
            )
            row = cursor.fetchone()
            return self._cli_row_to_dict(row) if row else None

    def register_or_update_cli_agent(
        self,
        name: str,
        binary: str,
        args_template: Optional[List[str]] = None,
        auto_approve_args: Optional[List[str]] = None,
        default_project_path: str = "",
        auto_approve: bool = False,
        env: Optional[Dict[str, str]] = None,
        description: str = "",
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """Creates or updates an external CLI agent configuration (e.g. Claude Code, Antigravity, Codex, Copilot, Aider)."""
        slug = slugify_identifier(name, default="custom_cli")
        existing = self.get_cli_agent(slug)
        args_list = args_template if args_template is not None else (existing["args_template"] if existing else ["-p", "{prompt}"])
        approve_list = auto_approve_args if auto_approve_args is not None else (existing["auto_approve_args"] if existing else [])
        env_dict = env if env is not None else (existing["env"] if existing else {})
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_conn() as conn:
            cursor = conn.cursor()
            if existing:
                cursor.execute(
                    """
                    UPDATE external_cli_agents
                    SET name = ?, binary = ?, args_template_json = ?, auto_approve_args_json = ?,
                        env_json = ?, default_project_path = ?, auto_approve = ?,
                        description = ?, enabled = ?, updated_at = ?
                    WHERE slug = ?
                    """,
                    (
                        name or existing["name"],
                        binary or existing["binary"],
                        json.dumps(args_list, ensure_ascii=False),
                        json.dumps(approve_list, ensure_ascii=False),
                        json.dumps(env_dict, ensure_ascii=False),
                        default_project_path or existing["default_project_path"],
                        1 if auto_approve else 0,
                        description or existing["description"],
                        1 if enabled else 0,
                        now_str,
                        existing["slug"],
                    ),
                )
                status = "updated"
                slug = existing["slug"]
            else:
                cursor.execute(
                    """
                    INSERT INTO external_cli_agents (
                        slug, name, binary, args_template_json, auto_approve_args_json,
                        env_json, default_project_path, auto_approve, description, is_builtin, enabled
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        slug,
                        name,
                        binary,
                        json.dumps(args_list, ensure_ascii=False),
                        json.dumps(approve_list, ensure_ascii=False),
                        json.dumps(env_dict, ensure_ascii=False),
                        default_project_path,
                        1 if auto_approve else 0,
                        description or f"External PC CLI Agent ({binary})",
                        1 if enabled else 0,
                    ),
                )
                status = "created"
            conn.commit()

        res = self.get_cli_agent(slug) or {}
        res["status"] = status
        return res

    def remove_cli_agent(self, name_or_slug: str) -> Dict[str, Any]:
        cli = self.get_cli_agent(name_or_slug)
        if not cli:
            return {"status": "not_found", "error": f"CLI agent '{name_or_slug}' not found."}
        if cli.get("is_builtin"):
            return {"status": "error", "error": f"Cannot delete built-in CLI profile '{cli['slug']}'. You can disable or update its binary path instead."}
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM external_cli_agents WHERE slug = ?", (cli["slug"],))
            conn.commit()
        return {"status": "deleted", "slug": cli["slug"]}

    def _resolve_cli_binary(self, cli_agent: Dict[str, Any]) -> Optional[str]:
        """Locates the executable binary on the host PC across PATH and common npm/user bin folders."""
        candidates = [cli_agent["binary"]] + [b for b in cli_agent.get("alt_binaries", []) if " " not in b]
        extra_search_dirs = [
            Path.home() / ".local" / "bin",
            Path.home() / ".npm-global" / "bin",
            Path(os.environ.get("APPDATA", "")) / "npm",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Antigravity" / "bin",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "claude-code",
        ]
        path_env = os.environ.get("PATH", "")
        augmented_path = os.pathsep.join([path_env] + [str(d) for d in extra_search_dirs if d.exists()])

        for cand in candidates:
            if not cand:
                continue
            p = Path(cand).expanduser()
            if p.is_absolute() and p.exists():
                return str(p)
            found = shutil.which(cand, path=augmented_path)
            if found:
                return found
        return None

    async def detect_installed_cli_agents(self) -> List[Dict[str, Any]]:
        """Probes the PC for installed CLI coding agents (`claude`, `antigravity`, `codex`, `gh`, etc.) and their versions."""
        agents = self.list_cli_agents()
        results: List[Dict[str, Any]] = []

        for cli in agents:
            resolved_bin = self._resolve_cli_binary(cli)
            version_str = ""
            installed = resolved_bin is not None

            if installed and resolved_bin:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        resolved_bin,
                        cli.get("version_arg") or "--version",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=6)
                    raw_v = (out_b or err_b).decode("utf-8", errors="replace").strip()
                    version_str = raw_v.splitlines()[0][:80] if raw_v else "installed"
                except Exception:
                    version_str = "installed"

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE external_cli_agents SET last_detected_path = ?, last_version = ? WHERE slug = ?",
                    (resolved_bin or "", version_str, cli["slug"]),
                )
                conn.commit()

            item = dict(cli)
            item["installed"] = installed
            item["detected_path"] = resolved_bin or ""
            item["version"] = version_str
            results.append(item)

        return results

    async def run_external_cli_agent(
        self,
        agent_name: str,
        prompt: str,
        project_path: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
        auto_approve: Optional[bool] = None,
        timeout_seconds: int = 240,
    ) -> Dict[str, Any]:
        """
        Executes a task using an external CLI agent installed on the user's PC
        (`claude_code`, `antigravity`, `codex`, `github_copilot`, or custom CLI)
        inside the target PC `project_path`.
        """
        cli = self.get_cli_agent(agent_name)
        if not cli:
            return {
                "status": "not_found",
                "error": f"External CLI agent '{agent_name}' is not registered. Available: {[c['slug'] for c in self.list_cli_agents()]}",
            }
        if not cli.get("enabled", True):
            return {"status": "disabled", "error": f"External CLI agent '{cli['name']}' is currently disabled."}

        target_cwd = project_path or cli.get("default_project_path") or self.get_active_project_path() or str(Path.cwd())
        cwd_path = Path(target_cwd).expanduser()
        if not cwd_path.exists() or not cwd_path.is_dir():
            cwd_path = Path.cwd()

        resolved_bin = self._resolve_cli_binary(cli)
        if not resolved_bin:
            return {
                "status": "not_installed",
                "agent": cli["slug"],
                "binary": cli["binary"],
                "cwd": str(cwd_path),
                "error": (
                    f"Executable '{cli['binary']}' for {cli['name']} was not found on your PC PATH. "
                    f"Install it or set its full binary path via `/cli set_binary {cli['slug']} <full_path>`."
                ),
            }

        # Build command arguments from template
        cmd_args: List[str] = []
        prompt_injected = False
        for token in cli.get("args_template") or []:
            if "{prompt}" in token:
                cmd_args.append(token.replace("{prompt}", prompt))
                prompt_injected = True
            elif "{project_path}" in token:
                cmd_args.append(token.replace("{project_path}", str(cwd_path)))
            else:
                cmd_args.append(token)
        if not prompt_injected and prompt:
            cmd_args.append(prompt)

        use_approve = auto_approve if auto_approve is not None else cli.get("auto_approve", True)
        if use_approve:
            for flag in cli.get("auto_approve_args") or []:
                if flag not in cmd_args:
                    cmd_args.append(flag)

        if extra_args:
            cmd_args.extend([str(a) for a in extra_args])

        env = os.environ.copy()
        for k, v in (cli.get("env") or {}).items():
            if v is not None:
                env[str(k)] = str(v)

        try:
            proc = await asyncio.create_subprocess_exec(
                resolved_bin,
                *cmd_args,
                cwd=str(cwd_path),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                proc.kill()
                return {
                    "status": "timeout",
                    "agent": cli["slug"],
                    "cwd": str(cwd_path),
                    "error": f"{cli['name']} timed out after {timeout_seconds}s.",
                }

            stdout_txt = stdout_b.decode("utf-8", errors="replace").strip()
            stderr_txt = stderr_b.decode("utf-8", errors="replace").strip()
            status_str = "success" if proc.returncode == 0 else "failed"

            self.log_run(
                run_type=f"cli:{cli['slug']}",
                agent_slug=cli["slug"],
                task=prompt[:500],
                project_path=str(cwd_path),
                status=status_str,
                result_summary=(stdout_txt or stderr_txt)[:1000],
            )

            return {
                "status": status_str,
                "agent": cli["slug"],
                "name": cli["name"],
                "binary": resolved_bin,
                "cwd": str(cwd_path),
                "exit_code": proc.returncode,
                "stdout": stdout_txt[:10000],
                "stderr": stderr_txt[:4000],
            }
        except Exception as e:
            return {"status": "error", "agent": cli["slug"], "cwd": str(cwd_path), "error": str(e)}

    # =====================================================================
    # PART D: Sub-Agent Logging & Tracking
    # =====================================================================
    def log_run(
        self,
        run_type: str,
        agent_slug: str,
        task: str,
        project_path: str = "",
        status: str = "completed",
        result_summary: str = "",
    ) -> Dict[str, Any]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO subagent_runs (run_type, agent_slug, task, project_path, status, result_summary)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_type, agent_slug, task, project_path, status, result_summary[:2000]),
            )
            conn.commit()
            cursor.execute("SELECT * FROM subagent_runs WHERE id = ?", (cursor.lastrowid,))
            return dict(cursor.fetchone())

    def list_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM subagent_runs ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]


agent_manager = AgentAndWorkspaceManager()
