import aiohttp
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Union, List
from config import settings

class NineRouterClient:
    """Client for 9Router REST APIs (Chat, Models, Images, STT, Embeddings)."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or settings.NINEROUTER_URL).rstrip("/")
        self.api_key = api_key or settings.NINEROUTER_KEY

    def _headers(self, is_json: bool = True) -> Dict[str, str]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if is_json:
            headers["Content-Type"] = "application/json"
        return headers

    async def check_health(self) -> bool:
        """
        Check if 9Router is active.
        Tries /api/health first, then falls back to checking /v1/models.
        """
        try:
            async with aiohttp.ClientSession() as session:
                # 1. Check /api/health
                try:
                    async with session.get(
                        f"{self.base_url}/api/health",
                        headers=self._headers(),
                        timeout=aiohttp.ClientTimeout(total=3)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("ok", False):
                                return True
                except Exception:
                    pass

                # 2. Fallback check: /v1/models
                async with session.get(
                    f"{self.base_url}/v1/models",
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=4)
                ) as resp:
                    return resp.status in (200, 401)
        except Exception:
            return False

    async def fetch_models(self, kind: Optional[str] = None) -> List[str]:
        """
        Fetch available model IDs from 9Router.
        kind: None (Chat/LLM), 'image', 'stt', 'tts', 'embedding', 'web', 'image-to-text'
        """
        endpoint = f"{self.base_url}/v1/models/{kind}" if kind else f"{self.base_url}/v1/models"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    if resp.status == 200:
                        payload = await resp.json()
                        data = payload.get("data", [])
                        return [item.get("id") for item in data if isinstance(item, dict) and "id" in item]
                    else:
                        err_text = await resp.text()
                        print(f"⚠️ 9Router returned HTTP {resp.status} for {endpoint}: {err_text}")
                        return []
        except Exception as e:
            print(f"⚠️ Failed to fetch models from {endpoint}: {str(e)}")
            return []

    async def validate_configured_models(self) -> Dict[str, Any]:
        """
        Fetches all model registries from 9Router and verifies whether the
        configured default models from .env (AGENT_MODEL, STT_MODEL, IMAGE_MODEL) exist.
        """
        chat_models, stt_models, image_models = await asyncio.gather(
            self.fetch_models(kind=None),
            self.fetch_models(kind="stt"),
            self.fetch_models(kind="image"),
            return_exceptions=True
        )

        chat_list = chat_models if isinstance(chat_models, list) else []
        stt_list = stt_models if isinstance(stt_models, list) else []
        image_list = image_models if isinstance(image_models, list) else []

        return {
            "chat": {
                "configured": settings.AGENT_MODEL,
                "exists": settings.AGENT_MODEL in chat_list,
                "available": chat_list
            },
            "stt": {
                "configured": settings.STT_MODEL,
                "exists": settings.STT_MODEL in stt_list,
                "available": stt_list
            },
            "image": {
                "configured": settings.IMAGE_MODEL,
                "exists": settings.IMAGE_MODEL in image_list,
                "available": image_list
            }
        }

    async def transcribe_audio(self, audio_file_path: Union[str, Path], language: Optional[str] = None, model: Optional[str] = None) -> str:
        """
        Transcribe audio via 9Router POST /v1/audio/transcriptions
        Supports Persian (fa), English (en), and auto-detect.
        """
        path = Path(audio_file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        chosen_model = model or settings.STT_MODEL
        url = f"{self.base_url}/v1/audio/transcriptions"

        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field("model", chosen_model)
            if language:
                data.add_field("language", language)

            with open(path, "rb") as f:
                data.add_field("file", f, filename=path.name, content_type="audio/ogg")
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                async with session.post(url, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        raise RuntimeError(f"9Router STT Error ({resp.status}): {err_text}")
                    result = await resp.json()
                    return result.get("text", "")

    async def generate_image(
        self,
        prompt: str,
        output_path: Union[str, Path],
        model: Optional[str] = None,
        size: str = "1024x1024"
    ) -> Path:
        """
        Generate image via 9Router POST /v1/images/generations
        Saves the binary image directly to output_path.
        """
        chosen_model = model or settings.IMAGE_MODEL
        url = f"{self.base_url}/v1/images/generations?response_format=binary"
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "model": chosen_model,
            "prompt": prompt,
            "size": size
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    raise RuntimeError(f"9Router Image Gen Error ({resp.status}): {err_text}")
                
                content = await resp.read()
                with open(out, "wb") as f:
                    f.write(content)
                return out

router_client = NineRouterClient()
