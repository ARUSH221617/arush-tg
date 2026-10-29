# 📋 Arush Manager Agent — Master Architectural Plan

> **Mission:** Build a personal executive co-founder, knowledge vault, and Windows automation agent that runs locally 24/7, connects to Telegram (`@arush_agentbot`), routes models through **9Router**, and assists Arush across freelance platforms (Ponisha & Karlancer), projects, finances, habits, and PC control.

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
- [x] **9Router Gateway Integration:** Unified client connecting to `$NINEROUTER_URL/v1` for chat, audio transcription, and image generation.
- [x] **OpenAI Tool-Calling Engine:** Multi-turn autonomous tool execution loop with dynamic function calling (`powershell`, `computer`, `vault`, `image`).
- [x] **Token & Entity Safeguards:**
  - Hard truncation safeguard (12,000 chars) preventing prompt overflow.
  - Efficient JPEG screen compression (70KB instead of 2MB).
  - Safe Telegram error reporting with Markdown fallback.
- [x] **Initial Project Structure & Git Repository.**
- [x] **Docker & Docker Compose Containerization.**

---

### Phase 2: Project Knowledge Vault & Multimodal Ingestion 🟡 (IN PROGRESS)
*Goal: Transform Telegram into an effortless second brain for all projects and financials.*

- [ ] **2.1 Hierarchical Project Vault:**
  - Create project workspaces in `data/projects/{slug}/` (e.g. `context.md`, `specs.json`, `assets/`).
  - Commands to create, switch, and view project summaries (`/project <name>`).
- [ ] **2.2 Financial Ledger & Receipt Parser:**
  - Auto-OCR for Iranian bank receipts (`کارت به کارت`, `پایا`, `ساتنا`, `بلو`, `سامان`, `ملت`).
  - Extract: Tracking code (`کد رهگیری`), sender/receiver cards, amount (Toman/Rial), date/time.
  - Deduplication engine preventing double-logging identical tracking codes.
  - Weekly and monthly income/expense summary commands.
- [ ] **2.3 Voice Memo & Ideas Incubator:**
  - Stream voice notes to 9Router STT (`groq/whisper-large-v3-turbo`).
  - Auto-structure unstructured voice thoughts into:
    * *Core Concept*
    * *Technical Feasibility Score (1-10)*
    * *Recommended Tech Stack*
    * *Immediate Action Steps*
- [ ] **2.4 Semantic Vector Memory:**
  - Generate embeddings using 9Router `/v1/embeddings` (`openai/text-embedding-3-small`).
  - Enable semantic similarity search: "What did the client say about button colors in project X?"

---

### Phase 3: Freelance Radar (Karlancer, Ponisha & Telegram) ⏳
*Goal: Automatically scan for freelance gigs, filter out spam, and generate winning proposals.*

- [ ] **3.1 Iranian Split-Network Client:**
  - Build an `aiohttp` session that explicitly bypasses system VPNs to connect directly to Iranian `.ir` domains (Karlancer and Ponisha).
- [ ] **3.2 Karlancer & Ponisha Project Feed Scraper:**
  - Periodic background poller (every 10 minutes) querying web feeds without triggering Cloudflare blocks.
  - Filters by categories (Python, React, Bot, AI, Web Scraping) and minimum budget.
- [ ] **3.3 Telegram Freelance Channel Monitor:**
  - Telethon userbot daemon listening to selected job/freelance channels.
- [ ] **3.4 AI Lead Matchmaker & Proposal Generator:**
  - Evaluates new projects against your portfolio profile.
  - If match score > 80%, sends an instant Telegram alert with:
    * Project summary & employer rating
    * Suggested bid amount and timeline
    * Custom Persian proposal draft
    * One-click direct link button to submit the bid.

---

### Phase 4: Advanced Computer & Browser Automation ⏳
*Goal: Deep Windows desktop control and autonomous browser workflows.*

