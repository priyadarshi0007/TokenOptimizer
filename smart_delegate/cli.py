"""smart-delegate CLI.

Usage:
  smart-delegate bulk-read <file> --instructions "..."
  smart-delegate code-write "<prompt>" [--context <file>]
  smart-delegate cache-clear
  smart-delegate doctor
"""
from __future__ import annotations

import sys

import click

from .cache import ContentCache
from .config import load_config
from .delegate import SmartDelegate
from .providers.base import ProviderError
from .sanitize import ExcludedPathError


@click.group()
@click.option("--config", "config_path", default=None, help="Path to config.yaml (overrides auto-discovery).")
@click.pass_context
def main(ctx: click.Context, config_path: str | None):
    """smart-delegate: route grunt-work file I/O and boilerplate generation to cheap worker models."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


@main.command("bulk-read")
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--instructions", "-i", required=True, help="What the worker model should extract/summarize.")
@click.pass_context
def bulk_read(ctx: click.Context, file_path: str, instructions: str):
    """Delegate reading and summarizing a large file to the configured worker model."""
    try:
        config = load_config(ctx.obj.get("config_path"))
        sd = SmartDelegate(config)
        result = sd.bulk_read(file_path, instructions)
    except ExcludedPathError as exc:
        click.echo(f"REFUSED: {exc}", err=True)
        sys.exit(2)
    except ProviderError as exc:
        click.echo(f"PROVIDER ERROR: {exc}", err=True)
        sys.exit(1)

    click.echo(result.text)
    click.echo(
        f"\n--- [smart-delegate] provider={result.provider_name} model={result.model_id} "
        f"cache_hit={result.cache_hit} redactions={result.redactions} ---",
        err=True,
    )


@main.command("code-write")
@click.argument("prompt")
@click.option("--context", "context_path", type=click.Path(exists=True, dir_okay=False), default=None,
              help="Optional file providing pattern/style context for generation.")
@click.option("--apply", "apply_path", type=click.Path(dir_okay=False), default=None,
              help="Write the draft straight to this path instead of printing it. "
                   "The calling agent never ingests the generated tokens — only a "
                   "short confirmation. Review the file yourself before trusting it.")
@click.pass_context
def code_write(ctx: click.Context, prompt: str, context_path: str | None, apply_path: str | None):
    """Delegate boilerplate/pattern-matching code generation to the configured worker model.

    NOTE: Output is a full replacement/new-file draft, not a precise diff.
    Do not use this for surgical edits to existing code you must review line-by-line.
    """
    try:
        config = load_config(ctx.obj.get("config_path"))
        sd = SmartDelegate(config)
        result = sd.code_write(prompt, context_path)
    except ExcludedPathError as exc:
        click.echo(f"REFUSED: {exc}", err=True)
        sys.exit(2)
    except ProviderError as exc:
        click.echo(f"PROVIDER ERROR: {exc}", err=True)
        sys.exit(1)

    if apply_path:
        from pathlib import Path
        Path(apply_path).write_text(result.text, encoding="utf-8")
        click.echo(
            f"Draft written to {apply_path} ({len(result.text)} chars). "
            f"Not printed here — read it yourself before relying on it."
        )
    else:
        click.echo(result.text)

    click.echo(
        f"\n--- [smart-delegate] provider={result.provider_name} model={result.model_id} "
        f"cache_hit={result.cache_hit} redactions={result.redactions} ---",
        err=True,
    )


@main.command("cache-clear")
@click.pass_context
def cache_clear(ctx: click.Context):
    """Delete all cached worker-model responses."""
    config = load_config(ctx.obj.get("config_path"))
    cache = ContentCache(config.cache.directory, config.cache.ttl_seconds, config.cache.enabled)
    count = cache.clear()
    click.echo(f"Cleared {count} cache entr{'y' if count == 1 else 'ies'}.")


@main.command("doctor")
@click.pass_context
def doctor(ctx: click.Context):
    """Validate config and provider connectivity."""
    try:
        config = load_config(ctx.obj.get("config_path"))
    except FileNotFoundError as exc:
        click.echo(f"FAIL: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Config: {config.source_path}")
    click.echo(f"Active provider: {config.active_provider}")
    try:
        from .providers.registry import build_provider
        provider = build_provider(config.active())
        click.echo(f"Provider initialized OK. model_id={provider.model_id}")
    except ProviderError as exc:
        click.echo(f"FAIL: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Guardrail max_raw_read_lines: {config.guardrails.max_raw_read_lines}")
    click.echo(f"Excluded path patterns: {config.guardrails.excluded_path_patterns}")
    click.echo(f"Cache: enabled={config.cache.enabled} dir={config.cache.directory}")


if __name__ == "__main__":
    main()
