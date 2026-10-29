import asyncio
import json
import uuid
import time
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse

try:
    import aiohttp
except ImportError:
    aiohttp = None

from config import settings
from core.router_client import router_client
from tools.vault import vault

SUPPORTED_CLOUD_MODELS = {
    "flux-schnell": "black-forest-labs/flux-1-schnell",
    "flux": "black-forest-labs/flux-1-schnell",
    "dalle3": "openai/dall-e-3",
    "dall-e-3": "openai/dall-e-3",
    "imagen": "gemini/gemini-3-pro-image-preview",
    "gemini-imagen": "gemini/gemini-3-pro-image-preview",
}

ASPECT_RATIO_DIMENSIONS = {
    "1:1": (1024, 1024),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "4:3": (1152, 896),
    "3:4": (896, 1152),
}


class ComfyUILocalRunner:
    """
    Phase 5.2: Local ComfyUI Runner.
    WebSocket (`ws://127.0.0.1:8188/ws`) and HTTP client communicating with local ComfyUI instance.
    Triggers local GPU workflows:
    - `sdxl`: SDXL Base/Turbo text-to-image
    - `flux_gguf`: Local FLUX-GGUF workflow
    - `inpainting`: Mask-based image inpainting
    - `controlnet_ui`: ControlNet UI wireframe-to-mockup generation
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.COMFYUI_URL).rstrip("/")
        parsed = urlparse(self.base_url)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        self.ws_url = f"{ws_scheme}://{parsed.netloc}/ws"

    def build_workflow_graph(
        self,
        prompt: str,
        workflow_type: str = "flux_gguf",
        negative_prompt: str = "blurry, low quality, distorted, watermark, ugly",
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """Constructs a standard ComfyUI API node graph for the requested workflow type."""
        actual_seed = seed if seed is not None else int(time.time() * 1000) % (2**31)
        ckpt_map = {
            "sdxl": "sd_xl_base_1.0.safetensors",
            "flux_gguf": "flux1-dev-Q4_K_S.gguf",
            "inpainting": "sd_xl_inpainting_1.0.safetensors",
            "controlnet_ui": "sd_xl_base_1.0.safetensors"
        }
        ckpt_name = ckpt_map.get(workflow_type, "flux1-dev-Q4_K_S.gguf")

        return {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "cfg": 1.0 if "flux" in workflow_type else 7.0,
                    "denoise": 1.0,
                    "latent_image": ["5", 0],
                    "model": ["4", 0],
                    "negative": ["7", 0],
                    "positive": ["6", 0],
                    "sampler_name": "euler",
                    "scheduler": "simple" if "flux" in workflow_type else "normal",
                    "seed": actual_seed,
                    "steps": steps
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": ckpt_name}
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"batch_size": 1, "height": height, "width": width}
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["4", 1], "text": prompt}
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["4", 1], "text": negative_prompt}
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]}
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": f"Arush_{workflow_type}", "images": ["8", 0]}
            }
        }

    async def check_available(self) -> bool:
        if aiohttp is None:
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/system_stats",
                    timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def run_workflow(
        self,
        prompt: str,
        output_path: Path,
        workflow_type: str = "flux_gguf",
        aspect_ratio: str = "1:1",
        steps: int = 20
    ) -> Dict[str, Any]:
        """Submits workflow to ComfyUI HTTP `/prompt`, tracks execution via WebSocket `/ws`, and downloads image."""
        if aiohttp is None:
            return {"error": "aiohttp not installed"}

        width, height = ASPECT_RATIO_DIMENSIONS.get(aspect_ratio, (1024, 1024))
        graph = self.build_workflow_graph(
            prompt=prompt,
            workflow_type=workflow_type,
            width=width,
            height=height,
            steps=steps
        )
        client_id = str(uuid.uuid4())

        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    f"{self.ws_url}?clientId={client_id}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as ws:
                    async with session.post(
                        f"{self.base_url}/prompt",
                        json={"prompt": graph, "client_id": client_id},
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp:
                        if resp.status != 200:
                            return {"error": f"ComfyUI /prompt returned HTTP {resp.status}"}
                        q_data = await resp.json()
                        prompt_id = q_data.get("prompt_id")

                    # Wait for completion message on WebSocket
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            payload = json.loads(msg.data)
                            if payload.get("type") == "executing":
                                data = payload.get("data", {})
                                if data.get("node") is None and data.get("prompt_id") == prompt_id:
                                    break

                # Fetch history and download generated image
                async with session.get(f"{self.base_url}/history/{prompt_id}") as h_resp:
                    history = await h_resp.json()
                    outputs = history.get(prompt_id, {}).get("outputs", {})
                    for node_output in outputs.values():
                        images = node_output.get("images", [])
                        if images:
                            img_meta = images[0]
                            params = {
                                "filename": img_meta["filename"],
                                "subfolder": img_meta.get("subfolder", ""),
                                "type": img_meta.get("type", "output")
                            }
                            async with session.get(f"{self.base_url}/view", params=params) as v_resp:
                                if v_resp.status == 200:
                                    output_path.parent.mkdir(parents=True, exist_ok=True)
                                    output_path.write_bytes(await v_resp.read())
                                    return {
                                        "status": "success",
                                        "engine": f"comfyui:{workflow_type}",
                                        "file_path": str(output_path),
                                        "prompt_id": prompt_id
                                    }
            return {"error": "ComfyUI workflow finished without image output"}
        except Exception as e:
            return {"error": f"ComfyUI execution error: {str(e)}"}


class ImageStudio:
    """
    Phase 5: Unified Image Studio & Creative Engine (9Router Cloud + Local ComfyUI).
    """

    def __init__(self):
        self.comfy = ComfyUILocalRunner()

    def resolve_model(self, model_alias: Optional[str]) -> str:
        if not model_alias:
            return settings.IMAGE_MODEL
        clean = model_alias.strip().lower()
        return SUPPORTED_CLOUD_MODELS.get(clean, model_alias)

    async def generate(
        self,
        prompt: str,
        engine: str = "9router",
        model: Optional[str] = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
        workflow_type: str = "flux_gguf",
        project_slug: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates an image via 9Router Cloud (FLUX Schnell, DALL-E 3, Gemini Imagen)
        or Local ComfyUI WebSocket Runner, saves it to the workspace, and indexes it in Vault.
        """
        ts = int(time.time() * 1000)
        filename = f"studio_{ts}.png"
        if project_slug:
            proj = vault.create_or_get_project(project_slug)
            out_path = settings.VAULT_DATA_DIR / "projects" / proj["slug"] / "assets" / filename
        else:
            out_path = settings.VAULT_DATA_DIR / "media" / filename

        width, height = ASPECT_RATIO_DIMENSIONS.get(aspect_ratio, (1024, 1024))
        size_str = f"{width}x{height}"

        if engine.lower() == "comfyui" or (model and model.lower() == "comfyui"):
            res = await self.comfy.run_workflow(
                prompt=prompt,
                output_path=out_path,
                workflow_type=workflow_type,
                aspect_ratio=aspect_ratio
            )
            if res.get("status") == "success":
                vault.save_artifact(
                    artifact_type="screenshot",
                    title=f"ComfyUI ({workflow_type}): {prompt[:50]}",
                    content=prompt,
                    project_slug=project_slug,
                    file_path=str(out_path),
                    tags=f"image,comfyui,{workflow_type}"
                )
            return res

        resolved_model = self.resolve_model(model)
        try:
            saved_path = await router_client.generate_image(
                prompt=prompt,
                output_path=out_path,
                model=resolved_model,
                size=size_str,
                aspect_ratio=aspect_ratio,
                quality=quality
            )
            vault.save_artifact(
                artifact_type="screenshot",
                title=f"Generated Image ({resolved_model}): {prompt[:50]}",
                content=prompt,
                project_slug=project_slug,
                file_path=str(saved_path),
                tags=f"image,9router,{aspect_ratio}"
            )
            return {
                "status": "success",
                "engine": "9router",
                "model": resolved_model,
                "aspect_ratio": aspect_ratio,
                "size": size_str,
                "quality": quality,
                "file_path": str(saved_path)
            }
        except Exception as e:
            return {"error": f"Image generation failed: {str(e)}"}


image_studio = ImageStudio()
