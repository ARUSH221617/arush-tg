import asyncio
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None

from config import settings

DB_PATH = settings.VAULT_DATA_DIR / "db" / "vault.sqlite"


def slugify_mcp(name: str) -> str:
    clean = re.sub(r"[^\w]+", "_", name.lower().strip()).strip("_")
    return clean or "mcp_server"


MCP_PRESETS: Dict[str, Dict[str, Any]] = {
    "filesystem": {
        "name": "filesystem",
        "description": "Official MCP Filesystem Server (read/write/search local directories)",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        "env": {},
    },
    "github": {
        "name": "github",
        "description": "Official MCP GitHub Server (repos, issues, PRs, code search)",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": settings.GITHUB_TOKEN or ""},
    },
    "sqlite": {
        "name": "sqlite",
        "description": "MCP SQLite Server (query and inspect SQLite databases)",
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-sqlite", "--db-path", str(DB_PATH)],
        "env": {},
    },
    "memory": {
        "name": "memory",
        "description": "Official MCP Knowledge Graph Memory Server",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "env": {},
    },
    "fetch": {
        "name": "fetch",
        "description": "Official MCP Web Fetch Server (fetch and convert web pages to markdown)",
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "env": {},
    },
    "playwright": {
        "name": "playwright",
        "description": "Playwright MCP Browser Automation Server",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest"],
        "env": {},
    },
}


