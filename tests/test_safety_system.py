import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock

from config import settings
from core.agent import ClaudeManagerAgent


class TestAntiLoopSafetySystem(unittest.TestCase):
    """
    Test suite for the Agent Loop Safety System:
    - Normalization of tool call signatures.
    - Detection of identical tool calls with same input.
    - Banning of tools when attempted 3 times with identical input.
    - Allowing turns to proceed up to the increased turn limit when calls differ.
    """

    def setUp(self):
        self.agent = ClaudeManagerAgent()

    def test_signature_normalization(self):
        """Verifies that different key order and whitespace produce identical signatures."""
        args1 = {"query": "test", "top_k": 5}
        args2 = {"top_k": 5, "query": "test"}
        args3_str = '{"query": "test",  "top_k": 5}'

        sig1 = self.agent.normalize_tool_signature("search_vault", args1)
        sig2 = self.agent.normalize_tool_signature("search_vault", args2)
        sig3 = self.agent.normalize_tool_signature("search_vault", args3_str)

        self.assertEqual(sig1, sig2)
        self.assertEqual(sig1, sig3)

        # Different input must produce different signature
        diff_sig = self.agent.normalize_tool_signature("search_vault", {"query": "other", "top_k": 5})
        self.assertNotEqual(sig1, diff_sig)

        # Different tool name must produce different signature
        diff_tool_sig = self.agent.normalize_tool_signature("powershell", {"query": "test", "top_k": 5})
        self.assertNotEqual(sig1, diff_tool_sig)

    def test_settings_turn_and_repeat_limit(self):
        """Verifies settings have increased turns and 3-repeat limit."""
        self.assertGreaterEqual(self.agent.default_max_turns, 200)
        self.assertEqual(self.agent.tool_repeat_limit, 3)

    def test_repeat_tool_call_banning_in_chat(self):
        """
        Simulates an LLM calling the same tool with the same input 3 times.
        Verifies that on the 3rd time, the tool is banned and NOT executed.
        """
        mock_client = MagicMock()
        mock_completions = MagicMock()
        mock_client.chat.completions = mock_completions

        # Create tool call helper
        def make_turn_response(tool_name: str, args_dict: dict):
            tc = MagicMock()
            tc.id = f"tc_{len(args_dict)}"
            tc.function.name = tool_name
            tc.function.arguments = json.dumps(args_dict)

            choice = MagicMock()
            choice.message.tool_calls = [tc]
            choice.message.content = None

            resp = MagicMock()
            resp.choices = [choice]
            return resp

        # Turns 1, 2, 3: Identical tool call to powershell
        resp_turn1 = make_turn_response("powershell", {"command": "dir"})
        resp_turn2 = make_turn_response("powershell", {"command": "dir"})
        resp_turn3 = make_turn_response("powershell", {"command": "dir"})

        # Turn 4: Model stops calling tools and provides a final answer
        final_choice = MagicMock()
        final_choice.message.tool_calls = None
        final_choice.message.content = "I noticed the tool was banned, so here is my final answer."
        resp_turn4 = MagicMock()
        resp_turn4.choices = [final_choice]

        mock_completions.create = AsyncMock(side_effect=[
            resp_turn1,
            resp_turn2,
            resp_turn3,
            resp_turn4
        ])

        # Track execution of execute_tool
        executed_tools = []
        original_execute_tool = self.agent.execute_tool

        async def tracking_execute_tool(t_name, t_args):
            executed_tools.append((t_name, t_args))
            return {"output": "dummy"}

        self.agent.execute_tool = tracking_execute_tool
        self.agent.client = mock_client

        status_updates = []

        async def status_cb(text: str):
            status_updates.append(text)

        result = asyncio.run(
            self.agent.chat(
                [{"role": "user", "content": "run dir"}],
                on_status_update=status_cb,
                max_turns=30
            )
        )

        self.agent.execute_tool = original_execute_tool

        # Turn 1: executed (count=1)
        # Turn 2: executed (count=2)
        # Turn 3: BANNED and NOT executed (count=3)
        self.assertEqual(len(executed_tools), 2, "Tool should only have been executed 2 times before ban.")
        self.assertIn("final answer", result)

        # Status callback should have warned about the ban
        banned_warnings = [s for s in status_updates if "مسدود شد" in s]
        self.assertGreaterEqual(len(banned_warnings), 1)

    def test_different_inputs_allow_more_turns(self):
        """
        Simulates an LLM calling tools with different inputs.
        Verifies that these are NOT banned and are allowed to proceed.
        """
        mock_client = MagicMock()
        mock_completions = MagicMock()
        mock_client.chat.completions = mock_completions

        executed_tools = []

        async def tracking_execute_tool(t_name, t_args):
            executed_tools.append((t_name, t_args))
            return {"output": f"done {len(executed_tools)}"}

        self.agent.execute_tool = tracking_execute_tool
        self.agent.client = mock_client

        def make_turn_response(idx: int):
            tc = MagicMock()
            tc.id = f"tc_{idx}"
            tc.function.name = "powershell"
            tc.function.arguments = json.dumps({"command": f"step_{idx}"})

            choice = MagicMock()
            choice.message.tool_calls = [tc]
            choice.message.content = None

            resp = MagicMock()
            resp.choices = [choice]
            return resp

        # 5 distinct turns with different inputs
        responses = [make_turn_response(i) for i in range(5)]

        # Turn 6: final answer
        final_choice = MagicMock()
        final_choice.message.tool_calls = None
        final_choice.message.content = "Finished 5 different steps."
        final_resp = MagicMock()
        final_resp.choices = [final_choice]
        responses.append(final_resp)

        mock_completions.create = AsyncMock(side_effect=responses)

        result = asyncio.run(
            self.agent.chat(
                [{"role": "user", "content": "do multi-step"}],
                max_turns=30
            )
        )

        # All 5 different commands should be executed without being banned
        self.assertEqual(len(executed_tools), 5)
        self.assertEqual(result, "Finished 5 different steps.")


if __name__ == "__main__":
    unittest.main()

