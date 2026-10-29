import asyncio
import json
from typing import List, Dict, Any, Optional, Callable, Awaitable

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

from config import settings
from core.prompts import SYSTEM_PROMPT
from core.router_client import router_client
from tools.computer_use import controller as computer_ctrl
from tools.powershell import ps_executor
from tools.vault import vault
from tools.receipt_parser import receipt_parser
from tools.idea_incubator import idea_incubator
from tools.freelance_radar import freelance_radar
from tools.browser_agent import browser_agent
from tools.github_tool import github_tool
from tools.image_studio import image_studio
from tools.life_tracker import life_tracker
from tools.agent_manager import agent_manager
from tools.skills_manager import skills_manager
from tools.mcp_manager import mcp_manager


class ClaudeManagerAgent:
    """
    Unified Agent Controller powered by 9Router.
    Integrates all tools across Phases 1 through 8 (including Prebuilt/Custom Agents,
    Saved PC Project Workspace / Claude Code Editor, Sub-Agents, External CLI Agents,
    Skills, and MCP Servers) with multi-turn OpenAI-compatible tool calling.
    """

    def __init__(self):
        base_url = f"{settings.NINEROUTER_URL.rstrip('/')}/v1"
        api_key = settings.NINEROUTER_KEY or "none"
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key) if AsyncOpenAI else None
        self.model = settings.AGENT_MODEL
        self.default_max_turns: int = getattr(settings, "AGENT_MAX_TURNS", 200)
        self.tool_repeat_limit: int = getattr(settings, "AGENT_TOOL_REPEAT_LIMIT", 3)
        self.last_generated_images: List[str] = []
        self.last_pending_confirmations: List[Dict[str, Any]] = []

    @staticmethod
    def normalize_tool_signature(tool_name: str, tool_args: Any) -> str:
        """
        Creates a deterministic normalized signature string for a tool call.
        Ensures consistent JSON key ordering so identical tool arguments
        with different formatting or whitespace are recognized accurately.
        """
        if isinstance(tool_args, str):
            try:
                parsed = json.loads(tool_args)
            except Exception:
                parsed = {"raw": tool_args.strip()}
        elif isinstance(tool_args, dict):
            parsed = tool_args
        elif tool_args is None:
            parsed = {}
        else:
            parsed = {"raw": str(tool_args)}

        try:
            canonical_args = json.dumps(parsed, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            canonical_args = str(parsed)

        return f"{tool_name}::{canonical_args}"

    def get_tool_definitions(self, include_mcp_dynamic: bool = True) -> List[Dict[str, Any]]:
        """Defines all Phase 1–8 tools in standard OpenAI Function Calling schema."""
        base_tools = [
            # 1. PowerShell CLI Executor (Phase 1 & 4)
            {
                "type": "function",
                "function": {
                    "name": "powershell",
                    "description": "Execute a command in Windows PowerShell on the host PC.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Exact PowerShell command to run."}
                        },
                        "required": ["command"]
                    }
                }
            },
            # 2. Native Computer GUI Control (Phase 1 & 4.1)
            {
                "type": "function",
                "function": {
                    "name": "computer",
                    "description": "Perform mouse/keyboard actions on Windows desktop, take screenshots, or request confirmation for sensitive actions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "screenshot", "mouse_move", "left_click", "right_click",
                                    "double_click", "triple_click", "middle_click", "scroll",
                                    "type", "key", "cursor_position", "kill_process", "delete_file"
                                ]
                            },
                            "coordinate": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "Target [x, y] coordinates in 1280x800 space."
                            },
                            "text": {"type": "string", "description": "Text to type, key combo, or target process/file."},
                            "monitor_index": {"type": "integer", "default": 1}
                        },
                        "required": ["action"]
                    }
                }
            },
            # 3. Project Workspace Manager (Phase 2.1)
            {
                "type": "function",
                "function": {
                    "name": "manage_project",
                    "description": "Create, switch active project workspace (`data/projects/{slug}/`), list projects, or view a project summary.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["create_or_switch", "summary", "list"]
                            },
                            "name": {"type": "string", "description": "Project name or slug."},
                            "client": {"type": "string"},
                            "platform": {"type": "string", "default": "direct"},
                            "budget": {"type": "string"},
                            "deadline": {"type": "string"}
                        },
                        "required": ["operation"]
                    }
                }
            },
            # 4. Vault Artifact Saver with Vector Indexing (Phase 2.1 & 2.4)
            {
                "type": "function",
                "function": {
                    "name": "save_to_vault",
                    "description": "Save an idea, screenshot, note, code snippet, or client requirement to the Project Knowledge Vault with vector embeddings.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "artifact_type": {
                                "type": "string",
                                "enum": ["idea", "screenshot", "note", "code_snippet", "client_requirement"]
                            },
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "project_slug": {"type": "string"},
                            "tags": {"type": "string"}
                        },
                        "required": ["artifact_type", "title", "content"]
                    }
                }
            },
            # 5. Semantic & Hybrid Vault Searcher (Phase 2.4)
            {
                "type": "function",
                "function": {
                    "name": "search_vault",
                    "description": "Semantic vector similarity search across the Project Knowledge Vault (e.g. 'What did the client say about button colors in project X?').",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "project_slug": {"type": "string"},
                            "artifact_type": {
                                "type": "string",
                                "enum": ["idea", "screenshot", "note", "code_snippet", "client_requirement"]
                            },
                            "top_k": {"type": "integer", "default": 5}
                        },
                        "required": ["query"]
                    }
                }
            },
            # 6. Iranian Bank Receipt Parser & Deduplicated Recorder (Phase 2.2)
            {
                "type": "function",
                "function": {
                    "name": "parse_and_record_receipt",
                    "description": "Parse Iranian bank receipt text (کارت به کارت, پایا, ساتنا, بلو, سامان, ملت), extract tracking code & cards, and record with deduplication.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "raw_text": {"type": "string", "description": "OCR or extracted text from the receipt."},
                            "category": {"type": "string", "enum": ["income", "expense"], "default": "income"},
                            "project_slug": {"type": "string"}
                        },
                        "required": ["raw_text"]
                    }
                }
            },
            # 7. Financial Transaction Recorder & Summary (Phase 2.2)
            {
                "type": "function",
                "function": {
                    "name": "record_transaction",
                    "description": "Record an income or expense transaction in the financial ledger (with tracking code deduplication).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "amount": {"type": "number"},
                            "currency": {"type": "string", "enum": ["Toman", "Rial", "USDT", "USD"], "default": "Toman"},
                            "category": {"type": "string", "enum": ["income", "expense"], "default": "income"},
                            "tracking_code": {"type": "string"},
                            "description": {"type": "string"},
                            "project_slug": {"type": "string"}
                        },
                        "required": ["amount", "description"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_financial_summary",
                    "description": "Get weekly (7 days) or monthly (30 days) income/expense financial summary.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "days": {"type": "integer", "default": 7},
                            "project_slug": {"type": "string"}
                        }
                    }
                }
            },
            # 8. Voice Memo & Ideas Incubator (Phase 2.3)
            {
                "type": "function",
                "function": {
                    "name": "incubate_voice_idea",
                    "description": "Structure an unstructured voice memo or raw idea into Core Concept, Feasibility Score (1-10), Tech Stack, and Immediate Action Steps.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transcript": {"type": "string"},
                            "project_slug": {"type": "string"}
                        },
                        "required": ["transcript"]
                    }
                }
            },
            # 9. Freelance Radar (Phase 3)
            {
                "type": "function",
                "function": {
                    "name": "scan_freelance_radar",
                    "description": "Poll Karlancer, Ponisha, and Telegram channels for freelance gigs or evaluate a project lead and generate a Persian proposal.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mode": {"type": "string", "enum": ["poll_live", "top_leads", "evaluate_custom"], "default": "top_leads"},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "budget_max": {"type": "number"}
                        }
                    }
                }
            },
            # 10. Agentic Browser Automation (Phase 4.2)
            {
                "type": "function",
                "function": {
                    "name": "browser_automation",
                    "description": "Control persistent Google Chrome profile via Playwright to navigate, fill forms, or download project attachments.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["navigate", "fill_form", "download_attachments", "screenshot"]},
                            "url": {"type": "string"},
                            "selectors": {"type": "object"},
                            "submit_selector": {"type": "string"}
                        },
                        "required": ["action", "url"]
                    }
                }
            },
            # 11. GitHub Integration (Phase 4.3)
            {
                "type": "function",
                "function": {
                    "name": "github_action",
                    "description": "Execute local Git commands (`status`, `diff`, `commit_all`, `push`) or GitHub REST API calls (`list_open_prs`, `create_issue`, `list_workflow_runs`).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["status", "diff", "log", "commit_all", "push", "list_open_prs", "create_issue", "list_workflow_runs"]
                            },
                            "repo": {"type": "string"},
                            "title": {"type": "string"},
                            "body": {"type": "string"},
                            "message": {"type": "string"}
                        },
                        "required": ["operation"]
                    }
                }
            },
            # 12. Image Studio (Phase 5.1 & 5.2)
            {
                "type": "function",
                "function": {
                    "name": "generate_image",
                    "description": "Generate an image via 9Router Cloud (FLUX Schnell, DALL-E 3, Gemini Imagen) or local ComfyUI WebSocket (`sdxl`, `flux_gguf`, `inpainting`, `controlnet_ui`).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string"},
                            "engine": {"type": "string", "enum": ["9router", "comfyui"], "default": "9router"},
                            "model": {"type": "string", "description": "e.g. flux-schnell, dall-e-3, gemini-imagen"},
                            "aspect_ratio": {"type": "string", "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"], "default": "1:1"},
                            "quality": {"type": "string", "enum": ["standard", "hd"], "default": "standard"},
                            "workflow_type": {"type": "string", "enum": ["sdxl", "flux_gguf", "inpainting", "controlnet_ui"], "default": "flux_gguf"},
                            "project_slug": {"type": "string"}
                        },
                        "required": ["prompt"]
                    }
                }
            },
            # 13. Medical Lab Report Parser & Bio-Logging (Phase 6.1 & 6.2)
            {
                "type": "function",
                "function": {
                    "name": "parse_medical_lab",
                    "description": "Extract blood test / lab biomarkers (CBC, vitamins, thyroid, metabolic) and flag out-of-range values.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "raw_text": {"type": "string"},
                            "lab_date": {"type": "string"}
                        },
                        "required": ["raw_text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "log_bio_habit",
                    "description": "Log daily sleep hours, caffeine, headaches, workouts, or habits.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "note": {"type": "string", "description": "Natural language bio note or habit update."}
                        },
                        "required": ["note"]
                    }
                }
            },
            # 14. PC Project Path & Claude Code Workspace Engine (Phase 8.1)
            {
                "type": "function",
                "function": {
                    "name": "code_workspace",
                    "description": (
                        "Save/switch the local project path on the user's PC and perform Claude Code actions: "
                        "inspect directory tree, read files with line numbers, surgical edit_file (search & replace with diff), "
                        "multi_edit_file, write_file, grep_search across codebase, glob_files, and run_in_project (tests, git, builds)."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": [
                                    "set_project_path",
                                    "get_active_path",
                                    "list_workspaces",
                                    "switch_workspace",
                                    "inspect_tree",
                                    "read_file",
                                    "write_file",
                                    "edit_file",
                                    "multi_edit_file",
                                    "grep_search",
                                    "glob_files",
                                    "run_in_project"
                                ]
                            },
                            "path": {"type": "string", "description": "PC directory path (for set_project_path / inspect_tree) or file path (relative to active project or absolute)."},
                            "name": {"type": "string", "description": "Optional workspace alias name when saving a PC project path."},
                            "create_if_missing": {"type": "boolean", "default": False},
                            "start_line": {"type": "integer", "default": 1},
                            "end_line": {"type": "integer", "default": 300},
                            "content": {"type": "string", "description": "Full file content for write_file."},
                            "old_text": {"type": "string", "description": "Exact text block to find for edit_file."},
                            "new_text": {"type": "string", "description": "Replacement text block for edit_file."},
                            "replace_all": {"type": "boolean", "default": False},
                            "edits": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "old_text": {"type": "string"},
                                        "new_text": {"type": "string"}
                                    }
                                },
                                "description": "List of {old_text, new_text} objects for multi_edit_file."
                            },
                            "pattern": {"type": "string", "description": "Regex/text pattern for grep_search or file pattern for glob_files."},
                            "file_glob": {"type": "string", "default": "*", "description": "Filename filter for grep_search (e.g. '*.py')."},
                            "command": {"type": "string", "description": "Shell/PowerShell/test command to run inside the active PC project directory."}
                        },
                        "required": ["operation"]
                    }
                }
            },
            # 15. Prebuilt & Custom Persona Agents Manager (Phase 8.1)
            {
                "type": "function",
                "function": {
                    "name": "manage_agents",
                    "description": (
                        "Manage prebuilt agents (`programmer`, `planner`, `reviewer`, `debugger`, `researcher`, `manager`) "
                        "and custom agents: list agents, switch active agent, create/update custom agent, bind a PC project path, or attach skills."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["list", "get_active", "switch", "create_or_update", "delete"]
                            },
                            "name": {"type": "string", "description": "Agent slug or name (e.g. programmer, planner, reviewer, debugger, researcher)."},
                            "role_title": {"type": "string"},
                            "description": {"type": "string"},
                            "system_prompt": {"type": "string"},
                            "structure_template": {"type": "string"},
                            "preferred_model": {"type": "string"},
                            "attached_skills": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "project_path": {"type": "string", "description": "Local PC project directory path to bind to this agent."},
                            "activate": {"type": "boolean", "default": False}
                        },
                        "required": ["operation"]
                    }
                }
            },
            # 16. Autonomous Sub-Agent Spawner (Phase 8.1)
            {
                "type": "function",
                "function": {
                    "name": "spawn_subagent",
                    "description": (
                        "Spawn an autonomous Sub-Agent (e.g. `programmer`, `planner`, `reviewer`, `debugger`, `researcher`, or custom) "
                        "to execute a focused multi-step coding, planning, or research task on the PC project path and return structured results."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent_slug": {
                                "type": "string",
                                "description": "Target sub-agent persona (`programmer`, `planner`, `reviewer`, `debugger`, `researcher`, or custom slug).",
                                "default": "programmer"
                            },
                            "task": {"type": "string", "description": "Detailed task instructions for the sub-agent."},
                            "project_path": {"type": "string", "description": "Optional PC project path override."},
                            "skills": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional skill slugs to attach to this sub-agent run."
                            },
                            "max_turns": {"type": "integer", "default": 12}
                        },
                        "required": ["task"]
                    }
                }
            },
            # 17. External PC CLI Coding Agents Manager (Claude Code, Antigravity, Codex, GitHub Copilot)
            {
                "type": "function",
                "function": {
                    "name": "manage_external_cli_agent",
                    "description": (
                        "Detect, create, configure, and run tasks on external AI CLI agents installed on the user's PC: "
                        "`claude_code` (Claude Code CLI), `antigravity` (Antigravity CLI), `codex` (OpenAI Codex CLI), "
                        "`github_copilot` (GitHub Copilot CLI), or any custom local CLI agent."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["list", "detect_installed", "run", "register_or_update", "remove"]
                            },
                            "agent_name": {
                                "type": "string",
                                "description": "CLI agent slug or name (`claude_code`, `antigravity`, `codex`, `github_copilot`, or custom name)."
                            },
                            "prompt": {"type": "string", "description": "Task or coding instruction to send to the CLI agent (for `run`)."},
                            "project_path": {"type": "string", "description": "PC project directory where the CLI agent should execute."},
                            "binary": {"type": "string", "description": "Executable name or full path on PC (e.g. `claude`, `antigravity`, `codex`, `gh`)."},
                            "args_template": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "CLI args template containing `{prompt}` (e.g. `['-p', '{prompt}']`)."
                            },
                            "auto_approve": {"type": "boolean", "default": False},
                            "timeout_seconds": {"type": "integer", "default": 240}
                        },
                        "required": ["operation"]
                    }
                }
            },
            # 18. Skills Manager (Phase 8.2)
            {
                "type": "function",
                "function": {
                    "name": "manage_skills",
                    "description": "List, inspect, create/update (`SKILL.md`), enable/disable, or delete reusable agent skills.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["list", "get", "create_or_update", "toggle", "delete"]
                            },
                            "name": {"type": "string", "description": "Skill name or slug."},
                            "description": {"type": "string"},
                            "category": {"type": "string", "default": "general"},
                            "triggers": {"type": "string", "description": "Comma-separated trigger keywords."},
                            "content": {"type": "string", "description": "Markdown instructions or full SKILL.md content."},
                            "enabled": {"type": "boolean", "default": True}
                        },
                        "required": ["operation"]
                    }
                }
            },
            # 19. MCP (Model Context Protocol) Manager (Phase 8.3)
            {
                "type": "function",
                "function": {
                    "name": "manage_mcp",
                    "description": (
                        "Manage Model Context Protocol (MCP) servers and tools: list servers, add stdio/HTTP server, "
                        "add preset (`filesystem`, `github`, `sqlite`, `memory`, `fetch`, `playwright`), import `mcpServers` JSON, "
                        "discover tools (`tools/list`), or call an MCP tool (`tools/call`)."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": [
                                    "list_servers",
                                    "add_server",
                                    "add_preset",
                                    "import_json",
                                    "remove_server",
                                    "toggle_server",
                                    "discover_tools",
                                    "call_tool"
                                ]
                            },
                            "server_name": {"type": "string", "description": "MCP server name/slug or preset name."},
                            "transport": {"type": "string", "enum": ["stdio", "http"], "default": "stdio"},
                            "command": {"type": "string", "description": "Executable for stdio MCP server (e.g. `npx`, `uvx`, `python`)."},
                            "args": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "env": {"type": "object"},
                            "url": {"type": "string", "description": "Endpoint URL for HTTP MCP server."},
                            "cwd": {"type": "string", "description": "Working directory or target path for the MCP server."},
                            "raw_json": {"type": "string", "description": "Raw JSON string with `mcpServers` config (for `import_json`)."},
                            "tool_name": {"type": "string", "description": "MCP tool name to execute (for `call_tool`)."},
                            "arguments": {"type": "object", "description": "Arguments dictionary for `call_tool`."},
                            "enabled": {"type": "boolean", "default": True}
                        },
                        "required": ["operation"]
                    }
                }
            }
        ]

        if include_mcp_dynamic:
            try:
                base_tools.extend(mcp_manager.get_openai_tool_definitions())
            except Exception:
                pass

        return base_tools

    async def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches tool execution across all Phase 1–8 modules and dynamic MCP tools."""
        # Dynamic MCP tool bridge: mcp__{server_slug}__{tool_name}
        if tool_name.startswith("mcp__"):
            parts = tool_name.split("__", 2)
            if len(parts) == 3:
                _, srv_slug, mcp_tool_name = parts
                return await mcp_manager.call_tool(srv_slug, mcp_tool_name, arguments=tool_input)

        if tool_name == "powershell":
            return await ps_executor.execute(tool_input.get("command", ""))

        elif tool_name == "computer":
            res = computer_ctrl.execute_action(
                action=tool_input.get("action", "screenshot"),
                coordinate=tool_input.get("coordinate"),
                text=tool_input.get("text"),
                monitor_index=int(tool_input.get("monitor_index", 1))
            )
            if res.get("status") == "requires_confirmation":
                self.last_pending_confirmations.append(res)
            return res

        elif tool_name == "manage_project":
            op = tool_input.get("operation", "list")
            if op == "create_or_switch":
                proj = vault.switch_active_project(tool_input.get("name", "default_project"))
                if any(tool_input.get(k) for k in ("client", "platform", "budget", "deadline")):
                    vault.create_or_get_project(
                        name=proj["name"],
                        client=tool_input.get("client", ""),
                        platform=tool_input.get("platform", "direct"),
                        budget=tool_input.get("budget", ""),
                        deadline=tool_input.get("deadline", "")
                    )
                return {"status": "active_project_set", "summary": vault.get_project_summary(proj["slug"])}
            elif op == "summary":
                return {"summary": vault.get_project_summary(tool_input.get("name"))}
            else:
                return {"projects": vault.list_projects()}

        elif tool_name == "save_to_vault":
            title = tool_input.get("title", "")
            content = tool_input.get("content", "")
            emb = await router_client.create_embedding(f"{title}\n{content}")
            res = vault.save_artifact(
                artifact_type=tool_input.get("artifact_type", "note"),
                title=title,
                content=content,
                project_slug=tool_input.get("project_slug"),
                tags=tool_input.get("tags"),
                embedding=emb,
                embedding_model=settings.EMBEDDING_MODEL
            )
            return {"status": "saved", "id": res["id"], "project_id": res.get("project_id")}

        elif tool_name == "search_vault":
            query = tool_input.get("query", "")
            q_emb = await router_client.create_embedding(query)
            res = vault.semantic_search_vault(
                query=query,
                query_embedding=q_emb,
                project_slug=tool_input.get("project_slug"),
                artifact_type=tool_input.get("artifact_type"),
                top_k=int(tool_input.get("top_k", 5))
            )
            return {"results": res}

        elif tool_name == "parse_and_record_receipt":
            return receipt_parser.parse_and_record(
                raw_text=tool_input.get("raw_text", ""),
                category=tool_input.get("category", "income"),
                project_slug=tool_input.get("project_slug")
            )

        elif tool_name == "record_transaction":
            res = vault.record_transaction(
                amount=float(tool_input.get("amount", 0)),
                currency=tool_input.get("currency", "Toman"),
                category=tool_input.get("category", "income"),
                tracking_code=tool_input.get("tracking_code"),
                description=tool_input.get("description"),
                project_slug=tool_input.get("project_slug")
            )
            return {"status": "duplicate_skipped" if res.get("duplicate") else "recorded", "transaction": res}

        elif tool_name == "get_financial_summary":
            return vault.get_financial_summary(
                days=int(tool_input.get("days", 7)),
                project_slug=tool_input.get("project_slug")
            )

        elif tool_name == "incubate_voice_idea":
            return await idea_incubator.incubate_transcript(
                transcript=tool_input.get("transcript", ""),
                project_slug=tool_input.get("project_slug")
            )

        elif tool_name == "scan_freelance_radar":
            mode = tool_input.get("mode", "top_leads")
            if mode == "poll_live":
                alerts = await freelance_radar.poll_sources_once()
                return {"new_high_match_leads": alerts}
            elif mode == "evaluate_custom":
                lead = await freelance_radar.process_custom_lead({
                    "external_id": f"custom_{hash(tool_input.get('title', ''))}",
                    "platform": "manual",
                    "title": tool_input.get("title", "Custom Project"),
                    "description": tool_input.get("description", ""),
                    "budget_max": float(tool_input.get("budget_max") or 10_000_000)
                })
                return {"evaluated_lead": lead}
            else:
                return {"top_leads": vault.get_top_freelance_leads(min_score=0, limit=10)}

        elif tool_name == "browser_automation":
            return await browser_agent.execute_browser_task(
                action=tool_input.get("action", "navigate"),
                url=tool_input.get("url", "https://ponisha.ir"),
                selectors=tool_input.get("selectors"),
                submit_selector=tool_input.get("submit_selector")
            )

        elif tool_name == "github_action":
            op = tool_input.get("operation", "status")
            if op in {"status", "diff", "log", "commit_all", "push"}:
                return await github_tool.run_local_git(
                    op,
                    repo_path=agent_manager.get_active_project_path(),
                    message=tool_input.get("message")
                )
            elif op == "list_open_prs":
                return await github_tool.list_open_prs(repo=tool_input.get("repo"))
            elif op == "create_issue":
                return await github_tool.create_issue(
                    title=tool_input.get("title", "New Issue"),
                    body=tool_input.get("body", ""),
                    repo=tool_input.get("repo")
                )
            elif op == "list_workflow_runs":
                return await github_tool.list_workflow_runs(repo=tool_input.get("repo"))
            return {"error": f"Unknown github_action operation: {op}"}

        elif tool_name == "generate_image":
            res = await image_studio.generate(
                prompt=tool_input.get("prompt", ""),
                engine=tool_input.get("engine", "9router"),
                model=tool_input.get("model"),
                aspect_ratio=tool_input.get("aspect_ratio", "1:1"),
                quality=tool_input.get("quality", "standard"),
                workflow_type=tool_input.get("workflow_type", "flux_gguf"),
                project_slug=tool_input.get("project_slug")
            )
            if res.get("status") == "success" and res.get("file_path"):
                self.last_generated_images.append(res["file_path"])
            return res

        elif tool_name == "parse_medical_lab":
            return life_tracker.parse_and_store_lab_report(
                raw_text=tool_input.get("raw_text", ""),
                lab_date=tool_input.get("lab_date", "")
            )

        elif tool_name == "log_bio_habit":
            logged = life_tracker.parse_and_log_bio_note(tool_input.get("note", ""))
            return {"logged_entries": logged}

        elif tool_name == "list_projects":
            return {"projects": vault.list_projects(status=tool_input.get("status"))}

        # ==========================================================
        # Phase 8.1: PC Project Workspace & Claude Code File Engine
        # ==========================================================
        elif tool_name == "code_workspace":
            op = tool_input.get("operation", "get_active_path")
            if op == "set_project_path":
                return agent_manager.set_project_path(
                    path_str=tool_input.get("path", ""),
                    name=tool_input.get("name"),
                    create_if_missing=bool(tool_input.get("create_if_missing", False))
                )
            elif op == "get_active_path":
                return {
                    "active_project_path": agent_manager.get_active_project_path(),
                    "workspaces": agent_manager.list_workspaces()
                }
            elif op == "list_workspaces":
                return {"workspaces": agent_manager.list_workspaces()}
            elif op == "switch_workspace":
                return agent_manager.switch_workspace(tool_input.get("path") or tool_input.get("name") or "")
            elif op == "inspect_tree":
                return agent_manager.inspect_tree(path_str=tool_input.get("path"))
            elif op == "read_file":
                return agent_manager.read_file(
                    file_path=tool_input.get("path", ""),
                    start_line=int(tool_input.get("start_line", 1)),
                    end_line=int(tool_input.get("end_line", 300))
                )
            elif op == "write_file":
                return agent_manager.write_file(
                    file_path=tool_input.get("path", ""),
                    content=tool_input.get("content", "")
                )
            elif op == "edit_file":
                return agent_manager.edit_file(
                    file_path=tool_input.get("path", ""),
                    old_text=tool_input.get("old_text", ""),
                    new_text=tool_input.get("new_text", ""),
                    replace_all=bool(tool_input.get("replace_all", False))
                )
            elif op == "multi_edit_file":
                return agent_manager.multi_edit_file(
                    file_path=tool_input.get("path", ""),
                    edits=tool_input.get("edits") or []
                )
            elif op == "grep_search":
                return agent_manager.grep_search(
                    pattern=tool_input.get("pattern", ""),
                    file_glob=tool_input.get("file_glob", "*")
                )
            elif op == "glob_files":
                return agent_manager.glob_files(pattern=tool_input.get("pattern", "**/*"))
            elif op == "run_in_project":
                return await agent_manager.run_in_project(command=tool_input.get("command", ""))
            return {"error": f"Unknown code_workspace operation: {op}"}

        # ==========================================================
        # Phase 8.1: Prebuilt & Custom Persona Agents
        # ==========================================================
        elif tool_name == "manage_agents":
            op = tool_input.get("operation", "list")
            if op == "list":
                return {"agents": agent_manager.list_agents()}
            elif op == "get_active":
                return {"active_agent": agent_manager.get_active_agent()}
            elif op == "switch":
                return agent_manager.switch_agent(
                    name_or_slug=tool_input.get("name", "manager"),
                    project_path=tool_input.get("project_path")
                )
            elif op == "create_or_update":
                return agent_manager.create_or_update_agent(
                    name=tool_input.get("name", "custom_agent"),
                    system_prompt=tool_input.get("system_prompt", "You are a specialized agent."),
                    role_title=tool_input.get("role_title", "Specialized Agent"),
                    description=tool_input.get("description", ""),
                    structure_template=tool_input.get("structure_template", ""),
                    preferred_model=tool_input.get("preferred_model", ""),
                    attached_skills=tool_input.get("attached_skills"),
                    project_path=tool_input.get("project_path", ""),
                    activate=bool(tool_input.get("activate", False))
                )
            elif op == "delete":
                return agent_manager.delete_agent(tool_input.get("name", ""))
            return {"error": f"Unknown manage_agents operation: {op}"}

        # ==========================================================
        # Phase 8.1: Autonomous Sub-Agent Execution
        # ==========================================================
        elif tool_name == "spawn_subagent":
            return await self.run_subagent(
                agent_slug=tool_input.get("agent_slug", "programmer"),
                task=tool_input.get("task", ""),
                project_path=tool_input.get("project_path"),
                skills=tool_input.get("skills"),
                max_turns=int(tool_input.get("max_turns", 12))
            )

        # ==========================================================
        # Phase 8.1: External Local PC CLI Agents (Claude Code, Antigravity, Codex, Copilot)
        # ==========================================================
        elif tool_name == "manage_external_cli_agent":
            op = tool_input.get("operation", "list")
            if op == "list":
                return {"cli_agents": agent_manager.list_cli_agents()}
            elif op == "detect_installed":
                detected = await agent_manager.detect_installed_cli_agents()
                return {"cli_agents": detected}
            elif op == "run":
                return await agent_manager.run_external_cli_agent(
                    agent_name=tool_input.get("agent_name", "claude_code"),
                    prompt=tool_input.get("prompt", ""),
                    project_path=tool_input.get("project_path"),
                    auto_approve=tool_input.get("auto_approve"),
                    timeout_seconds=int(tool_input.get("timeout_seconds", 240))
                )
            elif op == "register_or_update":
                return agent_manager.register_or_update_cli_agent(
                    name=tool_input.get("agent_name", "custom_cli"),
                    binary=tool_input.get("binary", ""),
                    args_template=tool_input.get("args_template"),
                    default_project_path=tool_input.get("project_path", ""),
                    auto_approve=bool(tool_input.get("auto_approve", False))
                )
            elif op == "remove":
                return agent_manager.remove_cli_agent(tool_input.get("agent_name", ""))
            return {"error": f"Unknown manage_external_cli_agent operation: {op}"}

        # ==========================================================
        # Phase 8.2: Skills Manager
        # ==========================================================
        elif tool_name == "manage_skills":
            op = tool_input.get("operation", "list")
            if op == "list":
                return {"skills": skills_manager.list_skills()}
            elif op == "get":
                sk = skills_manager.get_skill(tool_input.get("name", ""))
                return {"skill": sk} if sk else {"status": "not_found"}
            elif op == "create_or_update":
                return skills_manager.create_or_update_skill(
                    name=tool_input.get("name", "custom-skill"),
                    content=tool_input.get("content", ""),
                    description=tool_input.get("description", ""),
                    category=tool_input.get("category", "general"),
                    triggers=tool_input.get("triggers", ""),
                    enabled=bool(tool_input.get("enabled", True))
                )
            elif op == "toggle":
                return skills_manager.toggle_skill(
                    name_or_slug=tool_input.get("name", ""),
                    enabled=bool(tool_input.get("enabled", True))
                )
            elif op == "delete":
                return skills_manager.delete_skill(tool_input.get("name", ""))
            return {"error": f"Unknown manage_skills operation: {op}"}

        # ==========================================================
        # Phase 8.3: MCP (Model Context Protocol) Manager
        # ==========================================================
        elif tool_name == "manage_mcp":
            op = tool_input.get("operation", "list_servers")
            if op == "list_servers":
                return {"mcp_servers": mcp_manager.list_servers()}
            elif op == "add_server":
                return mcp_manager.add_or_update_server(
                    name=tool_input.get("server_name", "mcp_server"),
                    transport=tool_input.get("transport", "stdio"),
                    command=tool_input.get("command", ""),
                    args=tool_input.get("args"),
                    env=tool_input.get("env"),
                    url=tool_input.get("url", ""),
                    cwd=tool_input.get("cwd", ""),
                    enabled=bool(tool_input.get("enabled", True))
                )
            elif op == "add_preset":
                return mcp_manager.add_preset_server(
                    preset_name=tool_input.get("server_name", "filesystem"),
                    target_path=tool_input.get("cwd") or agent_manager.get_active_project_path(),
                    extra_env=tool_input.get("env")
                )
            elif op == "import_json":
                return mcp_manager.import_mcp_json(tool_input.get("raw_json", "{}"))
            elif op == "remove_server":
                return mcp_manager.remove_server(tool_input.get("server_name", ""))
            elif op == "toggle_server":
                return mcp_manager.toggle_server(
                    name_or_slug=tool_input.get("server_name", ""),
                    enabled=bool(tool_input.get("enabled", True))
                )
            elif op == "discover_tools":
                return await mcp_manager.discover_server_tools(tool_input.get("server_name", ""))
            elif op == "call_tool":
                return await mcp_manager.call_tool(
                    server_name=tool_input.get("server_name", ""),
                    tool_name=tool_input.get("tool_name", ""),
                    arguments=tool_input.get("arguments") or {}
                )
            return {"error": f"Unknown manage_mcp operation: {op}"}

        return {"error": f"Unknown tool: {tool_name}"}

    async def run_subagent(
        self,
        agent_slug: str,
        task: str,
        project_path: Optional[str] = None,
        skills: Optional[List[str]] = None,
        max_turns: int = 12,
    ) -> Dict[str, Any]:
        """
        Spawns an isolated sub-agent with the specified persona (`programmer`, `planner`, `reviewer`, `debugger`, etc.),
        bound PC project workspace, and attached skills.
        """
        target_agent = agent_manager.get_agent(agent_slug) or agent_manager.get_agent("programmer")
        resolved_path = project_path or (target_agent.get("project_path") if target_agent else None) or agent_manager.get_active_project_path()

        if project_path:
            agent_manager.set_project_path(project_path, bind_to_active_agent=False)

        attached_skills = list(target_agent.get("attached_skills") or []) if target_agent else []
        if skills:
            for s in skills:
                if s not in attached_skills:
                    attached_skills.append(s)

        skills_block = skills_manager.build_skills_prompt_block(prompt=task, explicit_skills=attached_skills)
        sub_system_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"### SUB-AGENT EXECUTION MODE: {target_agent['name']} (`{target_agent['slug']}`)\n"
            f"**Role:** {target_agent.get('role_title', '')}\n"
            f"{target_agent.get('system_prompt', '')}\n"
        )
        if target_agent.get("structure_template"):
            sub_system_prompt += f"\n### Required Output Structure:\n{target_agent['structure_template']}\n"
        if resolved_path:
            sub_system_prompt += f"\n### Target PC Project Path:\n`{resolved_path}`\n"
        if skills_block:
            sub_system_prompt += f"\n{skills_block}\n"

        if self.client is None:
            summary = f"[Sub-Agent '{target_agent['slug']}' initialized for task: {task} (Path: {resolved_path or 'default'})]"
            rec = agent_manager.log_run(
                run_type="subagent",
                agent_slug=target_agent["slug"],
                task=task,
                project_path=resolved_path or "",
                status="simulated_offline",
                result_summary=summary,
            )
            return {
                "status": "completed",
                "subagent": target_agent["slug"],
                "project_path": resolved_path,
                "run_id": rec["id"],
                "output": summary,
            }

        # Exclude recursive spawn_subagent inside sub-agent to prevent unbounded recursion
        sub_tools = [
            t for t in self.get_tool_definitions()
            if t.get("function", {}).get("name") != "spawn_subagent"
        ]
        conv: List[Any] = [
            {"role": "system", "content": sub_system_prompt},
            {"role": "user", "content": task},
        ]

        chosen_model = target_agent.get("preferred_model") or self.model
        final_output = ""
        steps_taken = 0

        try:
            for _ in range(1, max(1, max_turns) + 1):
                steps_taken += 1
                response = await self.client.chat.completions.create(
                    model=chosen_model,
                    messages=conv,
                    tools=sub_tools,
                )
                msg = response.choices[0].message
                if not msg.tool_calls:
                    final_output = msg.content or "Sub-agent task completed."
                    break

                conv.append(msg)
                for tc in msg.tool_calls:
                    t_name = tc.function.name
                    try:
                        t_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except Exception:
                        t_args = {"raw": tc.function.arguments}
                    tool_res = await self.execute_tool(t_name, t_args)
                    content_str = json.dumps(tool_res, ensure_ascii=False)
                    if len(content_str) > 10000:
                        content_str = content_str[:10000] + "\n... [truncated]"
                    conv.append({"role": "tool", "tool_call_id": tc.id, "content": content_str})
            else:
                final_output = "Sub-agent reached max turns limit."

            rec = agent_manager.log_run(
                run_type="subagent",
                agent_slug=target_agent["slug"],
                task=task,
                project_path=resolved_path or "",
                status="completed",
                result_summary=final_output,
            )
            return {
                "status": "completed",
                "subagent": target_agent["slug"],
                "name": target_agent["name"],
                "project_path": resolved_path,
                "turns_used": steps_taken,
                "run_id": rec["id"],
                "output": final_output,
            }
        except Exception as e:
            agent_manager.log_run(
                run_type="subagent",
                agent_slug=target_agent["slug"],
                task=task,
                project_path=resolved_path or "",
                status="error",
                result_summary=str(e),
            )
            return {"status": "error", "subagent": target_agent["slug"], "error": str(e)}

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        on_status_update: Optional[Callable[[str], Awaitable[None]]] = None,
        max_turns: Optional[int] = None
    ) -> str:
        """
        Runs the multi-turn agent loop with tool calls via 9Router.
        Dynamically injects Active Persona Agent, Saved PC Project Path, and Triggered Skills.
        Includes an Anti-Loop Safety System:
        - Detects when the AI calls the same tool with the identical input parameters.
        - Banning trigger: If called >= AGENT_TOOL_REPEAT_LIMIT (default 3) times,
          the tool execution is blocked and banned, forcing the model to synthesize or use another approach.
        """
        self.last_generated_images.clear()
        self.last_pending_confirmations.clear()

        if self.client is None:
            return "OpenAI SDK is not installed in this environment."

        effective_max_turns = max_turns if (max_turns is not None and max_turns > 0) else self.default_max_turns
        repeat_limit = self.tool_repeat_limit

        # Extract latest user text to match relevant skills
        latest_user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                c = m.get("content", "")
                if isinstance(c, str):
                    latest_user_text = c
                elif isinstance(c, list):
                    latest_user_text = " ".join(
                        item.get("text", "") for item in c if isinstance(item, dict) and item.get("type") == "text"
                    )
                break

        dynamic_context = agent_manager.build_active_agent_prompt_context(user_prompt=latest_user_text)
        full_system_prompt = f"{SYSTEM_PROMPT}\n{dynamic_context}"

        active_ag = agent_manager.get_active_agent()
        active_model = active_ag.get("preferred_model") or self.model

        tools = self.get_tool_definitions()
        conv: List[Any] = [{"role": "system", "content": full_system_prompt}]
        conv.extend(messages)

        # Anti-Loop Safety Tracking State
        tool_call_counts: Dict[str, int] = {}
        banned_signatures: set = set()
        consecutive_all_banned_turns: int = 0
        last_model_message: Optional[Any] = None

        for turn_index in range(1, effective_max_turns + 1):
            response = await self.client.chat.completions.create(
                model=active_model,
                messages=conv,
                tools=tools
            )

            choice = response.choices[0]
            msg = choice.message
            last_model_message = msg

            if not msg.tool_calls:
                return msg.content or "عملیات انجام شد."

            conv.append(msg)
            screenshot_to_attach = None
            turn_banned_flags: List[bool] = []

            for tc in msg.tool_calls:
                t_name = tc.function.name
                try:
                    t_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except Exception:
                    t_args = {"raw": tc.function.arguments}

                # Calculate canonical tool call signature
                sig = self.normalize_tool_signature(t_name, t_args)
                current_count = tool_call_counts.get(sig, 0) + 1
                tool_call_counts[sig] = current_count

                # --- Anti-Loop Safety Check ---
                if current_count >= repeat_limit or sig in banned_signatures:
                    banned_signatures.add(sig)
                    turn_banned_flags.append(True)

                    if on_status_update:
                        await on_status_update(
                            f"⚠️ تکرار {current_count} بار ورودی یکسان برای `{t_name}`! این دستور مسدود شد (Anti-Loop Safety)."
                        )

                    tool_res = {
                        "status": "banned",
                        "error": (
                            f"SAFETY POLICY VIOLATION: Tool '{t_name}' was requested with identical input {current_count} times. "
                            f"This tool execution is BANNED to protect against infinite loops (limit: {repeat_limit}). "
                            f"You must NOT call '{t_name}' with these arguments again. "
                            f"Formulate your response using existing findings or try a completely different approach."
                        ),
                        "tool": t_name,
                        "attempts": current_count,
                        "banned": True
                    }
                else:
                    turn_banned_flags.append(False)
                    if on_status_update:
                        await on_status_update(f"⚙️ در حال اجرای `{t_name}` (مرحله {turn_index}/{effective_max_turns})...")

                    tool_res = await self.execute_tool(t_name, t_args)

                    if t_name == "computer" and isinstance(tool_res, dict) and "base64_image" in tool_res:
                        screenshot_to_attach = tool_res.pop("base64_image")
                        tool_res["note"] = "Desktop screenshot captured. Visual image attached."

                content_str = json.dumps(tool_res, ensure_ascii=False)
                if len(content_str) > 12000:
                    content_str = content_str[:12000] + "\n... [خروجی ابزار به دلیل طولانی بودن کوتاه شد]"

                conv.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content_str
                })

            # Check if all tool calls in this turn were banned
            if turn_banned_flags and all(turn_banned_flags):
                consecutive_all_banned_turns += 1
                if consecutive_all_banned_turns >= 2:
                    if msg.content:
                        return msg.content
                    return (
                        "⚠️ اجرای دستور متوقف شد: مدل هوش مصنوعی چند بار متوالی ابزارهای مسدود شده را فراخوانی کرد. "
                        "لطفاً درخواست خود را با دستورات یا جزئیات متفاوتی ارسال فرمایید."
                    )
            else:
                consecutive_all_banned_turns = 0

            if screenshot_to_attach:
                conv.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "تصویر زنده فعلی مانیتور:"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{screenshot_to_attach}"}
                        }
                    ]
                })

        if last_model_message and last_model_message.content:
            return f"{last_model_message.content}\n\n⚠️ _[حداکثر سقف دورهای ابزار ({effective_max_turns}) تکمیل شد.]_"

        return (
            f"⚠️ ایجنت پس از انجام {effective_max_turns} مرحله به حداکثر سقف مجاز رسید. "
            f"جهت تکمیل پردازش، لطفاً دستور خود را دقیق‌تر یا به صورت مرحله‌به‌مرحله ارسال فرمایید."
        )


agent = ClaudeManagerAgent()
