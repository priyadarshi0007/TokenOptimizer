"""Provider interface all worker-model backends implement."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(Exception):
    """Raised on any worker-model failure: timeout, HTTP error, bad response."""


class ProviderTimeoutError(ProviderError):
    """Raised specifically when the worker did not respond in time."""


@dataclass
class ProviderResponse:
    text: str
    model_id: str
    provider_name: str


def build_summarize_prompt(content: str, instructions: str) -> str:
    """Wrap file content in XML tags so the worker can't confuse it with the
    instructions — cheap models are more reliable at respecting this boundary
    than a plain '--- START/END ---' fence."""
    return (
        "You are a file-summarization worker. Follow the instructions exactly "
        "and be concise and factual. Do not invent content not present in the file.\n\n"
        f"<instructions>{instructions}</instructions>\n\n"
        f"<file_content>\n{content}\n</file_content>"
    )


def build_codegen_prompt(prompt: str, context: str = "") -> str:
    parts = [
        "You are a boilerplate code-generation worker. Output only code "
        "(plus minimal necessary comments), no explanations.\n"
    ]
    if context:
        parts.append(f"<context_file>\n{context}\n</context_file>\n")
    parts.append(f"<task>{prompt}</task>")
    return "\n".join(parts)


class Provider(ABC):
    """Base class for a pluggable worker-model backend.

    Implementations must be synchronous and must enforce their own
    request timeout — never rely on the caller to do it — so a hung
    worker can never stall the calling agent session. Workers should run
    at a low temperature (0.2 by default): delegated tasks are read/write
    grunt work, not creative generation, and low temperature keeps output
    consistent across identical/cached calls.
    """

    name: str

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Stable identifier used in cache keys, e.g. 'ollama:gemma2:9b'."""

    @abstractmethod
    def summarize(self, content: str, instructions: str) -> ProviderResponse:
        """Summarize/analyze bulk file content per instructions. Read-only task."""

    @abstractmethod
    def generate_code(self, prompt: str, context: str = "") -> ProviderResponse:
        """Generate boilerplate/pattern-matching code from a prompt + optional context."""
