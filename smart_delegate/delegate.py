"""Orchestrates guardrails -> cache -> provider for a delegated task."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .cache import ContentCache
from .config import SmartDelegateConfig, load_config
from .providers.base import Provider
from .providers.registry import build_provider
from .sanitize import assert_path_allowed, redact_secrets


@dataclass
class DelegationResult:
    text: str
    cache_hit: bool
    model_id: str
    provider_name: str
    redactions: int


class SmartDelegate:
    def __init__(self, config: SmartDelegateConfig | None = None):
        self.config = config or load_config()
        self.provider: Provider = build_provider(self.config.active())
        self.cache = ContentCache(
            directory=self.config.cache.directory,
            ttl_seconds=self.config.cache.ttl_seconds,
            enabled=self.config.cache.enabled,
        )

    def _prepare_content(self, path: Path, content: str) -> tuple[str, int]:
        assert_path_allowed(path, self.config.guardrails.excluded_path_patterns)
        return redact_secrets(content, self.config.guardrails.secret_patterns)

    def bulk_read(self, path: str | Path, instructions: str) -> DelegationResult:
        path = Path(path)
        raw = path.read_text(encoding="utf-8", errors="replace")
        clean, redactions = self._prepare_content(path, raw)

        cache_key = self.cache.compute_key(
            task_kind="bulk-read",
            model_id=self.provider.model_id,
            content=clean,
            extra={"instructions": instructions},
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            return DelegationResult(
                text=cached,
                cache_hit=True,
                model_id=self.provider.model_id,
                provider_name=self.provider.name,
                redactions=redactions,
            )

        response = self.provider.summarize(clean, instructions)
        self.cache.set(cache_key, response.text, "bulk-read", self.provider.model_id)
        return DelegationResult(
            text=response.text,
            cache_hit=False,
            model_id=response.model_id,
            provider_name=response.provider_name,
            redactions=redactions,
        )

    def code_write(self, prompt: str, context_path: str | Path | None = None) -> DelegationResult:
        context = ""
        redactions = 0
        if context_path:
            cp = Path(context_path)
            raw = cp.read_text(encoding="utf-8", errors="replace")
            context, redactions = self._prepare_content(cp, raw)

        prompt_clean, prompt_redactions = redact_secrets(prompt, self.config.guardrails.secret_patterns)
        redactions += prompt_redactions

        cache_key = self.cache.compute_key(
            task_kind="code-write",
            model_id=self.provider.model_id,
            content=prompt_clean,
            extra={"context": context},
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            return DelegationResult(
                text=cached,
                cache_hit=True,
                model_id=self.provider.model_id,
                provider_name=self.provider.name,
                redactions=redactions,
            )

        response = self.provider.generate_code(prompt_clean, context)
        self.cache.set(cache_key, response.text, "code-write", self.provider.model_id)
        return DelegationResult(
            text=response.text,
            cache_hit=False,
            model_id=response.model_id,
            provider_name=response.provider_name,
            redactions=redactions,
        )
