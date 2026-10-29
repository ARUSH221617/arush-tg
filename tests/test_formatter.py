import unittest
from bot.formatter import (
    markdown_to_telegram_html,
    convert_markdown_tables,
    split_telegram_message,
    strip_html_tags,
    _get_open_tags,
)


class TestTelegramFormatter(unittest.TestCase):

    def test_headers_conversion(self):
        md = "### 1. Executive Summary / Action Taken\n## 2. Technical Details\n# Main Title"
        out = markdown_to_telegram_html(md)
        self.assertIn("<b>1. Executive Summary / Action Taken</b>", out)
        self.assertIn("<b>2. Technical Details</b>", out)
        self.assertIn("<b>Main Title</b>", out)
        self.assertNotIn("###", out)
        self.assertNotIn("##", out)
        self.assertNotIn("# Main Title", out)

    def test_horizontal_rules(self):
        md = "Section A\n---\nSection B\n***\nSection C"
        out = markdown_to_telegram_html(md)
        self.assertIn("— — — — — — — — — —", out)
        self.assertNotIn("---", out)
        self.assertNotIn("***", out)

    def test_table_conversion_multi_column(self):
        md = (
            "| Stage | Command / Target | Status | Notes |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| Lint & Bytecode | python -m py_compile **/*.py | ✅ Passed | 0 syntax errors across entire codebase |\n"
            "| Fix in agent_manager.py | run_in_project PowerShell escaping | ✅ Fixed | Added & prefix operator |"
        )
        out = markdown_to_telegram_html(md)
        self.assertIn("▫️ <b>Lint &amp; Bytecode</b>", out)
        self.assertIn("• <b>Command / Target:</b>", out)
        self.assertIn("<code>python -m py_compile **/*.py</code>", out)
        self.assertIn("• <b>Status:</b> ✅ Passed", out)
        self.assertIn("• <b>Notes:</b> 0 syntax errors across entire codebase", out)
        self.assertIn("▫️ <b>Fix in agent_manager.py</b>", out)
        self.assertIn("Added &amp; prefix operator", out)
        self.assertNotIn("| :--- |", out)

    def test_table_conversion_two_column(self):
        md = (
            "| Parameter | Value |\n"
            "| --- | --- |\n"
            "| Model | gpt-4o |\n"
            "| Uptime | 3600s |"
        )
        out = markdown_to_telegram_html(md)
        self.assertIn("• <b>Model:</b> gpt-4o", out)
        self.assertIn("• <b>Uptime:</b> 3600s", out)

    def test_code_blocks_and_inline_code(self):
        md = (
            "Check this script:\n"
            "```python\n"
            "def check_health(x):\n"
            "    if x < 10 and y > 2:\n"
            "        return 'OK'\n"
            "```\n"
            "Run with `python -m py_compile **/*.py` directly."
        )
        out = markdown_to_telegram_html(md)
        self.assertIn('<pre><code class="language-python">def check_health(x):\n    if x &lt; 10 and y &gt; 2:\n        return &#x27;OK&#x27;</code></pre>', out)
        self.assertIn("<code>python -m py_compile **/*.py</code>", out)

    def test_snake_case_underscores_preserved(self):
        md = "Modified files: agent_manager.py, backup_20261029_182410, and run_in_project."
        out = markdown_to_telegram_html(md)
        self.assertIn("agent_manager.py", out)
        self.assertIn("backup_20261029_182410", out)
        self.assertIn("run_in_project", out)
        self.assertNotIn("<i>manager", out)
        self.assertNotIn("<i>20261029", out)

    def test_intentional_italics_and_bold(self):
        md = "This is **bold text** and this is _italic text_ and *star italic*."
        out = markdown_to_telegram_html(md)
        self.assertIn("<b>bold text</b>", out)
        self.assertIn("<i>italic text</i>", out)
        self.assertIn("<i>star italic</i>", out)

    def test_html_special_chars_escaping(self):
        md = "Price is 5 < 10 & 20 > 15. [Link](https://example.com/test?a=1&b=2)"
        out = markdown_to_telegram_html(md)
        self.assertIn("5 &lt; 10 &amp; 20 &gt; 15", out)
        self.assertIn('<a href="https://example.com/test?a=1&amp;b=2">Link</a>', out)

    def test_lone_brackets_preserved(self):
        md = "[Voice note from user]: Hello world. [Prebuilt] [Custom]"
        out = markdown_to_telegram_html(md)
        self.assertIn("[Voice note from user]: Hello world. [Prebuilt] [Custom]", out)
        self.assertNotIn("<a ", out)

    def test_full_user_request_example(self):
        user_md = """### 1. Executive Summary / Action Taken
The full CI/CD pipeline verification for arush-tg was executed directly inside D:\\arush\\arush-tg:
- Bytecode & Syntax Verification: Passed across all core, bot, tools, tests, and scripts modules.
- PowerShell Call-Operator Fix: Diagnosed and fixed a Windows PowerShell invocation bug in agent_manager.run_in_project (quoted paths require &  prefix in PowerShell execution).
- Automated Test Suite: Ran all 23 unit & integration tests covering Phases 1 through 8. Result: 100% Passed (23/23 OK).
- Startup Diagnostics (--check-only): All endpoints, models, and vault integrity passed.
- Backup Verification (--backup-now): Verified automated hot backup (data\\backups\\backup_20261029_182410).

---

### 2. Technical / Pipeline Details

| Stage | Command / Target | Status | Notes |
| :--- | :--- | :--- | :--- |
| Lint & Bytecode | python -m py_compile **/*.py | ✅ Passed | 0 syntax errors across entire codebase |
| Fix in agent_manager.py | run_in_project PowerShell escaping | ✅ Fixed | Added &  prefix operator when executing quoted command paths in PowerShell |
| Test Suite | unittest discover -s tests | ✅ Passed | 23 tests ran in 24.3s without errors or failures |
| System Diagnostics | python run.py --check-only | ✅ Passed | 9Router connected, models & health check verified |
| Hot Backup | python run.py --backup-now | ✅ Passed | Backup completed cleanly |

---

### 3. Verification & Next Steps
- Working tree status shows Phase 8 changes + the PowerShell fix ready to commit:
    git add tools/agent_manager.py
  git commit -m "fix(agent_manager): support quoted commands with call operator in powershell"
  
- Everything is green and ready for deployment or push to GitHub. Ready whenever you want to commit or push!"""

        out = markdown_to_telegram_html(user_md)
        # Check headers converted to bold
        self.assertIn("<b>1. Executive Summary / Action Taken</b>", out)
        self.assertIn("<b>2. Technical / Pipeline Details</b>", out)
        self.assertIn("<b>3. Verification &amp; Next Steps</b>", out)
        self.assertNotIn("###", out)

        # Check table converted to cards
        self.assertIn("▫️ <b>Lint &amp; Bytecode</b>", out)
        self.assertIn("• <b>Command / Target:</b>", out)
        self.assertIn("• <b>Status:</b> ✅ Passed", out)
        self.assertIn("▫️ <b>Fix in agent_manager.py</b>", out)
        self.assertIn("▫️ <b>Test Suite</b>", out)
        self.assertIn("▫️ <b>System Diagnostics</b>", out)
        self.assertIn("▫️ <b>Hot Backup</b>", out)
        self.assertNotIn("| :--- |", out)

        # Check dividers
        self.assertIn("— — — — — — — — — —", out)

        # Check unclosed underscores in agent_manager didn't produce broken tags
        self.assertIn("agent_manager.run_in_project", out)
        self.assertIn("backup_20261029_182410", out)

        # Check & was escaped
        self.assertIn("Added &amp;  prefix operator", out)

    def test_message_splitting_short(self):
        short = "<p>Short message</p>"
        chunks = split_telegram_message(short, max_length=100)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], short)

    def test_message_splitting_long_with_tags(self):
        # Paragraph with a code block exceeding chunk size
        text = "<pre><code class=\"language-python\">\n" + ("print('hello')\n" * 50) + "</code></pre>"
        chunks = split_telegram_message(text, max_length=200)
        self.assertGreater(len(chunks), 1)

        # Verify chunk 1 closes tags
        self.assertTrue(chunks[0].endswith("</code></pre>"))
        # Verify chunk 2 reopens tags
        self.assertTrue(chunks[1].startswith("<pre><code class=\"language-python\">"))

    def test_strip_html_tags(self):
        html_str = "<b>Hello</b> &amp; <i>World</i>! <a href=\"https://example.com\">Link</a>"
        plain = strip_html_tags(html_str)
        self.assertEqual(plain, "Hello & World! Link")


if __name__ == "__main__":
    unittest.main()
