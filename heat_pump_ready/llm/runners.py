"""Disabled, chat-completions API and optional local MLX inference adapters."""

import base64
import io
import json
import os
import urllib.request
import urllib.error
from urllib.parse import urlsplit
from .interfaces import LLMRequest, LLMResponse, LLMRunner, RunnerError


DEFAULT_LOCAL_MODEL = "mlx-community/gemma-4-12B-it-4bit"


class DisabledRunner:
    """Default offline mode; no simulated image observations are generated."""

    supports_images = False

    def start(self) -> None:
        """No resources to initialize."""
        return None

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Report explicitly that model inference is disabled."""
        raise RunnerError(
            "LLM ist deaktiviert. Bitte bekannte Angaben manuell eintragen."
        )

    def close(self) -> None:
        """No resources to release."""
        return None


class ApiLLMRunner:
    """Adapter for a configured chat-completions endpoint, not every vendor API."""

    supports_images = True

    def __init__(self, endpoint: str, model: str, api_key: str, workspace_id: str = "") -> None:
        """Store explicit credentials in memory; no network call occurs here."""
        if not endpoint.startswith(
            ("https://", "http://localhost:", "http://127.0.0.1:")
        ):
            raise ValueError("API URL must use HTTPS or localhost")
        self.endpoint, self.model, self.api_key = endpoint, model, api_key
        self.workspace_id = workspace_id

    def start(self) -> None:
        """No persistent model resources are needed for this adapter."""
        return None

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Request model output; allow 120 seconds for longer narrative responses."""
        content = [{"type": "text", "text": request.prompt}]
        for attachment in request.attachments:
            if not attachment.media_type.startswith("image/"):
                raise RunnerError(
                    "PDF-Auswertung noch nicht unterstützt; bitte Rechnungsfoto nutzen."
                )
            encoded = base64.b64encode(attachment.content).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:" + attachment.media_type + ";base64," + encoded
                    },
                }
            )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": request.max_tokens,
        }
        is_claude = urlsplit(self.endpoint).hostname == "api.anthropic.com"
        if is_claude:
            # Current Claude models reject temperature=0; use the provider default.
            payload.pop("temperature", None)
            # Adaptive thinking shares the output budget; 600 tokens can truncate JSON.
            payload["max_tokens"] = max(request.max_tokens, 4096)
        headers = {"Content-Type": "application/json"}
        if is_claude and self.workspace_id:
            headers["anthropic-workspace-id"] = self.workspace_id
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        call = urllib.request.Request(
            self.endpoint, json.dumps(payload).encode(), headers
        )
        try:
            with urllib.request.urlopen(call, timeout=120 if payload["max_tokens"] > 600 else 45) as response:
                data = json.load(response)
            choice = data["choices"][0]
            if choice.get("finish_reason") in ("length", "max_tokens"):
                raise RunnerError("Modellantwort wurde abgeschnitten. Bitte die Auswertung erneut starten.")
            return LLMResponse(choice["message"]["content"], self.model)
        except (
            urllib.error.URLError,
            TimeoutError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as error:
            raise RunnerError(
                "API-Auswertung fehlgeschlagen; Verbindung, Modell und Antwortformat prüfen."
            ) from error

    def close(self) -> None:
        """No persistent connection is retained."""
        return None


class LocalMLXRunner:
    """Optional Apple-Silicon adapter; MLX/Pillow are imported only when selected."""

    supports_images = True

    def __init__(self, model_id: str) -> None:
        """Store selected model identifier without loading or downloading it."""
        self.model_id = model_id
        self.model = self.processor = None

    def start(self) -> None:
        """Load the chosen model explicitly; missing dependencies fail at startup."""
        from mlx_vlm import load

        self.model, self.processor = load(self.model_id)

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Run local multimodal extraction. Returns: raw text with model identifier."""
        from PIL import Image
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        images = []
        try:
            for attachment in request.attachments:
                if not attachment.media_type.startswith("image/"):
                    raise RunnerError(
                        "PDF-Auswertung noch nicht unterstützt; bitte Rechnungsfoto nutzen."
                    )
                with Image.open(io.BytesIO(attachment.content)) as original:
                    if original.width * original.height > 25000000:
                        raise RunnerError("Bildauflösung zu groß; bitte verkleinern.")
                    images.append(original.convert("RGB"))
            prompt = apply_chat_template(
                self.processor,
                self.model.config,
                request.prompt,
                num_images=len(images),
                enable_thinking=False,
            )
            generation_options = {}
            if request.json_schema is not None:
                from mlx_vlm.structured import build_json_schema_logits_processor

                tokenizer = getattr(self.processor, "tokenizer", self.processor)
                generation_options["logits_processors"] = [
                    build_json_schema_logits_processor(tokenizer, request.json_schema)
                ]
            response = generate(
                self.model,
                self.processor,
                prompt,
                image=images or None,
                max_tokens=request.max_tokens,
                temperature=0,
                enable_thinking=False,
                skip_special_tokens=True,
                **generation_options,
            )
            return LLMResponse(response.text, self.model_id)
        except RunnerError:
            raise
        except Exception as error:
            raise RunnerError(
                "Lokale Modellinferenz fehlgeschlagen: " + type(error).__name__
            ) from error
        finally:
            for image in images:
                image.close()

    def close(self) -> None:
        """Release model references and the MLX allocator cache."""
        import gc
        import mlx.core as mx

        self.model = self.processor = None
        gc.collect()
        mx.clear_cache()


def build_runner(mode: str) -> LLMRunner:
    """Build explicitly configured adapter; never fall back from local to external API."""
    if mode == "disabled":
        return DisabledRunner()
    if mode == "api":
        endpoint, model = os.environ.get("LLM_API_URL"), os.environ.get("LLM_MODEL")
        if not endpoint or not model:
            raise ValueError("LLM_API_URL und LLM_MODEL müssen gesetzt sein.")
        return ApiLLMRunner(endpoint, model, os.environ.get("LLM_API_KEY", ""), os.environ.get("LLM_API_WORKSPACE_ID", ""))
    if mode == "mlx":
        model = os.environ.get("LLM_MODEL") or DEFAULT_LOCAL_MODEL
        return LocalMLXRunner(model)
    raise ValueError("Unbekannter LLM-Modus: " + mode)
