import asyncio
import os
import shutil
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import settings


class KDEConnectTool:
    """
    KDE Connect Integration for Android SMS, notifications, and device bridge.
    Executes commands via kdeconnect-cli on Windows/Linux.
    """

    def __init__(self):
        self._cached_binary: Optional[str] = None

    def find_executable(self) -> Optional[str]:
        """Locates kdeconnect-cli executable across PATH and common Windows install directories."""
        if self._cached_binary and os.path.exists(self._cached_binary):
            return self._cached_binary

        # 1. Check system PATH
        found = shutil.which("kdeconnect-cli")
        if found:
            self._cached_binary = found
            return found

        # 2. Check standard Windows Program Files install directories
        candidate_paths = [
            r"C:\Program Files\KDE Connect\bin\kdeconnect-cli.exe",
            r"C:\Program Files\KDE Connect\kdeconnect-cli.exe",
            r"C:\Program Files (x86)\KDE Connect\bin\kdeconnect-cli.exe",
            r"C:\Program Files (x86)\KDE Connect\kdeconnect-cli.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\KDE Connect\bin\kdeconnect-cli.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\KDE Connect\kdeconnect-cli.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\kdeconnect-cli.exe"),
        ]
        for p in candidate_paths:
            if os.path.exists(p):
                self._cached_binary = p
                return p

        # 3. Check WindowsApps for AppX / MSIX packaging
        windows_apps = Path(r"C:\Program Files\WindowsApps")
        if windows_apps.exists():
            try:
                for match in windows_apps.glob("*KDEConnect*/kdeconnect-cli.exe"):
                    if match.is_file():
                        self._cached_binary = str(match)
                        return self._cached_binary
            except Exception:
                pass

        return None

    def is_installed(self) -> bool:
        """Returns True if kdeconnect-cli was detected on the host system."""
        return self.find_executable() is not None

    async def _run_cli(self, args: List[str], timeout: int = 25) -> Dict[str, Any]:
        binary = self.find_executable()
        if not binary:
            return {
                "success": False,
                "error": (
                    "KDE Connect CLI (`kdeconnect-cli`) is not installed or not found on this PC. "
                    "Install via Windows Terminal: `winget install KDE.KDEConnect`"
                )
            }

        try:
            proc = await asyncio.create_subprocess_exec(
                binary,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            out_str = stdout.decode("utf-8", errors="replace").strip()
            err_str = stderr.decode("utf-8", errors="replace").strip()

            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": out_str,
                "stderr": err_str
            }
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return {"success": False, "error": f"KDE Connect command timed out after {timeout} seconds."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_devices(self) -> Dict[str, Any]:
        """Lists paired and available devices from `kdeconnect-cli -l`."""
        res = await self._run_cli(["-l"])
        if not res["success"]:
            return res

        devices: List[Dict[str, Any]] = []
        raw_output = res.get("stdout", "")
        # Output format typically:
        # - Phone Name: a1b2c3d4e5 (paired and reachable)
        # - Another Device: 12345678 (paired)
        for line in raw_output.splitlines():
            line_str = line.strip()
            if not line_str.startswith("-"):
                continue
            line_clean = line_str.lstrip("-").strip()
            match = re.match(r"^(.*?):\s*([a-zA-Z0-9_\-\.]+)\s*\((.*?)\)$", line_clean)
            if match:
                dev_name, dev_id, status_str = match.groups()
                status_lower = status_str.lower()
                devices.append({
                    "name": dev_name.strip(),
                    "id": dev_id.strip(),
                    "is_paired": "paired" in status_lower,
                    "is_reachable": "reachable" in status_lower,
                    "status": status_str.strip()
                })
            else:
                devices.append({"raw": line_clean})

        configured_id = getattr(settings, "KDE_CONNECT_DEVICE_ID", None)
        return {
            "success": True,
            "count": len(devices),
            "devices": devices,
            "configured_default_id": configured_id,
            "raw_output": raw_output
        }

    async def send_sms(
        self,
        phone_number: str,
        message: str,
        device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends an SMS to the destination phone number via the connected Android phone.
        Example: kdeconnect-cli --send-sms "Hello" --destination "+989123456789" -d <device_id>
        """
        target_dev = device_id or getattr(settings, "KDE_CONNECT_DEVICE_ID", None)
        cmd_args = ["--send-sms", message, "--destination", phone_number]
        if target_dev:
            cmd_args.extend(["-d", str(target_dev)])

        res = await self._run_cli(cmd_args, timeout=30)
        if res.get("success"):
            return {
                "success": True,
                "status": "sent",
                "phone_number": phone_number,
                "message": message,
                "device_id": target_dev or "default",
                "output": res.get("stdout") or "SMS dispatched via KDE Connect"
            }
        return res

    async def ring_phone(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Rings the connected phone to help locate it."""
        target_dev = device_id or getattr(settings, "KDE_CONNECT_DEVICE_ID", None)
        cmd_args = ["--ring"]
        if target_dev:
            cmd_args.extend(["-d", str(target_dev)])

        res = await self._run_cli(cmd_args, timeout=10)
        if res.get("success"):
            return {"success": True, "status": "ringing", "device_id": target_dev or "default"}
        return res

    async def ping_device(
        self,
        message: str = "Ping from Arush Manager Agent",
        device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sends a notification ping to the connected phone."""
        target_dev = device_id or getattr(settings, "KDE_CONNECT_DEVICE_ID", None)
        cmd_args = ["--ping-msg", message]
        if target_dev:
            cmd_args.extend(["-d", str(target_dev)])

        res = await self._run_cli(cmd_args, timeout=10)
        if res.get("success"):
            return {"success": True, "status": "pinged", "device_id": target_dev or "default", "message": message}
        return res

    async def share(
        self,
        content_or_path: str,
        device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Shares a link, text, or local file to the phone."""
        target_dev = device_id or getattr(settings, "KDE_CONNECT_DEVICE_ID", None)
        cmd_args = ["--share", content_or_path]
        if target_dev:
            cmd_args.extend(["-d", str(target_dev)])

        res = await self._run_cli(cmd_args, timeout=20)
        if res.get("success"):
            return {"success": True, "status": "shared", "device_id": target_dev or "default", "content": content_or_path}
        return res


kde_connect = KDEConnectTool()
