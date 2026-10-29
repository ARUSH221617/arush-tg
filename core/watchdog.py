import asyncio
import json
import time
import logging
from typing import Dict, Any, Callable, Awaitable, Optional
from config import settings
from core.router_client import router_client
from tools.vault import vault

logger = logging.getLogger("arush-watchdog")


class SelfHealingWatchdog:
    """
    Phase 7.3: Health Check, Heartbeat & Self-Healing Reconnection Engine.
    - Continuously monitors 9Router connectivity, SQLite Vault integrity, and uptime.
    - Exposes a lightweight async HTTP health endpoint (`GET /health`) on `settings.HEALTHCHECK_PORT`
      for Docker `HEALTHCHECK`, NSSM, and GitHub CD deployment verification.
    - Wraps the Telegram bot polling loop with automatic exponential backoff reconnection
      when internet or VPN drops and reconnects.
    """

    def __init__(self):
        self.start_time = time.time()
        self.last_9router_ok = False
        self.last_heartbeat_ts = 0.0
        self.reconnect_count = 0
        self._running = False
        self._server: Optional[asyncio.AbstractServer] = None

    async def get_health_status(self) -> Dict[str, Any]:
        router_ok = await router_client.check_health()
        self.last_9router_ok = router_ok
        self.last_heartbeat_ts = time.time()

        db_ok = False
        try:
            _ = vault.list_projects()
            db_ok = True
        except Exception:
            db_ok = False

        return {
            "status": "healthy" if db_ok else "degraded",
            "uptime_seconds": round(time.time() - self.start_time, 1),
            "ninerouter_connected": router_ok,
            "vault_db_ok": db_ok,
            "reconnect_count": self.reconnect_count,
            "agent_model": settings.AGENT_MODEL,
            "timestamp": int(self.last_heartbeat_ts)
        }

    async def _handle_http_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:
        try:
            await asyncio.wait_for(reader.read(1024), timeout=5.0)
            health = await self.get_health_status()
            body = json.dumps(health).encode("utf-8")
            status_line = "HTTP/1.1 200 OK\r\n" if health["vault_db_ok"] else "HTTP/1.1 503 Service Unavailable\r\n"
            headers = (
                f"{status_line}"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("utf-8")
            writer.write(headers + body)
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    async def start_health_server(self, host: str = "0.0.0.0", port: Optional[int] = None) -> None:
        target_port = port or settings.HEALTHCHECK_PORT
        try:
            self._server = await asyncio.start_server(self._handle_http_client, host=host, port=target_port)
            logger.info(f"Healthcheck HTTP server listening on http://{host}:{target_port}/health")
        except Exception as e:
            logger.warning(f"Could not bind healthcheck server on port {target_port}: {e}")

    async def run_with_self_healing(
        self,
        coro_factory: Callable[[], Awaitable[None]],
        max_backoff_seconds: int = 60
    ) -> None:
        """
        Executes a long-running async service (such as Telegram polling) and automatically
        reconnects with exponential backoff when internet/VPN drops.
        """
        self._running = True
        backoff = 2
        while self._running:
            try:
                await coro_factory()
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.reconnect_count += 1
                logger.warning(
                    f"⚠️ Connection interrupted ({e}). Self-healing reconnect #{self.reconnect_count} in {backoff}s..."
                )
                await asyncio.sleep(backoff)
                backoff = min(max_backoff_seconds, backoff * 2)

    async def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()


watchdog = SelfHealingWatchdog()
