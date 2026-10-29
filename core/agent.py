import os
import json
import asyncio
from typing import List, Dict, Any, Optional, Callable, Awaitable
from openai import AsyncOpenAI
from config import settings
from core.prompts import SYSTEM_PROMPT
from tools.computer_use import controller as computer_ctrl
from tools.powershell import ps_executor
from tools.vault import vault
from core.router_client import router_client

class ClaudeManagerAgent:
    """
    Unified Agent Controller powered by 9Router.
    Uses standard OpenAI-compatible client for flawless tool-calling and multimodal compatibility.
    """

    def __init__(self):
        base_url = f"{settings.NINEROUTER_URL.rstrip('/')}/v1"
        api_key = settings.NINEROUTER_KEY or "none"
        
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key
        )
        self.model = settings.AGENT_MODEL

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Defines tools in standard OpenAI Function Calling schema."""
        return [
            # 1. PowerShell CLI Executor
            {
                "type": "function",
                "function": {
                    "name": "powershell",
                    "description": "Execute a command in Windows PowerShell on the host PC (e.g. open apps like chrome.exe, inspect directories, manage processes).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The exact PowerShell command to run (e.g. 'Start-Process chrome.exe')."
                            }
                        },
                        "required": ["command"]
                    }
                }
            },
            # 2. Native Computer GUI Control
            {
                "type": "function",
                "function": {
                    "name": "computer",
                    "description": "Perform mouse and keyboard actions on the Windows desktop, or take screenshots.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "screenshot", "mouse_move", "left_click", "right_click",
                                    "double_click", "triple_click", "middle_click", "type", "key", "cursor_position"
                                ],
                                "description": "Action to perform on the host display."
                            },
                            "coordinate": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "Target [x, y] coordinates in 1280x800 space (if applicable)."
                            },
                            "text": {
                                "type": "string",
                                "description": "Text to type or key combo (e.g. 'ctrl+c', 'enter')."
                            }
                        },
                        "required": ["action"]
                    }
                }
            },
            # 3. Vault Artifact Saver
            {
                "type": "function",
                "function": {
                    "name": "save_to_vault",
                    "description": "Save an idea, screenshot reference, note, or client requirement to the Project Knowledge Vault.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "artifact_type": {
                                "type": "string",
                                "enum": ["idea", "screenshot", "note", "code_snippet", "client_requirement"]
                            },
                            "title": {"type": "string", "description": "Short descriptive title."},
                            "content": {"type": "string", "description": "Detailed text or breakdown."},
                            "project_slug": {"type": "string", "description": "Associated project slug (e.g. 'crypto_dashboard'). Optional."},
                            "tags": {"type": "string", "description": "Comma-separated tags (e.g. 'ui,react')."}
                        },
                        "required": ["artifact_type", "title", "content"]
                    }
                }
            },
            # 4. Vault Searcher
            {
                "type": "function",
                "function": {
                    "name": "search_vault",
                    "description": "Search the Project Knowledge Vault for past ideas, notes, screenshots, or project details.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Keywords to search for."},
                            "artifact_type": {
                                "type": "string",
                                "enum": ["idea", "screenshot", "note", "code_snippet", "client_requirement"]
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            # 5. Financial Transaction Recorder
            {
                "type": "function",
                "function": {
                    "name": "record_transaction",
                    "description": "Record an income or expense transaction from bank receipts, card-to-card, or crypto.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "amount": {"type": "number", "description": "Amount in specified currency."},
                            "currency": {
                                "type": "string",
                                "enum": ["Toman", "Rial", "USDT", "USD"],
                                "default": "Toman"
                            },
                            "category": {"type": "string", "enum": ["income", "expense"], "default": "income"},
                            "tracking_code": {"type": "string", "description": "Tracking / reference number (کد رهگیری / پیگیری)."},
                            "description": {"type": "string", "description": "What this payment was for."},
                            "project_slug": {"type": "string", "description": "Related project slug if applicable."}
                        },
                        "required": ["amount", "description"]
                    }
                }
            },
            # 6. Image Generator via 9Router
            {
                "type": "function",
                "function": {
                    "name": "generate_image",
                    "description": "Generate an image using 9Router (FLUX, DALL-E) or local ComfyUI.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "Detailed image generation prompt."},
                            "size": {"type": "string", "default": "1024x1024"}
                        },
                        "required": ["prompt"]
                    }
                }
            },
            # 7. List Projects
            {
                "type": "function",
                "function": {
                    "name": "list_projects",
                    "description": "List all active or past projects stored in the vault.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "enum": ["lead", "in_progress", "delivered", "completed"]}
                        }
                    }
                }
            }
        ]

    async def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches tool execution and returns formatted result dict."""
        if tool_name == "powershell":
            cmd = tool_input.get("command", "")
            res = await ps_executor.execute(cmd)
            return res

        elif tool_name == "computer":
            action = tool_input.get("action")
            coord = tool_input.get("coordinate")
            text = tool_input.get("text")
            res = computer_ctrl.execute_action(action, coordinate=coord, text=text)
            return res

        elif tool_name == "save_to_vault":
            res = vault.save_artifact(
                artifact_type=tool_input.get("artifact_type"),
                title=tool_input.get("title"),
                content=tool_input.get("content"),
                project_slug=tool_input.get("project_slug"),
                tags=tool_input.get("tags")
            )
            return {"status": "saved", "id": res["id"]}

        elif tool_name == "search_vault":
            res = vault.search_vault(
                query=tool_input.get("query"),
                artifact_type=tool_input.get("artifact_type")
            )
            return {"results": res}

        elif tool_name == "record_transaction":
            res = vault.record_transaction(
                amount=tool_input.get("amount"),
                currency=tool_input.get("currency", "Toman"),
                category=tool_input.get("category", "income"),
                tracking_code=tool_input.get("tracking_code"),
                description=tool_input.get("description"),
                project_slug=tool_input.get("project_slug")
            )
            return {"status": "recorded", "id": res["id"]}

        elif tool_name == "generate_image":
            prompt = tool_input.get("prompt")
            size = tool_input.get("size", "1024x1024")
            timestamp = int(asyncio.get_event_loop().time())
            filename = f"gen_{timestamp}.png"
            target_path = settings.VAULT_DATA_DIR / "media" / filename
            try:
                saved = await router_client.generate_image(prompt, target_path, size=size)
                return {"status": "success", "file_path": str(saved)}
            except Exception as e:
                return {"error": f"Image generation failed: {str(e)}"}

        elif tool_name == "list_projects":
            res = vault.list_projects(status=tool_input.get("status"))
            return {"projects": res}

        return {"error": f"Unknown tool: {tool_name}"}

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        on_status_update: Optional[Callable[[str], Awaitable[None]]] = None,
        max_turns: int = 10
    ) -> str:
        """
        Runs the multi-turn agent loop with tool calls via 9Router.
        """
        tools = self.get_tool_definitions()
        
        # Build conversation with system prompt
        conv = [{"role": "system", "content": SYSTEM_PROMPT}]
        conv.extend(messages)

        for turn in range(max_turns):
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=conv,
                tools=tools
            )

            choice = response.choices[0]
            msg = choice.message

            # If no tool calls requested, return the assistant message content
            if not msg.tool_calls:
                return msg.content or "عملیات انجام شد."

            # Append assistant message with its tool calls to history
            conv.append(msg)

            # Execute each requested tool call
            screenshot_to_attach = None

            for tc in msg.tool_calls:
                t_name = tc.function.name
                try:
                    t_args = json.loads(tc.function.arguments)
                except Exception:
                    t_args = {}

                if on_status_update:
                    await on_status_update(f"⚙️ در حال اجرای `{t_name}`...")

                tool_res = await self.execute_tool(t_name, t_args)

                # Special handling for screenshots: don't dump raw base64 as text into tool content!
                if t_name == "computer" and isinstance(tool_res, dict) and "base64_image" in tool_res:
                    screenshot_to_attach = tool_res.pop("base64_image")
                    tool_res["note"] = "Desktop screenshot captured. Visual image attached."

                content_str = json.dumps(tool_res, ensure_ascii=False)
                # Safeguard: truncate huge command outputs (e.g. from PowerShell or files)
                if len(content_str) > 12000:
                    content_str = content_str[:12000] + "\n... [خروجی ابزار به دلیل طولانی بودن کوتاه شد]"

                # Append tool result in OpenAI format
                conv.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content_str
                })

            # If a screenshot was taken, attach it cleanly as a visual block for the model
            if screenshot_to_attach:
                conv.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "تصویر زنده فعلی مانیتور:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{screenshot_to_attach}"
                            }
                        }
                    ]
                })

        return "Agent reached maximum tool turns without finishing."

agent = ClaudeManagerAgent()
