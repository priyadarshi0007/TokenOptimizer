#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block raw reads of large files.

Wire it up in settings.json:

  {
    "hooks": {
      "PreToolUse": [
        {
          "matcher": "Read|Bash",
          "hooks": [
            {"type": "command", "command": "python3 /absolute/path/to/hooks/enforce-read-threshold.py"}
          ]
        }
      ]
    }
  }

Behavior:
  - Intercepts the native Read tool and Bash invocations of cat/head/tail/less/more.
  - Counts lines in the target file. If it exceeds guardrails.max_raw_read_lines
    (from smart-delegate's config.yaml), the tool call is BLOCKED (exit code 2)
    and Claude is told to use `smart-delegate bulk-read` instead.
  - Files matching guardrails.excluded_path_patterns (credentials, .env, *.pem,
    etc.) are ALWAYS allowed through raw, since those must never be delegated
    to an external worker model.
  - Fails open: any error in the hook itself (missing config, bad JSON, unreadable
    file) allows the tool call through rather than stalling the agent session.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

# Bash utilities that read file contents wholesale/partially.
_RAW_READ_COMMANDS = ("cat", "head", "tail", "less", "more")


def _load_guardrails() -> dict:
    """Load guardrails config without depending on smart_delegate being importable
    from the hook's execution context (Claude Code hooks run in their own subprocess)."""
    search_paths = [
        Path.cwd() / ".smart-delegate" / "config.yaml",
        Path.home() / ".smart-delegate" / "config.yaml",
        Path(__file__).resolve().parent.parent / "config.yaml",
    ]
    for path in search_paths:
        if path.is_file() and yaml is not None:
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                return raw.get("guardrails", {})
            except Exception:
                continue
    return {"max_raw_read_lines": 300, "excluded_path_patterns": []}


def _is_excluded(path: str, patterns: list[str]) -> bool:
    lower = path.lower()
    name = Path(path).name.lower()
    for pattern in patterns:
        pat = pattern.lower()
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(lower, pat):
            return True
        if "*" not in pat and "?" not in pat and pat in lower:
            return True
    return False


def _count_lines(path: str) -> int | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return None


def _extract_read_path(tool_input: dict) -> str | None:
    return tool_input.get("file_path") or tool_input.get("path")


def _extract_bash_target(tool_input: dict) -> str | None:
    """Best-effort extraction of a target file from a cat/head/tail/less/more command."""
    command = tool_input.get("command", "")
    if not command:
        return None
    # Match `head -n 50 file.txt`, `cat file.txt`, `tail -f /a/b.log`, etc.
    match = re.match(
        r"^\s*(?:cat|head|tail|less|more)\b(?:\s+-\S+(?:\s+\S+)?)*\s+([^\s|;&<>]+)",
        command,
    )
    if not match:
        return None
    candidate = match.group(1).strip("'\"")
    return candidate


def _block(reason: str) -> None:
    payload = {
        "decision": "block",
        "reason": reason,
    }
    print(json.dumps(payload))
    sys.exit(2)


def _allow() -> None:
    sys.exit(0)


def main() -> None:
    try:
        raw_input = sys.stdin.read()
        event = json.loads(raw_input) if raw_input else {}
    except json.JSONDecodeError:
        _allow()
        return

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}

    target_path: str | None = None
    if tool_name == "Read":
        target_path = _extract_read_path(tool_input)
    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        first_word = command.strip().split(" ", 1)[0] if command.strip() else ""
        if first_word not in _RAW_READ_COMMANDS:
            _allow()
            return
        target_path = _extract_bash_target(tool_input)

    if not target_path:
        _allow()
        return

    guardrails = _load_guardrails()
    excluded_patterns = guardrails.get("excluded_path_patterns", [])
    max_lines = guardrails.get("max_raw_read_lines", 300)
    env_override = os.environ.get("SMART_DELEGATE_MIN_LINES")
    if env_override:
        try:
            max_lines = int(env_override)
        except ValueError:
            pass

    if _is_excluded(target_path, excluded_patterns):
        _allow()
        return

    resolved = target_path
    if not Path(resolved).is_absolute():
        resolved = str(Path.cwd() / resolved)

    line_count = _count_lines(resolved)
    if line_count is None:
        _allow()
        return

    if line_count > max_lines:
        _block(
            f"File '{target_path}' has {line_count} lines, exceeding the "
            f"{max_lines}-line raw-read threshold. Use "
            f"`smart-delegate bulk-read {target_path} --instructions \"<what you need>\"` "
            f"to delegate this to the configured worker model instead of reading it "
            f"directly. If you need to make precise, line-numbered edits, read only "
            f"the specific section you need (e.g. an offset/limit range) rather than "
            f"the whole file."
        )
        return

    _allow()


if __name__ == "__main__":
    main()
