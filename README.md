# Arush Manager Agent 🚀 (Complete Phases 1–8: Agents, Claude Code Workspace, Sub-Agents, CLI Agents, Skills & MCP)

Personal executive co-founder, hierarchical project knowledge vault, Claude Code local PC workspace editor, sub-agent & CLI agent orchestrator, skills registry, MCP client, freelance radar, creative studio, bio-tracker, and Windows PC automation agent powered by **9Router**, **aiogram 3.x**, and **OpenAI-compatible tool calling**.

---

## ✨ Implemented Capabilities (Phases 1–8)

| Phase | Module | Highlights |
|---|---|---|
| **Phase 1: Core & Gateway** | `bot/app.py`, `core/agent.py`, `core/router_client.py` | `aiogram 3.x` Telegram bot, Whitelist security middleware, 9Router multi-turn tool loop, 12K token safeguard, JPEG screen compression |
| **Phase 2: Knowledge Vault & Finance** | `tools/vault.py`, `tools/receipt_parser.py`, `tools/idea_incubator.py` | Hierarchical project workspaces (`data/projects/{slug}/context.md`, `specs.json`, `assets/`), Iranian bank receipt OCR/parser (`کارت به کارت`, `پایا`, `ساتنا`, `بلو`, `سامان`, `ملت`) with tracking code (`کد رهگیری`) deduplication, Voice Idea Incubator, and `/v1/embeddings` semantic vector search |
| **Phase 3: Freelance Radar** | `tools/freelance_radar.py` | Direct `.ir` `aiohttp` split-network client bypassing VPNs (`trust_env=False`), 10-min background poller for Karlancer, Ponisha & Telegram channels, AI portfolio matchmaker, and Persian proposal generator |
| **Phase 4: PC, Browser & GitHub** | `tools/computer_use.py`, `tools/browser_agent.py`, `tools/github_tool.py` | Multi-monitor DPI scaling, Telegram inline confirmation buttons (`[Confirm]`, `[Cancel]`) for sensitive actions, Playwright persistent Chrome profile automation, local Git CLI & GitHub REST API (PRs, Issues, Actions) |
| **Phase 5: Image Studio** | `tools/image_studio.py` | 9Router Cloud Image API (FLUX Schnell, DALL-E 3, Gemini Imagen) with aspect ratios + Local ComfyUI WebSocket (`ws://127.0.0.1:8188/ws`) workflow runner (`sdxl`, `flux_gguf`, `inpainting`, `controlnet_ui`) |
| **Phase 6: Life & Bio-Tracking** | `tools/life_tracker.py`, `core/scheduler.py` | Medical lab report PDF/text parser (CBC, vitamins, thyroid, metabolic) with `LOW`/`HIGH` flags, natural-language bio-logging (sleep, caffeine, headaches, workouts), 08:30 AM Morning Briefing & 10:30 PM Nightly Review |
| **Phase 7: Production Daemon & CI/CD** | `core/watchdog.py`, `scripts/`, `.github/workflows/` | Self-healing exponential backoff reconnect loop, `GET /health` HTTP server (`:8089`), online SQLite hot-backup with retention, Windows NSSM & Task Scheduler scripts, and GitHub Actions CI/CD/Release pipelines |
| **Phase 8: Agents, Claude Code Workspace, Sub-Agents, CLI Agents, Skills & MCP** | `tools/agent_manager.py`, `tools/skills_manager.py`, `tools/mcp_manager.py` | Prebuilt & custom persona agents (`programmer`, `planner`, `reviewer`, `debugger`, `researcher`, `manager`), persistent PC project path manager with full Claude Code operations (`inspect_tree`, `read_file`, surgical `edit_file` with diff, `multi_edit_file`, `write_file`, `grep_search`, `glob_files`, `run_in_project`), autonomous Sub-Agents, External PC CLI Agent Manager (`claude_code`, `antigravity`, `codex`, `github_copilot`), `SKILL.md` Skills registry, and Model Context Protocol (MCP) stdio/HTTP client |

---

## 📱 Telegram Bot Commands

### 🤖 Phase 8: Agents, PC Code Workspace, Sub-Agents, CLI Agents, Skills & MCP
* `/agents` — List & switch prebuilt agents (`programmer`, `planner`, `reviewer`, `debugger`, `researcher`, `manager`) or create custom agents (`/agents create <name> | <role> | <prompt>`)
* `/workspace <pc_path>` — Save & activate a local project directory on your PC (e.g. `/workspace D:\projects\my-app`) or inspect its tree (`/workspace tree`) for Claude Code-style file reading, editing, diffing, grep, and test execution
* `/subagent <role> <task>` — Spawn an autonomous specialized sub-agent (e.g. `/subagent programmer Fix authentication bug in auth.py`)
* `/cli` — Manage & run local CLI coding agents installed on your PC (`claude_code`, `antigravity`, `codex`, `github_copilot`, or custom CLIs via `/cli detect`, `/cli run <agent> <prompt>`, `/cli set_binary`, `/cli add`)
* `/skills` — View, toggle (`🟢/⚪`), or create reusable `SKILL.md` skills (`/skills add <name> | <triggers> | <instructions>`)
* `/mcp` — Manage stdio & HTTP MCP servers, install presets (`/mcp preset filesystem D:\projects`), import Claude `mcpServers` JSON (`/mcp import {...}`), discover tools (`/mcp discover <server>`), and execute MCP tools

### 🗂️ Phases 1–7: Core Commands
* `/start` & `/help` — Full system overview and command guide
* `/project <name>` & `/projects` — Manage project workspaces in the Knowledge Vault
* `/finance [week|month]` — Weekly (7-day) or monthly (30-day) income/expense ledger summary
* `/idea <text>` — Structure an idea in the Incubator (Core Concept, Feasibility 1–10, Tech Stack, Action Steps)
* `/search <query>` — Semantic vector search across all project artifacts
* `/radar` — Poll Karlancer, Ponisha, and Telegram freelance channels and display top matches with Persian proposals
* `/screenshot` — Capture live Windows desktop screenshot
* `/github [status|prs|ci]` — Check local Git status, open Pull Requests, or GitHub Actions CI/CD runs
* `/imagine <prompt>` — Generate images via 9Router or ComfyUI and receive directly in chat
* `/bio <note>` & `/lab <text>` — Log daily bio habits or parse blood test biomarkers
* `/briefing`, `/review`, `/backup`, `/status`, `/cancel` — Daily routines, hot backup, system health, and safety gate cancellation