class MCPManager:
    """
    Phase 8.3: Model Context Protocol (MCP) Client & Server Registry.
    Supports:
    - Stdio MCP servers (JSON-RPC 2.0 over stdin/stdout subprocess)
    - HTTP JSON-RPC MCP servers (POST JSON-RPC 2.0 endpoint)
    - Claude Desktop / Claude Code compatible `mcp_servers.json` import & export
    - Tool discovery (`initialize` + `tools/list`), caching, and dynamic OpenAI function calling bridge.
    """

    def __init__(self, db_path: Path = DB_PATH, data_dir: Optional[Path] = None):
        self.db_path = db_path
        self.data_dir = data_dir or settings.VAULT_DATA_DIR
        self.config_json_path = self.data_dir / "mcp_servers.json"
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS mcp_servers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    transport TEXT DEFAULT 'stdio',
                    command TEXT DEFAULT '',
                    args_json TEXT DEFAULT '[]',
                    env_json TEXT DEFAULT '{}',
                    url TEXT DEFAULT '',
                    cwd TEXT DEFAULT '',
                    cached_tools_json TEXT DEFAULT '[]',
                    enabled INTEGER DEFAULT 1,
                    last_status TEXT DEFAULT 'configured',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
        self._sync_to_json_file()

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        try:
            d["args"] = json.loads(d.get("args_json") or "[]")
        except Exception:
            d["args"] = []
        try:
            d["env"] = json.loads(d.get("env_json") or "{}")
        except Exception:
            d["env"] = {}
        try:
            d["cached_tools"] = json.loads(d.get("cached_tools_json") or "[]")
        except Exception:
            d["cached_tools"] = []
        d["enabled"] = bool(d.get("enabled", 1))
        return d

    def _sync_to_json_file(self) -> None:
        """Writes standard Claude Code / Claude Desktop compatible `mcpServers` JSON file."""
        try:
            servers = self.list_servers()
            mcp_servers_map: Dict[str, Any] = {}
            for srv in servers:
                if srv["transport"] == "http":
                    mcp_servers_map[srv["slug"]] = {
                        "type": "http",
                        "url": srv["url"],
                        "enabled": srv["enabled"],
                    }
                else:
                    entry: Dict[str, Any] = {
                        "command": srv["command"],
                        "args": srv["args"],
                    }
                    if srv["env"]:
                        entry["env"] = srv["env"]
                    if srv.get("cwd"):
                        entry["cwd"] = srv["cwd"]
                    entry["enabled"] = srv["enabled"]
                    mcp_servers_map[srv["slug"]] = entry

            self.config_json_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_json_path.write_text(
                json.dumps({"mcpServers": mcp_servers_map}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def list_servers(self, only_enabled: bool = False) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if only_enabled:
                cursor.execute("SELECT * FROM mcp_servers WHERE enabled = 1 ORDER BY id ASC")
            else:
                cursor.execute("SELECT * FROM mcp_servers ORDER BY id ASC")
            return [self._row_to_dict(r) for r in cursor.fetchall()]

    def get_server(self, name_or_slug: str) -> Optional[Dict[str, Any]]:
        if not name_or_slug:
            return None
        slug = slugify_mcp(name_or_slug)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM mcp_servers WHERE slug = ? OR LOWER(name) = LOWER(?)",
                (slug, name_or_slug.strip()),
            )
            row = cursor.fetchone()
            return self._row_to_dict(row) if row else None

    def add_or_update_server(
        self,
        name: str,
        transport: str = "stdio",
        command: str = "",
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        url: str = "",
        cwd: str = "",
        description: str = "",
        enabled: bool = True,
        cached_tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        slug = slugify_mcp(name)
        transport = transport.lower().strip()
        if transport not in ("stdio", "http", "sse"):
            transport = "http" if url else "stdio"

        args_json = json.dumps(args or [], ensure_ascii=False)
        env_json = json.dumps(env or {}, ensure_ascii=False)
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM mcp_servers WHERE slug = ?", (slug,))
            existing = cursor.fetchone()
            if existing:
                tools_json = (
                    json.dumps(cached_tools, ensure_ascii=False)
                    if cached_tools is not None
                    else existing["cached_tools_json"]
                )
                cursor.execute(
                    """
                    UPDATE mcp_servers
                    SET name = ?, description = ?, transport = ?, command = ?,
                        args_json = ?, env_json = ?, url = ?, cwd = ?,
                        cached_tools_json = ?, enabled = ?, updated_at = ?
                    WHERE slug = ?
                    """,
                    (
                        name,
                        description or existing["description"],
                        transport,
                        command,
                        args_json,
                        env_json,
                        url,
                        cwd,
                        tools_json,
                        1 if enabled else 0,
                        now_str,
                        slug,
                    ),
                )
                status = "updated"
            else:
                tools_json = json.dumps(cached_tools or [], ensure_ascii=False)
                cursor.execute(
                    """
                    INSERT INTO mcp_servers (
                        slug, name, description, transport, command,
                        args_json, env_json, url, cwd, cached_tools_json, enabled
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        slug,
                        name,
                        description or f"MCP Server ({transport})",
                        transport,
                        command,
                        args_json,
                        env_json,
                        url,
                        cwd,
                        tools_json,
                        1 if enabled else 0,
                    ),
                )
                status = "created"
            conn.commit()

        self._sync_to_json_file()
        srv = self.get_server(slug) or {}
        srv["status"] = status
        return srv

    def add_preset_server(
        self,
        preset_name: str,
        target_path: Optional[str] = None,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        key = preset_name.lower().strip()
        if key not in MCP_PRESETS:
            return {
                "status": "error",
                "error": f"Unknown MCP preset '{preset_name}'. Available presets: {list(MCP_PRESETS.keys())}",
            }
        preset = MCP_PRESETS[key]
        args = list(preset["args"])
        if key == "filesystem" and target_path:
            args[-1] = target_path
        elif key == "sqlite" and target_path:
            args[-1] = target_path

        merged_env = dict(preset.get("env") or {})
        if extra_env:
            merged_env.update(extra_env)

        return self.add_or_update_server(
            name=preset["name"],
            description=preset["description"],
            transport=preset["transport"],
            command=preset["command"],
            args=args,
            env=merged_env,
            cwd=target_path or "",
            enabled=True,
        )

    def import_mcp_json(self, raw_json: str) -> Dict[str, Any]:
        """Imports servers from a Claude Code / Claude Desktop `mcpServers` JSON payload."""
        try:
            data = json.loads(raw_json)
        except Exception as e:
            return {"status": "error", "error": f"Invalid JSON: {e}"}

        servers_block = data.get("mcpServers", data) if isinstance(data, dict) else {}
        if not isinstance(servers_block, dict):
            return {"status": "error", "error": "Expected JSON object with server definitions."}

        imported: List[str] = []
        for name, cfg in servers_block.items():
            if not isinstance(cfg, dict):
                continue
            url = cfg.get("url", "")
            transport = cfg.get("type") or ("http" if url else "stdio")
            cmd = cfg.get("command", "")
            args = cfg.get("args", [])
            env = cfg.get("env", {})
            cwd = cfg.get("cwd", "")
            enabled = cfg.get("enabled", True)
            srv = self.add_or_update_server(
                name=name,
                transport=transport,
                command=cmd,
                args=args if isinstance(args, list) else [],
                env=env if isinstance(env, dict) else {},
                url=url,
                cwd=cwd,
                enabled=bool(enabled),
            )
            imported.append(srv["slug"])

        return {"status": "imported", "imported_servers": imported, "count": len(imported)}

    def remove_server(self, name_or_slug: str) -> Dict[str, Any]:
        srv = self.get_server(name_or_slug)
        if not srv:
            return {"status": "not_found", "error": f"MCP server '{name_or_slug}' not found."}
        slug = srv["slug"]
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM mcp_servers WHERE slug = ?", (slug,))
            conn.commit()
        self._sync_to_json_file()
        return {"status": "deleted", "slug": slug}

    def toggle_server(self, name_or_slug: str, enabled: bool) -> Dict[str, Any]:
        srv = self.get_server(name_or_slug)
        if not srv:
            return {"status": "not_found", "error": f"MCP server '{name_or_slug}' not found."}
        slug = srv["slug"]
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE mcp_servers SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
                (1 if enabled else 0, slug),
            )
            conn.commit()
        self._sync_to_json_file()
        return {"status": "updated", "server": self.get_server(slug)}

    # ==========================================================
    # JSON-RPC 2.0 Transport Execution (Stdio & HTTP)
    # ==========================================================
    async def _stdio_exchange(
        self,
        server: Dict[str, Any],
        requests: List[Dict[str, Any]],
        timeout_seconds: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        Spawns an MCP stdio server subprocess, sends `initialize` + `notifications/initialized`
        followed by the requested JSON-RPC messages over newline-delimited stdio, and collects responses.
        """
        cmd = server.get("command")
        if not cmd:
            raise ValueError(f"MCP server '{server['slug']}' has no command configured.")

        args = [str(a) for a in (server.get("args") or [])]
        env = os.environ.copy()
        for k, v in (server.get("env") or {}).items():
            if v is not None:
                env[str(k)] = str(v)

        cwd = server.get("cwd") or None
        if cwd and not Path(cwd).exists():
            cwd = None

        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "arush-tg-agent", "version": "2.0.0"},
            },
        }
        init_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }

        all_messages = [init_req, init_notif] + requests
        stdin_payload = "\n".join(json.dumps(m, ensure_ascii=False) for m in all_messages) + "\n"

        proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=cwd,
        )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(input=stdin_payload.encode("utf-8")),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(f"MCP server '{server['slug']}' timed out after {timeout_seconds}s")

        stdout_text = stdout_b.decode("utf-8", errors="replace")
        responses: List[Dict[str, Any]] = []
        for line in stdout_text.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict) and ("result" in parsed or "error" in parsed):
                    responses.append(parsed)
            except Exception:
                continue

        if not responses and stderr_b:
            err_str = stderr_b.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"MCP stdio error: {err_str[:500]}")

        return responses

    async def _http_exchange(
        self,
        server: Dict[str, Any],
        rpc_request: Dict[str, Any],
        timeout_seconds: int = 25,
    ) -> Dict[str, Any]:
        if aiohttp is None:
            raise RuntimeError("aiohttp is not installed")
        url = server.get("url")
        if not url:
            raise ValueError(f"MCP server '{server['slug']}' has no URL configured.")

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        for k, v in (server.get("env") or {}).items():
            if k.lower().startswith("authorization") or k.lower().startswith("x-"):
                headers[k] = str(v)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=rpc_request,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout_seconds),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"MCP HTTP {resp.status}: {text[:400]}")
                return await resp.json()

    async def discover_server_tools(self, name_or_slug: str, timeout_seconds: int = 25) -> Dict[str, Any]:
        """Connects to an MCP server, queries `tools/list`, and caches discovered tool schemas in SQLite."""
        srv = self.get_server(name_or_slug)
        if not srv:
            return {"status": "not_found", "error": f"MCP server '{name_or_slug}' not found."}

        list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        try:
            if srv["transport"] in ("http", "sse") and srv.get("url"):
                resp = await self._http_exchange(srv, list_req, timeout_seconds=timeout_seconds)
                tools = (resp.get("result") or {}).get("tools", [])
            else:
                responses = await self._stdio_exchange(srv, [list_req], timeout_seconds=timeout_seconds)
                tools = []
                for r in responses:
                    if r.get("id") == 2 and "result" in r:
                        tools = (r.get("result") or {}).get("tools", [])
                        break

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE mcp_servers
                    SET cached_tools_json = ?, last_status = 'connected', updated_at = CURRENT_TIMESTAMP
                    WHERE slug = ?
                    """,
                    (json.dumps(tools, ensure_ascii=False), srv["slug"]),
                )
                conn.commit()

            return {"status": "connected", "server": srv["slug"], "tools_count": len(tools), "tools": tools}
        except Exception as e:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE mcp_servers SET last_status = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
                    (f"error: {str(e)[:120]}", srv["slug"]),
                )
                conn.commit()
            return {"status": "error", "server": srv["slug"], "error": str(e)}

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 45,
    ) -> Dict[str, Any]:
        """Executes `tools/call` on the target MCP server."""
        srv = self.get_server(server_name)
        if not srv:
            return {"status": "not_found", "error": f"MCP server '{server_name}' not found."}
        if not srv.get("enabled", True):
            return {"status": "disabled", "error": f"MCP server '{server_name}' is currently disabled."}

        call_req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments or {}},
        }

        try:
            if srv["transport"] in ("http", "sse") and srv.get("url"):
                resp = await self._http_exchange(srv, call_req, timeout_seconds=timeout_seconds)
                if "error" in resp:
                    return {"status": "error", "server": srv["slug"], "tool": tool_name, "error": resp["error"]}
                return {"status": "success", "server": srv["slug"], "tool": tool_name, "result": resp.get("result")}
            else:
                responses = await self._stdio_exchange(srv, [call_req], timeout_seconds=timeout_seconds)
                for r in responses:
                    if r.get("id") == 3:
                        if "error" in r:
                            return {"status": "error", "server": srv["slug"], "tool": tool_name, "error": r["error"]}
                        return {"status": "success", "server": srv["slug"], "tool": tool_name, "result": r.get("result")}
                return {"status": "error", "server": srv["slug"], "tool": tool_name, "error": "No JSON-RPC response for tools/call"}
        except Exception as e:
            return {"status": "error", "server": srv["slug"], "tool": tool_name, "error": str(e)}

    def get_openai_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Converts cached tools across all enabled MCP servers into OpenAI function definitions
        named `mcp__{server_slug}__{tool_name}` so the LLM agent can invoke them seamlessly.
        """
        openai_tools: List[Dict[str, Any]] = []
        for srv in self.list_servers(only_enabled=True):
            srv_slug = srv["slug"]
            for t in srv.get("cached_tools") or []:
                if not isinstance(t, dict) or not t.get("name"):
                    continue
                raw_name = t["name"]
                safe_tool_name = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_name)
                fn_name = f"mcp__{srv_slug}__{safe_tool_name}"[:64]
                input_schema = t.get("inputSchema") or {"type": "object", "properties": {}}
                openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": fn_name,
                            "description": f"[MCP:{srv['name']}] {t.get('description') or raw_name}",
                            "parameters": input_schema,
                        },
                    }
                )
        return openai_tools


mcp_manager = MCPManager()
