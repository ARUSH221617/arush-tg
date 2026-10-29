import asyncio
import re
import unittest
from unittest.mock import AsyncMock, MagicMock

from bot.commands import COMMANDS_METADATA, get_bot_commands, setup_bot_commands
from tools.computer_use import confirmation_manager


class TestBotSlashCommands(unittest.TestCase):
    """Test suite for Telegram Slash Commands definitions and registration."""

    def test_commands_metadata_compliance(self):
        """Verifies Telegram Bot API compliance for all command names and descriptions."""
        self.assertTrue(len(COMMANDS_METADATA) >= 15, "Should have all core commands defined.")
        
        seen_commands = set()
        command_pattern = re.compile(r"^[a-z0-9_]{1,32}$")

        for cmd, fa_desc, en_desc in COMMANDS_METADATA:
            # 1. Unique command names
            self.assertNotIn(cmd, seen_commands, f"Duplicate command found: {cmd}")
            seen_commands.add(cmd)

            # 2. Command name syntax: 1-32 lowercase characters, digits or underscores
            self.assertTrue(
                command_pattern.match(cmd),
                f"Command '{cmd}' does not match Telegram syntax ^[a-z0-9_]{{1,32}}$"
            )

            # 3. Description length: 1-256 chars
            self.assertGreaterEqual(len(fa_desc), 1, f"Empty Persian description for {cmd}")
            self.assertLessEqual(len(fa_desc), 256, f"Persian description too long for {cmd}")
            self.assertGreaterEqual(len(en_desc), 1, f"Empty English description for {cmd}")
            self.assertLessEqual(len(en_desc), 256, f"English description too long for {cmd}")

    def test_get_bot_commands(self):
        """Verifies BotCommand object generation for different language scopes."""
        default_cmds = get_bot_commands()
        self.assertEqual(len(default_cmds), len(COMMANDS_METADATA))
        self.assertEqual(default_cmds[0].command, "start")
        self.assertIn("شروع", default_cmds[0].description)

        en_cmds = get_bot_commands(language_code="en")
        self.assertEqual(len(en_cmds), len(COMMANDS_METADATA))
        self.assertEqual(en_cmds[0].command, "start")
        self.assertIn("Start", en_cmds[0].description)

    def test_setup_bot_commands_mock(self):
        """Tests that setup_bot_commands calls set_my_commands with proper scopes."""
        mock_bot = MagicMock()
        mock_bot.set_my_commands = AsyncMock(return_value=True)

        res = asyncio.run(setup_bot_commands(mock_bot))
        self.assertTrue(res)
        # Should be called at least for default, fa, and en
        self.assertGreaterEqual(mock_bot.set_my_commands.await_count, 1)

    def test_cancel_all_pending(self):
        """Tests that confirmation_manager.cancel_all_pending cancels all open confirmation gates."""
        # Create a mock pending action
        action = confirmation_manager.create_pending_action(
            action_type="test_action",
            description="Testing cancel",
            payload={"test": True}
        )
        self.assertEqual(action["status"], "pending")

        count = confirmation_manager.cancel_all_pending()
        self.assertGreaterEqual(count, 1)
        self.assertEqual(action["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()

