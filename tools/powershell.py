import asyncio
from typing import Dict, Any

BLOCKED_COMMANDS = [
    "format-volume",
    "remove-item c:\\windows",
    "del /s /q c:\\windows",
    "rmdir /s /q c:\\windows",
    "stop-computer",
    "restart-computer"
]

class PowerShellExecutor:
    """Async executor for local PowerShell commands."""

    async def execute(self, command: str, timeout_seconds: int = 45) -> Dict[str, Any]:
        """Runs a command via PowerShell and returns stdout, stderr, and return code."""
        cmd_lower = command.lower().strip()
        for blocked in BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                return {
                    "success": False,
                    "error": f"Security Exception: Command '{blocked}' is blocked by safety guardrails."
                }

        try:
            process = await asyncio.create_subprocess_exec(
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-Command", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                process.kill()
                return {
                    "success": False,
                    "error": f"Command timed out after {timeout_seconds} seconds."
                }

            stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()

            return {
                "success": process.returncode == 0,
                "exit_code": process.returncode,
                "stdout": stdout_text,
                "stderr": stderr_text
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Execution error: {str(e)}"
            }

ps_executor = PowerShellExecutor()
