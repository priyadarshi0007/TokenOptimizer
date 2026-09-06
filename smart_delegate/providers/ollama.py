"""Local Ollama provider — code never leaves the machine."""
from __future__ import annotations

import requests

from .base import (
    Provider,
    ProviderError,
    ProviderResponse,
    ProviderTimeoutError,
    build_codegen_prompt,
    build_summarize_prompt,
)


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout_seconds: int = 30, temperature: float = 0.2):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature

    @property
    def model_id(self) -> str:
        return f"ollama:{self.model}"

    def _generate(self, prompt: str) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout_seconds)
        except requests.exceptions.Timeout as exc:
            raise ProviderTimeoutError(
                f"Ollama request timed out after {self.timeout_seconds}s "
                f"(model={self.model}, url={url})"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise ProviderError(
                f"Could not reach Ollama at {self.base_url}. Is `ollama serve` running?"
            ) from exc

        if resp.status_code != 200:
            raise ProviderError(f"Ollama returned HTTP {resp.status_code}: {resp.text[:500]}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError("Ollama returned non-JSON response") from exc

        text = data.get("response")
        if text is None:
            raise ProviderError(f"Ollama response missing 'response' field: {data}")
        return text

    def summarize(self, content: str, instructions: str) -> ProviderResponse:
        text = self._generate(build_summarize_prompt(content, instructions))
        return ProviderResponse(text=text, model_id=self.model_id, provider_name=self.name)

    def generate_code(self, prompt: str, context: str = "") -> ProviderResponse:
        text = self._generate(build_codegen_prompt(prompt, context))
        return ProviderResponse(text=text, model_id=self.model_id, provider_name=self.name)
