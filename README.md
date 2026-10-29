# Arush Manager Agent 🚀

Personal executive manager, project knowledge vault, and Windows PC automation agent powered by the **Claude Agent SDK**, **9Router**, and **aiogram 3.x**.

---

## 🏗️ Architecture

```
                       [ Telegram: @arush_agentbot ]
                                    │
                                    ▼
                     [ aiogram 3.x Telegram Gateway ]
                      (Whitelist Security Filter)
                                    │
                      ┌─────────────┴─────────────┐
                      │                           │
               [ Text / Photos ]           [ Voice Memos ]
                      │                           │
                      │                   [ 9Router STT ]
                      │                 (Whisper / Groq)
                      ▼                           ▼
        ┌────────────────────────────────────────────────────────┐
        │                 Claude Agent SDK Loop                  │
        │             (Model: Claude 3.7 / 3.5 Sonnet)           │
        │             Base URL: $NINEROUTER_URL/v1               │
        └──────────────────────────┬─────────────────────────────┘
                                   │  Native Tool Calls
       ┌───────────────────────────┼───────────────────────────┐
       ▼                           ▼                           ▼
[ Computer Use Tool ]     [ Developer & Vault Tools ]    [ External Tools ]
├── `mss` screen grab     ├── Persistent PowerShell      ├── Karlancer & Ponisha
├── Coordinate rescale    ├── Project Vault (SQLite)     │   (Direct .ir HTTP)
├── `SendInput` clicks    ├── 9router Image API          └── GitHub REST API
└── TG Inline Approval    └── ComfyUI Local WebSocket
```

---

## ⚡ Features Implemented (Phase 1 MVP)

1. **Claude Agent SDK Brain via 9Router:**
   - Multi-turn tool execution loop using `anthropic.AsyncAnthropic` with `base_url=f"{NINEROUTER_URL}/v1"`.
2. **Native Windows Computer Use (`computer_20241022`):**
   - High-speed display capture via `mss` (<15ms).
   - Dynamic coordinate rescaling from Claude's target resolution ($1280 \times 800$) to native display resolution.
   - Mouse clicks (`left`, `right`, `double`, `triple`), typing, and hotkeys via `pyautogui`.
3. **Multimodal Audio Processing (Voice Memos):**
   - Telegram voice notes (`.oga` / Opus) are automatically routed to `9Router POST /v1/audio/transcriptions` using `groq/whisper-large-v3-turbo` for instant Persian & English speech-to-text.
4. **Project Knowledge Vault (SQLite):**
   - Preserves complete project context (screenshots, ideas, client requirements, code references) in `data/projects/` and `data/db/vault.sqlite`.
5. **Financial & Receipt Extractor:**
   - Analyzes bank screenshots (کارت به کارت, پایا, ساتنا, بلو/سامان/ملت), extracts tracking codes (`کد رهگیری`) and amounts in Toman/Rial, and records them in the local ledger.
6. **Whitelist Security:**
   - Protects your host PC: only authorized Telegram user IDs can trigger tools or execute commands.

---

## 🛠️ Setup & Running

### 1. Install Dependencies
```powershell
cd d:\arush\arush-tg
pip install -r requirements.txt
```

### 2. Configure `.env`
Open `d:\arush\arush-tg\.env`:
* **`NINEROUTER_URL`**: URL of your 9Router instance (default: `http://localhost:20128` or your VPS tunnel).
* **`NINEROUTER_KEY`**: Your 9Router API key (if required).
* **`TELEGRAM_PROXY`**: Set this if your machine needs a proxy to access Telegram in Iran (e.g. `socks5://127.0.0.1:10808` or `http://127.0.0.1:10809`).
* **`ALLOWED_TELEGRAM_USER_IDS`**: Your numeric Telegram user ID (e.g. `123456789`).

### 3. Run the Agent
```powershell
python run.py
```

---

## 📱 Telegram Commands
* `/start` — System overview and quick status
* `/screenshot` — Capture and view current desktop screen in chat
* `/projects` — List active projects in your Knowledge Vault
* `/status` — Test 9Router connectivity and active models
