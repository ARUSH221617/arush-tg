# 📋 Arush Manager Agent — Master Architectural Plan

> **Mission:** Build a personal executive co-founder, knowledge vault, and Windows automation agent that runs locally 24/7, connects to Telegram (`@arush_agentbot`), routes models through **9Router**, and assists Arush across freelance platforms (Ponisha & Karlancer), projects, finances, habits, PC control, and automated GitHub CI/CD.

---

## 🏛️ System Architecture

```
                          [ You on Telegram ]
                                   │
                                   ▼
                   [ aiogram 3.x Telegram Gateway ]
                     (Whitelist Security Guard)
                                   │
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
      [ Text / Photos ]                          [ Voice Notes ]
              │                                         │
              │                                   [ 9Router STT ]
              │                             (Whisper / Groq / Gemini)
              ▼                                         ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                    Arush Agent Brain                        │
   │               (Model via 9Router Gateway)                   │
   │           e.g. ag/claude-sonnet-4-6 / gpt-4o                │
   └──────────────────────────────┬──────────────────────────────┘
                                  │  OpenAI-Compatible Tool Calls
      ┌───────────────────────────┼───────────────────────────┐
      ▼                           ▼                           ▼
[ Computer & OS ]        [ Knowledge Vault ]         [ External Services ]
├── PowerShell Tool      ├── Projects DB (SQLite)    ├── Ponisha (.ir direct)
├── Native GUI Clicker   ├── Artifacts & Screenshots ├── Karlancer (.ir direct)
├── Screen Capture (MSS) ├── Financial Ledger        ├── 9Router Image API
└── Browser Controller   └── Vector Embeddings       └── ComfyUI Local WS
```

---

## 🚀 All Development Phases

### Phase 1: Core Foundation & Gateway ✅ (COMPLETED)
- [x] **Telegram Gateway:** Modern `aiogram 3.x` bot connecting to `@arush_agentbot`.
- [x] **Security Whitelist:** Middleware ensuring only authorized Telegram User IDs can trigger commands or control the PC.
- [x] **9Router Gateway Integration:** Unified client connecting to `$NINEROUTER_URL/v1` for chat, audio transcription, embeddings, and image generation.
- [x] **OpenAI Tool-Calling Engine:** Multi-turn autonomous tool execution loop with dynamic function calling.
- [x] **Token & Entity Safeguards:**
  - Hard truncation safeguard (12,000 chars) preventing prompt overflow.
  - Efficient JPEG screen compression (70KB instead of 2MB).
  - Safe Telegram error reporting with Markdown fallback.
- [x] **Initial Project Structure & Git Repository.**
- [x] **Docker & Docker Compose Containerization.**

---

### Phase 2: Project Knowledge Vault & Multimodal Ingestion ✅ (COMPLETED)
*Goal: Transform Telegram into an effortless second brain for all projects and financials.*

- [x] **2.1 Hierarchical Project Vault (`tools/vault.py`):**
  - Automatic project workspaces in `data/projects/{slug}/` (`context.md`, `specs.json`, `assets/`).
  - Commands to create, switch, and view project summaries (`/project <name>`, `/projects`).
- [x] **2.2 Financial Ledger & Receipt Parser (`tools/receipt_parser.py`):**
  - Auto-OCR & regex parser for Iranian bank receipts (`کارت به کارت`, `پایا`, `ساتنا`, `بلو`, `سامان`, `ملت`).
  - Extracts: Tracking code (`کد رهگیری`), sender/receiver cards, amount (Toman/Rial normalized), and date/time.
  - Deduplication engine preventing double-logging identical tracking codes.
  - Weekly and monthly income/expense summary commands (`/finance week`, `/finance month`).
- [x] **2.3 Voice Memo & Ideas Incubator (`tools/idea_incubator.py`):**
  - Streams voice notes to 9Router STT (`groq/whisper-large-v3-turbo`).
  - Auto-structures unstructured voice thoughts into Core Concept, Technical Feasibility Score (1–10), Recommended Tech Stack, and Immediate Action Steps (`/idea`).
- [x] **2.4 Semantic Vector Memory (`core/router_client.py` & `tools/vault.py`):**
  - Generates embeddings using 9Router `/v1/embeddings` (`openai/text-embedding-3-small`) with deterministic local n-gram vector fallback.
  - Enables cosine similarity + lexical boost search (`/search <query>`).

---

### Phase 3: Freelance Radar (Karlancer, Ponisha & Telegram) ✅ (COMPLETED)
*Goal: Automatically scan for freelance gigs, filter out spam, and generate winning proposals.*

- [x] **3.1 Iranian Split-Network Client (`tools/freelance_radar.py`):**
  - `IranianSplitNetworkClient` (`trust_env=False`) explicitly bypasses system VPNs to connect directly to Iranian `.ir` domains (Karlancer and Ponisha).
