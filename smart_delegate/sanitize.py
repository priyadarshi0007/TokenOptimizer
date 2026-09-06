"""Path exclusion and secret-redaction guardrails.

These run BEFORE any content is handed to a provider wrapper, so a bug in a
provider module can never leak a credential — the payload is already clean
(or the call is already refused) by the time it gets there.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path


class ExcludedPathError(Exception):
    """Raised when a path matches a compliance/secret exclusion pattern."""


def is_path_excluded(path: str | Path, patterns: list[str]) -> bool:
    p = str(path)
    lower = p.lower()
    name = Path(p).name.lower()
    for pattern in patterns:
        pat = pattern.lower()
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(lower, pat):
            return True
        # substring fallback for bare fragments like ".env" or "secret"
        if "*" not in pat and "?" not in pat and pat in lower:
            return True
    return False


def assert_path_allowed(path: str | Path, patterns: list[str]) -> None:
    if is_path_excluded(path, patterns):
        raise ExcludedPathError(
            f"Refusing to delegate '{path}': matches an excluded pattern "
            f"(credentials/secrets/compliance-sensitive path). Read this file "
            f"directly instead."
        )


def redact_secrets(text: str, patterns: list[str]) -> tuple[str, int]:
    """Redact secret-shaped substrings. Returns (clean_text, redaction_count)."""
    count = 0
    for pattern in patterns:
        try:
            compiled = re.compile(pattern)
        except re.error:
            continue

        def _sub(match: re.Match) -> str:
            nonlocal count
            count += 1
            return "[REDACTED]"

        text = compiled.sub(_sub, text)
    return text, count
