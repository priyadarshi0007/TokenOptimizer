"""Pluggable provider registry — maps config 'kind' to Provider implementations."""
from __future__ import annotations

from typing import Callable

from ..config import ProviderConfig
from .base import Provider, ProviderError
from .ollama import OllamaProvider
from .gemini import GeminiProvider

_BUILDERS: dict[str, Callable[[ProviderConfig], Provider]] = {
    "ollama": lambda cfg: OllamaProvider(
        base_url=cfg.settings.get("base_url", "http://localhost:11434"),
        model=cfg.settings.get("model", "gemma2:9b"),
        timeout_seconds=cfg.settings.get("timeout_seconds", 30),
        temperature=cfg.settings.get("temperature", 0.2),
    ),
    "gemini": lambda cfg: GeminiProvider(
        api_key_env=cfg.settings.get("api_key_env", "GOOGLE_API_KEY"),
        model=cfg.settings.get("model", "gemini-1.5-flash"),
        timeout_seconds=cfg.settings.get("timeout_seconds", 30),
        temperature=cfg.settings.get("temperature", 0.2),
    ),
}


def register_provider(kind: str, builder: Callable[[ProviderConfig], Provider]) -> None:
    """Allow third-party plugins to add a new provider kind at runtime."""
    _BUILDERS[kind] = builder


def build_provider(cfg: ProviderConfig) -> Provider:
    builder = _BUILDERS.get(cfg.kind)
    if builder is None:
        raise ProviderError(
            f"Unknown provider kind '{cfg.kind}'. Registered kinds: {sorted(_BUILDERS)}"
        )
    return builder(cfg)
