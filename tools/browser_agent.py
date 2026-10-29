import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from config import settings

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def get_default_chrome_user_data_dir() -> str:
    """Detects the persistent personal Google Chrome profile directory across Windows/Linux/macOS."""
    if settings.CHROME_USER_DATA_DIR:
        return settings.CHROME_USER_DATA_DIR
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", r"C:\Users\Arush\AppData\Local")
        return str(Path(local_app_data) / "Google" / "Chrome" / "User Data")
    return str(settings.VAULT_DATA_DIR / "chrome_profile")


class AgenticBrowserController:
    """
    Phase 4.2: Agentic Browser (`browser-use` + Playwright).
    Connects Playwright to a persistent personal Google Chrome profile (`--user-data-dir`)
    to retain login sessions for Karlancer, Ponisha, GitHub, and Gmail without CAPTCHAs.
    Supports:
    - Navigating & extracting structured page content
    - Filling forms and submitting proposals
    - Downloading project attachments directly into `data/downloads/` or `data/projects/{slug}/assets/`
    """

    def __init__(self, user_data_dir: Optional[str] = None, headless: Optional[bool] = None):
        self.user_data_dir = user_data_dir or get_default_chrome_user_data_dir()
        self.headless = settings.BROWSER_HEADLESS if headless is None else headless

    def get_launch_args(self) -> List[str]:
        return [
            f"--profile-directory={settings.CHROME_PROFILE_NAME}",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ]

    async def execute_browser_task(
        self,
        action: str,
        url: str,
        selectors: Optional[Dict[str, str]] = None,
        submit_selector: Optional[str] = None,
        download_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Executes an autonomous Playwright browser workflow with persistent profile.
        Actions: 'navigate', 'fill_form', 'download_attachments', 'screenshot'
        """
        target_dl_dir = download_dir or (settings.VAULT_DATA_DIR / "downloads")
        target_dl_dir.mkdir(parents=True, exist_ok=True)

        if not HAS_PLAYWRIGHT:
            return {
                "status": "playwright_not_installed",
                "action": action,
                "url": url,
                "user_data_dir": self.user_data_dir,
                "launch_args": self.get_launch_args(),
                "message": "Playwright package not installed in current environment; configuration validated."
            }

        try:
            async with async_playwright() as p:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=self.headless,
                    args=self.get_launch_args(),
                    accept_downloads=True
                )
                try:
                    page = context.pages[0] if context.pages else await context.new_page()
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)

                    if action == "navigate":
                        title = await page.title()
                        text_content = await page.evaluate("() => document.body ? document.body.innerText : ''")
                        return {
                            "status": "success",
                            "action": "navigate",
                            "url": page.url,
                            "title": title,
                            "content": (text_content or "")[:8000]
                        }

                    elif action == "fill_form":
                        filled_fields: List[str] = []
                        for field_selector, value in (selectors or {}).items():
                            await page.fill(field_selector, str(value))
                            filled_fields.append(field_selector)
                        if submit_selector:
                            await page.click(submit_selector)
                        return {
                            "status": "success",
                            "action": "fill_form",
                            "url": page.url,
                            "filled_fields": filled_fields,
                            "submitted": bool(submit_selector)
                        }

                    elif action == "download_attachments":
                        downloaded_files: List[str] = []
                        sel = submit_selector or "a[download], a[href$='.zip'], a[href$='.pdf'], a[href$='.docx']"
                        elements = await page.query_selector_all(sel)
                        for el in elements[:5]:
                            try:
                                async with page.expect_download(timeout=15000) as dl_info:
                                    await el.click()
                                download = await dl_info.value
                                save_path = target_dl_dir / download.suggested_filename
                                await download.save_as(str(save_path))
                                downloaded_files.append(str(save_path))
                            except Exception:
                                continue
                        return {
                            "status": "success",
                            "action": "download_attachments",
                            "files": downloaded_files
                        }

                    elif action == "screenshot":
                        shot_path = settings.VAULT_DATA_DIR / "media" / "browser_capture.png"
                        await page.screenshot(path=str(shot_path), full_page=False)
                        return {
                            "status": "success",
                            "action": "screenshot",
                            "file_path": str(shot_path)
                        }

                    return {"error": f"Unknown browser action: {action}"}
                finally:
                    await context.close()
        except Exception as e:
            return {"error": f"Browser automation error: {str(e)}"}


browser_agent = AgenticBrowserController()
