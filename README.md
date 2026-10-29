# Arush Manager Agent 🚀 (Complete Phases 1–7 + GitHub CI/CD)

Personal executive co-founder, hierarchical project knowledge vault, freelance radar, creative studio, bio-tracker, and Windows PC automation agent powered by **9Router**, **aiogram 3.x**, and **OpenAI-compatible tool calling**.

---

## ✨ Implemented Capabilities (Phases 1–7)

| Phase | Module | Highlights |
|---|---|---|
| **Phase 1: Core & Gateway** | `bot/app.py`, `core/agent.py`, `core/router_client.py` | `aiogram 3.x` Telegram bot, Whitelist security middleware, 9Router multi-turn tool loop, 12K token safeguard, JPEG screen compression |
| **Phase 2: Knowledge Vault & Finance** | `tools/vault.py`, `tools/receipt_parser.py`, `tools/idea_incubator.py` | Hierarchical project workspaces (`data/projects/{slug}/context.md`, `specs.json`, `assets/`), Iranian bank receipt OCR/parser (`کارت به کارت`, `پایا`, `ساتنا`, `بلو`, `سامان`, `ملت`) with tracking code (`کد رهگیری`) deduplication, Voice Idea Incubator, and `/v1/embeddings` semantic vector search |
| **Phase 3: Freelance Radar** | `tools/freelance_radar.py` | Direct `.ir` `aiohttp` split-network client bypassing VPNs (`trust_env=False`), 10-min background poller for Karlancer, Ponisha & Telegram channels, AI portfolio matchmaker, and Persian proposal generator |
| **Phase 4: PC, Browser & GitHub** | `tools/computer_use.py`, `tools/browser_agent.py`, `tools/github_tool.py` | Multi-monitor DPI scaling, Telegram inline confirmation buttons (`[Confirm]`, `[Cancel]`) for sensitive actions, Playwright persistent Chrome profile automation, local Git CLI & GitHub REST API (PRs, Issues, Actions) |
| **Phase 5: Image Studio** | `tools/image_studio.py` | 9Router Cloud Image API (FLUX Schnell, DALL-E 3, Gemini Imagen) with aspect ratios + Local ComfyUI WebSocket (`ws://127.0.0.1:8188/ws`) workflow runner (`sdxl`, `flux_gguf`, `inpainting`, `controlnet_ui`) |
| **Phase 6: Life & Bio-Tracking** | `tools/life_tracker.py`, `core/scheduler.py` | Medical lab report PDF/text parser (CBC, vitamins, thyroid, metabolic) with `LOW`/`HIGH` flags, natural-language bio-logging (sleep, caffeine, headaches, workouts), 08:30 AM Morning Briefing & 10:30 PM Nightly Review |
| **Phase 7: Production Daemon & CI/CD** | `core/watchdog.py`, `scripts/`, `.github/workflows/` | Self-healing exponential backoff reconnect loop, `GET /health` HTTP server (`:8089`), online SQLite hot-backup with retention, Windows NSSM & Task Scheduler scripts, and GitHub Actions CI/CD/Release pipelines |

---

## 📱 Telegram Bot Commands

* `/start` — Full system overview and command guide
* `/help` — Complete command reference and operational guide
* `/project <name>` — Create, switch active project workspace, or view project summary (`context.md`, `specs.json`, financials)
* `/projects` — List all projects in the Knowledge Vault
* `/finance [week|month]` — Weekly (7-day) or monthly (30-day) income/expense ledger summary
* `/idea <text>` — Structure an idea in the Incubator (Core Concept, Feasibility 1–10, Tech Stack, Action Steps)
* `/search <query>` — Semantic vector search across all project artifacts
* `/radar` — Poll Karlancer, Ponisha, and Telegram freelance channels and display top matches with Persian proposals
* `/screenshot` — Capture live Windows desktop screenshot
* `/github [status|prs|ci]` — Check local Git status, open Pull Requests, or GitHub Actions CI/CD runs
* `/imagine <prompt>` — Generate images via 9Router or ComfyUI and receive directly in chat
* `/bio <note>` — Log daily sleep hours, caffeine, headaches, or workouts
* `/lab <text>` — Parse blood test / lab biomarkers with out-of-range flags
* `/briefing` & `/review` — Trigger the 08:30 AM Morning Briefing or 10:30 PM Nightly Review on demand
* `/backup` — Trigger an immediate hot backup of `vault.sqlite` and `.env`
* `/status` — View self-healing watchdog health, uptime, and 9Router model status
* `/cancel` — Cancel pending sensitive desktop actions or reset state

---

## 🛠️ Setup, Testing & Deployment

### 1. Local Development & Testing
```bash
pip install -r requirements.txt
cp .env.example .env

# Run unit & integration test suite (Phases 1–7)
make test
# Or directly:
python -m unittest discover -s tests -p "test_*.py" -v

# Run startup diagnostics check
python run.py --check-only

# Register Telegram bot slash commands
python run.py --set-commands
# Or: make commands

# Start the agent
python run.py
```

### 2. Windows 24/7 Service / Auto-Start (Phase 7.1)
> **Note:** Requires Administrator privileges (will automatically request a Windows UAC elevation prompt if run in a standard terminal).

```powershell
# Option A: Register in Windows Task Scheduler (recommended for desktop GUI access)
powershell -ExecutionPolicy Bypass -File .\scripts\register_task.ps1

# Option B: Install as a Windows Service via NSSM
powershell -ExecutionPolicy Bypass -File .\scripts\install_service.ps1
```

### 3. Docker & Docker Compose
```bash
docker compose up -d --build
curl http://localhost:8089/health
```

### 4. GitHub Actions CI/CD Pipelines
* **`.github/workflows/ci.yml`**: Runs on every push and PR to `main`/`develop` — verifies Python bytecode compilation, runs Ruff linting, executes the Phase 1–7 test matrix across `ubuntu-latest` and `windows-latest` (Python 3.11 & 3.12), and validates the Docker build.
* **`.github/workflows/cd.yml`**: Builds and pushes multi-stage container images to GitHub Container Registry (`ghcr.io/arush221617/arush-tg:latest`) and supports automated SSH Docker Compose deployment (with `/health` probe) or Windows self-hosted NSSM service restarts.
* **`.github/workflows/release.yml`**: Automatically runs tests, packages a clean release `.zip`, and publishes GitHub Releases on `v*.*.*` tags.
