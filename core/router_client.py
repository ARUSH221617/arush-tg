import asyncio
import hashlib
import math
from pathlib import Path
from typing import Optional, Dict, Any, Union, List

try:
    import aiohttp
except ImportError:
    aiohttp = None

from config import settings


def compute_local_embedding(text: str, dim: int = 128) -> List[float]:
    """
    Deterministic local character/word n-gram embedding fallback when 9Router
    embedding endpoint is offline or unreachable. Returns unit-normalized vector.
    """
    vec = [0.0] * dim
    if not text:
        return vec
    normalized = text.lower().strip()
    tokens = normalized.split()
    features: List[str] = list(tokens)
    # Add character 3-grams for Persian/English morphological similarity
    cleaned = "".join(ch for ch in normalized if not ch.isspace())
    for i in range(max(0, len(cleaned) - 2)):
        features.append(cleaned[i:i + 3])

    for feat in features:
        digest = hashlib.sha256(feat.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if (digest[4] % 2 == 0) else -1.0
        vec[idx] += sign

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [round(v / norm, 6) for v in vec]
    return vec


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
        if aiohttp is None:
            return False
        try:
            async with aiohttp.ClientSession() as session:
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
        if aiohttp is None:
            return []
        endpoint = f"{self.base_url}/v1/models/{kind}" if kind else f"{self.base_url}/v1/models"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    if resp.status == 200:
                        payload = await resp.json()
                        data = payload.get("data", [])
                        return [item.get("id") for item in data if isinstance(item, dict) and "id" in item]
                    else:
                        return []
        except Exception:
            return []

    async def validate_configured_models(self) -> Dict[str, Any]:
        """
        Fetches all model registries from 9Router and verifies whether the
        configured default models from .env (AGENT_MODEL, STT_MODEL, IMAGE_MODEL, EMBEDDING_MODEL) exist.
        """
        chat_models, stt_models, image_models, emb_models = await asyncio.gather(
            self.fetch_models(kind=None),
            self.fetch_models(kind="stt"),
            self.fetch_models(kind="image"),
            self.fetch_models(kind="embedding"),
            return_exceptions=True
        )

        chat_list = chat_models if isinstance(chat_models, list) else []
        stt_list = stt_models if isinstance(stt_models, list) else []
        image_list = image_models if isinstance(image_models, list) else []
        emb_list = emb_models if isinstance(emb_models, list) else []

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
            },
            "embedding": {
                "configured": settings.EMBEDDING_MODEL,
                "exists": (settings.EMBEDDING_MODEL in emb_list) or (settings.EMBEDDING_MODEL in chat_list),
                "available": emb_list
            }
        }

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        response_format: Optional[Dict[str, Any]] = None
    ) -> str:
        """Direct helper for structured prompts (Idea Incubator, Receipt OCR, Lead Scoring)."""
        if aiohttp is None:
            raise RuntimeError("aiohttp is not installed")
        chosen_model = model or settings.AGENT_MODEL
        url = f"{self.base_url}/v1/chat/completions"
        payload: Dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature
        }
        if response_format:
            payload["response_format"] = response_format

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=90)) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    raise RuntimeError(f"9Router Chat Error ({resp.status}): {err_text}")
                data = await resp.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "") or ""
                return ""

    async def transcribe_audio(
        self,
        audio_file_path: Union[str, Path],
        language: Optional[str] = None,
        model: Optional[str] = None
    ) -> str:
        """
        Transcribe audio via 9Router POST /v1/audio/transcriptions
        Supports Persian (fa), English (en), and auto-detect.
        """
        if aiohttp is None:
            raise RuntimeError("aiohttp is not installed")
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

    async def create_embedding(
        self,
        text: str,
        model: Optional[str] = None
    ) -> List[float]:
        """
        Generate semantic vector embeddings via 9Router POST /v1/embeddings.
        Automatically falls back to deterministic local n-gram embeddings if 9Router is offline.
        """
        chosen_model = model or settings.EMBEDDING_MODEL
        url = f"{self.base_url}/v1/embeddings"
        if aiohttp is not None:
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {"model": chosen_model, "input": text}
                    async with session.post(
                        url,
                        json=payload,
                        headers=self._headers(),
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            emb_data = data.get("data", [])
                            if emb_data and "embedding" in emb_data[0]:
                                return [float(x) for x in emb_data[0]["embedding"]]
            except Exception:
                pass
        return compute_local_embedding(text)

    async def generate_image(
        self,
        prompt: str,
        output_path: Union[str, Path],
        model: Optional[str] = None,
        size: str = "1024x1024",
        aspect_ratio: Optional[str] = None,
        quality: str = "standard"
    ) -> Path:
        """
        Generate image via 9Router POST /v1/images/generations
        Supports aspect ratio mapping, quality, and model selection (FLUX Schnell, DALL-E 3, Gemini Imagen).
        """
        if aiohttp is None:
            raise RuntimeError("aiohttp is not installed")
        chosen_model = model or settings.IMAGE_MODEL
        aspect_map = {
            "1:1": "1024x1024",
            "16:9": "1344x768",
            "9:16": "768x1344",
            "4:3": "1152x896",
            "3:4": "896x1152"
        }
        resolved_size = aspect_map.get(aspect_ratio or "", size)
        url = f"{self.base_url}/v1/images/generations?response_format=binary"
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        payload: Dict[str, Any] = {
            "model": chosen_model,
            "prompt": prompt,
            "size": resolved_size,
            "quality": quality
        }
        if aspect_ratio:
            payload["aspect_ratio"] = aspect_ratio

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