- [ ] **4.1 Visual Computer Use (Sense-Decide-Act):**
  - Enhanced visual coordinate mapping from 9Router vision models to Windows monitors.
  - Interactive confirmation buttons in Telegram for sensitive actions (`[Confirm Kill Task]`, `[Cancel]`).
- [ ] **4.2 Agentic Browser (`browser-use` + Playwright):**
  - Connect Playwright to your persistent personal Google Chrome profile (`--user-data-dir`).
  - Retain login sessions for Karlancer, Ponisha, GitHub, and email without CAPTCHA.
  - Download project attachment files and fill forms automatically.
- [ ] **4.3 GitHub Integration:**
  - Local Git automation (`git status`, commit, push) via safe PowerShell functions.
  - GitHub REST API tools: list open PRs, create issues from Telegram voice notes.

---

### Phase 5: Image Studio & Creative Engine (9Router + ComfyUI) ⏳
*Goal: Complete text-to-image, inpainting, and UI mockup pipeline.*

- [ ] **5.1 9Router Cloud Image Integration:**
  - Dedicated tool parameters for aspect ratio, quality, and model selection (FLUX Schnell, DALL-E 3, Gemini Imagen).
  - Direct delivery of generated images to Telegram chat.
- [ ] **5.2 Local ComfyUI Runner:**
  - WebSocket client communicating with `ws://127.0.0.1:8188`.
  - Trigger local GPU workflows (SDXL, Flux-GGUF, Inpainting, ControlNet UI-to-Code).

---

### Phase 6: Life, Bio-Tracking & Daily Routines ⏳
*Goal: Keep Arush healthy, focused, and organized.*

- [ ] **6.1 Medical Lab Report Parser:**
  - Extract blood test / lab report PDFs and images (CBC, vitamins, thyroid) into structured SQLite tables with out-of-range value flags.
- [ ] **6.2 Daily Bio-Logging:**
  - Quick voice note logging for sleep hours, caffeine, headaches, and workouts.
- [ ] **6.3 Autonomous Morning Briefing (08:30 AM):**
  - Sends daily briefing: today's calendar events, active project deadlines, top freelance leads.
- [ ] **6.4 Nightly Review Cycle (10:30 PM):**
  - Checks completed habits, summarizes daily income/expenses, prompts for voice reflection.

---

### Phase 7: Production Daemon & Self-Healing ⏳
*Goal: Ensure the agent runs uninterrupted forever.*

- [ ] **7.1 Windows Service / Auto-Start:**
  - Configure NSSM (Non-Sucking Service Manager) or Windows Task Scheduler to launch `run.py` on PC boot.
- [ ] **7.2 Automatic Database Backups:**
  - Scheduled daily backup of `vault.sqlite` and `.env` to a secure local folder or cloud storage.
- [ ] **7.3 Health Check & Heartbeat:**
  - Automatic reconnection logic when internet or VPN drops and reconnects.

---

## 🛠️ Tech Stack Matrix

| Layer | Technology | Purpose |
|---|---|---|
| **Telegram Gateway** | `aiogram 3.x` (Python Async) | Real-time chat, media streaming, inline buttons |
| **AI Gateway** | **9Router** | Unified router for Claude, GPT, Gemini, FLUX, Whisper |
| **Agent Protocol** | OpenAI-compatible tool calling | High-reliability function calling and multimodal blocks |
| **PC Control** | `mss` + `pyautogui` + Win32 API | Screen capture (<15ms) and cursor/keystroke emulation |
| **Terminal Runner** | Async PowerShell Subprocess | Safe Windows CLI command execution |
| **Browser Engine** | Playwright + Persistent Chrome Profile | Automated web workflows with active logins |
| **Knowledge Vault** | SQLite3 + `sqlite-vec` / ChromaDB | Local-first relational + semantic vector memory |
| **Voice Processing** | 9Router STT (`groq/whisper-large-v3`) | Instant Persian & English transcription |
| **Containerization** | Docker & Docker Compose | Portable deployment and background service runner |
