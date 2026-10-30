import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from core.agent import agent
from tools.agent_manager import AgentAndWorkspaceManager
from tools.skills_manager import SkillsManager
from tools.mcp_manager import MCPManager


class TestPhase8AgentsSkillsMCP(unittest.TestCase):
    """Comprehensive verification suite for Phase 8: Agents, Claude Code Workspace, Sub-Agents, CLI Agents, Skills & MCP."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.data_path = Path(self.tmp_dir.name)
        self.db_path = self.data_path / "db" / "vault.sqlite"
        self.skills_mgr = SkillsManager(db_path=self.db_path, data_dir=self.data_path)
        self.mcp_mgr = MCPManager(db_path=self.db_path, data_dir=self.data_path)
        self.ag_mgr = AgentAndWorkspaceManager(db_path=self.db_path, data_dir=self.data_path)

    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    # ----------------------------------------------------------
    # 1. Prebuilt & Custom Persona Agents
    # ----------------------------------------------------------
    def test_prebuilt_and_custom_agents(self):
        agents = self.ag_mgr.list_agents()
        slugs = {a["slug"] for a in agents}
        for required in ("manager", "programmer", "planner", "reviewer", "debugger", "researcher"):
            self.assertIn(required, slugs)

        # Switch to prebuilt programmer agent
        sw = self.ag_mgr.switch_agent("programmer")
        self.assertEqual(sw["status"], "switched")
        self.assertEqual(self.ag_mgr.get_active_agent()["slug"], "programmer")

        # Create custom agent
        custom = self.ag_mgr.create_or_update_agent(
            name="DevOps Architect",
            role_title="Cloud & Kubernetes Specialist",
            system_prompt="You manage Docker and CI/CD pipelines.",
            structure_template="1. Infra Plan\n2. Commands",
            attached_skills=["clean-architecture"],
            activate=True,
        )
        self.assertEqual(custom["slug"], "devops_architect")
        self.assertEqual(self.ag_mgr.get_active_agent()["slug"], "devops_architect")

        # Delete custom agent
        del_res = self.ag_mgr.delete_agent("devops_architect")
        self.assertEqual(del_res["status"], "deleted")

        # Built-in agents cannot be deleted
        builtin_del = self.ag_mgr.delete_agent("programmer")
        self.assertEqual(builtin_del["status"], "error")

    # ----------------------------------------------------------
    # 2. PC Project Path Saving & Claude Code File Operations
    # ----------------------------------------------------------
    def test_pc_project_workspace_and_claude_code_operations(self):
        pc_project = self.data_path / "sample_pc_repo"
        pc_project.mkdir(parents=True, exist_ok=True)
        (pc_project / "requirements.txt").write_text("fastapi==0.115.0\n", encoding="utf-8")
        (pc_project / "app.py").write_text(
            "def greet(name: str) -> str:\n    return f'Hello {name}'\n",
            encoding="utf-8",
        )

        # Save PC project path
        saved = self.ag_mgr.set_project_path(str(pc_project), name="My FastAPI App")
        self.assertEqual(saved["status"], "saved_and_activated")
        self.assertIn("Python", saved["tech_stack"])
        self.assertEqual(self.ag_mgr.get_active_project_path(), str(pc_project.resolve()))

        # Inspect directory tree
        tree = self.ag_mgr.inspect_tree()
        self.assertEqual(tree["status"], "success")
        self.assertIn("app.py", tree["tree"])

        # Read file with line numbers
        read_res = self.ag_mgr.read_file("app.py", start_line=1, end_line=10)
        self.assertEqual(read_res["status"], "success")
        self.assertIn("1: def greet(name: str) -> str:", read_res["content"])

        # Surgical edit_file (like Claude Code Edit)
        edit_res = self.ag_mgr.edit_file(
            file_path="app.py",
            old_text="return f'Hello {name}'",
            new_text="return f'Welcome, {name}!'",
        )
        self.assertEqual(edit_res["status"], "edited")
        self.assertIn("-    return f'Hello {name}'", edit_res["diff"])
        self.assertIn("+    return f'Welcome, {name}!'", edit_res["diff"])

        # Multi-edit file
        multi_res = self.ag_mgr.multi_edit_file(
            file_path="app.py",
            edits=[
                {"old_text": "def greet(", "new_text": "def welcome_user("},
                {"old_text": "Welcome,", "new_text": "Salam,"},
            ],
        )
        self.assertEqual(multi_res["status"], "edited")
        self.assertEqual(multi_res["edits_applied"], 2)

        # Write new file
        write_res = self.ag_mgr.write_file("utils/helpers.py", "CONSTANT = 42\n")
        self.assertEqual(write_res["status"], "created")

        # Grep search across project
        grep_res = self.ag_mgr.grep_search("CONSTANT", file_glob="*.py")
        self.assertEqual(grep_res["matches_count"], 1)
        self.assertIn("helpers.py", grep_res["matches"][0]["file"])

        # Glob files
        glob_res = self.ag_mgr.glob_files("**/*.py")
        self.assertEqual(glob_res["count"], 2)

        # Run command inside project directory
        cmd_res = asyncio.run(self.ag_mgr.run_in_project(f'"{sys.executable}" -c "import app; print(app.welcome_user(\'Arush\'))"'))
        self.assertEqual(cmd_res["status"], "success")
        self.assertIn("Salam, Arush!", cmd_res["stdout"])

    # ----------------------------------------------------------
    # 3. External PC CLI Agents (Claude Code, Antigravity, Codex, GitHub Copilot)
    # ----------------------------------------------------------
    def test_external_cli_agents_management_and_execution(self):
        cli_list = self.ag_mgr.list_cli_agents()
        cli_slugs = {c["slug"] for c in cli_list}
        for expected in ("claude_code", "antigravity", "codex", "github_copilot"):
            self.assertIn(expected, cli_slugs)

        # Register a custom Python-based CLI agent to test real subprocess execution in PC project path
        pc_proj = self.data_path / "cli_proj"
        pc_proj.mkdir(parents=True, exist_ok=True)
        self.ag_mgr.set_project_path(str(pc_proj))

        reg = self.ag_mgr.register_or_update_cli_agent(
            name="mock_claude_cli",
            binary=sys.executable,
            args_template=["-c", "import sys, os; print('CLI_OK:', sys.argv[1], 'IN:', os.getcwd())", "{prompt}"],
        )
        self.assertIn(reg["status"], ("created", "updated"))

        run_res = asyncio.run(
            self.ag_mgr.run_external_cli_agent(
                agent_name="mock_claude_cli",
                prompt="Refactor authentication module",
            )
        )
        self.assertEqual(run_res["status"], "success")
        self.assertIn("CLI_OK: Refactor authentication module", run_res["stdout"])
        self.assertIn(str(pc_proj.resolve()), run_res["stdout"])

    # ----------------------------------------------------------
    # 4. Sub-Agent Spawning
    # ----------------------------------------------------------
    def test_subagent_spawning(self):
        mock_msg = MagicMock()
        mock_msg.tool_calls = None
        mock_msg.content = "Sub-agent plan generated successfully."
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]

        with patch.object(agent.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_resp
            res = asyncio.run(
                agent.run_subagent(
                    agent_slug="planner",
                    task="Create an architecture plan for microservice auth",
                    max_turns=2,
                )
            )
            self.assertEqual(res["status"], "completed")
            self.assertEqual(res["subagent"], "planner")

    # ----------------------------------------------------------
    # 5. Skills System (SKILL.md + SQLite + Prompt Injection)
    # ----------------------------------------------------------
    def test_skills_manager_crud_and_matching(self):
        skills = self.skills_mgr.list_skills()
        self.assertGreaterEqual(len(skills), 5)

        created = self.skills_mgr.create_or_update_skill(
            name="React Tailwind Pro",
            description="Modern React 19 + Tailwind CSS patterns",
            category="frontend",
            triggers="react,tailwind,jsx,tsx",
            content="# React Rules\nAlways use functional components and hooks.",
        )
        self.assertEqual(created["slug"], "react-tailwind-pro")
        self.assertTrue(Path(created["file_path"]).exists())

        matched = self.skills_mgr.match_skills_for_prompt("Please build a React and Tailwind dashboard")
        matched_slugs = {m["slug"] for m in matched}
        self.assertIn("react-tailwind-pro", matched_slugs)

        # Toggle off
        self.skills_mgr.toggle_skill("react-tailwind-pro", enabled=False)
        matched_after = self.skills_mgr.match_skills_for_prompt("Please build a React and Tailwind dashboard")
        self.assertNotIn("react-tailwind-pro", {m["slug"] for m in matched_after})

    # ----------------------------------------------------------
    # 6. MCP (Model Context Protocol) Stdio Server & Tool Bridge
    # ----------------------------------------------------------
    def test_mcp_manager_stdio_discovery_and_tool_call(self):
        # Create a lightweight real JSON-RPC 2.0 MCP stdio server script
        mock_mcp_script = self.data_path / "mock_mcp_server.py"
        mock_mcp_script.write_text(
            "import sys, json\n"
            "for line in sys.stdin:\n"
            "    line = line.strip()\n"
            "    if not line:\n"
            "        continue\n"
            "    req = json.loads(line)\n"
            "    method = req.get('method')\n"
            "    req_id = req.get('id')\n"
            "    if method == 'initialize':\n"
            "        resp = {'jsonrpc': '2.0', 'id': req_id, 'result': {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}}}\n"
            "        print(json.dumps(resp), flush=True)\n"
            "    elif method == 'tools/list':\n"
            "        tools = [{'name': 'add_numbers', 'description': 'Adds two integers', 'inputSchema': {'type': 'object', 'properties': {'a': {'type': 'integer'}, 'b': {'type': 'integer'}}, 'required': ['a', 'b']}}]\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': req_id, 'result': {'tools': tools}}), flush=True)\n"
            "    elif method == 'tools/call':\n"
            "        args = req.get('params', {}).get('arguments', {})\n"
            "        total = int(args.get('a', 0)) + int(args.get('b', 0))\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': req_id, 'result': {'content': [{'type': 'text', 'text': f'SUM={total}'}]}}), flush=True)\n",
            encoding="utf-8",
        )

        # Register stdio MCP server
        srv = self.mcp_mgr.add_or_update_server(
            name="math_mcp",
            transport="stdio",
            command=sys.executable,
            args=[str(mock_mcp_script)],
        )
        self.assertEqual(srv["slug"], "math_mcp")

        # Discover tools over JSON-RPC 2.0 stdio
        disc = asyncio.run(self.mcp_mgr.discover_server_tools("math_mcp"))
        self.assertEqual(disc["status"], "connected")
        self.assertEqual(disc["tools_count"], 1)
        self.assertEqual(disc["tools"][0]["name"], "add_numbers")

        # Verify OpenAI function definition generation
        oa_tools = self.mcp_mgr.get_openai_tool_definitions()
        self.assertEqual(len(oa_tools), 1)
        self.assertEqual(oa_tools[0]["function"]["name"], "mcp__math_mcp__add_numbers")

        # Call tool over JSON-RPC 2.0 stdio
        call_res = asyncio.run(self.mcp_mgr.call_tool("math_mcp", "add_numbers", {"a": 17, "b": 25}))
        self.assertEqual(call_res["status"], "success")
        self.assertIn("SUM=42", json.dumps(call_res["result"]))

        # Test importing standard Claude mcpServers JSON
        imp = self.mcp_mgr.import_mcp_json(
            json.dumps({
                "mcpServers": {
                    "memory_srv": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-memory"]
                    }
                }
            })
        )
        self.assertEqual(imp["status"], "imported")
        self.assertIn("memory_srv", imp["imported_servers"])


if __name__ == "__main__":
    unittest.main()
