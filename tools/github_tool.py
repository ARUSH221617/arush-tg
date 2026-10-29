import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None

from config import settings


class GitHubIntegrationTool:
    """
    Phase 4.3: GitHub Integration.
    1. Safe local Git CLI automation (`git status`, `git diff`, `git commit`, `git push`).
    2. GitHub REST API client:
       - List open Pull Requests (`list_open_prs`)
       - Create GitHub Issues from text or Telegram voice notes (`create_issue`)
       - Inspect GitHub Actions CI/CD workflow runs (`list_workflow_runs`)
    """

    def __init__(self, token: Optional[str] = None, default_repo: Optional[str] = None):
        self.token = token or settings.GITHUB_TOKEN
        self.default_repo = default_repo or settings.GITHUB_DEFAULT_REPO
        self.api_base = "https://api.github.com"

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Arush-Manager-Agent"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def run_local_git(
        self,
        subcommand: str,
        repo_path: Optional[str] = None,
        message: Optional[str] = None,
        branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes safe, parameterized local git operations."""
        cwd = Path(repo_path) if repo_path else Path(__file__).resolve().parent.parent
        allowed = {"status", "diff", "log", "branch", "pull", "push", "commit_all"}
        if subcommand not in allowed:
            return {"success": False, "error": f"Unsupported git subcommand '{subcommand}'. Allowed: {sorted(allowed)}"}

        try:
            if subcommand == "status":
                cmd = ["git", "status", "--short", "--branch"]
            elif subcommand == "diff":
                cmd = ["git", "diff", "--stat"]
            elif subcommand == "log":
                cmd = ["git", "log", "-n", "5", "--oneline"]
            elif subcommand == "branch":
                cmd = ["git", "branch", "-a"]
            elif subcommand == "pull":
                cmd = ["git", "pull", "--ff-only"]
            elif subcommand == "push":
                cmd = ["git", "push", "origin", branch] if branch else ["git", "push"]
            elif subcommand == "commit_all":
                commit_msg = (message or "chore: automated update by Arush Manager Agent").strip()
                add_proc = await asyncio.create_subprocess_exec(
                    "git", "add", "-A",
                    cwd=str(cwd),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await add_proc.communicate()
                cmd = ["git", "commit", "-m", commit_msg]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=30)
            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": stdout_b.decode("utf-8", errors="replace").strip(),
                "stderr": stderr_b.decode("utf-8", errors="replace").strip()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_open_prs(self, repo: Optional[str] = None) -> Dict[str, Any]:
        """Fetches open Pull Requests from GitHub REST API."""
        target_repo = repo or self.default_repo
        if aiohttp is None:
            return {"error": "aiohttp not installed"}
        url = f"{self.api_base}/repos/{target_repo}/pulls?state=open&per_page=10"
        try:
            async with aiohttp.ClientSession(headers=self._headers()) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return {"error": f"GitHub API HTTP {resp.status}: {await resp.text()}"}
                    data = await resp.json()
                    prs = [
                        {
                            "number": pr.get("number"),
                            "title": pr.get("title"),
                            "author": (pr.get("user") or {}).get("login"),
                            "head": (pr.get("head") or {}).get("ref"),
                            "base": (pr.get("base") or {}).get("ref"),
                            "url": pr.get("html_url"),
                            "created_at": pr.get("created_at")
                        }
                        for pr in data if isinstance(pr, dict)
                    ]
                    return {"repo": target_repo, "open_prs": prs}
        except Exception as e:
            return {"error": str(e)}

    async def create_issue(
        self,
        title: str,
        body: str = "",
        labels: Optional[List[str]] = None,
        repo: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a new GitHub Issue (e.g. from a Telegram voice note or bug report)."""
        target_repo = repo or self.default_repo
        if not self.token:
            return {
                "error": "GITHUB_TOKEN is not configured in .env",
                "draft_issue": {"repo": target_repo, "title": title, "body": body, "labels": labels or []}
            }
        if aiohttp is None:
            return {"error": "aiohttp not installed"}

        url = f"{self.api_base}/repos/{target_repo}/issues"
        payload: Dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels

        try:
            async with aiohttp.ClientSession(headers=self._headers()) as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status not in (200, 201):
                        return {"error": f"GitHub API HTTP {resp.status}: {await resp.text()}"}
                    data = await resp.json()
                    return {
                        "status": "created",
                        "number": data.get("number"),
                        "title": data.get("title"),
                        "url": data.get("html_url")
                    }
        except Exception as e:
            return {"error": str(e)}

    async def list_workflow_runs(self, repo: Optional[str] = None, limit: int = 5) -> Dict[str, Any]:
        """Lists recent GitHub Actions CI/CD workflow runs for the repository."""
        target_repo = repo or self.default_repo
        if aiohttp is None:
            return {"error": "aiohttp not installed"}
        url = f"{self.api_base}/repos/{target_repo}/actions/runs?per_page={limit}"
        try:
            async with aiohttp.ClientSession(headers=self._headers()) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return {"error": f"GitHub API HTTP {resp.status}: {await resp.text()}"}
                    data = await resp.json()
                    runs = [
                        {
                            "id": r.get("id"),
                            "name": r.get("name"),
                            "status": r.get("status"),
                            "conclusion": r.get("conclusion"),
                            "branch": r.get("head_branch"),
                            "url": r.get("html_url"),
                            "created_at": r.get("created_at")
                        }
                        for r in data.get("workflow_runs", [])
                    ]
                    return {"repo": target_repo, "workflow_runs": runs}
        except Exception as e:
            return {"error": str(e)}


github_tool = GitHubIntegrationTool()
