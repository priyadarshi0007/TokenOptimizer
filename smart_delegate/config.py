"""Configuration loading for smart-delegate.

Resolution order (first found wins):
  1. $SMART_DELEGATE_CONFIG (explicit path)
  2. ./.smart-delegate/config.yaml   (project-local)
  3. ~/.smart-delegate/config.yaml   (user-global)
  4. bundled config.yaml shipped alongside this package (fallback defaults)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _candidate_paths() -> list[Path]:
    candidates = []
    env_path = os.environ.get("SMART_DELEGATE_CONFIG")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path.cwd() / ".smart-delegate" / "config.yaml")
    candidates.append(Path.home() / ".smart-delegate" / "config.yaml")
    candidates.append(_PACKAGE_ROOT / "config.yaml")
    return candidates


def find_config_path() -> Path:
    for path in _candidate_paths():
        if path.is_file():
            return path
    raise FileNotFoundError(
        "No smart-delegate config.yaml found. Checked: "
        + ", ".join(str(p) for p in _candidate_paths())
    )


@dataclass
class Guardrails:
    max_raw_read_lines: int = 300
    excluded_path_patterns: list[str] = field(default_factory=list)
    secret_patterns: list[str] = field(default_factory=list)


@dataclass
class CacheConfig:
    enabled: bool = True
    directory: str = ".smart_delegate_cache"
    ttl_seconds: int = 604800


@dataclass
class ProviderConfig:
    name: str
    kind: str
    settings: dict[str, Any]


@dataclass
class SmartDelegateConfig:
    active_provider: str
    providers: dict[str, ProviderConfig]
    guardrails: Guardrails
    cache: CacheConfig
    source_path: Path

    def active(self) -> ProviderConfig:
        try:
            return self.providers[self.active_provider]
        except KeyError as exc:
            raise ValueError(
                f"active_provider '{self.active_provider}' is not defined under "
                f"'providers' in {self.source_path}"
            ) from exc


def load_config(path: str | os.PathLike | None = None) -> SmartDelegateConfig:
    config_path = Path(path) if path else find_config_path()
    with open(config_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    providers_raw = raw.get("providers", {})
    providers = {
        name: ProviderConfig(name=name, kind=cfg.get("kind", name), settings=cfg)
        for name, cfg in providers_raw.items()
    }

    guardrails_raw = raw.get("guardrails", {})
    max_lines = guardrails_raw.get("max_raw_read_lines", 300)
    env_override = os.environ.get("SMART_DELEGATE_MIN_LINES")
    if env_override:
        try:
            max_lines = int(env_override)
        except ValueError:
            pass
    guardrails = Guardrails(
        max_raw_read_lines=max_lines,
        excluded_path_patterns=guardrails_raw.get("excluded_path_patterns", []),
        secret_patterns=guardrails_raw.get("secret_patterns", []),
    )

    cache_raw = raw.get("cache", {})
    cache = CacheConfig(
        enabled=cache_raw.get("enabled", True),
        directory=cache_raw.get("directory", ".smart_delegate_cache"),
        ttl_seconds=cache_raw.get("ttl_seconds", 604800),
    )

    return SmartDelegateConfig(
        active_provider=raw.get("active_provider", "ollama"),
        providers=providers,
        guardrails=guardrails,
        cache=cache,
        source_path=config_path,
    )
