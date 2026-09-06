"""Google Gemini (Flash) cloud provider.

Requires `pip install smart-delegate[gemini]` and an API key in the
environment variable named by `api_key_env` in config.yaml. Never hardcode
keys in config.yaml itself.
"""
from __future__ import annotations

import concurrent.futures
import os

from .base import (
    Provider,
    ProviderError,
    ProviderResponse,
    ProviderTimeoutError,
    build_codegen_prompt,
    build_summarize_prompt,
)


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, api_key_env: str, model: str, timeout_seconds: int = 30, temperature: float = 0.2):
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ProviderError(
                f"Environment variable '{api_key_env}' is not set. "
                f"Export your Gemini API key there before using the gemini provider."
            )
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ProviderError(
                "google-genai is not installed. Run: pip install smart-delegate[gemini]"
            ) from exc

        self._client = genai.Client(api_key=api_key)
        self._types = types
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature

    @property
    def model_id(self) -> str:
        return f"gemini:{self.model}"

    def _call(self, prompt: str) -> str:
        def _do_request():
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._types.GenerateContentConfig(temperature=self.temperature),
            )
            return response.text or ""

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_do_request)
            try:
                return future.result(timeout=self.timeout_seconds)
            except concurrent.futures.TimeoutError as exc:
                raise ProviderTimeoutError(
                    f"Gemini request timed out after {self.timeout_seconds}s (model={self.model})"
                ) from exc
            except Exception as exc:
                raise ProviderError(f"Gemini request failed: {exc}") from exc

    def summarize(self, content: str, instructions: str) -> ProviderResponse:
        text = self._call(build_summarize_prompt(content, instructions))
        return ProviderResponse(text=text, model_id=self.model_id, provider_name=self.name)

    def generate_code(self, prompt: str, context: str = "") -> ProviderResponse:
        text = self._call(build_codegen_prompt(prompt, context))
        return ProviderResponse(text=text, model_id=self.model_id, provider_name=self.name)