- [x] **3.2 Karlancer & Ponisha Project Feed Scraper:**
  - Periodic background poller (every 10 minutes) querying web/JSON/RSS feeds and filtering by categories (Python, React, Bot, AI, Web Scraping) and minimum budget.
- [x] **3.3 Telegram Freelance Channel Monitor:**
  - Monitors configured Telegram freelance channels via Telethon / public channel web feed parser.
- [x] **3.4 AI Lead Matchmaker & Proposal Generator:**
  - Evaluates new projects against Arush's portfolio profile.
  - Sends instant Telegram alerts for high-match leads (>80%) with project summary, employer rating, suggested bid/timeline, custom Persian proposal draft, and one-click inline button (`/radar`).

---

### Phase 4: Advanced Computer & Browser Automation ✅ (COMPLETED)
*Goal: Deep Windows desktop control and autonomous browser workflows.*

- [x] **4.1 Visual Computer Use — Sense-Decide-Act (`tools/computer_use.py`):**
  - Multi-monitor & high-DPI coordinate mapping from 9Router vision models to Windows monitors.
  - Interactive confirmation buttons in Telegram (`[✅ تایید اجرای عملیات]`, `[❌ لغو]`) via `PendingConfirmationManager` for sensitive actions.
- [x] **4.2 Agentic Browser (`tools/browser_agent.py`):**
  - Connects Playwright (`launch_persistent_context`) to personal Google Chrome profile (`--user-data-dir`) to retain sessions without CAPTCHAs, download attachments, and fill forms.
- [x] **4.3 GitHub Integration (`tools/github_tool.py`):**
  - Safe local Git CLI automation (`status`, `diff`, `log`, `commit_all`, `push`) and GitHub REST API client (`list_open_prs`, `create_issue`, `list_workflow_runs` via `/github`).

---

### Phase 5: Image Studio & Creative Engine (9Router + ComfyUI) ✅ (COMPLETED)
*Goal: Complete text-to-image, inpainting, and UI mockup pipeline.*

- [x] **5.1 9Router Cloud Image Integration (`tools/image_studio.py`):**
  - Supports aspect ratio (`1:1`, `16:9`, `9:16`, `4:3`, `3:4`), quality, and model selection (FLUX Schnell, DALL-E 3, Gemini Imagen) with direct photo delivery to Telegram (`/imagine`).
- [x] **5.2 Local ComfyUI Runner (`tools/image_studio.py`):**
  - Async WebSocket (`ws://127.0.0.1:8188/ws`) and HTTP runner triggering local GPU node graphs (`sdxl`, `flux_gguf`, `inpainting`, `controlnet_ui`).

---

### Phase 6: Life, Bio-Tracking & Daily Routines ✅ (COMPLETED)
*Goal: Keep Arush healthy, focused, and organized.*

- [x] **6.1 Medical Lab Report Parser (`tools/life_tracker.py`):**
  - Extracts blood test / lab report PDFs and text (CBC, vitamins, thyroid, metabolic) into `medical_lab_results` with automatic `LOW` / `NORMAL` / `HIGH` flags (`/lab`).
- [x] **6.2 Daily Bio-Logging (`tools/life_tracker.py`):**
  - Natural language logging for sleep hours, caffeine, headaches, and workouts (`/bio`).
- [x] **6.3 Autonomous Morning Briefing — 08:30 AM (`core/scheduler.py`):**
  - Sends daily briefing with active project deadlines, top freelance leads, and flagged lab reminders (`/briefing`).
- [x] **6.4 Nightly Review Cycle — 10:30 PM (`core/scheduler.py`):**
  - Summarizes daily income/expenses, checks logged habits, and prompts for voice reflection (`/review`).

---

### Phase 7: Production Daemon, Self-Healing & GitHub CI/CD ✅ (COMPLETED)
*Goal: Ensure the agent runs uninterrupted forever with automated testing and deployment.*

- [x] **7.1 Windows Service / Auto-Start:**
  - NSSM service installer (`scripts/install_service.ps1`) and Windows Task Scheduler logon script (`scripts/register_task.ps1`).
- [x] **7.2 Automatic Database Backups (`scripts/backup.py`):**
  - Online SQLite hot-backup of `vault.sqlite` and `.env` with configurable retention pruning (`/backup` & `python run.py --backup-now`).
- [x] **7.3 Health Check & Self-Healing Heartbeat (`core/watchdog.py`):**
  - Exponential backoff reconnection loop + async HTTP health endpoint (`GET /health` on port `8089`).
- [x] **7.4 GitHub Actions CI/CD Pipelines (`.github/workflows/`):**
  - `ci.yml`: Bytecode verification, Ruff lint, Ubuntu/Windows matrix tests (Python 3.11 & 3.12), and Docker Buildx validation.
  - `cd.yml`: Multi-stage GHCR image publishing (`ghcr.io/arush221617/arush-tg`), SSH Docker Compose rollout with `/health` verification, and Windows self-hosted runner service restart.
  - `release.yml`: Automated tagged release archive packaging and GitHub Release publishing.
